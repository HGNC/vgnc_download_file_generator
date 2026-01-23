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

    def __init__(self, bucket_name: str, project_id: str) -> None:
        """Initialize the GCS writer.

        Args:
            bucket_name: Name of the GCS bucket for uploads
            project_id: Google Cloud project ID
        """
        self.bucket_name = bucket_name
        self.project_id = project_id

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
                will be set to "application/gzip" regardless of the file extension.

        Yields:
            File-like object for streaming writes

        Example:
            >>> writer = GCSStreamWriter("my-bucket", "my-project")
            >>> with writer.open_write_stream("data.json", "application/json") as f:
            ...     f.write('{"key": "value"}')
        """
        # Auto-detect content-type if not provided
        if content_type is None:
            content_type = self._detect_content_type(path)

        # Override content-type for compressed files
        if compress:
            content_type = "application/gzip"

        # Get blob reference
        blob = self._bucket.blob(path)

        # Set content type before opening stream
        blob.content_type = content_type

        # Open streaming upload with retry logic
        stream = self._open_blob_with_retry(blob)

        try:
            yield stream
        finally:
            # Ensure stream is closed on exit
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
            >>> writer = GCSStreamWriter("my-bucket", "my-project")
            >>> writer.upload_from_file("/tmp/data.json", "json/data.json")
        """
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
        blob = self._bucket.blob(gcs_path)

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

        Args:
            source_path: The source file path (e.g., "tsv/cattle/cattle_vgnc_gene_set_chr_X.txt")
            legacy_species: The legacy species name to replace in the path (e.g., "cow")

        Example:
            >>> writer = GCSStreamWriter("my-bucket", "my-project")
            >>> writer.create_backward_compatibility_copy(
            ...     "tsv/cattle/cattle_vgnc_gene_set_chr_X.txt",
            ...     "cow"
            ... )
            # Creates copy at: tsv/cow/cow_vgnc_gene_set_chr_X.txt
        """
        # Replace all occurrences of the normalized species name in the path
        # with the legacy species name
        dest_path = source_path.replace("/cattle/", f"/{legacy_species}/")
        dest_path = dest_path.replace("cattle_", f"{legacy_species}_")

        # Get source and destination blobs
        source_blob = self._bucket.blob(source_path)
        dest_blob = self._bucket.blob(dest_path)

        # Copy the source blob to the destination (rewrite operation)
        # This creates a backward compatibility link without using actual symlinks
        source_blob.copy_to(dest_blob, timeout=300)
        # Note: Bucket uses uniform bucket-level access
        # Public access is granted via IAM policy, not object ACLs
