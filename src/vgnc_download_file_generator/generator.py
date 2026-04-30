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


class BaseFileGenerator(ABC):
    """Abstract base class for file generators.

    Provides common functionality for generating VGNC download files,
    including filename generation and database connection management.

    Subclasses must implement get_headers() and stream_rows() methods
    to provide file-specific behavior.

    Attributes:
        db: Database connection manager
        species: Species information for the file being generated
        chromosome: Optional chromosome filter
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
        chromosome: str | None = None,
        locus_group: str | None = None,
        locus_type: str | None = None,
    ) -> None:
        """Initialize the file generator.

        Args:
            db: Database connection manager
            species: Species information for this file
            chromosome: Optional chromosome filter (e.g., "X", "1", "Un")
            locus_group: Optional locus group filter
            locus_type: Optional locus type filter
        """
        self.db = db
        self.species = species
        self.chromosome = chromosome
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
        generator's filter criteria (chromosome, locus_type, locus_group).

        Args:
            extension: File extension (e.g., "txt", "json")

        Returns:
            GCS storage path for the file

        Examples:
            >>> # Chromosome-specific file
            >>> generator.generate_filename("json")
            'json/bolivian_squirrel_monkey/bolivian_squirrel_monkeyvgnc_gene_set_chrX.json'

            >>> # Locus type-specific file
            >>> generator.generate_filename("json")
            'json/cow/locus_types/cow_gene_with_protein_product_All.json'

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
            chromosome=self.chromosome,
            file_type=file_type,  # type: ignore[arg-type]
            extension=extension,  # type: ignore[arg-type]
        )

        return spec.gcs_path()
