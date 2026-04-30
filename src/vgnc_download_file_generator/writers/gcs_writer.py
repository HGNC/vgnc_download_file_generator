"""GCS streaming writer for direct uploads to Google Cloud Storage.

This module provides the GCSStreamWriter class for memory-efficient
streaming uploads to GCS with support for compression and retry logic.
"""

import gzip
import logging
import time
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from google.api_core.exceptions import (
    DeadlineExceeded,
    ServiceUnavailable,
)
from google.cloud import storage

logger = logging.getLogger(__name__)


# Transient errors that should trigger retries
TRANSIENT_ERRORS = (ServiceUnavailable, DeadlineExceeded)


def retry_with_exponential_backoff(
    max_retries: int = 3,
    initial_backoff: int = 1,
    multiplier: int = 2,
) -> Callable:
    """Decorator for retrying operations with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        initial_backoff: Initial backoff time in seconds (default: 1)
        multiplier: Backoff multiplier for each retry (default: 2)

    Returns:
        Decorator function
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            backoff = initial_backoff

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except TRANSIENT_ERRORS as e:
                    last_exception = e

                    if attempt < max_retries - 1:
                        logger.warning(
                            "Attempt %d/%d failed: %s. Retrying in %d seconds...",
                            attempt + 1,
                            max_retries,
                            str(e),
                            backoff,
                        )
                        time.sleep(backoff)
                        backoff *= multiplier
                    else:
                        logger.error(
                            "All %d attempts failed. Last error: %s",
                            max_retries,
                            str(e),
                        )

            # Raise the last exception if all retries failed
            if last_exception:
                raise last_exception

            return None

        return wrapper

    return decorator


class GCSStreamWriter:
    """Streaming writer for Google Cloud Storage uploads.

    Provides context manager for streaming uploads to GCS with support
    for compression and retry logic on transient failures.

    Attributes:
        bucket_name: Name of the GCS bucket
        project_id: Google Cloud project ID
        path_prefix: Optional path prefix for all GCS objects (e.g., "vgnc/")
        _client: GCS storage client
        _bucket: GCS bucket reference
    """

    # Content-type mapping for file extensions
    CONTENT_TYPE_MAP = {
        ".txt": "text/tab-separated-values",
        ".tsv": "text/tab-separated-values",
        ".json": "application/json",
        ".gz": "application/gzip",
    }

    def __init__(self, bucket_name: str, project_id: str, path_prefix: str = "") -> None:
        """Initialize the GCS writer.

        Args:
            bucket_name: Name of the GCS bucket for uploads
            project_id: Google Cloud project ID
            path_prefix: Optional path prefix for all GCS objects (e.g., "vgnc/")
                If blank, no prefix is added to paths.
        """
        self.bucket_name = bucket_name
        self.project_id = project_id
        self.path_prefix = path_prefix

        # Initialize GCS storage client
        self._client = storage.Client(project=project_id)

        # Get bucket reference
        self._bucket = self._client.bucket(bucket_name)

    def _detect_content_type(self, path: str) -> str:
        """Detect content-type from file extension.

        Args:
            path: File path to detect content-type from

        Returns:
            MIME content-type string
        """
        ext = Path(path).suffix.lower()

        # Check for .gz extension first (compound extensions like .json.gz)
        if ext == ".gz":
            return "application/gzip"

        # Return mapped content-type or default
        return self.CONTENT_TYPE_MAP.get(ext, "application/octet-stream")

    def _apply_path_prefix(self, path: str) -> str:
        """Apply the path prefix to a GCS object path.

        Args:
            path: Original GCS object path

        Returns:
            Path with prefix applied. If path_prefix is empty, returns path unchanged.
            Ensures no double slashes if path already starts with /.
        """
        if not self.path_prefix:
            return path

        # Remove leading slash from path if present
        clean_path = path.lstrip("/")
        # Remove trailing slash from prefix if present
        clean_prefix = self.path_prefix.rstrip("/")

        return f"{clean_prefix}/{clean_path}"

    @contextmanager
    def open_write_stream(
        self, path: str, content_type: str | None = None, compress: bool = False
    ) -> Any:
        """Open a streaming write stream to GCS.

        Creates a context manager that yields a file-like object for
        streaming writes directly to GCS without local intermediate storage.

        Args:
            path: GCS object path (e.g., "json/data.json")
            content_type: MIME content type (e.g., "text/plain", "application/json").
                If None, will be auto-detected from file extension.
            compress: Whether to apply gzip compression. When True, content-type
                will be set to "application/gzip" and data will be compressed.

        Yields:
            File-like object for streaming writes

        Example:
            >>> writer = GCSStreamWriter("my-bucket", "my-project", path_prefix="vgnc/")
            >>> with writer.open_write_stream("data.json", "application/json") as f:
            ...     f.write('{"key": "value"}')
        """
        # Apply path prefix
        full_path = self._apply_path_prefix(path)

        # Auto-detect content-type if not provided
        if content_type is None:
            content_type = self._detect_content_type(path)

        # Override content-type for compressed files
        if compress:
            content_type = "application/gzip"

        # Get blob reference
        blob = self._bucket.blob(full_path)

        # Set content type before opening stream
        blob.content_type = content_type

        # For compressed files, we need to use a different approach
        # since GCS blob.open() doesn't support transparent gzip compression
        if compress:
            # Open blob in binary mode for direct upload
            import tempfile

            with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".gz") as tmp_file:
                tmp_path = tmp_file.name

            try:
                # Create a gzip file wrapper
                with gzip.open(tmp_path, "wb") as gzip_file:
                    # Yield a wrapper that writes to the gzip file
                    class _GzipWriteWrapper:
                        """Wrapper that writes to gzip file."""

                        def __init__(self, gzip_fp: Any) -> None:
                            self._gzip_fp = gzip_fp

                        def write(self, data: str) -> int:
                            """Write data to gzip file."""
                            bytes_data = data.encode("utf-8")
                            self._gzip_fp.write(bytes_data)
                            return len(data)

                        def close(self) -> None:
                            """Close the gzip file."""
                            try:
                                self._gzip_fp.close()
                            except Exception:
                                pass

                    wrapper = _GzipWriteWrapper(gzip_file)
                    yield wrapper
            finally:
                # Upload the compressed file to GCS
                try:
                    blob.upload_from_filename(tmp_path, content_type="application/gzip")
                finally:
                    # Clean up temp file
                    import pathlib
                    pathlib.Path(tmp_path).unlink(missing_ok=True)
        else:
            # Non-compressed: use streaming upload
            stream = self._open_blob_with_retry(blob)
            try:
                yield stream
            finally:
                stream.close()
        # Note: Bucket uses uniform bucket-level access
        # Public access is granted via IAM policy, not object ACLs

    @retry_with_exponential_backoff(max_retries=3, initial_backoff=1, multiplier=2)
    def _open_blob_with_retry(self, blob: storage.Blob) -> Any:
        """Open blob stream with retry logic.

        Args:
            blob: GCS blob object

        Returns:
            Open stream object
        """
        return blob.open("w", encoding="utf-8")

    def upload_from_file(
        self,
        source_path: str,
        gcs_path: str,
        content_type: str | None = None,
        compress: bool = False,
    ) -> None:
        """Upload a local file to GCS.

        Uploads a file from the local filesystem to GCS. This is a non-streaming
        upload suitable for smaller files or when streaming is not required.

        Args:
            source_path: Path to the local file to upload
            gcs_path: Destination path in GCS (e.g., "data/uploads/file.txt")
            content_type: MIME content type. If None, will be auto-detected
                from the gcs_path extension.
            compress: Whether to compress the file with gzip before uploading.
                When True, content-type will be set to "application/gzip".

        Example:
            >>> writer = GCSStreamWriter("my-bucket", "my-project", path_prefix="vgnc/")
            >>> writer.upload_from_file("/tmp/data.json", "json/data.json")
        """
        # Apply path prefix
        full_path = self._apply_path_prefix(gcs_path)

        # Auto-detect content-type if not provided
        if content_type is None:
            content_type = self._detect_content_type(gcs_path)

        # Handle compression
        if compress:
            content_type = "application/gzip"
            # For compressed uploads, we need to compress the file first
            compressed_path = f"{source_path}.gz"
            with open(source_path, "rb") as f_in:
                with gzip.open(compressed_path, "wb") as f_out:
                    f_out.writelines(f_in)
            upload_path = compressed_path
        else:
            upload_path = source_path

        # Get blob reference
        blob = self._bucket.blob(full_path)

        # Set content type
        blob.content_type = content_type

        # Upload the file with retry logic
        self._upload_blob_with_retry(blob, upload_path)

        # Clean up compressed file if it was created
        if compress:
            Path(compressed_path).unlink(missing_ok=True)

    @retry_with_exponential_backoff(max_retries=3, initial_backoff=1, multiplier=2)
    def _upload_blob_with_retry(self, blob: storage.Blob, source_path: str) -> None:
        """Upload blob from file with retry logic.

        Args:
            blob: GCS blob object
            source_path: Path to the local file to upload
        """
        blob.upload_from_filename(source_path)
        # Note: Bucket uses uniform bucket-level access
        # Public access is granted via IAM policy, not object ACLs

    def create_backward_compatibility_copy(self, source_path: str, legacy_species: str) -> None:
        """Create a backward compatibility copy from new path to legacy species path.

        This method creates a copy of a file from its new location (e.g., with "cattle")
        to the legacy location (e.g., with "cow") for backward compatibility.
        The path prefix is applied to both source and destination paths.

        Args:
            source_path: The source file path (e.g., "tsv/cattle/cattle_vgnc_gene_set_chr_X.txt")
            legacy_species: The legacy species name to replace in the path (e.g., "cow")

        Example:
            >>> writer = GCSStreamWriter("my-bucket", "my-project", path_prefix="vgnc/")
            >>> writer.create_backward_compatibility_copy(
            ...     "tsv/cattle/cattle_vgnc_gene_set_chr_X.txt",
            ...     "cow"
            ... )
            # Creates copy at: vgnc/tsv/cow/cow_vgnc_gene_set_chr_X.txt
        """
        # Apply path prefix to source
        full_source_path = self._apply_path_prefix(source_path)

        # Replace all occurrences of the normalized species name in the path
        # with the legacy species name
        dest_path = source_path.replace("/cattle/", f"/{legacy_species}/")
        dest_path = dest_path.replace("cattle_", f"{legacy_species}_")

        # Apply path prefix to destination
        full_dest_path = self._apply_path_prefix(dest_path)

        # Get source and destination blobs
        source_blob = self._bucket.blob(full_source_path)
        dest_blob = self._bucket.blob(full_dest_path)

        # Copy the source blob to the destination (download and re-upload)
        # This creates a backward compatibility link without using actual symlinks
        source_bytes = source_blob.download_as_bytes()
        dest_blob.upload_from_string(source_bytes, content_type=source_blob.content_type)
        # Note: Bucket uses uniform bucket-level access
        # Public access is granted via IAM policy, not object ACLs
