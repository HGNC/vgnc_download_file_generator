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

    def get_headers(self, extension: str) -> list[str]:  # noqa: ARG002
        """Get column headers for the file format.

        Returns standard 22 headers with special cases:
        - 'All' species: adds taxon_id first and primary_db_id last
        - Zebrafish (taxon 9913): adds bgd_id before pubmed_id

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

        # Handle Zebrafish (taxon 9913) - add bgd_id before pubmed_id
        is_zebrafish = self.species.taxon_id == 9913
        if is_zebrafish:
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

        # Execute the query
        cursor.execute(query)

        # Get column names from cursor description
        # cursor.description is a sequence of (name, type_code, ...) tuples
        headers = [desc[0] for desc in cursor.description] if cursor.description else []

        # Stream rows using the stream_gene_data utility
        yield from stream_gene_data(cursor, headers, chunk_size)

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
        Produces an array of objects with lowercase_underscore keys matching TSV headers.

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
                # Keys are already lowercase_underscore from the database
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
