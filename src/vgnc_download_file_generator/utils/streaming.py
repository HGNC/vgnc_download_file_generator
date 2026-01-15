"""Streaming utilities for memory-efficient data processing.

This module provides utilities for streaming large result sets from the database
without loading all data into memory at once.
"""

from collections.abc import Iterator
from typing import Any


def dictify_rows(headers: list[str], rows: list[tuple[Any, ...]]) -> Iterator[dict[str, Any]]:
    """Convert database rows (tuples) to dictionaries.

    Takes column headers and row tuples, and yields dictionaries that map
    column names to values. This is a generator function for memory efficiency.

    Args:
        headers: List of column names
        rows: Iterator or list of row tuples from database query

    Yields:
        Dictionaries mapping column names to values

    Examples:
        >>> headers = ["id", "name", "status"]
        >>> rows = [("1", "Gene1", "Approved"), ("2", "Gene2", "Withdrawn")]
        >>> list(dictify_rows(headers, rows))
        [{'id': '1', 'name': 'Gene1', 'status': 'Approved'},
         {'id': '2', 'name': 'Gene2', 'status': 'Withdrawn'}]
    """
    for row in rows:
        yield dict(zip(headers, row, strict=False))


def stream_gene_data(
    cursor: Any, headers: list[str], chunk_size: int = 5000
) -> Iterator[list[dict[str, Any]]]:
    """Stream gene data from database cursor in chunks.

    Uses server-side cursor (SSCursor) to fetch data in batches, preventing
    memory issues with large result sets. Each chunk is a list of dictionaries
    mapping column names to values.

    Args:
        cursor: Database cursor with fetchmany() method (typically SSCursor)
        headers: List of column names for the result set
        chunk_size: Number of rows to fetch per batch (default: 5000)

    Yields:
        Lists of dictionaries, where each dictionary represents a row
        with column names as keys

    Examples:
        >>> cursor = conn.get_streaming_cursor()
        >>> cursor.execute("SELECT genefam_id, assigned_symbol FROM genefam")
        >>> headers = ["genefam_id", "assigned_symbol"]
        >>> for chunk in stream_gene_data(cursor, headers, chunk_size=100):
        ...     for row in chunk:
        ...         print(row["genefam_id"], row["assigned_symbol"])
    """
    while True:
        # Fetch a batch of rows from the cursor
        rows = cursor.fetchmany(chunk_size)

        # If no rows returned, we've reached the end
        if not rows:
            break

        # Convert tuples to dictionaries and yield as a chunk
        chunk = list(dictify_rows(headers, rows))
        yield chunk


def count_streamed_rows(stream: Iterator[list[dict[str, Any]]]) -> int:
    """Count total rows from a stream without loading all data into memory.

    Consumes the stream and returns the total count of rows across all chunks.
    This is memory-efficient because it processes chunks sequentially and doesn't
    store the row data after counting.

    Args:
        stream: Iterator yielding lists of dictionaries (from stream_gene_data)

    Returns:
        Total number of rows in the stream

    Examples:
        >>> cursor = conn.get_streaming_cursor()
        >>> cursor.execute("SELECT genefam_id, assigned_symbol FROM genefam")
        >>> headers = ["genefam_id", "assigned_symbol"]
        >>> data_stream = stream_gene_data(cursor, headers, chunk_size=5000)
        >>> total_count = count_streamed_rows(data_stream)
        >>> print(f"Total rows: {total_count}")
    """
    count = 0
    for chunk in stream:
        count += len(chunk)
    return count
