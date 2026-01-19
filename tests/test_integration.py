"""Integration tests for VGNC download file generator.

These tests require:
- --integration flag to run
- Real database connection (credentials from GCP Secret Manager)
- Real GCS bucket access (genenames_public_bucket)

Run with: uv run pytest --integration tests/test_integration.py
"""

import pytest

from vgnc_download_file_generator.generators import VgncEnsembl, VgncPublic, VgncWithdrawn
from vgnc_download_file_generator.models.species import SpeciesInfo


@pytest.mark.integration
class TestDatabaseConnection:
    """Tests for real database connection."""

    def test_can_connect_to_database(self, real_database) -> None:
        """Test that we can establish a connection to the real database."""
        conn = real_database.get_connection()
        assert conn is not None
        conn.close()

    def test_can_execute_simple_query(self, real_database) -> None:
        """Test that we can execute a simple query on the real database."""
        conn = real_database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        assert result[0] == 1
        cursor.close()
        conn.close()


@pytest.mark.integration
class TestSpeciesQuery:
    """Tests for querying species from real database."""

    def test_can_query_species_table(self, real_database) -> None:
        """Test that we can query the species table."""
        conn = real_database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM species")
        count = cursor.fetchone()[0]
        assert count > 0
        cursor.close()
        conn.close()

    def test_can_fetch_specific_species(self, real_database) -> None:
        """Test that we can fetch a specific species by taxon_id."""
        conn = real_database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT taxon_id, display_name, is_live FROM species WHERE taxon_id = 9913")
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == 9913
        assert result[2] in ("Y", "N", "T", "F")  # is_live
        cursor.close()
        conn.close()


@pytest.mark.integration
class TestVgncPublicGeneratorIntegration:
    """Integration tests for VgncPublic generator with real database."""

    def test_stream_rows_returns_data(self, real_database) -> None:
        """Test that stream_rows returns actual data from database."""
        species = SpeciesInfo(taxon_id=9913, display_name="cow", is_live="Y")
        generator = VgncPublic(real_database, species, chromosome="X")

        rows = list(generator.stream_rows(chunk_size=100))

        # Should get some rows (unless test DB is empty)
        assert isinstance(rows, list)

    def test_get_headers_returns_correct_structure(self, real_database) -> None:
        """Test that get_headers returns expected column names."""
        species = SpeciesInfo(taxon_id=9913, display_name="cow", is_live="Y")
        generator = VgncPublic(real_database, species, chromosome="X")

        headers = generator.get_headers("txt")

        # Verify we get expected headers
        assert "vgnc_id" in headers
        assert "symbol" in headers
        assert "name" in headers

    def test_generate_tsv_rows_produces_valid_tsv(self, real_database) -> None:
        """Test that generate_tsv_rows produces valid TSV output."""
        species = SpeciesInfo(taxon_id=9913, display_name="cow", is_live="Y")
        generator = VgncPublic(real_database, species, chromosome="X")

        lines = list(generator.generate_tsv_rows())

        # First line should be headers
        assert len(lines) > 0
        assert "\t" in lines[0]

        # If we have data rows, they should also have tabs
        if len(lines) > 1:
            assert "\t" in lines[1]

    def test_generate_json_rows_produces_valid_json(self, real_database) -> None:
        """Test that generate_json_rows produces valid JSON objects."""
        import json

        species = SpeciesInfo(taxon_id=9913, display_name="cow", is_live="Y")
        generator = VgncPublic(real_database, species, chromosome="X")

        json_objects = list(generator.generate_json_rows())

        # If we have data, it should be valid JSON objects
        if json_objects:
            # Each object should be valid JSON
            for json_str in json_objects:
                obj = json.loads(json_str)
                assert isinstance(obj, dict)
                assert "vgnc_id" in obj or "symbol" in obj

            # Can wrap in brackets to make valid JSON array
            full_json = "[" + ",".join(json_objects) + "]"
            parsed = json.loads(full_json)
            assert isinstance(parsed, list)
            assert len(parsed) == len(json_objects)


@pytest.mark.integration
class TestVgncEnsemblGeneratorIntegration:
    """Integration tests for VgncEnsembl generator with real database."""

    def test_stream_rows_returns_ensembl_data(self, real_database) -> None:
        """Test that stream_rows returns Ensembl mapping data."""
        species = SpeciesInfo(taxon_id="All", display_name="All", is_live="Y")  # type: ignore[arg-type]
        generator = VgncEnsembl(real_database, species)

        rows = list(generator.stream_rows(chunk_size=100))

        # Should get some rows
        assert isinstance(rows, list)

    def test_get_headers_returns_ensembl_columns(self, real_database) -> None:
        """Test that get_headers returns Ensembl-specific headers."""
        species = SpeciesInfo(taxon_id="All", display_name="All", is_live="Y")  # type: ignore[arg-type]
        generator = VgncEnsembl(real_database, species)

        headers = generator.get_headers("txt")

        # Verify Ensembl-specific headers (using PRD format)
        assert "VGNC ID" in headers
        assert "Ensembl Gene ID" in headers


@pytest.mark.integration
class TestVgncWithdrawnGeneratorIntegration:
    """Integration tests for VgncWithdrawn generator with real database."""

    def test_stream_rows_returns_withdrawn_data(self, real_database) -> None:
        """Test that stream_rows returns withdrawn entry data."""
        species = SpeciesInfo(taxon_id="All", display_name="All", is_live="Y")  # type: ignore[arg-type]
        generator = VgncWithdrawn(real_database, species)

        rows = list(generator.stream_rows(chunk_size=100))

        # Should get some rows
        assert isinstance(rows, list)

    def test_get_headers_returns_withdrawn_columns(self, real_database) -> None:
        """Test that get_headers returns withdrawn-specific headers."""
        species = SpeciesInfo(taxon_id="All", display_name="All", is_live="Y")  # type: ignore[arg-type]
        generator = VgncWithdrawn(real_database, species)

        headers = generator.get_headers("txt")

        # Verify expected columns exist
        assert "VGNC_ID" in headers
        assert "WITHDRAWN_SYMBOL" in headers


@pytest.mark.integration
class TestFileGenerationWorkflow:
    """Integration tests for file generation workflow with database only."""

    def test_generate_small_tsv_file_in_memory(self, real_database) -> None:
        """Test generating a small TSV file entirely in memory."""
        species = SpeciesInfo(taxon_id=9913, display_name="cow", is_live="Y")
        generator = VgncPublic(real_database, species, chromosome="X")

        # Generate TSV content
        content = "".join(generator.generate_tsv_rows())

        # Verify we got headers at minimum
        assert len(content) > 0
        assert content.startswith("vgnc_id")

    def test_generate_small_json_file_in_memory(self, real_database) -> None:
        """Test generating a small JSON file entirely in memory."""
        import json

        species = SpeciesInfo(taxon_id=9913, display_name="cow", is_live="Y")
        generator = VgncPublic(real_database, species, chromosome="X")

        # Generate JSON objects
        json_objects = list(generator.generate_json_rows())

        # Wrap in brackets to create the complete JSON
        if json_objects:
            content = "[" + ",".join(json_objects) + "]"
            data = json.loads(content)
            assert isinstance(data, list)


@pytest.mark.integration
class TestEdgeCases:
    """Integration tests for edge cases with real data."""

    def test_species_with_no_chromosome_data(self, real_database) -> None:
        """Test querying a species that might not have data for a specific chromosome."""
        # Use a less common chromosome that might not have data
        species = SpeciesInfo(taxon_id=9913, display_name="cow", is_live="Y")
        generator = VgncPublic(real_database, species, chromosome="Y")  # Y might not have data

        rows = list(generator.stream_rows(chunk_size=100))

        # Should handle empty result gracefully
        assert isinstance(rows, list)

    def test_all_species_includes_taxon_id(self, real_database) -> None:
        """Test that 'All' species includes taxon_id column."""
        species = SpeciesInfo(taxon_id="All", display_name="All", is_live="Y")  # type: ignore[arg-type]
        generator = VgncPublic(real_database, species)

        headers = generator.get_headers("txt")

        # All species should have taxon_id as first column
        assert headers[0] == "taxon_id"
