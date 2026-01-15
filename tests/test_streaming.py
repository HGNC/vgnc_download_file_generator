"""Tests for streaming utilities."""

from typing import Any
from unittest.mock import MagicMock

from vgnc_download_file_generator.utils.streaming import (
    count_streamed_rows,
    dictify_rows,
    stream_gene_data,
)


class TestDictifyRows:
    """Tests for dictify_rows function."""

    def test_converts_tuples_to_dicts(self) -> None:
        """Test that dictify_rows converts tuples to dictionaries using headers."""
        headers = ["col1", "col2", "col3"]
        rows = [
            ("value1", "value2", "value3"),
            ("value4", "value5", "value6"),
        ]

        result = list(dictify_rows(headers, rows))

        assert result == [
            {"col1": "value1", "col2": "value2", "col3": "value3"},
            {"col1": "value4", "col2": "value5", "col3": "value6"},
        ]

    def test_handles_empty_rows(self) -> None:
        """Test that dictify_rows handles empty row list."""
        headers = ["col1", "col2"]
        rows: list[tuple[Any, ...]] = []

        result = list(dictify_rows(headers, rows))

        assert result == []

    def test_handles_single_row(self) -> None:
        """Test that dictify_rows handles single row."""
        headers = ["col1", "col2"]
        rows = [("value1", "value2")]

        result = list(dictify_rows(headers, rows))

        assert result == [{"col1": "value1", "col2": "value2"}]

    def test_preserves_none_values(self) -> None:
        """Test that dictify_rows preserves None values."""
        headers = ["col1", "col2", "col3"]
        rows = [("value1", None, "value3")]

        result = list(dictify_rows(headers, rows))

        assert result == [{"col1": "value1", "col2": None, "col3": "value3"}]


class TestStreamGeneData:
    """Tests for stream_gene_data function."""

    def test_yields_chunks_of_correct_size(self) -> None:
        """Test that stream_gene_data yields chunks of the specified size."""
        # Mock cursor that returns 15 rows total
        mock_cursor = MagicMock()
        mock_cursor.fetchmany.side_effect = [
            [("row1",), ("row2",), ("row3",), ("row4",), ("row5",)],  # First chunk
            [("row6",), ("row7",), ("row8",), ("row9",), ("row10",)],  # Second chunk
            [("row11",), ("row12",), ("row13",), ("row14",), ("row15",)],  # Third chunk
            [],  # Empty to signal end
        ]

        headers = ["col1"]
        chunks = list(stream_gene_data(mock_cursor, headers, chunk_size=5))

        assert len(chunks) == 3
        assert len(chunks[0]) == 5
        assert len(chunks[1]) == 5
        assert len(chunks[2]) == 5
        assert chunks[0][0] == {"col1": "row1"}

    def test_uses_default_chunk_size_of_5000(self) -> None:
        """Test that stream_gene_data uses default chunk_size of 5000."""
        mock_cursor = MagicMock()
        mock_cursor.fetchmany.side_effect = [[], []]  # Empty to signal end

        headers = ["col1"]
        list(stream_gene_data(mock_cursor, headers))

        # Should call fetchmany with default chunk_size
        mock_cursor.fetchmany.assert_called_with(5000)

    def test_stops_when_no_more_data(self) -> None:
        """Test that stream_gene_data stops yielding when cursor is exhausted."""
        mock_cursor = MagicMock()
        mock_cursor.fetchmany.side_effect = [
            [("row1",), ("row2",)],
            [],  # Empty to signal end
        ]

        headers = ["col1"]
        chunks = list(stream_gene_data(mock_cursor, headers, chunk_size=10))

        assert len(chunks) == 1
        assert len(chunks[0]) == 2

    def test_converts_tuples_to_dicts(self) -> None:
        """Test that stream_gene_data converts tuples to dicts using headers."""
        mock_cursor = MagicMock()
        mock_cursor.fetchmany.side_effect = [
            [("val1", "val2", "val3")],
            [],
        ]

        headers = ["col1", "col2", "col3"]
        chunks = list(stream_gene_data(mock_cursor, headers, chunk_size=10))

        assert chunks[0][0] == {"col1": "val1", "col2": "val2", "col3": "val3"}

    def test_handles_last_partial_chunk(self) -> None:
        """Test that stream_gene_data handles last partial chunk correctly."""
        mock_cursor = MagicMock()
        mock_cursor.fetchmany.side_effect = [
            [("row1",), ("row2",), ("row3",), ("row4",), ("row5",)],  # Full chunk
            [("row6",), ("row7",)],  # Partial chunk (less than chunk_size)
            [],  # Empty to signal end
        ]

        headers = ["col1"]
        chunks = list(stream_gene_data(mock_cursor, headers, chunk_size=5))

        assert len(chunks) == 2
        assert len(chunks[0]) == 5
        assert len(chunks[1]) == 2

    def test_returns_iterator(self) -> None:
        """Test that stream_gene_data returns an iterator."""
        from collections.abc import Iterator

        mock_cursor = MagicMock()
        mock_cursor.fetchmany.side_effect = [[], []]

        headers = ["col1"]
        result = stream_gene_data(mock_cursor, headers)

        assert isinstance(result, Iterator)


class TestCountStreamedRows:
    """Tests for count_streamed_rows function."""

    def test_counts_rows_in_single_chunk(self) -> None:
        """Test counting rows when there's only one chunk."""
        stream = [
            [{"id": 1}, {"id": 2}, {"id": 3}],
        ]

        count = count_streamed_rows(iter(stream))

        assert count == 3

    def test_counts_rows_across_multiple_chunks(self) -> None:
        """Test counting rows across multiple chunks."""
        stream = [
            [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}, {"id": 5}],
            [{"id": 6}, {"id": 7}, {"id": 8}],
            [{"id": 9}, {"id": 10}],
        ]

        count = count_streamed_rows(iter(stream))

        assert count == 10

    def test_counts_zero_for_empty_stream(self) -> None:
        """Test that count is 0 for empty stream."""
        stream: list[list[dict[str, Any]]] = []

        count = count_streamed_rows(iter(stream))

        assert count == 0

    def test_counts_large_stream_efficiently(self) -> None:
        """Test that counting doesn't load all data into memory."""
        # Create a generator that yields chunks
        def chunk_generator(n_chunks: int, chunk_size: int):
            for i in range(n_chunks):
                yield [{"id": i * chunk_size + j} for j in range(chunk_size)]

        # Simulate large dataset (100,000 rows in chunks of 5000)
        n_chunks = 20
        chunk_size = 5000
        stream = chunk_generator(n_chunks, chunk_size)

        count = count_streamed_rows(stream)

        assert count == n_chunks * chunk_size

    def test_counts_partial_last_chunk(self) -> None:
        """Test counting with partial last chunk."""
        stream = [
            [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}, {"id": 5}],
            [{"id": 6}, {"id": 7}],  # Partial chunk
        ]

        count = count_streamed_rows(iter(stream))

        assert count == 7
