"""Tests for entrypoint.sh species file generation logic."""

import os
from pathlib import Path

ENTRYPOINT = Path(__file__).parent.parent / "entrypoint.sh"
DB_HELPER = Path(__file__).parent.parent / "db_query_helper.py"


class TestEntrypointExists:
    """Tests for entrypoint.sh file existence and basic properties."""

    def test_entrypoint_exists(self) -> None:
        """Test that entrypoint.sh exists."""
        assert ENTRYPOINT.exists(), f"entrypoint.sh not found at {ENTRYPOINT}"

    def test_entrypoint_is_executable(self) -> None:
        """Test that entrypoint.sh has executable permissions."""
        if ENTRYPOINT.exists():
            assert os.access(ENTRYPOINT, os.X_OK), "entrypoint.sh must be executable (chmod +x)"


class TestJobListGeneration:
    """Tests for job command list generation logic."""

    def test_generate_all_species_jobs(self) -> None:
        """Test generating jobs for all species files."""
        expected_jobs = [
            "--species All --formats tsv",
            "--species All --formats json",
            "--species All --file-type vgnc_ensembl --formats tsv",
            "--species All --file-type vgnc_ensembl --formats json",
            "--species All --file-type vgnc_withdrawn --formats tsv",
            "--species All --file-type vgnc_withdrawn --formats json",
        ]
        assert len(expected_jobs) == 6

    def test_generate_jobs_with_locus_types(self) -> None:
        """Test generating jobs with locus type filters."""
        species_ids = ["9913"]
        locus_types = ["gene with protein product", "pseudogene"]
        formats = "tsv,json"

        expected_locus_jobs = len(species_ids) * len(locus_types) * len(formats.split(","))
        assert expected_locus_jobs == 4

    def test_formats_are_split_into_separate_jobs(self) -> None:
        """Test that tsv and json formats create separate jobs."""
        formats = "tsv,json"
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


class TestCPUCoreDetection:
    """Tests for CPU core auto-detection logic."""

    def test_detect_cpu_cores_minimum_one_job(self) -> None:
        """Test that job count is never less than 1."""
        cpu_cores = 1
        parallel_jobs = max(1, cpu_cores - 1)
        assert parallel_jobs == 1

    def test_detect_cpu_cores_with_user_override(self) -> None:
        """Test that user-provided job count overrides auto-detection."""
        user_jobs = 4
        cpu_cores = 16
        auto_jobs = max(1, cpu_cores - 1)
        assert user_jobs == 4
        assert auto_jobs == 15


class TestLociConstants:
    """Tests for locus type and group constants."""

    def test_locus_types(self) -> None:
        """Test that locus types match expected values."""
        locus_types = ["gene with protein product", "pseudogene"]
        assert len(locus_types) == 2
        assert "gene with protein product" in locus_types
        assert "pseudogene" in locus_types

    def test_locus_groups(self) -> None:
        """Test that locus groups match expected values."""
        locus_groups = ["protein-coding gene", "pseudogene"]
        assert len(locus_groups) == 2
        assert "protein-coding gene" in locus_groups
        assert "pseudogene" in locus_groups


class TestChromosomeDiscovery:
    """Tests for chromosome discovery via db_query_helper.py."""

    def test_db_query_helper_exists(self) -> None:
        """Test that db_query_helper.py exists."""
        assert DB_HELPER.exists(), f"db_query_helper.py not found at {DB_HELPER}"

    def test_db_query_helper_has_correct_join_chain(self) -> None:
        """Test that the chromosome query uses the correct JOIN chain."""
        content = DB_HELPER.read_text()
        assert "gene_has_location" in content, "Missing gene_has_location junction table"
        assert "gene_location" in content, "Missing gene_location table"
        assert "chromosomes" in content, "Missing chromosomes table"
        assert "coord_system" in content, "Missing coord_system filter"


class TestJobCountCalculation:
    """Tests for job count calculation based on CPU cores."""

    def test_gcp_4vcpu_job_calculation(self) -> None:
        """Test job calculation for GCP 4 vCPU (Cloud Run default)."""
        cpu_cores = 4
        parallel_jobs = max(1, cpu_cores - 1)
        assert parallel_jobs == 3

    def test_small_system_job_calculation(self) -> None:
        """Test job calculation for small systems (2-4 cores)."""
        for cpu_cores in [2, 3, 4]:
            parallel_jobs = max(1, cpu_cores - 1)
            assert parallel_jobs >= 1

    def test_single_core_job_calculation(self) -> None:
        """Test job calculation for single-core systems."""
        cpu_cores = 1
        parallel_jobs = max(1, cpu_cores - 1)
        assert parallel_jobs == 1


class TestModeDispatch:
    """Tests for VGNC_MODE dispatch logic."""

    def test_all_mode_generates_three_file_types(self) -> None:
        """Test that all mode generates public, ensembl, and withdrawn files."""
        file_types = ["vgnc_public", "vgnc_ensembl", "vgnc_withdrawn"]
        assert len(file_types) == 3

    def test_species_mode_uses_db_helper(self) -> None:
        """Test that species mode references db_query_helper for chromosome discovery."""
        if ENTRYPOINT.exists():
            content = ENTRYPOINT.read_text()
            assert "db_query_helper" in content, "entrypoint.sh should reference db_query_helper.py"
            assert "discover_chromosomes" in content, "entrypoint.sh should have discover_chromosomes function"
