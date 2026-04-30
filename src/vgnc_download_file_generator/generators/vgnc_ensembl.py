"""VgncEnsembl file generator for Ensembl gene ID mapping files.

This module provides the VgncEnsembl generator for creating TSV and JSON
downloads of VGNC gene data with Ensembl cross-references.
"""

import json
from collections.abc import Generator, Iterator
from typing import Any

from vgnc_download_file_generator.generator import BaseFileGenerator
from vgnc_download_file_generator.utils.streaming import stream_gene_data


class VgncEnsembl(BaseFileGenerator):
    """Generator for VGNC Ensembl gene ID mapping files.

    Generates TSV and JSON files with Ensembl cross-reference information
    for Approved VGNC genes only.
    """

    # File type identifier for this generator
    _FILE_TYPE: str = "vgnc_ensembl"

    # Ensembl-specific headers (space-separated format from PRD)
    _ENSEMBL_HEADERS: list[str] = [
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

    def _get_column_map(self) -> dict[str, str]:
        """Get mapping from database column names to Ensembl headers.

        The database query returns columns with different names than the
        Ensembl headers. This method provides the mapping.

        Returns:
            Dictionary mapping database column names to Ensembl header names
        """
        return {
            "genefam_id": "VGNC ID",
            "assigned_id": "VGNC ID",
            "assigned_symbol": "Approved Symbol",
            "assigned_name": "Approved Name",
            "prev_symbol": "Previous Symbols",
            "alias_symbol": "Synonyms",
            "ncbi_id": "Entrez Gene ID",
            "ensembl_gene_id": "Ensembl Gene ID",
            "uniprot_ids": "Uniprot ID(supplied by UniProt)",
        }

    def get_headers(self, extension: str) -> list[str]:  # noqa: ARG002
        """Get column headers for the file format.

        Args:
            extension: File extension (txt or json) - ignored, returns same headers

        Returns:
            List of column header strings for Ensembl mapping file
        """
        return self._ENSEMBL_HEADERS.copy()

    def stream_rows(
        self, chunk_size: int = 5000
    ) -> Iterator[list[dict[str, Any]]]:
        """Stream rows from the database in chunks.

        Filters for 'Approved' status genes only.
        Uses split query architecture for performance.

        Args:
            chunk_size: Number of rows to fetch per batch (default: 5000)

        Yields:
            Iterator of lists, where each list contains chunk_size dictionaries
        """
        # Import split query functions
        from vgnc_download_file_generator.database.queries_split import (
            build_gene_data_query,
            build_xrefs_query,
            build_aliases_query,
            build_dates_query,
            merge_gene_results,
        )
        from vgnc_download_file_generator.database.queries import compile_query_for_mysql

        # Build filters for the query - Approved status only
        filters: dict[str, str | int | list[str]] = {"status": "Approved"}

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

        # Filter by status_id - only include specific status values
        filters["status_id"] = [6, 11, 12]

        # Create mapping from database column names to standard headers
        column_map = self._get_column_map()

        # Execute Query 1: Main gene data
        gene_query = build_gene_data_query(filters=filters if filters else None)
        cursor = self.db.get_streaming_cursor()
        gene_sql, gene_params = compile_query_for_mysql(gene_query)
        cursor.execute(gene_sql, gene_params)

        # Fetch all gene data
        db_headers = [desc[0] for desc in cursor.description] if cursor.description else []
        gene_data_raw = []

        for row in cursor:
            row_dict = dict(zip(db_headers, row))
            gene_data_raw.append(row_dict)

        cursor.close()

        # If no gene data, return empty iterator
        if not gene_data_raw:
            return

        # Extract genefam_ids for the other queries
        genefam_ids = [row["genefam_id"] for row in gene_data_raw]

        # Execute Query 2: Xrefs
        xrefs_query = build_xrefs_query(genefam_ids=genefam_ids)
        cursor = self.db.get_cursor()
        xrefs_sql, xrefs_params = compile_query_for_mysql(xrefs_query)
        cursor.execute(xrefs_sql, xrefs_params)
        xrefs_db_headers = [desc[0] for desc in cursor.description] if cursor.description else []
        xrefs = [dict(zip(xrefs_db_headers, row)) for row in cursor]
        cursor.close()

        # Execute Query 3: Aliases
        aliases_query = build_aliases_query(genefam_ids=genefam_ids)
        cursor = self.db.get_cursor()
        aliases_sql, aliases_params = compile_query_for_mysql(aliases_query)
        cursor.execute(aliases_sql, aliases_params)
        aliases_db_headers = [desc[0] for desc in cursor.description] if cursor.description else []
        aliases = [dict(zip(aliases_db_headers, row)) for row in cursor]
        cursor.close()

        # Execute Query 4: Dates
        dates_query = build_dates_query(genefam_ids=genefam_ids)
        cursor = self.db.get_cursor()
        dates_sql, dates_params = compile_query_for_mysql(dates_query)
        cursor.execute(dates_sql, dates_params)
        dates_db_headers = [desc[0] for desc in cursor.description] if cursor.description else []
        dates = [dict(zip(dates_db_headers, row)) for row in cursor]
        cursor.close()

        # Merge all results
        merged_results = merge_gene_results(gene_data_raw, xrefs, aliases, dates)

        # Stream merged results in chunks
        chunk: list[dict[str, Any]] = []
        for merged_row in merged_results:
            # Map database column names to standard headers
            mapped_dict = {}
            for db_col, value in merged_row.items():
                standard_header = column_map.get(db_col, db_col)
                mapped_dict[standard_header] = value

            chunk.append(mapped_dict)

            # Yield chunk when it reaches chunk_size
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []

        # Yield final partial chunk
        if chunk:
            yield chunk

    def generate_tsv_rows(self) -> Generator[str]:
        """Generate TSV-formatted rows as strings.

        Yields TSV lines one at a time for memory-efficient streaming.
        First line is the header row, followed by data rows.

        Yields:
            Generator yielding TSV-formatted strings (one line per yield)
        """
        # Get headers for TSV output
        headers = self.get_headers("txt")

        # Yield header row joined by tabs, with newline at end
        yield "\t".join(headers) + "\n"

        # Stream data rows and yield them as TSV
        for chunk in self.stream_rows():
            for row_dict in chunk:
                # Convert row dict to list of values in header order
                # Convert None values to empty strings
                values = [
                    str(row_dict.get(header, "")) if row_dict.get(header) is not None else ""
                    for header in headers
                ]
                # Yield the row joined by tabs, with newline at end
                yield "\t".join(values) + "\n"

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
