"""Tests for GCSStreamWriter class."""

from unittest.mock import MagicMock, patch

from vgnc_download_file_generator.writers.gcs_writer import GCSStreamWriter


class TestGCSStreamWriterInit:
    """Tests for GCSStreamWriter.__init__ method."""

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_initializes_storage_client_with_project_id(self, mock_storage) -> None:
        """Test that storage.Client is initialized with project_id."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        mock_storage.Client.assert_called_once_with(project="test-project")
        assert writer._client == mock_client
        assert writer._bucket == mock_bucket

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_stores_bucket_name_and_project_id(self, mock_storage) -> None:
        """Test that bucket_name and project_id are stored as attributes."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        assert writer.bucket_name == "test-bucket"
        assert writer.project_id == "test-project"


class TestOpenWriteStream:
    """Tests for open_write_stream method."""

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_opens_blob_with_correct_path(self, mock_storage) -> None:
        """Test that blob is opened with the correct path."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_stream = MagicMock()
        mock_blob.open.return_value = mock_stream

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        with writer.open_write_stream("test/path.txt", "text/plain"):
            pass

        mock_bucket.blob.assert_called_once_with("test/path.txt")

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_opens_stream_with_write_mode_and_utf8_encoding(self, mock_storage) -> None:
        """Test that blob.open is called with 'w' mode and utf-8 encoding."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_stream = MagicMock()
        mock_blob.open.return_value = mock_stream

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        with writer.open_write_stream("test/path.txt", "text/plain"):
            pass

        mock_blob.open.assert_called_once_with("w", encoding="utf-8")

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_sets_content_type_on_blob(self, mock_storage) -> None:
        """Test that content_type is set on the blob before opening stream."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_stream = MagicMock()
        mock_blob.open.return_value = mock_stream

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        with writer.open_write_stream("test/path.txt", "application/json"):
            pass

        assert mock_blob.content_type == "application/json"

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_returns_stream_object_from_context_manager(self, mock_storage) -> None:
        """Test that the context manager returns the stream object."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_stream = MagicMock()
        mock_blob.open.return_value = mock_stream

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        with writer.open_write_stream("test/path.txt", "text/plain") as stream:
            assert stream == mock_stream

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_closes_stream_on_context_exit(self, mock_storage) -> None:
        """Test that the stream is properly closed when exiting context."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_stream = MagicMock()
        mock_blob.open.return_value = mock_stream

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        with writer.open_write_stream("test/path.txt", "text/plain"):
            pass

        mock_stream.close.assert_called_once()

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_handles_exception_in_context_without_closing(self, mock_storage) -> None:
        """Test that exceptions in the context don't prevent cleanup."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        class TestError(Exception):
            pass

        mock_stream = MagicMock()
        mock_stream.write.side_effect = TestError("Test error")
        mock_blob.open.return_value = mock_stream

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        try:
            with writer.open_write_stream("test/path.txt", "text/plain") as stream:
                stream.write("test")
        except TestError:
            pass

        # Stream should still be closed even on error
        mock_stream.close.assert_called_once()


class TestContentTypeDetection:
    """Tests for automatic content-type detection."""

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_detects_tsv_content_type_from_extension(self, mock_storage) -> None:
        """Test that .txt files get text/tab-separated-values content-type."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_stream = MagicMock()
        mock_blob.open.return_value = mock_stream

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        with writer.open_write_stream("data.txt", content_type=None):
            pass

        assert mock_blob.content_type == "text/tab-separated-values"

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_detects_tsv_content_type_from_tsv_extension(self, mock_storage) -> None:
        """Test that .tsv files get text/tab-separated-values content-type."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_stream = MagicMock()
        mock_blob.open.return_value = mock_stream

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        with writer.open_write_stream("data.tsv", content_type=None):
            pass

        assert mock_blob.content_type == "text/tab-separated-values"

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_detects_json_content_type_from_extension(self, mock_storage) -> None:
        """Test that .json files get application/json content-type."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_stream = MagicMock()
        mock_blob.open.return_value = mock_stream

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        with writer.open_write_stream("data.json", content_type=None):
            pass

        assert mock_blob.content_type == "application/json"

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_detects_gzip_content_type_from_gz_extension(self, mock_storage) -> None:
        """Test that .gz files get application/gzip content-type."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_stream = MagicMock()
        mock_blob.open.return_value = mock_stream

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        with writer.open_write_stream("data.json.gz", content_type=None):
            pass

        assert mock_blob.content_type == "application/gzip"

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_explicit_content_type_overrides_detection(self, mock_storage) -> None:
        """Test that explicit content_type parameter overrides auto-detection."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_stream = MagicMock()
        mock_blob.open.return_value = mock_stream

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        with writer.open_write_stream("data.json", content_type="text/plain"):
            pass

        assert mock_blob.content_type == "text/plain"

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_defaults_to_octet_stream_for_unknown_extension(self, mock_storage) -> None:
        """Test that unknown extensions default to application/octet-stream."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_stream = MagicMock()
        mock_blob.open.return_value = mock_stream

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        with writer.open_write_stream("data.unknown", content_type=None):
            pass

        assert mock_blob.content_type == "application/octet-stream"


class TestGzipCompression:
    """Tests for gzip compression functionality."""

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    @patch("vgnc_download_file_generator.writers.gcs_writer.gzip")
    def test_sets_gzip_content_type_when_compress_enabled(self, _mock_gzip, mock_storage) -> None:
        """Test that content-type is set to application/gzip when compress=True."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_stream = MagicMock()
        mock_blob.open.return_value = mock_stream

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        with writer.open_write_stream("All_species_data.txt", "text/plain", compress=True):
            pass

        # When compressing, content-type should be gzip
        assert mock_blob.content_type == "application/gzip"

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_sets_original_content_type_when_compress_disabled(self, mock_storage) -> None:
        """Test that content-type is not changed when compress=False."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_stream = MagicMock()
        mock_blob.open.return_value = mock_stream

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        with writer.open_write_stream("cow_data.txt", "text/plain", compress=False):
            pass

        # When not compressing, content-type should be the original
        assert mock_blob.content_type == "text/plain"

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_detects_compression_from_gz_extension(self, mock_storage) -> None:
        """Test that .gz files are detected as gzip content-type."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_stream = MagicMock()
        mock_blob.open.return_value = mock_stream

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        with writer.open_write_stream("data.json.gz", content_type=None):
            pass

        assert mock_blob.content_type == "application/gzip"


class TestUploadFromFile:
    """Tests for upload_from_file method."""

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_uploads_file_to_gcs(self, mock_storage) -> None:
        """Test that upload_from_file uploads a local file to GCS."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        # Create a temporary file for testing
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as tmp:
            tmp.write("test content")
            tmp_path = tmp.name

        try:
            writer.upload_from_file(tmp_path, "test/upload.txt", "text/plain")

            # Verify blob was created and uploaded
            mock_bucket.blob.assert_called_once_with("test/upload.txt")
            mock_blob.upload_from_filename.assert_called_once_with(tmp_path)
            assert mock_blob.content_type == "text/plain"
        finally:
            import os
            os.unlink(tmp_path)

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_sets_content_type_on_upload(self, mock_storage) -> None:
        """Test that content_type is set when uploading file."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
            tmp.write("test")
            tmp_path = tmp.name

        try:
            writer.upload_from_file(tmp_path, "data.json", "application/json")

            assert mock_blob.content_type == "application/json"
        finally:
            import os
            os.unlink(tmp_path)

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    @patch("vgnc_download_file_generator.writers.gcs_writer.gzip")
    def test_compresses_file_during_upload_when_requested(self, mock_gzip, mock_storage) -> None:
        """Test that file is compressed during upload when compress=True."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        mock_gzip.open.return_value.__enter__ = MagicMock()
        mock_gzip.open.return_value.__exit__ = MagicMock()
        mock_gzip.open.return_value.write = MagicMock()

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
            tmp.write("test content")
            tmp_path = tmp.name

        try:
            writer.upload_from_file(tmp_path, "All_data.txt", "text/plain", compress=True)

            # Verify gzip compression was used
            mock_gzip.open.assert_called_once()
            # Content type should be gzip when compressing
            assert mock_blob.content_type == "application/gzip"
        finally:
            import os
            os.unlink(tmp_path)

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_auto_detects_content_type_when_not_provided(self, mock_storage) -> None:
        """Test that content_type is auto-detected from extension when not provided."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as tmp:
            tmp.write("{}")
            tmp_path = tmp.name

        try:
            writer.upload_from_file(tmp_path, "data.json", content_type=None)

            assert mock_blob.content_type == "application/json"
        finally:
            import os
            os.unlink(tmp_path)


class TestRetryLogic:
    """Tests for exponential backoff retry logic."""

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    @patch("vgnc_download_file_generator.writers.gcs_writer.time.sleep")
    def test_retries_on_transient_gcs_errors(self, mock_sleep, mock_storage) -> None:
        """Test that transient GCS errors trigger retries."""
        from google.api_core.exceptions import ServiceUnavailable

        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        # Fail twice, then succeed
        mock_stream = MagicMock()
        mock_blob.open.side_effect = [
            ServiceUnavailable("Temporary error"),
            ServiceUnavailable("Temporary error"),
            mock_stream,
        ]

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        with writer.open_write_stream("data.txt", "text/plain"):
            pass

        # Verify 3 attempts (1 initial + 2 retries)
        assert mock_blob.open.call_count == 3
        # Verify sleep was called for backoff (2 times for 2 retries)
        assert mock_sleep.call_count == 2

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    @patch("vgnc_download_file_generator.writers.gcs_writer.time.sleep")
    def test_exponential_backoff_increments_correctly(self, mock_sleep, mock_storage) -> None:
        """Test that backoff times follow exponential pattern (1s, 2s, 4s)."""
        from google.api_core.exceptions import DeadlineExceeded

        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        # Fail all 3 times (max retries)
        MagicMock()
        mock_blob.open.side_effect = [
            DeadlineExceeded("Timeout"),
            DeadlineExceeded("Timeout"),
            DeadlineExceeded("Timeout"),
        ]

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        try:
            with writer.open_write_stream("data.txt", "text/plain"):
                pass
        except DeadlineExceeded:
            pass  # Expected after max retries

        # Verify exponential backoff: 1s, 2s
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert sleep_calls == [1, 2]

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    @patch("vgnc_download_file_generator.writers.gcs_writer.time.sleep")
    def test_succeeds_on_final_retry(self, _mock_sleep, mock_storage) -> None:
        """Test that operation succeeds on the final retry attempt."""
        from google.api_core.exceptions import ServiceUnavailable

        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        # Fail twice, succeed on third attempt
        mock_stream = MagicMock()
        mock_blob.open.side_effect = [
            ServiceUnavailable("Error 1"),
            ServiceUnavailable("Error 2"),
            mock_stream,
        ]

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        # Should succeed without raising exception
        with writer.open_write_stream("data.txt", "text/plain") as stream:
            assert stream == mock_stream

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    @patch("vgnc_download_file_generator.writers.gcs_writer.time.sleep")
    def test_propagates_error_after_max_retries(self, _mock_sleep, mock_storage) -> None:
        """Test that error is propagated after max retries exhausted."""
        from google.api_core.exceptions import ServiceUnavailable

        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        # Always fail
        mock_blob.open.side_effect = ServiceUnavailable("Persistent error")

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        try:
            with writer.open_write_stream("data.txt", "text/plain"):
                pass
            raise AssertionError("Should have raised ServiceUnavailable")
        except ServiceUnavailable as e:
            assert "Persistent error" in str(e)

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    @patch("vgnc_download_file_generator.writers.gcs_writer.time.sleep")
    def test_does_not_retry_on_non_transient_errors(self, mock_sleep, mock_storage) -> None:
        """Test that non-transient errors are not retried."""
        from google.api_core.exceptions import NotFound

        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        # Non-transient error (bucket doesn't exist)
        mock_blob.open.side_effect = NotFound("Bucket not found")

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        try:
            with writer.open_write_stream("data.txt", "text/plain"):
                pass
            raise AssertionError("Should have raised NotFound")
        except NotFound:
            pass

        # Should not retry non-transient errors
        assert mock_blob.open.call_count == 1
        assert mock_sleep.call_count == 0


class TestRetryLogicForUploadFromFile:
    """Tests for retry logic in upload_from_file method."""

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    @patch("vgnc_download_file_generator.writers.gcs_writer.time.sleep")
    @patch("vgnc_download_file_generator.writers.gcs_writer.Path")
    def test_upload_retries_on_transient_errors(self, mock_path, mock_sleep, mock_storage) -> None:
        """Test that upload_from_file retries on transient GCS errors."""
        from google.api_core.exceptions import ServiceUnavailable

        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        # Fail twice, then succeed
        mock_blob.upload_from_filename.side_effect = [
            ServiceUnavailable("Network error"),
            ServiceUnavailable("Network error"),
            None,  # Success
        ]

        # Mock Path.unlink to avoid actual file deletion
        mock_path.return_value.unlink.return_value = None

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
            tmp.write("test")
            tmp_path = tmp.name

        try:
            writer.upload_from_file(tmp_path, "data.txt", "text/plain")

            # Verify 3 attempts (1 initial + 2 retries)
            assert mock_blob.upload_from_filename.call_count == 3
            assert mock_sleep.call_count == 2
        finally:
            import os
            os.unlink(tmp_path)


class TestErrorLogging:
    """Tests for error logging in retry logic."""

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    @patch("vgnc_download_file_generator.writers.gcs_writer.time.sleep")
    @patch("vgnc_download_file_generator.writers.gcs_writer.logger")
    def test_logs_retry_attempts(self, mock_logger, _mock_sleep, mock_storage) -> None:
        """Test that retry attempts are logged with retry count."""
        from google.api_core.exceptions import ServiceUnavailable

        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        # Fail twice, then succeed
        mock_stream = MagicMock()
        mock_blob.open.side_effect = [
            ServiceUnavailable("Error 1"),
            ServiceUnavailable("Error 2"),
            mock_stream,
        ]

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        with writer.open_write_stream("data.txt", "text/plain"):
            pass

        # Verify logging occurred (check that warning was called at least twice)
        assert mock_logger.warning.call_count >= 2

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    @patch("vgnc_download_file_generator.writers.gcs_writer.time.sleep")
    @patch("vgnc_download_file_generator.writers.gcs_writer.logger")
    def test_logs_final_error_after_max_retries(self, mock_logger, _mock_sleep, mock_storage) -> None:
        """Test that final error is logged after max retries exhausted."""
        from google.api_core.exceptions import ServiceUnavailable

        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        # Always fail
        mock_blob.open.side_effect = ServiceUnavailable("Persistent error")

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        try:
            with writer.open_write_stream("data.txt", "text/plain"):
                pass
        except ServiceUnavailable:
            pass  # Expected

        # Verify error was logged
        assert mock_logger.error.call_count >= 1


class TestBackwardCompatibilityCopy:
    """Tests for creating backward compatibility copies (symlinks)."""

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_creates_copy_from_cattle_to_cow_path(self, mock_storage) -> None:
        """Test that a copy is created from cattle path to cow path for backward compatibility."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        # Mock the source blob (cattle path)
        source_blob = MagicMock()
        mock_bucket.blob.return_value = source_blob

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        # Create backward compatibility copy
        writer.create_backward_compatibility_copy(
            source_path="tsv/cattle/cattle_vgnc_gene_set_chr_X.txt",
            legacy_species="cow"
        )

        # Verify the destination blob (cow path) was created
        expected_dest_path = "tsv/cow/cow_vgnc_gene_set_chr_X.txt"
        mock_bucket.blob.assert_called_with(expected_dest_path)

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_copy_rewrites_cattle_path_to_cow_path(self, mock_storage) -> None:
        """Test that the blob download/upload is called to create the copy."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        source_blob = MagicMock()
        dest_blob = MagicMock()

        def blob_side_effect(path):
            if "cattle" in path:
                return source_blob
            else:
                return dest_blob

        mock_bucket.blob.side_effect = blob_side_effect

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        writer.create_backward_compatibility_copy(
            source_path="tsv/cattle/cattle_gene_with_protein_product_All.txt",
            legacy_species="cow"
        )

        # Verify download and upload were called (new implementation)
        source_blob.download_as_bytes.assert_called_once()
        dest_blob.upload_from_string.assert_called_once()

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_handles_subdirectory_paths_correctly(self, mock_storage) -> None:
        """Test that locus_types and locus_groups subdirectories are handled correctly."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        source_blob = MagicMock()
        dest_blob = MagicMock()

        def blob_side_effect(path):
            if "cattle" in path:
                return source_blob
            else:
                return dest_blob

        mock_bucket.blob.side_effect = blob_side_effect

        writer = GCSStreamWriter(bucket_name="test-bucket", project_id="test-project")

        writer.create_backward_compatibility_copy(
            source_path="json/cattle/locus_types/cattle_gene_with_protein_product_All.json",
            legacy_species="cow"
        )

        # Verify destination path was constructed correctly
        expected_calls = [
            "json/cattle/locus_types/cattle_gene_with_protein_product_All.json",
            "json/cow/locus_types/cow_gene_with_protein_product_All.json"
        ]
        actual_calls = [call[0][0] for call in mock_bucket.blob.call_args_list]
        assert actual_calls == expected_calls


class TestPathPrefix:
    """Tests for GCS path prefix functionality."""

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_applies_prefix_to_blob_path(self, mock_storage) -> None:
        """Test that path prefix is applied to blob paths."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_stream = MagicMock()
        mock_blob.open.return_value = mock_stream

        writer = GCSStreamWriter(
            bucket_name="test-bucket",
            project_id="test-project",
            path_prefix="vgnc/"
        )

        with writer.open_write_stream("tsv/file.txt", "text/plain"):
            pass

        # Verify the full path with prefix was used
        mock_bucket.blob.assert_called_once_with("vgnc/tsv/file.txt")

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_no_prefix_when_empty_string(self, mock_storage) -> None:
        """Test that empty prefix doesn't add anything to path."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_stream = MagicMock()
        mock_blob.open.return_value = mock_stream

        writer = GCSStreamWriter(
            bucket_name="test-bucket",
            project_id="test-project",
            path_prefix=""
        )

        with writer.open_write_stream("tsv/file.txt", "text/plain"):
            pass

        # Verify path was used without prefix
        mock_bucket.blob.assert_called_once_with("tsv/file.txt")

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_handles_leading_slash_correctly(self, mock_storage) -> None:
        """Test that leading slash in path is handled correctly with prefix."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_stream = MagicMock()
        mock_blob.open.return_value = mock_stream

        writer = GCSStreamWriter(
            bucket_name="test-bucket",
            project_id="test-project",
            path_prefix="vgnc/"
        )

        with writer.open_write_stream("/tsv/file.txt", "text/plain"):
            pass

        # Verify leading slash is stripped and prefix is applied
        mock_bucket.blob.assert_called_once_with("vgnc/tsv/file.txt")

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_handles_trailing_slash_in_prefix(self, mock_storage) -> None:
        """Test that trailing slash in prefix is handled correctly."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_stream = MagicMock()
        mock_blob.open.return_value = mock_stream

        writer = GCSStreamWriter(
            bucket_name="test-bucket",
            project_id="test-project",
            path_prefix="vgnc/"
        )

        with writer.open_write_stream("tsv/file.txt", "text/plain"):
            pass

        # Verify no double slashes
        mock_bucket.blob.assert_called_once_with("vgnc/tsv/file.txt")

    @patch("vgnc_download_file_generator.writers.gcs_writer.storage")
    def test_applies_prefix_in_backward_compatibility_copy(self, mock_storage) -> None:
        """Test that path prefix is applied to both source and dest in backward compatibility copy."""
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        source_blob = MagicMock()
        dest_blob = MagicMock()

        def blob_side_effect(path):
            if "cattle" in path:
                return source_blob
            else:
                return dest_blob

        mock_bucket.blob.side_effect = blob_side_effect

        writer = GCSStreamWriter(
            bucket_name="test-bucket",
            project_id="test-project",
            path_prefix="vgnc/"
        )

        writer.create_backward_compatibility_copy(
            source_path="tsv/cattle/cattle_file.txt",
            legacy_species="cow"
        )

        # Verify both paths have prefix applied
        expected_calls = [
            "vgnc/tsv/cattle/cattle_file.txt",
            "vgnc/tsv/cow/cow_file.txt"
        ]
        actual_calls = [call[0][0] for call in mock_bucket.blob.call_args_list]
        assert actual_calls == expected_calls
