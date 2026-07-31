"""VgncPublic file generator for main gene set files.

This module provides the VgncPublic generator for creating TSV and JSON
downloads of VGNC gene data with comprehensive annotations.
"""

import json
from collections.abc import Generator, Iterator
from typing import Any

from vgnc_download_file_generator.generator import PUBLIC_STATUS_IDS, BaseFileGenerator


def format_location_sortable(chromosome: str | None) -> str | None:
    """Return the chromosome formatted for lexical sorting.

    ``location_sortable`` is defined as ``location`` (the chromosome) with
    single-digit numeric chromosomes zero-padded so they sort before two-digit
    chromosomes (e.g. ``1`` -> ``01`` so ``01`` < ``18``). Only *numbered*
    chromosomes are padded; multi-digit numerics (``10``..``29``) and
    non-numeric labels (``X``, ``Y``, ``MT``, ``Un``) are returned unchanged,
    and ``None``/empty pass through unchanged. Genomic coordinates are never
    included.

    Args:
        chromosome: The chromosome display name (a.k.a. ``location``), or None.

    Returns:
        The zero-padded chromosome for single-digit numerics, else unchanged.
    """
    if not chromosome:
        return chromosome
    if len(chromosome) == 1 and chromosome.isdigit():
        return f"0{chromosome}"
    return chromosome


class VgncPublic(BaseFileGenerator):
    """Generator for VGNC Public gene set files.

    Generates TSV and JSON files with comprehensive gene annotations
    including standard VGNC fields plus special cases for 'All' species
    and Zebrafish (taxon_id 9913).
    """

    # File type identifier for this generator
    _FILE_TYPE: str = "vgnc_public"

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
        "gene_group",
        "gene_group_id",
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
            "gene_family": "gene_group",
            "gene_family_id": "gene_group_id",
            "ncbi_gene_id": "ncbi_id",
            "ensembl_gene_id": "ensembl_gene_id",
            "uniprot_ids": "uniprot_ids",
            "pubmed_id": "pubmed_id",
            "hgnc_orthologs": "hgnc_orthologs",
            "bgd_id": "bgd_id",
            "horde_id": "horde_id",
            "date_approved_reserved": "date_approved_reserved",
            "date_modified": "date_modified",
            "date_symbol_changed": "date_symbol_changed",
            "date_name_changed": "date_name_changed",
            "alias_symbol": "alias_symbol",
            "alias_name": "alias_name",
            "prev_symbol": "prev_symbol",
            "prev_name": "prev_name",
        }

    def _array_json_fields(self) -> set[str]:
        """Output headers that serialize as JSON arrays."""
        return {"uniprot_ids", "pubmed_id"}

    def get_headers(self, extension: str) -> list[str]:  # noqa: ARG002
        """Get column headers for the file format.

        Returns standard 22 headers with special cases:
        - 'All' species: adds taxon_id first
        - Cattle/Bos taurus (taxon 9913): adds bgd_id before pubmed_id

        Args:
            extension: File extension (txt or json)

        Returns:
            List of column header strings
        """
        headers = self._STANDARD_HEADERS.copy()

        # Handle 'All' species - add taxon_id first
        is_all_species = self.species.taxon_id == "All" or self.species.display_name == "All"
        if is_all_species:
            headers.insert(0, "taxon_id")

        # Handle Cattle/Bos taurus (taxon 9913) - add bgd_id before pubmed_id
        is_cattle = self.species.taxon_id == 9913
        if is_cattle:
            pubmed_idx = headers.index("pubmed_id")
            headers.insert(pubmed_idx, "bgd_id")

        return headers

    def stream_rows(
        self, chunk_size: int = 5000, batch_size: int = 5000
    ) -> Iterator[list[dict[str, Any]]]:
        """Stream rows in keyset-paginated batches on short-lived connections.

        Delegates to :meth:`BaseFileGenerator._paginate_gene_stream` -- the
        drop-safe pagination that replaced the old single long-lived
        server-side cursor (which Cloud SQL dropped mid-stream, raising
        ``MySQLdb.OperationalError (2013)`` / ``(2006)``).

        Args:
            chunk_size: Number of mapped rows to yield per chunk (default: 5000)
            batch_size: Number of distinct gene ids fetched per DB page (default: 5000)

        Yields:
            Iterator of lists, each up to chunk_size mapped row dicts
        """
        from vgnc_download_file_generator.validation import make_validator

        filters: dict[str, str | int | list[str] | list[int]] = {}

        if isinstance(self.species.taxon_id, int):
            filters["taxon_id"] = self.species.taxon_id

        if self.locus_group is not None:
            filters["locus_group"] = self.locus_group

        if self.locus_type is not None:
            filters["locus_type"] = self.locus_type

        filters["status_id"] = PUBLIC_STATUS_IDS

        # Runtime ID-format validation. Created per file-generation run so
        # violation counts accumulate across the whole stream.
        self._validator = make_validator()

        yield from self._paginate_gene_stream(
            filters, self._get_column_map(), chunk_size, batch_size
        )


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
            mapped = {
                column_map.get(db_col, db_col): value
                for db_col, value in merged_row.items()
            }
            # location_sortable is location (the chromosome) with single-digit
            # numeric chromosomes zero-padded for correct lexical sort. Derived
            # in Python, not SQL, so the rule is unit-testable and free of
            # MySQL-specific functions (CONCAT/REGEXP). See format_location_sortable.
            if "location" in mapped:
                mapped["location_sortable"] = format_location_sortable(mapped["location"])
            yield mapped

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
                # Keys are already lowercase_underscore from the database
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
