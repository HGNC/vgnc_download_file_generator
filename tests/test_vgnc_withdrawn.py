"""Tests for VgncWithdrawn generator."""

import json
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
            locus_group=None,
            locus_type=None,
        )

        txt_headers = generator.get_headers("txt")
        json_headers = generator.get_headers("json")

        assert txt_headers == json_headers


class TestVgncWithdrawnStreamRows:
    """VgncWithdrawn.stream_rows() uses the shared drop-safe keyset paginator.

    Regression context: the Cloud Run "Server has gone away" (2013/2006)
    failure came from a long-lived server-side cursor. No generator may use
    one; the pagination mechanics are shared and covered elsewhere, so these
    tests pin only this generator's specific filters.
    """

    def _generator(self, db):
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")
        return VgncWithdrawn(db=db, species=species, locus_group=None, locus_type=None)

    def test_does_not_use_streaming_cursor(self, paginating_db) -> None:
        """No server-side cursor is held open for the withdrawn stream."""
        db = paginating_db([1, 2], 5)
        list(self._generator(db).stream_rows())
        db.get_streaming_cursor.assert_not_called()

    def test_filters_by_withdrawn_statuses(self, paginating_db) -> None:
        """The query carries the withdrawn status filters."""
        db = paginating_db([1, 2], 5)
        list(self._generator(db).stream_rows())
        joined_sql = " ".join(db._cursor.executed)
        assert "gf.status_id" in joined_sql   # WITHDRAWN_STATUS_IDS [2, 3]
        assert "gs.status" in joined_sql       # status names (Entry/Symbol Withdrawn)

    def test_applies_species_filter_to_query(self, paginating_db) -> None:
        """The taxon_id filter reaches the query."""
        db = paginating_db([1, 2], 5)
        list(self._generator(db).stream_rows())
        joined_sql = " ".join(db._cursor.executed)
        assert "gf.taxon_id" in joined_sql


class TestVgncWithdrawnGenerateTsv:
    """Tests for VgncWithdrawn TSV generation."""

    def test_generate_tsv_rows_writes_headers(self) -> None:
        """Test that generate_tsv_rows() yields header row first."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncWithdrawn(
            db=db,
            species=species,
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
        # Headers should end with newline
        assert headers_line.endswith("\n")
        # Strip newline for comparison
        assert "\t".join(generator.get_headers("txt")) == headers_line.rstrip("\n")

    def test_withdrawn_data_rows_joined_with_tabs(self) -> None:
        """Test that withdrawn data fields are joined with TAB delimiter."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncWithdrawn(
            db=db,
            species=species,
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

        # Generate JSON rows (now yields only JSON objects)
        json_objects = list(generator.generate_json_rows())

        # Should have at least one JSON object
        assert len(json_objects) >= 1

        # Each line should be a valid JSON object
        for json_str in json_objects:
            obj = json.loads(json_str)
            assert isinstance(obj, dict)

        # Can wrap in brackets to make valid JSON array
        full_json = "[" + ",".join(json_objects) + "]"
        parsed = json.loads(full_json)
        assert isinstance(parsed, list)
