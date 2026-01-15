"""Tests for VgncEnsembl generator."""

from unittest.mock import MagicMock

from vgnc_download_file_generator.database.connection import DatabaseConnection
from vgnc_download_file_generator.generators.vgnc_ensembl import VgncEnsembl
from vgnc_download_file_generator.models.species import SpeciesInfo


class TestVgncEnsemblGetHeaders:
    """Tests for VgncEnsembl.get_headers() method."""

    def test_returns_ensembl_specific_headers(self) -> None:
        """Test that get_headers() returns correct Ensembl headers."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncEnsembl(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        headers = generator.get_headers("txt")

        # Verify all expected headers are present
        expected_headers = [
            "VGNC ID",
            "Approved Symbol",
            "Approved Name",
            "Previous Symbols",
            "Synonyms",
            "Entrez Gene ID",
            "Refseq IDs",
            "Entrez Gene ID(supplied by NCBI)",
            "RefSeq(supplied by NCBI)",
            "Ensembl Gene ID",
            "Uniprot ID(supplied by UniProt)",
            "Locus Specific Databases",
        ]

        assert headers == expected_headers

    def test_headers_in_correct_order(self) -> None:
        """Test that headers are in the specified order."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncEnsembl(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        headers = generator.get_headers("txt")

        # Verify exact order
        assert headers[0] == "VGNC ID"
        assert headers[5] == "Entrez Gene ID"
        assert headers[9] == "Ensembl Gene ID"
        assert headers[-1] == "Locus Specific Databases"


class TestVgncEnsemblStreamRows:
    """Tests for VgncEnsembl.stream_rows() method."""

    def test_filters_by_approved_status(self) -> None:
        """Test that stream_rows filters to only 'Approved' status."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncEnsembl(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock the streaming cursor
        mock_cursor = MagicMock()
        mock_cursor.fetchmany.side_effect = [[], []]
        db.get_streaming_cursor.return_value = mock_cursor

        # Stream rows
        list(generator.stream_rows())

        # Verify cursor.execute was called
        mock_cursor.execute.assert_called_once()
        # The query should filter by Approved status
        call_args = mock_cursor.execute.call_args
        query = call_args[0][0]
        # Query should have Approved filter
        assert "Approved" in str(query) or "status" in str(query).lower()

    def test_applies_species_filter_to_query(self) -> None:
        """Test that species taxon_id filter is applied to the query."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncEnsembl(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock the streaming cursor
        mock_cursor = MagicMock()
        mock_cursor.fetchmany.side_effect = [[], []]
        db.get_streaming_cursor.return_value = mock_cursor

        # Stream rows
        list(generator.stream_rows())

        # Verify cursor.execute was called
        mock_cursor.execute.assert_called_once()
        # The query should contain the taxon_id filter
        call_args = mock_cursor.execute.call_args
        query = call_args[0][0]
        # Query should have taxon_id filter
        assert "9593" in str(query) or "taxon_id" in str(query).lower()


class TestVgncEnsemblGenerateTsv:
    """Tests for VgncEnsembl TSV generation."""

    def test_generate_tsv_rows_writes_headers(self) -> None:
        """Test that generate_tsv_rows() yields header row first."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncEnsembl(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock stream_rows to return empty
        generator.stream_rows = lambda chunk_size=5000: iter([])  # type: ignore[method-assign]  # noqa: ARG005

        # Generate TSV rows
        tsv_lines = list(generator.generate_tsv_rows())

        # Should have at least headers
        assert len(tsv_lines) >= 1

        # First line should be headers
        headers_line = tsv_lines[0]
        assert "VGNC ID" in headers_line
        assert "Ensembl Gene ID" in headers_line
        assert "\t".join(generator.get_headers("txt")) == headers_line

    def test_generate_tsv_rows_joins_fields_with_tabs(self) -> None:
        """Test that fields are joined with TAB delimiter."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncEnsembl(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock stream_rows to return test data
        test_data = [
            [{"VGNC ID": "VGNC:12345", "Approved Symbol": "GENE1", "Ensembl Gene ID": "ENSG0001"}]
        ]

        def mock_stream_rows(chunk_size=5000):  # noqa: ARG001
            return iter(test_data)

        generator.stream_rows = mock_stream_rows  # type: ignore[method-assign]

        # Generate TSV rows
        tsv_lines = list(generator.generate_tsv_rows())

        # Second line should have data joined by tabs
        data_line = tsv_lines[1]
        assert "\t" in data_line
        assert "VGNC:12345" in data_line
        assert "GENE1" in data_line


class TestVgncEnsemblGenerateJson:
    """Tests for VgncEnsembl JSON generation."""

    def test_generate_json_rows_produces_valid_json(self) -> None:
        """Test that generate_json_rows() produces valid JSON strings."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncEnsembl(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock stream_rows to return test data
        test_data = [
            [{"VGNC ID": "VGNC:12345", "Approved Symbol": "GENE1", "Ensembl Gene ID": "ENSG0001"}]
        ]

        def mock_stream_rows(chunk_size=5000):  # noqa: ARG001
            return iter(test_data)

        generator.stream_rows = mock_stream_rows  # type: ignore[method-assign]

        # Generate JSON rows
        json_lines = list(generator.generate_json_rows())

        # Should have opening bracket, data, and closing bracket
        assert len(json_lines) >= 2
        assert json_lines[0] == "["
        assert json_lines[-1] == "]"
