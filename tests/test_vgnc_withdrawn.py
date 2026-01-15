"""Tests for VgncWithdrawn generator."""

from unittest.mock import MagicMock

from vgnc_download_file_generator.database.connection import DatabaseConnection
from vgnc_download_file_generator.generators.vgnc_withdrawn import VgncWithdrawn
from vgnc_download_file_generator.models.species import SpeciesInfo


class TestVgncWithdrawnGetHeaders:
    """Tests for VgncWithdrawn.get_headers() method."""

    def test_standard_headers_for_normal_species(self) -> None:
        """Test that get_headers() returns standard headers for normal species."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncWithdrawn(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        headers = generator.get_headers("txt")

        # Should have standard headers without TAXON_ID
        expected = ["VGNC_ID", "STATUS", "WITHDRAWN_SYMBOL", "MERGED_INTO_REPORT(S)"]
        assert headers == expected

    def test_all_species_adds_taxon_id_first(self) -> None:
        """Test that 'All' species gets TAXON_ID as first column."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id="All", display_name="All", is_live="Y")

        generator = VgncWithdrawn(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        headers = generator.get_headers("txt")

        # Should have TAXON_ID first
        assert headers[0] == "TAXON_ID"
        assert "VGNC_ID" in headers
        assert "MERGED_INTO_REPORT(S)" in headers

    def test_json_extension_returns_same_headers(self) -> None:
        """Test that JSON extension returns same headers as TSV."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncWithdrawn(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        txt_headers = generator.get_headers("txt")
        json_headers = generator.get_headers("json")

        assert txt_headers == json_headers


class TestVgncWithdrawnStreamRows:
    """Tests for VgncWithdrawn.stream_rows() method."""

    def test_filters_by_withdrawn_statuses(self) -> None:
        """Test that stream_rows filters to withdrawn status types."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncWithdrawn(
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
        # The query should filter by withdrawn statuses
        call_args = mock_cursor.execute.call_args
        query = call_args[0][0]
        # Query should have withdrawn status filters
        query_str = str(query).lower()
        assert "withdrawn" in query_str or "status" in query_str

    def test_applies_species_filter_to_query(self) -> None:
        """Test that species taxon_id filter is applied to the query."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncWithdrawn(
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


class TestVgncWithdrawnGenerateTsv:
    """Tests for VgncWithdrawn TSV generation."""

    def test_generate_tsv_rows_writes_headers(self) -> None:
        """Test that generate_tsv_rows() yields header row first."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncWithdrawn(
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
        assert "VGNC_ID" in headers_line
        assert "STATUS" in headers_line
        assert "\t".join(generator.get_headers("txt")) == headers_line

    def test_withdrawn_data_rows_joined_with_tabs(self) -> None:
        """Test that withdrawn data fields are joined with TAB delimiter."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncWithdrawn(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock stream_rows to return test data
        test_data = [
            [{"VGNC_ID": "VGNC:12345", "STATUS": "Entry Withdrawn", "WITHDRAWN_SYMBOL": "OLD1"}]
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
        assert "Entry Withdrawn" in data_line


class TestVgncWithdrawnGenerateJson:
    """Tests for VgncWithdrawn JSON generation."""

    def test_generate_json_rows_produces_valid_json(self) -> None:
        """Test that generate_json_rows() produces valid JSON strings."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncWithdrawn(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock stream_rows to return test data
        test_data = [
            [{"VGNC_ID": "VGNC:12345", "STATUS": "Symbol Withdrawn", "WITHDRAWN_SYMBOL": "OLD1"}]
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
