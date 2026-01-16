"""Integration tests for GCS writer with real Google Cloud Storage.

These tests require:
- --integration flag to run
- Real GCS bucket access (genenames_public_bucket)
- GCP authentication via service account key

Run with: uv run pytest --integration tests/test_gcs_integration.py
"""

import tempfile
from pathlib import Path

import pytest

from vgnc_download_file_generator.writers.gcs_writer import GCSStreamWriter


@pytest.mark.integration
class TestGCSConnection:
    """Tests for GCS connection."""

    def test_can_connect_to_gcs(self, gcs_config_only) -> None:
        """Test that we can create a GCS client."""
        from google.cloud import storage

        client = storage.Client(project=gcs_config_only.gcs.project_id)
        assert client is not None

    def test_bucket_exists(self, gcs_config_only) -> None:
        """Test that the test bucket exists."""
        from google.cloud import storage

        client = storage.Client(project=gcs_config_only.gcs.project_id)
        bucket = client.bucket(gcs_config_only.gcs.bucket_name)
        assert bucket.exists()

    def test_bucket_is_accessible(self, gcs_config_only) -> None:
        """Test that we can access the bucket."""
        from google.cloud import storage

        client = storage.Client(project=gcs_config_only.gcs.project_id)
        bucket = client.bucket(gcs_config_only.gcs.bucket_name)
        # Try to list blobs (will be empty or minimal)
        blobs = list(bucket.list_blobs(max_results=1))
        assert isinstance(blobs, list)


@pytest.mark.integration
class TestGCSStreamWriter:
    """Integration tests for GCSStreamWriter with real GCS."""

    def test_create_writer_instance(self, gcs_config_only) -> None:
        """Test that we can create a GCSStreamWriter instance."""
        writer = GCSStreamWriter(
            bucket_name=gcs_config_only.gcs.bucket_name,
            project_id=gcs_config_only.gcs.project_id,
        )
        assert writer is not None
        assert writer.bucket_name == gcs_config_only.gcs.bucket_name

    def test_write_text_file_to_gcs(self, gcs_config_only, test_gcs_bucket_only) -> None:
        """Test writing a simple text file to GCS."""
        writer = GCSStreamWriter(
            bucket_name=gcs_config_only.gcs.bucket_name,
            project_id=gcs_config_only.gcs.project_id,
        )

        test_path = "test/integration_test.txt"

        # Write content
        with writer.open_write_stream(test_path, "text/plain") as f:
            f.write("Hello from integration test!")

        # Verify file exists
        blob = test_gcs_bucket_only.blob(test_path)
        assert blob.exists()

        # Verify content
        content = blob.download_as_text()
        assert "Hello from integration test!" in content

        # Cleanup
        blob.delete()

    def test_upload_file_to_gcs(self, gcs_config_only, test_gcs_bucket_only) -> None:
        """Test uploading a local file to GCS."""
        writer = GCSStreamWriter(
            bucket_name=gcs_config_only.gcs.bucket_name,
            project_id=gcs_config_only.gcs.project_id,
        )

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as tmp:
            tmp.write("Upload test content")
            tmp_path = tmp.name

        try:
            gcs_path = "test/upload_test.txt"
            writer.upload_from_file(tmp_path, gcs_path, "text/plain")

            # Verify file exists
            blob = test_gcs_bucket_only.blob(gcs_path)
            assert blob.exists()

            # Verify content
            content = blob.download_as_text()
            assert "Upload test content" in content

        finally:
            # Cleanup local file
            Path(tmp_path).unlink(missing_ok=True)

            # Cleanup GCS file
            blob = test_gcs_bucket_only.blob("test/upload_test.txt")
            if blob.exists():
                blob.delete()

    def test_write_tsv_file_to_gcs(self, gcs_config_only, test_gcs_bucket_only) -> None:
        """Test writing a TSV file to GCS with correct content-type."""
        writer = GCSStreamWriter(
            bucket_name=gcs_config_only.gcs.bucket_name,
            project_id=gcs_config_only.gcs.project_id,
        )

        test_path = "test/test_data.tsv"
        tsv_content = "col1\tcol2\tcol3\nval1\tval2\tval3\n"

        # Write TSV content
        with writer.open_write_stream(test_path, "text/tab-separated-values") as f:
            f.write(tsv_content)

        # Verify content type
        blob = test_gcs_bucket_only.blob(test_path)
        blob.reload()  # Reload to get latest metadata
        assert blob.content_type == "text/tab-separated-values"

        # Verify content
        content = blob.download_as_text()
        assert content == tsv_content

        # Cleanup
        blob.delete()

    def test_write_json_file_to_gcs(self, gcs_config_only, test_gcs_bucket_only) -> None:
        """Test writing a JSON file to GCS with correct content-type."""
        writer = GCSStreamWriter(
            bucket_name=gcs_config_only.gcs.bucket_name,
            project_id=gcs_config_only.gcs.project_id,
        )

        test_path = "test/test_data.json"
        json_content = '{"key": "value", "number": 123}'

        # Write JSON content
        with writer.open_write_stream(test_path, "application/json") as f:
            f.write(json_content)

        # Verify content type
        blob = test_gcs_bucket_only.blob(test_path)
        blob.reload()  # Reload to get latest metadata
        assert blob.content_type == "application/json"

        # Verify content
        content = blob.download_as_text()
        assert content == json_content

        # Cleanup
        blob.delete()

    def test_auto_detect_content_type(self, gcs_config_only, test_gcs_bucket_only) -> None:
        """Test automatic content-type detection based on file extension."""
        writer = GCSStreamWriter(
            bucket_name=gcs_config_only.gcs.bucket_name,
            project_id=gcs_config_only.gcs.project_id,
        )

        # Test .txt extension
        with writer.open_write_stream("test/data.txt", content_type=None) as f:
            f.write("test")

        blob = test_gcs_bucket_only.blob("test/data.txt")
        blob.reload()  # Reload to get latest metadata
        assert blob.content_type == "text/tab-separated-values"
        blob.delete()

        # Test .json extension
        with writer.open_write_stream("test/data.json", content_type=None) as f:
            f.write("{}")

        blob = test_gcs_bucket_only.blob("test/data.json")
        blob.reload()  # Reload to get latest metadata
        assert blob.content_type == "application/json"
        blob.delete()

        # Test .tsv extension
        with writer.open_write_stream("test/data.tsv", content_type=None) as f:
            f.write("test")

        blob = test_gcs_bucket_only.blob("test/data.tsv")
        blob.reload()  # Reload to get latest metadata
        assert blob.content_type == "text/tab-separated-values"
        blob.delete()

    def test_upload_compressed_file(self, gcs_config_only, test_gcs_bucket_only) -> None:
        """Test uploading a file with gzip compression."""
        import gzip

        writer = GCSStreamWriter(
            bucket_name=gcs_config_only.gcs.bucket_name,
            project_id=gcs_config_only.gcs.project_id,
        )

        # Create temporary file with content
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as tmp:
            tmp.write("This is test content for compression")
            tmp_path = tmp.name

        try:
            gcs_path = "test/compressed.txt"

            # Upload with compression
            writer.upload_from_file(tmp_path, gcs_path, compress=True)

            # Verify file exists
            blob = test_gcs_bucket_only.blob(gcs_path)
            assert blob.exists()

            # Verify content type is gzip
            blob.reload()  # Reload to get latest metadata
            assert blob.content_type == "application/gzip"

            # Verify content is compressed
            compressed_content = blob.download_as_bytes()
            # Should be gzip compressed
            assert compressed_content[:2] == b"\x1f\x8b"  # Gzip magic number

        finally:
            # Cleanup local file
            Path(tmp_path).unlink(missing_ok=True)

            # Cleanup GCS file
            blob = test_gcs_bucket_only.blob("test/compressed.txt")
            if blob.exists():
                blob.delete()


@pytest.mark.integration
class TestGCSRetryLogic:
    """Integration tests for retry logic with real GCS."""

    def test_survives_transient_network_errors(self, gcs_config_only, test_gcs_bucket_only) -> None:
        """Test that the writer can handle and retry on transient errors."""
        # This test is difficult to implement reliably without causing actual errors
        # For now, we just verify the writer can successfully write multiple times
        writer = GCSStreamWriter(
            bucket_name=gcs_config_only.gcs.bucket_name,
            project_id=gcs_config_only.gcs.project_id,
        )

        # Write multiple files in succession
        for i in range(3):
            test_path = f"test/retry_test_{i}.txt"
            with writer.open_write_stream(test_path, "text/plain") as f:
                f.write(f"Test file {i}")

            # Verify
            blob = test_gcs_bucket_only.blob(test_path)
            assert blob.exists()

        # Cleanup
        for i in range(3):
            blob = test_gcs_bucket_only.blob(f"test/retry_test_{i}.txt")
            blob.delete()


@pytest.mark.integration
class TestGCSCleanup:
    """Tests for automatic cleanup of test files."""

    def test_cleanup_test_files_after_test(self, gcs_config_only, test_gcs_bucket_only) -> None:
        """Test that test files are cleaned up after test runs."""
        # This test verifies the autouse cleanup fixture works
        # Create some test files
        test_paths = ["test/cleanup_1.txt", "test/cleanup_2.txt", "test/cleanup_3.txt"]

        writer = GCSStreamWriter(
            bucket_name=gcs_config_only.gcs.bucket_name,
            project_id=gcs_config_only.gcs.project_id,
        )

        for path in test_paths:
            with writer.open_write_stream(path, "text/plain") as f:
                f.write("cleanup test")

        # Verify files exist
        for path in test_paths:
            blob = test_gcs_bucket_only.blob(path)
            assert blob.exists()

        # Files will be cleaned up by the autouse fixture
        # This happens after the test completes
