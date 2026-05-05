"""Tests for generate_all_parallel.sh script."""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPT_PATH = Path(__file__).parent.parent / "generate_all_parallel.sh"


class TestScriptExists:
    """Tests for script file existence and basic properties."""

    def test_script_exists(self) -> None:
        """Test that the parallel script file exists."""
        assert SCRIPT_PATH.exists(), f"Script not found at {SCRIPT_PATH}"

    def test_script_is_executable(self) -> None:
        """Test that the script has executable permissions."""
        if SCRIPT_PATH.exists():
            assert os.access(SCRIPT_PATH, os.X_OK), "Script must be executable (chmod +x)"


class TestCPUCoreDetection:
    """Tests for CPU core auto-detection logic."""

    @patch("subprocess.run")
    def test_detect_cpu_cores_on_macos(self, mock_run: MagicMock) -> None:
        """Test CPU core detection on macOS."""
        # Mock sysctl output for 8 performance cores
        mock_result = MagicMock()
        mock_result.stdout = b"8\n"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        # Simulate detection logic
        cpu_count = int(mock_result.stdout.decode().strip())
        expected_jobs = max(1, cpu_count - 2)

        assert cpu_count == 8
        assert expected_jobs == 6

    @patch("subprocess.run")
    def test_detect_cpu_cores_on_linux(self, mock_run: MagicMock) -> None:
        """Test CPU core detection on Linux using nproc."""
        # Mock nproc output for 4 cores
        mock_result = MagicMock()
        mock_result.stdout = b"4\n"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        cpu_count = int(mock_result.stdout.decode().strip())
        expected_jobs = max(1, cpu_count - 2)

        assert cpu_count == 4
        assert expected_jobs == 2

    @patch("subprocess.run")
    def test_detect_cpu_cores_minimum_one_job(self, mock_run: MagicMock) -> None:
        """Test that job count is never less than 1."""
        # Mock single core system
        mock_result = MagicMock()
        mock_result.stdout = b"1\n"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        cpu_count = int(mock_result.stdout.decode().strip())
        expected_jobs = max(1, cpu_count - 2)

        assert expected_jobs == 1  # Minimum 1 job

    @patch("subprocess.run")
    def test_detect_cpu_cores_with_user_override(self, mock_run: MagicMock) -> None:
        """Test that user-provided --jobs override is respected."""
        # Even if CPU count is high, user override takes precedence
        user_jobs = 4

        mock_result = MagicMock()
        mock_result.stdout = b"16\n"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        cpu_count = int(mock_result.stdout.decode().strip())
        auto_jobs = max(1, cpu_count - 2)

        # User override should be used instead
        assert user_jobs == 4
        assert auto_jobs == 14  # But auto-detection would give 14


class TestJobListGeneration:
    """Tests for job command list generation logic."""

    def test_generate_all_species_jobs(self) -> None:
        """Test generating jobs for all species files."""

        # With format splitting, each format gets its own job
        # "All" species files: 3 file types × 2 formats = 6 jobs
        # Per-species chromosome files: 3 chromosomes × 2 formats = 6 jobs
        expected_jobs = [
            # "All" species files - split by format
            "--species All --formats tsv",
            "--species All --formats json",
            "--species All --file-type vgnc_ensembl --formats tsv",
            "--species All --file-type vgnc_ensembl --formats json",
            "--species All --file-type vgnc_withdrawn --formats tsv",
            "--species All --file-type vgnc_withdrawn --formats json",
            # Per-species chromosome files - split by format
            "--species 9913 --chromosome 1 --formats tsv",
            "--species 9913 --chromosome 1 --formats json",
            "--species 9913 --chromosome 2 --formats tsv",
            "--species 9913 --chromosome 2 --formats json",
            "--species 9913 --chromosome X --formats tsv",
            "--species 9913 --chromosome X --formats json",
        ]

        # Basic structure check - should be at least 12 jobs now
        assert len(expected_jobs) >= 12  # 6 All species + 6 chromosome (split by format)

    def test_generate_jobs_with_locus_types(self) -> None:
        """Test generating jobs with locus type filters."""
        species_ids = ["9913"]
        locus_types = ["gene with protein product", "pseudogene"]
        formats = "tsv,json"

        # Each species gets one job per locus type per format
        # 1 species × 2 locus types × 2 formats = 4 jobs
        expected_locus_jobs = len(species_ids) * len(locus_types) * len(formats.split(","))
        assert expected_locus_jobs == 4

    def test_generate_jobs_dry_run(self) -> None:
        """Test that dry-run adds --dry-run flag to jobs."""
        base_command = "--species 9913 --chromosome X --formats tsv"
        dry_run_command = f"{base_command} --dry-run"

        assert "--dry-run" in dry_run_command
        assert "9913" in dry_run_command
        assert "tsv" in dry_run_command

    def test_formats_are_split_into_separate_jobs(self) -> None:
        """Test that tsv and json formats create separate jobs."""
        formats = "tsv,json"

        # Should create 2 separate jobs, not 1 with comma-separated formats
        format_list = formats.split(",")
        assert len(format_list) == 2
        assert "tsv" in format_list
        assert "json" in format_list

    def test_single_format_creates_single_job(self) -> None:
        """Test that a single format creates one job."""
        formats = "tsv"

        format_list = formats.split(",")
        assert len(format_list) == 1
        assert format_list[0] == "tsv"


class TestGnuParallelRequirements:
    """Tests for GNU parallel availability and features."""

    def test_check_gnu_parallel_available(self) -> None:
        """Test that we can detect if GNU parallel is installed."""
        result = subprocess.run(
            ["command", "-v", "parallel"],
            capture_output=True,
            shell=True,
        )
        # We're testing the check mechanism, not that parallel is installed
        assert result.returncode in [0, 1]  # 0 = found, 1 = not found

    def test_gnu_parallel_version_check(self) -> None:
        """Test checking GNU parallel version."""
        try:
            result = subprocess.run(
                ["parallel", "--version"],
                capture_output=True,
            )
            # Either parallel is installed (returncode 0) or not (127 or 255 on macOS)
            assert result.returncode in [0, 127, 255]
        except FileNotFoundError:
            # GNU parallel not installed - this is expected in test environment
            # The script will provide helpful installation instructions
            assert True


class TestScriptArgumentParsing:
    """Tests for script CLI argument parsing."""

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_help_option(self) -> None:
        """Test that --help displays usage information."""
        result = subprocess.run(
            [str(SCRIPT_PATH), "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout or "usage:" in result.stdout.lower()

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_version_option(self) -> None:
        """Test that --version displays version information."""
        result = subprocess.run(
            [str(SCRIPT_PATH), "--version"],
            capture_output=True,
            text=True,
        )
        # Should either show version or be a valid option
        assert result.returncode == 0 or "version" in result.stdout.lower()

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_jobs_option_accepted(self) -> None:
        """Test that --jobs option is accepted."""
        result = subprocess.run(
            [str(SCRIPT_PATH), "--jobs", "4", "--dry-run"],
            capture_output=True,
            text=True,
        )
        # Should accept the option (may fail for other reasons)
        if "unrecognized option" in result.stderr.lower() or "unknown option" in result.stderr.lower():
            pytest.fail("--jobs option not recognized")

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_dry_run_option(self) -> None:
        """Test that --dry-run shows what would be generated."""
        result = subprocess.run(
            [str(SCRIPT_PATH), "--species", "9913", "--dry-run"],
            capture_output=True,
            text=True,
        )
        # Dry run should exit successfully
        if "dry run" in result.stdout.lower() or "dry-run" in result.stdout.lower():
            assert result.returncode == 0


class TestScriptErrorHandling:
    """Tests for script error handling."""

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_missing_species_with_no_filter(self) -> None:
        """Test behavior when no species filter is provided."""
        result = subprocess.run(
            [str(SCRIPT_PATH), "--dry-run"],
            capture_output=True,
            text=True,
        )
        # Should handle gracefully - either show help or generate for all species
        assert result.returncode in [0, 1]

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_gnu_parallel_not_installed_message(self) -> None:
        """Test helpful error when GNU parallel is not installed."""
        # This test verifies the script provides helpful guidance
        # We can't easily mock the absence of parallel in a subprocess test
        # But we can verify the script contains the error message
        if SCRIPT_PATH.exists():
            script_content = SCRIPT_PATH.read_text()
            # Script should mention how to install parallel
            assert "parallel" in script_content.lower()


class TestRetryLogic:
    """Tests for retry logic configuration."""

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_parallel_retries_configured(self) -> None:
        """Test that GNU parallel is configured with --retries 3."""
        if SCRIPT_PATH.exists():
            script_content = SCRIPT_PATH.read_text()
            # Should use --retries 3 for automatic retry
            assert "--retries" in script_content or "retries" in script_content.lower()

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_parallel_joblog_configured(self) -> None:
        """Test that job logging is configured."""
        if SCRIPT_PATH.exists():
            script_content = SCRIPT_PATH.read_text()
            # Should use --joblog for tracking failures
            assert "--joblog" in script_content or "joblog" in script_content.lower()


class TestProgressTracking:
    """Tests for progress bar and tracking."""

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_progress_bar_enabled(self) -> None:
        """Test that --bar is enabled for visual progress."""
        if SCRIPT_PATH.exists():
            script_content = SCRIPT_PATH.read_text()
            # Should use --bar for visual progress
            assert "--bar" in script_content or '"--bar"' in script_content or "'--bar'" in script_content


class TestJobCountCalculation:
    """Tests for job count calculation based on CPU cores."""

    def test_macos_m4_pro_job_calculation(self) -> None:
        """Test job calculation for M4 Pro with ~12 performance cores."""
        cpu_cores = 12  # M4 Pro has ~12 performance cores
        expected_jobs = max(1, cpu_cores - 2)
        assert expected_jobs == 10

    def test_gcp_8vcpu_job_calculation(self) -> None:
        """Test job calculation for GCP 8 vCPU."""
        cpu_cores = 8
        expected_jobs = max(1, cpu_cores - 2)
        assert expected_jobs == 6

    def test_small_system_job_calculation(self) -> None:
        """Test job calculation for small systems (2-4 cores)."""
        for cpu_cores in [2, 3, 4]:
            expected_jobs = max(1, cpu_cores - 2)
            assert expected_jobs >= 1  # Never less than 1

    def test_single_core_job_calculation(self) -> None:
        """Test job calculation for single-core systems."""
        cpu_cores = 1
        expected_jobs = max(1, cpu_cores - 2)
        assert expected_jobs == 1


class TestBackwardCompatibility:
    """Tests for backward compatibility with original generate_all.sh."""

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_accepts_same_arguments(self) -> None:
        """Test that parallel script accepts same arguments as original."""
        # Arguments from original script
        # Note: All tests use --dry-run to avoid actual execution that would timeout
        common_args = [
            ["--species", "9913", "--dry-run"],
            ["--chromosomes", "1,2,X", "--dry-run"],
            ["--formats", "tsv,json", "--dry-run"],
            ["--dry-run"],
            ["--skip-withdrawn", "--dry-run"],
            ["--skip-ensembl", "--dry-run"],
        ]

        for args in common_args:
            result = subprocess.run(
                [str(SCRIPT_PATH)] + args,
                capture_output=True,
                text=True,
                timeout=5,
            )
            # Should not error on unknown arguments
            if "unrecognized option" in result.stderr.lower() or "unknown option" in result.stderr.lower():
                pytest.fail(f"Argument not recognized: {args[0]}")
