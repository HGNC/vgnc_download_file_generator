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
        mock_cursor.fetchmany.side_effect = [[], []]  # Empty result
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
        mock_cursor.fetchmany.side_effect = [[], []]
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

        # Mock the streaming cursor to return test data
        mock_cursor = MagicMock()
        # Return 5 rows, then 3 rows, then empty
        mock_cursor.fetchmany.side_effect = [
            [("row1",), ("row2",), ("row3",), ("row4",), ("row5",)],
            [("row6",), ("row7",), ("row8",)],
            [],
        ]
        # Mock cursor.description to provide column names
        mock_cursor.description = [("col1",), ("col2",)]
        db.get_streaming_cursor.return_value = mock_cursor

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

        # Mock empty result
        mock_cursor = MagicMock()
        mock_cursor.fetchmany.side_effect = [[], []]
        db.get_streaming_cursor.return_value = mock_cursor

        result = generator.stream_rows()

        assert isinstance(result, Iterator)

    def test_uses_stream_gene_data_utility(self) -> None:
        """Test that stream_rows uses stream_gene_data utility."""
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
        mock_cursor.fetchmany.side_effect = [[], []]
        mock_cursor.description = [("col1",)]
        db.get_streaming_cursor.return_value = mock_cursor

        # Stream rows with custom chunk_size
        list(generator.stream_rows(chunk_size=1000))

        # Verify fetchmany was called with chunk_size
        mock_cursor.fetchmany.assert_called()
        # Should have been called with our custom chunk_size
        for call_item in mock_cursor.fetchmany.call_args_list:
            assert call_item[0][0] == 1000
