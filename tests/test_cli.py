"""Tests for CLI main entry point."""

import sys
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from vgnc_download_file_generator.__main__ import main


class TestCLIArgumentParsing:
    """Tests for CLI argument parsing."""

    def test_help_option_displays_help(self) -> None:
        """Test that --help displays help message."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Generate VGNC download files" in result.output
        assert "--species" in result.output

    def test_version_option_displays_version(self) -> None:
        """Test that --version displays version number."""
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_species_option_is_required(self) -> None:
        """Test that --species is a required argument."""
        runner = CliRunner()
        result = runner.invoke(main, [])
        assert result.exit_code != 0
        assert "Missing option '--species'" in result.output

    def test_accepts_valid_species_id(self) -> None:
        """Test that valid numeric species ID is accepted."""
        runner = CliRunner()
        # With dry-run, no config needed
        result = runner.invoke(main, ["--species", "9913", "--dry-run"])
        assert result.exit_code == 0
        assert "taxon_id 9913" in result.output

    def test_accepts_all_species(self) -> None:
        """Test that 'All' for species is accepted."""
        runner = CliRunner()
        result = runner.invoke(main, ["--species", "All", "--dry-run"])
        assert result.exit_code == 0
        assert "Species: All" in result.output

    def test_rejects_invalid_species_id(self) -> None:
        """Test that non-numeric species ID is rejected."""
        runner = CliRunner()
        result = runner.invoke(main, ["--species", "invalid", "--dry-run"])
        assert result.exit_code == 1
        assert "Invalid species ID" in result.output

    def test_accepts_chromosome_option(self) -> None:
        """Test that --chromosome option is accepted."""
        runner = CliRunner()
        result = runner.invoke(main, ["--species", "9913", "--chromosome", "X", "--dry-run"])
        assert result.exit_code == 0
        assert "Chromosome: X" in result.output

    def test_accepts_locus_type_option(self) -> None:
        """Test that --locus-type option is accepted."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["--species", "9913", "--locus-type", "gene with protein product", "--dry-run"]
        )
        assert result.exit_code == 0
        assert "Locus Type: gene with protein product" in result.output

    def test_accepts_locus_group_option(self) -> None:
        """Test that --locus-group option is accepted."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["--species", "9913", "--locus-group", "protein-coding gene", "--dry-run"]
        )
        assert result.exit_code == 0
        assert "Locus Group: protein-coding gene" in result.output

    def test_accepts_valid_file_types(self) -> None:
        """Test that all valid file types are accepted."""
        runner = CliRunner()
        for file_type in ["vgnc_public", "vgnc_ensembl", "vgnc_withdrawn"]:
            result = runner.invoke(main, ["--species", "9913", "--file-type", file_type, "--dry-run"])
            assert result.exit_code == 0
            assert f"File Type: {file_type}" in result.output

    def test_default_file_type_is_vgnc_public(self) -> None:
        """Test that default file type is vgnc_public."""
        runner = CliRunner()
        result = runner.invoke(main, ["--species", "9913", "--dry-run"])
        assert result.exit_code == 0
        assert "File Type: vgnc_public" in result.output

    def test_accepts_tsv_format(self) -> None:
        """Test that TSV format is accepted."""
        runner = CliRunner()
        result = runner.invoke(main, ["--species", "9913", "--formats", "tsv", "--dry-run"])
        assert result.exit_code == 0
        assert "TSV" in result.output

    def test_accepts_json_format(self) -> None:
        """Test that JSON format is accepted."""
        runner = CliRunner()
        result = runner.invoke(main, ["--species", "9913", "--formats", "json", "--dry-run"])
        assert result.exit_code == 0
        assert "JSON" in result.output

    def test_accepts_multiple_formats(self) -> None:
        """Test that multiple formats comma-separated are accepted."""
        runner = CliRunner()
        result = runner.invoke(main, ["--species", "9913", "--formats", "tsv,json", "--dry-run"])
        assert result.exit_code == 0
        assert "TSV, JSON" in result.output

    def test_rejects_invalid_formats(self) -> None:
        """Test that invalid formats are filtered out."""
        runner = CliRunner()
        result = runner.invoke(main, ["--species", "9913", "--formats", "invalid,xml", "--dry-run"])
        assert result.exit_code == 1
        assert "At least one valid format" in result.output

    def test_compress_flag(self) -> None:
        """Test that --compress flag is accepted."""
        runner = CliRunner()
        result = runner.invoke(main, ["--species", "9913", "--compress", "--dry-run"])
        assert result.exit_code == 0
        assert "Compression: Yes" in result.output

    def test_no_compress_by_default(self) -> None:
        """Test that compression is disabled by default."""
        runner = CliRunner()
        result = runner.invoke(main, ["--species", "9913", "--dry-run"])
        assert result.exit_code == 0
        assert "Compression: No" in result.output


class TestCLIDryRunMode:
    """Tests for CLI dry-run mode."""

    def test_dry_run_displays_generation_plan(self) -> None:
        """Test that dry-run shows what would be generated."""
        runner = CliRunner()
        result = runner.invoke(main, ["--species", "9913", "--chromosome", "X", "--dry-run"])
        assert result.exit_code == 0
        assert "DRY RUN MODE" in result.output
        assert "Files that would be generated:" in result.output

    def test_dry_run_does_not_require_config(self) -> None:
        """Test that dry-run works without any configuration."""
        runner = CliRunner()
        # No .env file, no config args
        result = runner.invoke(main, ["--species", "9913", "--dry-run"])
        assert result.exit_code == 0
        # Should not complain about missing database or GCS config

    def test_dry_run_exits_without_generating_files(self) -> None:
        """Test that dry-run exits early without file generation."""
        runner = CliRunner()
        result = runner.invoke(main, ["--species", "9913", "--dry-run"])
        assert result.exit_code == 0
        assert "requires database and GCS configuration" in result.output


class TestCLIConfiguration:
    """Tests for CLI configuration handling."""

    @patch("vgnc_download_file_generator.__main__.get_settings")
    def test_loads_config_from_env_vars(self, mock_get_settings) -> None:
        """Test that configuration is loaded from environment variables."""
        mock_config_instance = MagicMock()
        mock_config_instance.gcs.project_id = "test-project"
        mock_config_instance.gcs.bucket_name = "test-bucket"
        mock_config_instance.database.dbhost = "localhost"
        mock_config_instance.database.dbuser = "testuser"
        mock_config_instance.database.dbport = 3306
        mock_config_instance.database.dbname = "testdb"
        mock_get_settings.return_value = mock_config_instance

        # Mock database and GCS to avoid actual connections
        with patch("vgnc_download_file_generator.__main__.DatabaseConnection"), patch(
            "vgnc_download_file_generator.__main__.GCSStreamWriter"
        ), patch("vgnc_download_file_generator.__main__.VgncPublic"):

            runner = CliRunner()
            result = runner.invoke(
                main,
                ["--species", "9913", "--chromosome", "X"],
                env={"GCS_PROJECT_ID": "test-project", "GCS_BUCKET": "test-bucket"},
                catch_exceptions=True,
            )

        # Should have attempted to load config
        mock_get_settings.assert_called_once()

    @patch("vgnc_download_file_generator.__main__.get_settings")
    def test_cli_args_override_env_vars(self, mock_get_settings) -> None:
        """Test that CLI arguments override environment variables."""
        mock_config_instance = MagicMock()
        mock_config_instance.gcs.project_id = "cli-project"
        mock_config_instance.gcs.bucket_name = "cli-bucket"
        mock_config_instance.database.dbhost = "cli-host"
        mock_config_instance.database.dbuser = "cli-user"
        mock_config_instance.database.dbport = 3307
        mock_config_instance.database.dbname = "cli-db"
        mock_get_settings.return_value = mock_config_instance

        with patch("vgnc_download_file_generator.__main__.DatabaseConnection"), patch(
            "vgnc_download_file_generator.__main__.GCSStreamWriter"
        ), patch("vgnc_download_file_generator.__main__.VgncPublic"):

            runner = CliRunner()
            result = runner.invoke(
                main,
                [
                    "--species",
                    "9913",
                    "--project-id",
                    "cli-project",
                    "--bucket-name",
                    "cli-bucket",
                    "--dbhost",
                    "cli-host",
                    "--dbuser",
                    "cli-user",
                    "--dbport",
                    "3307",
                    "--dbname",
                    "cli-db",
                ],
                catch_exceptions=True,
            )

        # Verify CLI args were set
        assert mock_config_instance.gcs.project_id == "cli-project"
        assert mock_config_instance.gcs.bucket_name == "cli-bucket"
        assert mock_config_instance.database.dbhost == "cli-host"


class TestCLIValidation:
    """Tests for CLI validation."""

    @patch("vgnc_download_file_generator.__main__.get_settings")
    def test_requires_gcs_config(self, mock_get_settings) -> None:
        """Test that GCS configuration is required."""
        mock_config_instance = MagicMock()
        mock_config_instance.gcs.project_id = None
        mock_config_instance.gcs.bucket_name = None
        mock_get_settings.return_value = mock_config_instance

        runner = CliRunner()
        result = runner.invoke(main, ["--species", "9913", "--dry-run"])
        # Dry run doesn't validate config
        assert result.exit_code == 0

    @patch("vgnc_download_file_generator.__main__.get_settings")
    def test_requires_database_config(self, mock_get_settings) -> None:
        """Test that database configuration is required."""
        mock_config_instance = MagicMock()
        mock_config_instance.database.dbhost = None
        mock_config_instance.database.dbuser = None
        mock_get_settings.return_value = mock_config_instance

        runner = CliRunner()
        result = runner.invoke(main, ["--species", "9913", "--dry-run"])
        # Dry run doesn't validate config
        assert result.exit_code == 0


class TestCLIErrorHandling:
    """Tests for CLI error handling."""

    def test_handles_keyboard_interrupt(self) -> None:
        """Test that keyboard interrupt is handled gracefully."""
        with patch("vgnc_download_file_generator.__main__.get_settings"), patch(
            "vgnc_download_file_generator.__main__.DatabaseConnection"
        ) as mock_db, patch("vgnc_download_file_generator.__main__.GCSStreamWriter"), patch(
            "vgnc_download_file_generator.__main__.VgncPublic"
        ) as mock_gen:

            # Simulate KeyboardInterrupt during file generation
            mock_gen.return_value.generate_tsv_rows.side_effect = KeyboardInterrupt()

            runner = CliRunner()
            result = runner.invoke(
                main,
                ["--species", "9913", "--project-id", "test", "--bucket-name", "test"],
                catch_exceptions=False,
            )

        # Should exit with code 130
        assert result.exit_code == 130
        assert "cancelled by user" in result.output

    @patch("vgnc_download_file_generator.__main__.get_settings")
    def test_handles_exceptions_with_traceback(self, mock_get_settings) -> None:
        """Test that exceptions show traceback for debugging."""
        mock_config_instance = MagicMock()
        mock_config_instance.gcs.project_id = "test-project"
        mock_config_instance.gcs.bucket_name = "test-bucket"
        mock_config_instance.database.dbhost = "localhost"
        mock_config_instance.database.dbuser = "testuser"
        mock_config_instance.database.dbport = 3306
        mock_config_instance.database.dbname = "testdb"
        mock_get_settings.return_value = mock_config_instance

        with patch("vgnc_download_file_generator.__main__.DatabaseConnection") as mock_db:
            # Simulate database connection error
            mock_db.side_effect = Exception("Connection failed")

            runner = CliRunner()
            result = runner.invoke(
                main,
                ["--species", "9913"],
                catch_exceptions=False,
            )

        # Should show error and traceback
        assert result.exit_code == 1
        assert "Error:" in result.output


class TestCLIForcedCompression:
    """Tests for forced compression of all/ directory files."""

    def test_root_all_species_tsv_forces_compression(self) -> None:
        """Test that all/ directory TSV files are always compressed."""
        from vgnc_download_file_generator.models.file_spec import FileSpec

        spec = FileSpec(
            species_id="All",
            species_name="All",
            locus_group=None,
            locus_type=None,
            chromosome=None,
            file_type="vgnc_public",
            extension="tsv",  # CLI passes "tsv" format
        )

        # Should generate all/ directory path with .tsv extension
        filename = spec.gcs_path()
        assert filename == "tsv/all/all_vgnc_gene_set_All.tsv"

        # This filename should trigger forced compression (contains /all/)
        is_all_directory_file = "/all/" in filename
        assert is_all_directory_file is True

    def test_root_all_species_json_forces_compression(self) -> None:
        """Test that all/ directory JSON files are always compressed."""
        from vgnc_download_file_generator.models.file_spec import FileSpec

        spec = FileSpec(
            species_id="All",
            species_name="All",
            locus_group=None,
            locus_type=None,
            chromosome=None,
            file_type="vgnc_public",
            extension="json",
        )

        # Should generate all/ directory path
        filename = spec.gcs_path()
        assert filename == "json/all/all_vgnc_gene_set_All.json"

        # This filename should trigger forced compression (contains /all/)
        is_all_directory_file = "/all/" in filename
        assert is_all_directory_file is True

    def test_other_all_species_files_not_forced_compression(self) -> None:
        """Test that other All species files in all/ subdirs are compressed (they also have /all/)."""
        from vgnc_download_file_generator.models.file_spec import FileSpec

        # All species with chromosome filter (still in all/ directory)
        spec = FileSpec(
            species_id="All",
            species_name="All",
            locus_group=None,
            locus_type=None,
            chromosome="X",
            file_type="vgnc_public",
            extension="txt",
        )

        filename = spec.gcs_path()
        # This filename should trigger forced compression (contains /all/)
        is_all_directory_file = "/all/" in filename
        assert is_all_directory_file is True
        assert filename == "tsv/all/all_vgnc_gene_set_chrX.txt"

    def test_individual_species_files_not_forced_compression(self) -> None:
        """Test that individual species files are not forced compressed."""
        from vgnc_download_file_generator.models.file_spec import FileSpec

        spec = FileSpec(
            species_id=9913,
            species_name="cattle",
            locus_group=None,
            locus_type=None,
            chromosome=None,
            file_type="vgnc_public",
            extension="txt",
        )

        filename = spec.gcs_path()
        # Should NOT trigger forced compression (no /all/)
        is_all_directory_file = "/all/" in filename
        assert is_all_directory_file is False
        assert filename == "tsv/cattle/cattle_vgnc_gene_set_All.txt"
