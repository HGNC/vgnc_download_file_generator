"""VgncEnsembl file generator for Ensembl gene ID mapping files.

This module provides the VgncEnsembl generator for creating TSV and JSON
downloads of VGNC gene data with Ensembl cross-references.
"""

import json
from collections.abc import Generator, Iterator
from typing import Any

from vgnc_download_file_generator.generator import PUBLIC_STATUS_IDS, BaseFileGenerator


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

    def _array_json_fields(self) -> set[str]:
        """Output headers that serialize as JSON arrays."""
        return {"Uniprot ID(supplied by UniProt)"}

    def get_headers(self, extension: str) -> list[str]:  # noqa: ARG002
        """Get column headers for the file format.

        Args:
            extension: File extension (txt or json) - ignored, returns same headers

        Returns:
            List of column header strings for Ensembl mapping file
        """
        return self._ENSEMBL_HEADERS.copy()

    def stream_rows(
        self, chunk_size: int = 5000, batch_size: int = 5000
    ) -> Iterator[list[dict[str, Any]]]:
        """Stream rows from the database in chunks.

        Filters for 'Approved' status genes only.
        Uses batched split query architecture to bound memory usage.

        Args:
            chunk_size: Number of mapped rows to yield per chunk (default: 5000)
            batch_size: Number of gene rows to process per sub-query batch (default: 5000)

        Yields:
            Iterator of lists, where each list contains up to chunk_size dictionaries
        """
        from vgnc_download_file_generator.database.queries import (
            compile_query_for_mysql,
        )
        from vgnc_download_file_generator.database.queries_split import (
            build_gene_data_query,
            fetch_sub_data_for_batch,
            merge_gene_results,
        )
        from vgnc_download_file_generator.validation import make_validator

        filters: dict[str, str | int | list[str]] = {"status": "Approved"}

        if isinstance(self.species.taxon_id, int):
            filters["taxon_id"] = self.species.taxon_id


        if self.locus_group is not None:
            filters["locus_group"] = self.locus_group

        if self.locus_type is not None:
            filters["locus_type"] = self.locus_type

        filters["status_id"] = PUBLIC_STATUS_IDS

        column_map = self._get_column_map()

        # Runtime ID-format validation (Task 4). Created per file-generation
        # run so violation counts accumulate across the whole stream.
        self._validator = make_validator()

        gene_query = build_gene_data_query(filters=filters if filters else None)
        gene_cursor = self.db.get_streaming_cursor()
        gene_sql, gene_params = compile_query_for_mysql(gene_query)
        gene_cursor.execute(gene_sql, gene_params)

        db_headers = [desc[0] for desc in gene_cursor.description] if gene_cursor.description else []

        sub_cursor = self.db.get_cursor()
        output_chunk: list[dict[str, Any]] = []
        gene_batch: list[dict[str, Any]] = []

        try:
            for row in gene_cursor:
                row_dict = dict(zip(db_headers, row, strict=False))
                gene_batch.append(row_dict)

                if len(gene_batch) >= batch_size:
                    for mapped_row in self._process_batch(
                        gene_batch, sub_cursor, column_map, compile_query_for_mysql,
                        fetch_sub_data_for_batch, merge_gene_results,
                    ):
                        output_chunk.append(mapped_row)
                        if len(output_chunk) >= chunk_size:
                            yield output_chunk
                            output_chunk = []
                    gene_batch = []

            if gene_batch:
                for mapped_row in self._process_batch(
                    gene_batch, sub_cursor, column_map, compile_query_for_mysql,
                    fetch_sub_data_for_batch, merge_gene_results,
                ):
                    output_chunk.append(mapped_row)
                    if len(output_chunk) >= chunk_size:
                        yield output_chunk
                        output_chunk = []
        finally:
            sub_cursor.close()
            gene_cursor.close()

        if output_chunk:
            yield output_chunk

    def _process_batch(
        self,
        gene_batch: list[dict[str, Any]],
        sub_cursor: Any,
        column_map: dict[str, str],
        compile_fn: Any,
        fetch_sub_fn: Any,
        merge_fn: Any,
    ) -> Iterator[dict[str, Any]]:
        """Run sub-queries for a batch of gene rows and yield mapped merged rows.

        Args:
            gene_batch: List of gene row dicts for this batch
            sub_cursor: Database cursor for sub-queries
            column_map: Mapping from database column names to output header names
            compile_fn: compile_query_for_mysql function
            fetch_sub_fn: fetch_sub_data_for_batch function
            merge_fn: merge_gene_results function

        Yields:
            Mapped and merged row dictionaries
        """
        genefam_ids = [row["genefam_id"] for row in gene_batch]
        xrefs, aliases, dates = fetch_sub_fn(genefam_ids, sub_cursor, compile_fn)
        merged = merge_fn(gene_batch, xrefs, aliases, dates)
        for merged_row in merged:
            self._validator.check(merged_row)
            yield {
                column_map.get(db_col, db_col): value
                for db_col, value in merged_row.items()
            }

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

                # Render multi-valued fields (e.g. uniprot_ids, arriving as a
                # pipe-separated GROUP_CONCAT string) as JSON arrays.
                for field in self._array_json_fields():
                    if field in obj:
                        obj[field] = self._pipe_string_to_list(obj[field])

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
