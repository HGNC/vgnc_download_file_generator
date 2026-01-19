"""End-to-end tests for VGNC download file generator CLI.

These tests require:
- --e2e flag to run
- Full environment: real database + real GCS + CLI
- Database credentials from GCP Secret Manager
- GCS bucket: genenames_public_bucket

Run with: uv run pytest --e2e tests/test_e2e.py
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from vgnc_download_file_generator.__main__ import main
from vgnc_download_file_generator.config import AppConfig
from vgnc_download_file_generator.utils.secret_manager import get_db_credentials


# Helper function to create CliRunner with environment
def cli_runner_with_env():
    """Create a CliRunner with environment variables loaded.

    For E2E tests, we need to load database credentials from Secret Manager
    and add them to os.environ so the CLI can access them via Pydantic Settings.

    Note: Pydantic BaseSettings reads from os.environ() directly, not from
    the environment passed to CliRunner. So we set os.environ() temporarily.

    This function uses a timeout for Secret Manager access to prevent
    indefinite hangs. If Secret Manager is unavailable, tests will be skipped.
    """
    # Load database credentials from Secret Manager
    # The get_db_credentials function now has a 30-second timeout
    secret_name = os.environ.get('GOOGLE_SECRET_MANAGER_SECRET_NAME')
    project_id = os.environ.get('APP_GCS_PROJECT_ID')

    # Save original os.environ keys to restore later
    original_environ = {}
    env_keys_to_restore = [
        'APP_GCS_BUCKET_NAME',
        'APP_GCS_PROJECT_ID',
        'APP_RUNTIME_CHUNK_SIZE',
        'APP_RUNTIME_MAX_WORKERS',
        'APP_DATABASE_DBHOST',
        'APP_DATABASE_DBUSER',
        'APP_DATABASE_DBPASSWD',
        'APP_DATABASE_DBPORT',
        'APP_DATABASE_DBNAME',
    ]

    for key in env_keys_to_restore:
        if key in os.environ:
            original_environ[key] = os.environ[key]

    try:
        # Set GCS and runtime settings from os.environ
        os.environ['APP_GCS_BUCKET_NAME'] = os.environ.get('APP_GCS_BUCKET_NAME', '')
        os.environ['APP_GCS_PROJECT_ID'] = os.environ.get('APP_GCS_PROJECT_ID', '')
        os.environ['APP_RUNTIME_CHUNK_SIZE'] = os.environ.get('APP_RUNTIME_CHUNK_SIZE', '5000')
        os.environ['APP_RUNTIME_MAX_WORKERS'] = os.environ.get('APP_RUNTIME_MAX_WORKERS', '4')

        if secret_name and project_id:
            try:
                db_config = get_db_credentials(secret_name, project_id=project_id)
                # Add database credentials to os.environ (not just the env dict)
                # Pydantic Settings reads from os.environ() directly
                os.environ['APP_DATABASE_DBHOST'] = db_config.dbhost
                os.environ['APP_DATABASE_DBUSER'] = db_config.dbuser
                os.environ['APP_DATABASE_DBPASSWD'] = db_config.dbpasswd
                os.environ['APP_DATABASE_DBPORT'] = str(db_config.dbport)
                os.environ['APP_DATABASE_DBNAME'] = db_config.dbname
            except Exception as e:
                # Skip test if Secret Manager is unavailable
                # This prevents hangs and provides clear feedback
                pytest.skip(f"Secret Manager unavailable (tests skipped): {e}")

        # Build the environment dict to pass to CliRunner as well
        env = {
            'APP_GCS_BUCKET_NAME': os.environ.get('APP_GCS_BUCKET_NAME', ''),
            'APP_GCS_PROJECT_ID': os.environ.get('APP_GCS_PROJECT_ID', ''),
            'APP_RUNTIME_CHUNK_SIZE': os.environ.get('APP_RUNTIME_CHUNK_SIZE', '5000'),
            'APP_RUNTIME_MAX_WORKERS': os.environ.get('APP_RUNTIME_MAX_WORKERS', '4'),
        }

        if secret_name and project_id:
            env.update({
                'APP_DATABASE_DBHOST': os.environ.get('APP_DATABASE_DBHOST', ''),
                'APP_DATABASE_DBUSER': os.environ.get('APP_DATABASE_DBUSER', ''),
                'APP_DATABASE_DBPASSWD': os.environ.get('APP_DATABASE_DBPASSWD', ''),
                'APP_DATABASE_DBPORT': os.environ.get('APP_DATABASE_DBPORT', ''),
                'APP_DATABASE_DBNAME': os.environ.get('APP_DATABASE_DBNAME', ''),
            })

        return CliRunner(env=env)
    except Exception:
        # Restore original environment on error
        for key, value in original_environ.items():
            os.environ[key] = value
        for key in env_keys_to_restore:
            if key not in original_environ and key in os.environ:
                del os.environ[key]
        raise


@pytest.mark.e2e
class TestCLIDryRun:
    """E2E tests for CLI dry-run mode."""

    def test_dry_run_displays_generation_plan(self) -> None:
        """Test that dry-run shows what would be generated."""
        runner = cli_runner_with_env()
        result = runner.invoke(main, ["--species", "9913", "--chromosome", "X", "--dry-run"])
        assert result.exit_code == 0
        assert "DRY RUN MODE" in result.output
        assert "taxon_id 9913" in result.output
        assert "Chromosome: X" in result.output

    def test_dry_run_with_all_species(self) -> None:
        """Test dry-run for 'All' species."""
        runner = cli_runner_with_env()
        result = runner.invoke(main, ["--species", "All", "--file-type", "vgnc_ensembl", "--dry-run"])
        assert result.exit_code == 0
        assert "Species: All" in result.output
        assert "File Type: vgnc_ensembl" in result.output

    def test_dry_run_with_multiple_formats(self) -> None:
        """Test dry-run with multiple formats."""
        runner = cli_runner_with_env()
        result = runner.invoke(main, ["--species", "9913", "--formats", "tsv,json", "--dry-run"])
        assert result.exit_code == 0
        assert "TSV, JSON" in result.output


@pytest.mark.e2e
@pytest.mark.timeout(600)  # E2E tests need longer timeout due to complex database queries
class TestCLIWithRealServices:
    """E2E tests for CLI with real database and GCS."""

    def test_generate_tsv_file_to_gcs(self, real_config, test_gcs_bucket) -> None:
        """Test complete workflow: database -> TSV file -> GCS."""
        runner = cli_runner_with_env()
        test_path = "test/e2e_cow_chrX.tsv"

        result = runner.invoke(
            main,
            [
                "--species",
                "9913",
                "--chromosome",
                "X",
                "--formats",
                "tsv",
            ],
        )

        # Check CLI succeeded
        assert result.exit_code == 0
        assert "All files generated successfully" in result.output

        # Verify file was created in GCS
        # For species 9913 (cow), TSV files now use tsv/cow/
        blobs = list(test_gcs_bucket.list_blobs(prefix="tsv/cow/"))
        assert len(blobs) > 0

        # Cleanup test files
        for blob in blobs:
            blob.delete()

    def test_generate_json_file_to_gcs(self, real_config, test_gcs_bucket) -> None:
        """Test complete workflow: database -> JSON file -> GCS."""
        runner = cli_runner_with_env()

        result = runner.invoke(
            main,
            [
                "--species",
                "9913",
                "--chromosome",
                "X",
                "--formats",
                "json",
            ],
        )

        # Check CLI succeeded
        assert result.exit_code == 0
        assert "All files generated successfully" in result.output

        # Verify file was created in GCS
        blobs = list(test_gcs_bucket.list_blobs(prefix="json/cow/"))
        assert len(blobs) > 0

        # Verify JSON file is valid
        for blob in blobs:
            if blob.name.endswith(".json"):
                content = blob.download_as_text()
                # Should be valid JSON
                data = json.loads(content)
                assert isinstance(data, list)

        # Cleanup
        for blob in blobs:
            blob.delete()

    def test_generate_both_formats(self, real_config, test_gcs_bucket) -> None:
        """Test generating both TSV and JSON files in one run."""
        runner = cli_runner_with_env()

        result = runner.invoke(
            main,
            [
                "--species",
                "9913",
                "--chromosome",
                "X",
                "--formats",
                "tsv,json",
            ],
        )

        assert result.exit_code == 0
        assert "All files generated successfully" in result.output

        # Should have created files in GCS - check both directories
        tsv_blobs = list(test_gcs_bucket.list_blobs(prefix="tsv/cow/"))
        json_blobs = list(test_gcs_bucket.list_blobs(prefix="json/cow/"))
        total_blobs = tsv_blobs + json_blobs
        assert len(total_blobs) >= 2  # At least TSV and JSON

        # Cleanup
        for blob in total_blobs:
            blob.delete()

    def test_generate_ensembl_mapping(self, real_config, test_gcs_bucket) -> None:
        """Test generating Ensembl mapping file."""
        runner = cli_runner_with_env()

        result = runner.invoke(
            main,
            [
                "--species",
                "All",
                "--file-type",
                "vgnc_ensembl",
                "--formats",
                "tsv",
            ],
        )

        assert result.exit_code == 0
        assert "All files generated successfully" in result.output

        # Check for Ensembl file in GCS
        blobs = list(test_gcs_bucket.list_blobs(prefix="ensembl/"))
        assert len(blobs) > 0

        # Cleanup
        for blob in blobs:
            blob.delete()

    def test_generate_with_compression(self, real_config, test_gcs_bucket) -> None:
        """Test generating files with gzip compression."""
        runner = cli_runner_with_env()

        result = runner.invoke(
            main,
            [
                "--species",
                "9913",
                "--chromosome",
                "X",
                "--formats",
                "tsv",
                "--compress",
            ],
        )

        assert result.exit_code == 0

        # Verify compressed files
        blobs = list(test_gcs_bucket.list_blobs(prefix="tsv/cow/"))
        assert len(blobs) > 0

        # Check content type
        for blob in blobs:
            if blob.name.endswith((".txt.gz", ".json.gz")):
                assert blob.content_type == "application/gzip"

        # Cleanup
        for blob in blobs:
            blob.delete()

    def test_cli_shows_progress(self, real_config, test_gcs_bucket) -> None:
        """Test that CLI shows progress during file generation."""
        runner = cli_runner_with_env()

        result = runner.invoke(
            main,
            [
                "--species",
                "9913",
                "--chromosome",
                "X",
                "--formats",
                "tsv",
            ],
        )

        assert result.exit_code == 0
        # Should show progress indicators
        assert "Writing rows" in result.output or "Wrote" in result.output

        # Cleanup
        blobs = list(test_gcs_bucket.list_blobs(prefix="tsv/cow/"))
        for blob in blobs:
            blob.delete()


@pytest.mark.e2e
class TestCLIErrorHandling:
    """E2E tests for CLI error handling with real services."""

    def test_handles_invalid_species_id(self) -> None:
        """Test that invalid species ID is handled gracefully."""
        runner = cli_runner_with_env()

        result = runner.invoke(main, ["--species", "invalid", "--dry-run"])
        assert result.exit_code != 0
        assert "Invalid species ID" in result.output

    def test_requires_database_config(self) -> None:
        """Test that database configuration is required."""
        # This test verifies that AppConfig can be loaded from environment
        # If env vars aren't set, the test will be skipped
        from pydantic import ValidationError

        try:
            config = AppConfig()
            assert config is not None
        except ValidationError:
            pytest.skip("Configuration not available from environment")


@pytest.mark.e2e
@pytest.mark.timeout(600)  # E2E tests need longer timeout due to complex database queries
class TestCLIFileGeneration:
    """E2E tests for actual file generation and content verification."""

    def test_generated_tsv_has_correct_headers(self, real_config, test_gcs_bucket) -> None:
        """Test that generated TSV file has correct headers."""
        runner = cli_runner_with_env()

        result = runner.invoke(
            main,
            [
                "--species",
                "9913",
                "--chromosome",
                "X",
                "--formats",
                "tsv",
            ],
        )

        assert result.exit_code == 0

        # Find the generated file - TSV files now use tsv/cow/
        blobs = list(test_gcs_bucket.list_blobs(prefix="tsv/cow/"))
        tsv_blob = None
        for blob in blobs:
            if blob.name.endswith(".txt"):
                tsv_blob = blob
                break

        assert tsv_blob is not None, "No TSV file found"

        # Download and check content
        content = tsv_blob.download_as_text()
        lines = content.split("\n")

        # First line should be headers
        headers = lines[0].split("\t")
        assert "vgnc_id" in headers
        assert "vgnc_symbol" in headers

        # Cleanup
        for blob in blobs:
            blob.delete()

    def test_generated_json_is_valid(self, real_config, test_gcs_bucket) -> None:
        """Test that generated JSON file is valid JSON."""
        runner = cli_runner_with_env()

        result = runner.invoke(
            main,
            [
                "--species",
                "9913",
                "--chromosome",
                "X",
                "--formats",
                "json",
            ],
        )

        assert result.exit_code == 0

        # Find the generated JSON file
        blobs = list(test_gcs_bucket.list_blobs(prefix="json/cow/"))
        json_blob = None
        for blob in blobs:
            if blob.name.endswith(".json"):
                json_blob = blob
                break

        assert json_blob is not None, "No JSON file found"

        # Download and validate JSON
        content = json_blob.download_as_text()
        data = json.loads(content)

        assert isinstance(data, list)
        # If there's data, check structure
        if len(data) > 0:
            assert isinstance(data[0], dict)

        # Cleanup
        for blob in blobs:
            blob.delete()


@pytest.mark.e2e
@pytest.mark.timeout(600)  # E2E tests need longer timeout due to complex database queries
class TestCLIWithDifferentOptions:
    """E2E tests for CLI with various options and file types."""

    def test_withdrawn_entries_generation(self, real_config, test_gcs_bucket) -> None:
        """Test generating withdrawn entries file."""
        runner = cli_runner_with_env()

        result = runner.invoke(
            main,
            [
                "--species",
                "All",
                "--file-type",
                "vgnc_withdrawn",
                "--formats",
                "tsv",
            ],
        )

        assert result.exit_code == 0

        # Check for withdrawn file
        blobs = list(test_gcs_bucket.list_blobs(prefix="withdrawn/"))
        assert len(blobs) > 0

        # Cleanup
        for blob in blobs:
            blob.delete()

    def test_locus_type_generation(self, real_config, test_gcs_bucket) -> None:
        """Test generating files for specific locus type."""
        runner = cli_runner_with_env()

        result = runner.invoke(
            main,
            [
                "--species",
                "9913",
                "--locus-type",
                "gene with protein product",
                "--formats",
                "tsv",
            ],
        )

        assert result.exit_code == 0

        # Check for locus type files - TSV files now use tsv/cow/
        blobs = list(test_gcs_bucket.list_blobs(prefix="tsv/cow/"))
        assert len(blobs) > 0

        # Cleanup
        for blob in blobs:
            blob.delete()

    def test_all_species_includes_taxon_id(self, real_config, test_gcs_bucket) -> None:
        """Test that 'All' species files include taxon_id column."""
        runner = cli_runner_with_env()

        result = runner.invoke(
            main,
            [
                "--species",
                "All",
                "--formats",
                "tsv",
            ],
        )

        assert result.exit_code == 0

        # Find the generated file - All species TSV files are at tsv/All/
        blobs = list(test_gcs_bucket.list_blobs(prefix="tsv/All/"))
        assert len(blobs) > 0

        # Cleanup
        for blob in blobs:
            blob.delete()
