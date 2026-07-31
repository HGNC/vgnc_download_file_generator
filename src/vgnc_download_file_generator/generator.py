"""Base file generator class for VGNC download files.

This module provides the abstract BaseFileGenerator class that defines
the interface for all file generators.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import suppress
from typing import Any

from vgnc_download_file_generator.database.connection import DatabaseConnection
from vgnc_download_file_generator.models.file_spec import FileSpec
from vgnc_download_file_generator.models.species import SpeciesInfo

# gene_status ids that select which genes appear in each download file.
# Verified against the vgnc_public_2026_07_05 snapshot and pinned by
# tests/test_query_data_contracts.py::TestCodeAssumptionsMatchRealDictionary.
# Public + Ensembl files: the Approved-family statuses (display = 'Approved').
PUBLIC_STATUS_IDS: list[int] = [6, 11, 12]
# Withdrawn file: the withdrawn statuses.
WITHDRAWN_STATUS_IDS: list[int] = [2, 3]

logger = logging.getLogger(__name__)

FilterValue = str | int | list[str] | list[int]


class BaseFileGenerator(ABC):
    """Abstract base class for file generators.

    Provides common functionality for generating VGNC download files,
    including filename generation and database connection management.

    Subclasses must implement get_headers() and stream_rows() methods
    to provide file-specific behavior.

    Attributes:
        db: Database connection manager
        species: Species information for the file being generated
        locus_group: Optional locus group filter
        locus_type: Optional locus type filter
        _FILE_TYPE: The file type identifier for this generator (overridden by subclasses)
    """

    # Subclasses should override this with their file type
    _FILE_TYPE: str = "vgnc_public"

    def __init__(
        self,
        db: DatabaseConnection,
        species: SpeciesInfo,
        locus_group: str | None = None,
        locus_type: str | None = None,
    ) -> None:
        """Initialize the file generator.

        Args:
            db: Database connection manager
            species: Species information for this file
            locus_group: Optional locus group filter
            locus_type: Optional locus type filter
        """
        self.db = db
        self.species = species
        self.locus_group = locus_group
        self.locus_type = locus_type

    @abstractmethod
    def get_headers(self, extension: str) -> list[str]:
        """Get column headers for the file format.

        Args:
            extension: File extension (e.g., "txt", "json")

        Returns:
            List of column header strings
        """

    @abstractmethod
    def stream_rows(
        self, chunk_size: int = 5000, use_streaming: bool = True
    ) -> Iterator[list[dict[str, Any]]]:
        """Stream rows from the database in chunks.

        Yields batches of rows to avoid loading all data into memory.
        Each batch is a list of dictionaries mapping column names to values.

        Args:
            chunk_size: Number of rows to fetch per batch (default: 5000)
            use_streaming: If True, use server-side cursor for large result sets.
                        If False, use regular cursor for smaller, faster queries.

        Yields:
            Iterator of lists, where each list contains chunk_size dictionaries
        """

    def _paginate_gene_stream(
        self,
        filters: dict[str, FilterValue],
        column_map: dict[str, str],
        chunk_size: int = 5000,
        batch_size: int = 5000,
    ) -> Iterator[list[dict[str, Any]]]:
        """Stream gene rows in keyset-paginated batches on short-lived connections.

        Shared by every generator's ``stream_rows``. Walks ``genefam_id`` in
        bounded pages (``gf.genefam_id > last_id ORDER BY gf.genefam_id LIMIT
        batch_size``), fetching the full row set plus the xrefs/aliases/dates
        sub-queries for one page at a time on a connection that is returned to
        the pool *before* the chunk is yielded upstream.

        This replaces a single long-lived server-side cursor that pinned one
        MySQL connection open for the whole export and was dropped mid-stream
        by Cloud SQL (``MySQLdb.OperationalError (2013)`` / ``(2006)``). Holding
        the connection only for the few seconds of DB reads -- never during the
        GCS upload -- keeps every connection well inside any idle timeout, so
        the drop can no longer happen. (Connection *checkout* is already
        retry-wrapped in ``DatabaseConnection``; a mid-page transient query
        failure would still abort the run, but that window is now seconds, not
        minutes -- and Cloud Run Jobs retry the whole task.)

        ``genefam_id`` is the ``genefam`` PK, so pagination is stable and
        lossless: a gene's rows share one id, so advancing past the last id in
        a page never splits or skips a gene.

        Args:
            filters: Gene filters (taxon_id / locus / status / status_id).
            column_map: DB-column -> output-header mapping for ``_process_batch``.
            chunk_size: Number of mapped rows to yield per chunk.
            batch_size: Number of distinct gene ids fetched per DB page.

        Yields:
            Iterator of lists, each up to ``chunk_size`` mapped row dicts.
        """
        from vgnc_download_file_generator.database.queries import (
            compile_query_for_mysql,
        )
        from vgnc_download_file_generator.database.queries_split import (
            build_gene_data_query,
            build_gene_id_page_query,
            fetch_sub_data_for_batch,
            merge_gene_results,
        )

        filt = filters if filters else None
        output_chunk: list[dict[str, Any]] = []
        after_genefam_id: int | None = None
        page_index = 0
        total_rows = 0

        while True:
            # Short-lived connection for this page's DB reads. The `try`
            # starts immediately after checkout so a failure in `conn.cursor()`
            # still returns the connection to the pool. The connection is
            # released here *before* the chunk is yielded upstream, so no
            # connection sits idle during the (slow) GCS upload.
            conn = self.db.get_connection()
            cursor = None
            try:
                cursor = conn.cursor()

                # 1) Keyset id page: distinct genefam_ids > last, ordered, limited.
                page_sql, page_params = compile_query_for_mysql(
                    build_gene_id_page_query(
                        filters=filt,
                        after_genefam_id=after_genefam_id,
                        limit=batch_size,
                    )
                )
                cursor.execute(page_sql, page_params)
                page_ids = [row[0] for row in cursor.fetchall()]
                if not page_ids:
                    break

                # 2) Full gene rows for this page (no LIMIT; preserves any
                #    family-join fan-out exactly as before).
                gene_sql, gene_params = compile_query_for_mysql(
                    build_gene_data_query(filters=filt, genefam_ids=page_ids)
                )
                cursor.execute(gene_sql, gene_params)
                db_headers = (
                    [desc[0] for desc in cursor.description] if cursor.description else []
                )
                gene_batch = [
                    dict(zip(db_headers, row, strict=False)) for row in cursor.fetchall()
                ]

                # 3) Sub-queries + merge + map + validation, materialised while
                #    the connection is held so it can be released before yield.
                mapped_rows = list(
                    self._process_batch(  # type: ignore[attr-defined]
                        gene_batch,
                        cursor,
                        column_map,
                        compile_query_for_mysql,
                        fetch_sub_data_for_batch,
                        merge_gene_results,
                    )
                )
            finally:
                if cursor is not None:
                    with suppress(Exception):
                        cursor.close()
                conn.close()

            page_index += 1
            total_rows += len(mapped_rows)
            logger.info(
                "%s: fetched page %d (after_id=%s, %d gene ids, %d rows emitted so far)",
                self._FILE_TYPE,
                page_index,
                after_genefam_id,
                len(page_ids),
                total_rows,
            )

            for mapped_row in mapped_rows:
                output_chunk.append(mapped_row)
                if len(output_chunk) >= chunk_size:
                    yield output_chunk
                    output_chunk = []

            after_genefam_id = page_ids[-1]
            if len(page_ids) < batch_size:
                break

        if output_chunk:
            yield output_chunk

    def generate_filename(self, extension: str) -> str:
        """Generate the GCS path for this file specification.

        Uses FileSpec to construct the appropriate path based on the
        generator's filter criteria (locus_type, locus_group).

        Args:
            extension: File extension (e.g., "txt", "json")

        Returns:
            GCS storage path for the file

        Examples:
            >>> # Species all-genes file
            >>> generator.generate_filename("json")
            'json/bolivian_squirrel_monkey/bolivian_squirrel_monkey_vgnc_gene_set_All.json'

            >>> # Locus type-specific file
            >>> generator.generate_filename("json")
            'json/cattle/locus_types/cattle_gene_with_protein_product_All.json'

            >>> # Ensembl mapping file (all species)
            >>> generator.generate_filename("txt")
            'ensembl/VGNC_to_Ensembl_mapping.txt'
        """
        # Use the generator's file type from class attribute
        file_type = self._FILE_TYPE

        # Create FileSpec and get path
        spec = FileSpec(
            species_id=self.species.taxon_id,
            species_name=self.species.display_name,
            locus_group=self.locus_group,
            locus_type=self.locus_type,
            file_type=file_type,  # type: ignore[arg-type]
            extension=extension,  # type: ignore[arg-type]
        )

        return spec.gcs_path()

    def _array_json_fields(self) -> set[str]:
        """Return the set of output header names that serialize as JSON arrays.

        Subclasses override this for multi-valued fields (e.g. ``uniprot_ids``,
        which arrives as a pipe-separated GROUP_CONCAT string). The default is
        an empty set, so scalar-only generators are unaffected.

        Returns:
            Set of output header names to render as JSON arrays
        """
        return set()

    @staticmethod
    def _pipe_string_to_list(value: Any) -> list[str] | None:
        """Convert a pipe-separated string (SQL GROUP_CONCAT) into a list.

        - ``None`` stays ``None`` (preserves JSON null for missing data, matching
          the treatment of other scalar fields).
        - An empty string becomes an empty list.
        - Otherwise the string is split on ``|`` and empty segments dropped.

        Args:
            value: A pipe-separated string, None, or (already) a list

        Returns:
            None, an empty list, or a list of non-empty string segments
        """
        if value is None:
            return None
        if isinstance(value, list):
            return value
        if value == "":
            return []
        return [part for part in str(value).split("|") if part]
