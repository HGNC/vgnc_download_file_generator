"""Base file generator class for VGNC download files.

This module provides the abstract BaseFileGenerator class that defines
the interface for all file generators.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
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
