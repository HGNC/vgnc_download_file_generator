"""Tests for VgncPublic.stream_rows() method."""

from unittest.mock import MagicMock

from vgnc_download_file_generator.database.connection import DatabaseConnection
from vgnc_download_file_generator.generators.vgnc_public import VgncPublic
from vgnc_download_file_generator.models.species import SpeciesInfo


class TestVgncPublicStreamRows:
    """Tests for VgncPublic.stream_rows() method."""

    def test_uses_build_gene_query(self) -> None:
        """Test that stream_rows uses build_gene_query()."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome="X",
            locus_group=None,
            locus_type=None,
        )

        # Mock the streaming cursor
        mock_cursor = MagicMock()
        # Use a list with empty list as side_effect - returns empty list on first call,
        # then raises StopIteration which the while loop in stream_gene_data handles
        mock_cursor.fetchmany.side_effect = [[]]
        mock_cursor.description = []  # Mock empty cursor description
        db.get_streaming_cursor.return_value = mock_cursor

        # Stream rows (should be empty due to mocking)
        list(generator.stream_rows(chunk_size=5000))

        # Verify get_streaming_cursor was called
        db.get_streaming_cursor.assert_called_once()

    def test_applies_species_filter_to_query(self) -> None:
        """Test that species taxon_id filter is applied to the query."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock the streaming cursor
        mock_cursor = MagicMock()
        # Return empty list to signal end of result set
        mock_cursor.fetchmany.side_effect = [[]]
        mock_cursor.description = []
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

    def test_applies_chromosome_filter_when_present(self) -> None:
        """Test that chromosome filter is applied when present."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome="X",
            locus_group=None,
            locus_type=None,
        )

        # Mock the streaming cursor
        mock_cursor = MagicMock()
        # Return empty list to signal end of result set
        mock_cursor.fetchmany.side_effect = [[]]
        mock_cursor.description = []
        db.get_streaming_cursor.return_value = mock_cursor

        # Stream rows
        list(generator.stream_rows())

        # Verify cursor.execute was called
        mock_cursor.execute.assert_called_once()
        # The query should filter by chromosome X
        call_args = mock_cursor.execute.call_args
        query = call_args[0][0]
        # Query should have chromosome filter
        assert "X" in str(query) or "chromosome" in str(query).lower()

    def test_yields_chunks_of_correct_size(self) -> None:
        """Test that stream_rows yields chunks of the specified size."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock the split query approach
        # Query 1: Main gene data (returns 8 rows)
        gene_cursor = MagicMock()
        gene_cursor.description = [("genefam_id",), ("assigned_symbol",)]
        gene_cursor.__iter__ = lambda _self: iter([
            (1, "GENE1"),
            (2, "GENE2"),
            (3, "GENE3"),
            (4, "GENE4"),
            (5, "GENE5"),
            (6, "GENE6"),
            (7, "GENE7"),
            (8, "GENE8"),
        ])

        # Queries 2-4: Return empty results
        empty_cursor = MagicMock()
        empty_cursor.description = []
        empty_cursor.__iter__ = lambda _self: iter([])

        # Configure mock to return different cursers for each call
        # get_streaming_cursor for gene data, get_cursor for other queries
        call_count = [0]
        def get_cursor_side_effect(*_args, **_kwargs):
            call_count[0] += 1
            if call_count[0] == 1:  # First call - gene data query
                return gene_cursor
            else:  # Subsequent calls - xrefs, aliases, dates
                return empty_cursor

        db.get_streaming_cursor.return_value = gene_cursor
        db.get_cursor.side_effect = get_cursor_side_effect

        # Stream rows with chunk_size=5
        chunks = list(generator.stream_rows(chunk_size=5))

        # Should get 2 chunks
        assert len(chunks) == 2
        # First chunk should have 5 rows
        assert len(chunks[0]) == 5
        # Second chunk should have 3 rows
        assert len(chunks[1]) == 3

    def test_returns_iterator(self) -> None:
        """Test that stream_rows returns an iterator."""
        from collections.abc import Iterator

        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock empty result for split queries
        gene_cursor = MagicMock()
        gene_cursor.description = []
        gene_cursor.__iter__ = lambda _self: iter([])

        empty_cursor = MagicMock()
        empty_cursor.description = []
        empty_cursor.__iter__ = lambda _self: iter([])

        call_count = [0]
        def get_cursor_side_effect(*_args, **_kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return gene_cursor
            else:
                return empty_cursor

        db.get_streaming_cursor.return_value = gene_cursor
        db.get_cursor.side_effect = get_cursor_side_effect

        result = generator.stream_rows()

        assert isinstance(result, Iterator)

    def test_uses_split_queries(self) -> None:
        """Test that stream_rows uses split query architecture."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock split query responses
        gene_cursor = MagicMock()
        gene_cursor.description = [("genefam_id",), ("assigned_symbol",)]
        gene_cursor.__iter__ = lambda _self: iter([(1, "GENE1")])

        empty_cursor = MagicMock()
        empty_cursor.description = []
        empty_cursor.__iter__ = lambda _self: iter([])

        # Track which cursors were called
        calls = []
        def get_streaming_cursor_side_effect():
            calls.append("get_streaming_cursor")
            return gene_cursor

        def get_cursor_side_effect():
            calls.append("get_cursor")
            return empty_cursor

        db.get_streaming_cursor.side_effect = get_streaming_cursor_side_effect
        db.get_cursor.side_effect = get_cursor_side_effect

        # Stream rows
        list(generator.stream_rows(chunk_size=1000))

        # Verify split query pattern:
        # 1 get_streaming_cursor call for gene data
        # 1 get_cursor call for sub-queries (xrefs, aliases, dates reuse same cursor)
        assert calls.count("get_streaming_cursor") == 1
        assert calls.count("get_cursor") == 1
