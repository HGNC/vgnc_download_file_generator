"""VgncWithdrawn file generator for withdrawn entry files.

This module provides the VgncWithdrawn generator for creating TSV and JSON
downloads of VGNC withdrawn gene entries.
"""

import json
from collections.abc import Generator, Iterator
from typing import Any

from vgnc_download_file_generator.database.queries import build_gene_query
from vgnc_download_file_generator.generator import BaseFileGenerator
from vgnc_download_file_generator.utils.streaming import stream_gene_data


class VgncWithdrawn(BaseFileGenerator):
    """Generator for VGNC withdrawn entry files.

    Generates TSV and JSON files for genes with withdrawn status
    (Entry Withdrawn or Symbol Withdrawn).
    """

    # Standard withdrawn headers (uppercase underscore format)
    _STANDARD_HEADERS: list[str] = [
        "VGNC_ID",
        "STATUS",
        "WITHDRAWN_SYMBOL",
        "MERGED_INTO_REPORT(S)",
    ]

    def _get_column_map(self) -> dict[str, str]:
        """Get mapping from database column names to withdrawn headers.

        The database query returns columns with different names than the
        withdrawn headers. This method provides the mapping.

        Returns:
            Dictionary mapping database column names to withdrawn header names
        """
        return {
            "genefam_id": "VGNC_ID",
            "assigned_id": "VGNC_ID",
            "assigned_symbol": "WITHDRAWN_SYMBOL",
            "gene_status": "STATUS",
        }

    def get_headers(self, extension: str) -> list[str]:  # noqa: ARG002
        """Get column headers for the file format.

        Returns standard headers with special case:
        - 'All' species: adds TAXON_ID as first column

        Args:
            extension: File extension (txt or json) - ignored, returns same headers

        Returns:
            List of column header strings
        """
        headers = self._STANDARD_HEADERS.copy()

        # Handle 'All' species - add TAXON_ID first
        is_all_species = self.species.taxon_id == "All" or self.species.display_name == "All"  # type: ignore[comparison-overlap]
        if is_all_species:
            headers.insert(0, "TAXON_ID")

        return headers

    def stream_rows(
        self, chunk_size: int = 5000
    ) -> Iterator[list[dict[str, Any]]]:
        """Stream rows from the database in chunks.

        Filters for withdrawn status genes only:
        - Entry Withdrawn
        - Symbol Withdrawn

        Args:
            chunk_size: Number of rows to fetch per batch (default: 5000)

        Yields:
            Iterator of lists, where each list contains chunk_size dictionaries
        """
        # Build filters for the query - withdrawn statuses only
        filters: dict[str, str | int | list[str]] = {
            "status": ["Entry Withdrawn", "Symbol Withdrawn"]
        }

        # Add taxon_id filter
        if isinstance(self.species.taxon_id, int):
            filters["taxon_id"] = self.species.taxon_id

        # Add chromosome filter if present
        if self.chromosome is not None:
            filters["chromosome"] = self.chromosome

        # Add locus_group filter if present
        if self.locus_group is not None:
            filters["locus_group"] = self.locus_group

        # Add locus_type filter if present
        if self.locus_type is not None:
            filters["locus_type"] = self.locus_type

        # Build the query with withdrawn status filter
        query = build_gene_query(filters=filters)

        # Get streaming cursor from database
        cursor = self.db.get_streaming_cursor()

        # Compile query for MySQLdb and execute
        from vgnc_download_file_generator.database.queries import compile_query_for_mysql

        sql, params = compile_query_for_mysql(query)
        cursor.execute(sql, params)

        # Get column names from cursor description
        # cursor.description is a sequence of (name, type_code, ...) tuples
        db_headers = [desc[0] for desc in cursor.description] if cursor.description else []

        # Create mapping from database column names to standard headers
        column_map = self._get_column_map()

        # Map database headers to standard headers and stream rows
        for chunk in stream_gene_data(cursor, db_headers, chunk_size):
            # Convert each row dict to use standard header names
            mapped_chunk = []
            for row_dict in chunk:
                mapped_dict = {}
                for db_col, value in row_dict.items():
                    # Map database column to standard header
                    standard_header = column_map.get(db_col, db_col)
                    mapped_dict[standard_header] = value
                mapped_chunk.append(mapped_dict)
            yield mapped_chunk

    def generate_tsv_rows(self) -> Generator[str]:
        """Generate TSV-formatted rows as strings.

        Yields TSV lines one at a time for memory-efficient streaming.
        First line is the header row, followed by data rows.

        Yields:
            Generator yielding TSV-formatted strings (one line per yield)
        """
        # Get headers for TSV output
        headers = self.get_headers("txt")

        # Yield header row joined by tabs
        yield "\t".join(headers)

        # Stream data rows and yield them as TSV
        for chunk in self.stream_rows():
            for row_dict in chunk:
                # Convert row dict to list of values in header order
                # Convert None values to empty strings
                values = [
                    str(row_dict.get(header, "")) if row_dict.get(header) is not None else ""
                    for header in headers
                ]
                # Yield the row joined by tabs
                yield "\t".join(values)

    def generate_json_rows(self) -> Generator[str]:
        """Generate JSON-formatted rows as strings.

        Yields JSON lines one at a time for memory-efficient streaming.
        Produces an array of objects with headers as keys.

        Yields:
            Generator yielding JSON strings (opening bracket, objects with commas,
            and closing bracket)
        """
        # Get headers for field selection
        headers = self.get_headers("txt")

        # Yield opening bracket
        yield "["

        # Stream data rows and convert to JSON objects
        first_object = True
        for chunk in self.stream_rows():
            for row_dict in chunk:
                # Convert row dict to use only header fields
                obj = {header: row_dict.get(header) for header in headers}

                # Serialize the object to JSON
                json_str = json.dumps(obj, ensure_ascii=False)

                # Add comma before object if not the first
                if not first_object:
                    yield ","

                yield json_str
                first_object = False

        # Yield closing bracket
        yield "]"
