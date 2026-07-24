"""Tests for VgncPublic.stream_rows() method."""

from unittest.mock import MagicMock

from vgnc_download_file_generator.database.connection import DatabaseConnection
from vgnc_download_file_generator.generators.vgnc_public import VgncPublic
from vgnc_download_file_generator.models.species import SpeciesInfo


def _no_compile(*_args, **_kwargs):
    """Stand-in for compile_query_for_mysql (unused when fetch_sub is mocked)."""
    return "", ()


class TestVgncPublicStreamRows:
    """Tests for VgncPublic.stream_rows() method."""

    def test_uses_build_gene_query(self) -> None:
        """Test that stream_rows uses build_gene_query()."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
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

    def test_query_includes_chromosome_location_fields(self) -> None:
        """Test that the query still selects chromosome/location context."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
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
        # The query should still include chromosome context in SELECT/JOINs
        call_args = mock_cursor.execute.call_args
        query = call_args[0][0]
        # Query should reference chromosome columns/tables
        assert "chromosome" in str(query).lower()

    def test_yields_chunks_of_correct_size(self) -> None:
        """Test that stream_rows yields chunks of the specified size."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
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


class TestVgncPublicRuntimeValidation:
    """Runtime ID-format validation wired into _process_batch (Task 4)."""

    def _generator(self, mode="strict", grace=5):
        from vgnc_download_file_generator.validation import RecordValidator

        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")
        gen = VgncPublic(db=db, species=species)
        gen._validator = RecordValidator(mode=mode, grace=grace)  # type: ignore[attr-defined]
        return gen

    def test_process_batch_raises_on_systematic_swap(self) -> None:
        """A swapped xref column (ncbi holds Ensembl values) must abort the batch."""
        from vgnc_download_file_generator.database.queries_split import (
            merge_gene_results,
        )

        gene_batch = [{"genefam_id": i, "assigned_id": f"VGNC:{i}"} for i in range(10)]
        # Simulate the original bug: ncbi_gene_id holds Ensembl IDs.
        swapped_xrefs = [
            {"genefam_id": i, "ncbi_gene_id": f"ENSG00000{i:06d}", "ensembl_gene_id": str(i)}
            for i in range(10)
        ]
        def fetch_sub(_ids, _cur, _cfn):
            return (swapped_xrefs, [], [])

        gen = self._generator(mode="strict", grace=5)
        column_map = gen._get_column_map()

        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            list(
                gen._process_batch(
                    gene_batch, MagicMock(), column_map, _no_compile,
                    fetch_sub, merge_gene_results,
                )
            )

    def test_process_batch_passes_valid_records(self) -> None:
        """Well-formed records stream through without raising."""
        from vgnc_download_file_generator.database.queries_split import (
            merge_gene_results,
        )

        gene_batch = [{"genefam_id": i, "assigned_id": f"VGNC:{i}"} for i in range(20)]
        valid_xrefs = [
            {"genefam_id": i, "ncbi_gene_id": str(i), "ensembl_gene_id": f"ENSG00000{i:06d}"}
            for i in range(20)
        ]
        def fetch_sub(_ids, _cur, _cfn):
            return (valid_xrefs, [], [])

        gen = self._generator(mode="strict", grace=0)
        column_map = gen._get_column_map()

        rows = list(
            gen._process_batch(
                gene_batch, MagicMock(), column_map, lambda *_a, **_k: ("", ()),
                fetch_sub, merge_gene_results,
            )
        )
        assert len(rows) == 20


class TestVgncPublicLocationSortable:
    """_process_batch must derive location_sortable from the chromosome (Spec Task 6)."""

    def _generator(self):
        from vgnc_download_file_generator.validation import RecordValidator

        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")
        gen = VgncPublic(db=db, species=species)
        gen._validator = RecordValidator(mode="strict", grace=50)  # type: ignore[attr-defined]
        return gen

    def test_process_batch_derives_padded_location_sortable(self) -> None:
        """Single-digit chrom is padded; two-digit and X unchanged; no coordinates."""
        from vgnc_download_file_generator.database.queries_split import (
            merge_gene_results,
        )

        gene_batch = [
            {"genefam_id": 1, "assigned_id": "VGNC:1", "chromosome": "5"},
            {"genefam_id": 2, "assigned_id": "VGNC:2", "chromosome": "18"},
            {"genefam_id": 3, "assigned_id": "VGNC:3", "chromosome": "X"},
        ]

        def fetch_sub(_ids, _cur, _cfn):
            return ([], [], [])

        gen = self._generator()
        column_map = gen._get_column_map()
        rows = list(
            gen._process_batch(
                gene_batch, MagicMock(), column_map, _no_compile,
                fetch_sub, merge_gene_results,
            )
        )
        by_id = {r["vgnc_id"]: r for r in rows}

        assert by_id["VGNC:1"]["location"] == "5"
        assert by_id["VGNC:1"]["location_sortable"] == "05"
        assert by_id["VGNC:2"]["location"] == "18"
        assert by_id["VGNC:2"]["location_sortable"] == "18"
        assert by_id["VGNC:3"]["location"] == "X"
        assert by_id["VGNC:3"]["location_sortable"] == "X"

    def test_process_batch_locationless_gene_has_none_location_sortable(self) -> None:
        """A gene with no location emits None for both location and location_sortable."""
        from vgnc_download_file_generator.database.queries_split import (
            merge_gene_results,
        )

        gene_batch = [{"genefam_id": 1, "assigned_id": "VGNC:1", "chromosome": None}]

        def fetch_sub(_ids, _cur, _cfn):
            return ([], [], [])

        gen = self._generator()
        column_map = gen._get_column_map()
        rows = list(
            gen._process_batch(
                gene_batch, MagicMock(), column_map, _no_compile,
                fetch_sub, merge_gene_results,
            )
        )

        assert rows[0]["location"] is None
        assert rows[0]["location_sortable"] is None
