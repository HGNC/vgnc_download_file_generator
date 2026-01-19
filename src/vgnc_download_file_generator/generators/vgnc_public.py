"""VgncPublic file generator for main gene set files.

This module provides the VgncPublic generator for creating TSV and JSON
downloads of VGNC gene data with comprehensive annotations.
"""

import json
from collections.abc import Generator, Iterator
from typing import Any

from vgnc_download_file_generator.database.queries import build_gene_query
from vgnc_download_file_generator.generator import BaseFileGenerator
from vgnc_download_file_generator.utils.streaming import stream_gene_data


class VgncPublic(BaseFileGenerator):
    """Generator for VGNC Public gene set files.

    Generates TSV and JSON files with comprehensive gene annotations
    including standard VGNC fields plus special cases for 'All' species
    and Zebrafish (taxon_id 9913).
    """

    # Standard 22 TSV headers
    _STANDARD_HEADERS: list[str] = [
        "vgnc_id",
        "symbol",
        "name",
        "locus_group",
        "locus_type",
        "status",
        "location",
        "location_sortable",
        "alias_symbol",
        "alias_name",
        "prev_symbol",
        "prev_name",
        "gene_family",
        "gene_family_id",
        "date_approved_reserved",
        "date_symbol_changed",
        "date_name_changed",
        "date_modified",
        "ncbi_id",
        "ensembl_gene_id",
        "uniprot_ids",
        "pubmed_id",
        "horde_id",
        "hgnc_orthologs",
    ]

    def _get_column_map(self) -> dict[str, str]:
        """Get mapping from database column names to standard headers.

        The database query returns columns with different names than the
        standard VGNC headers. This method provides the mapping.

        Returns:
            Dictionary mapping database column names to standard header names
        """
        return {
            "genefam_id": "vgnc_id",
            "assigned_id": "vgnc_id",
            "assigned_symbol": "symbol",
            "assigned_name": "name",
            "gene_status": "status",
            "locus_group": "locus_group",
            "locus_type": "locus_type",
            "chromosome": "location",
            "gene_family": "gene_family",
            "gene_family_id": "gene_family_id",
            "ncbi_gene_id": "ncbi_id",
            "ensembl_gene_id": "ensembl_gene_id",
            "uniprot_ids": "uniprot_ids",
            "pubmed_id": "pubmed_id",
            "hgnc_orthologs": "hgnc_orthologs",
            "bgd_id": "bgd_id",
            "date_approved_reserved": "date_approved_reserved",
            "date_modified": "date_modified",
            "date_symbol_changed": "date_symbol_changed",
            "date_name_changed": "date_name_changed",
            "alias_symbol": "alias_symbol",
            "alias_name": "alias_name",
            "prev_symbol": "prev_symbol",
            "prev_name": "prev_name",
        }

    def get_headers(self, extension: str) -> list[str]:  # noqa: ARG002
        """Get column headers for the file format.

        Returns standard 22 headers with special cases:
        - 'All' species: adds taxon_id first and primary_db_id last
        - Cattle/Bos taurus (taxon 9913): adds bgd_id before pubmed_id

        Args:
            extension: File extension (txt or json)

        Returns:
            List of column header strings
        """
        headers = self._STANDARD_HEADERS.copy()

        # Handle 'All' species - add taxon_id first and primary_db_id last
        is_all_species = self.species.taxon_id == "All" or self.species.display_name == "All"  # type: ignore[comparison-overlap]
        if is_all_species:
            headers.insert(0, "taxon_id")
            headers.append("primary_db_id")

        # Handle Cattle/Bos taurus (taxon 9913) - add bgd_id before pubmed_id
        is_cattle = self.species.taxon_id == 9913
        if is_cattle:
            pubmed_idx = headers.index("pubmed_id")
            headers.insert(pubmed_idx, "bgd_id")

        return headers

    def stream_rows(
        self, chunk_size: int = 5000
    ) -> Iterator[list[dict[str, Any]]]:
        """Stream rows from the database in chunks.

        Uses build_gene_query() to fetch data with appropriate filters
        based on chromosome, locus_group, and locus_type.

        Args:
            chunk_size: Number of rows to fetch per batch (default: 5000)

        Yields:
            Iterator of lists, where each list contains chunk_size dictionaries
        """
        # Build filters for the query
        filters: dict[str, str | int | list[str]] = {}

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

        # Build the query
        query = build_gene_query(filters=filters if filters else None)

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

        Yields JSON objects one at a time for memory-efficient streaming.
        Each yielded string is a JSON object. The caller is responsible
        for wrapping in array brackets and adding commas.

        Yields:
            Generator yielding JSON object strings
        """
        # Get headers for field selection
        headers = self.get_headers("txt")

        # Stream data rows and convert to JSON objects
        for chunk in self.stream_rows():
            for row_dict in chunk:
                # Convert row dict to use only header fields
                # Keys are already lowercase_underscore from the database
                obj = {header: row_dict.get(header) for header in headers}

                # Convert date objects to ISO format strings for JSON serialization
                obj = self._serialize_dates(obj)

                # Serialize the object to JSON
                yield json.dumps(obj, ensure_ascii=False)

    def _serialize_dates(self, obj: dict[str, Any]) -> dict[str, Any]:
        """Convert date objects to ISO format strings.

        Args:
            obj: Dictionary that may contain date objects

        Returns:
            Dictionary with dates converted to ISO format strings
        """
        from datetime import date

        result = {}
        for key, value in obj.items():
            if isinstance(value, date):
                # Convert date to ISO format string (YYYY-MM-DD)
                result[key] = value.isoformat()
            else:
                result[key] = value
        return result
