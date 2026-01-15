"""Dataclass for file specification with GCS path construction.

This module provides the FileSpec dataclass for defining download file
specifications and constructing GCS storage paths.
"""

from dataclasses import dataclass
from typing import Literal


def _normalize_species_name(name: str) -> str:
    """Normalize species name for use in file paths.

    Converts spaces to underscores while preserving special characters
    like apostrophes.

    Args:
        name: Raw species display name

    Returns:
        Normalized species name with spaces replaced by underscores

    Examples:
        >>> _normalize_species_name("Bolivian squirrel monkey")
        'bolivian_squirrel_monkey'
        >>> _normalize_species_name("Mark's goat")
        "mark's_goat"
    """
    # Convert to lowercase and replace spaces with underscores
    # Keep special characters like apostrophes
    return name.lower().replace(" ", "_")


@dataclass(frozen=True)
class FileSpec:
    """File specification for VGNC download files.

    Defines the parameters for a download file and provides methods to
    construct the corresponding GCS storage path.

    Attributes:
        species_id: Species taxonomy ID (int) or 'All' for combined files
        species_name: Display name of the species (e.g., "Bolivian squirrel monkey")
        locus_group: Optional locus group filter (e.g., "protein-coding_gene")
        locus_type: Optional locus type filter (e.g., "gene_with_protein_product")
        chromosome: Optional chromosome filter (e.g., "X", "1", "Un")
        file_type: Type of file (vgnc_public, vgnc_ensembl, or vgnc_withdrawn)
        extension: File extension (txt or json)
    """

    species_id: int | str
    species_name: str
    locus_group: str | None
    locus_type: str | None
    chromosome: str | None
    file_type: Literal["vgnc_public", "vgnc_ensembl", "vgnc_withdrawn"]
    extension: Literal["txt", "json"]

    def gcs_path(self) -> str:
        """Construct the GCS storage path for this file specification.

        Builds the appropriate path based on the file_type and filter criteria.
        Handles special cases like 'All' species for combined files and
        normalizes species names for use in paths.

        Returns:
            GCS path string for the file

        Examples:
            >>> # Chromosome-specific JSON file
            >>> FileSpec(
            ...     species_id=9593,
            ...     species_name="Bolivian squirrel monkey",
            ...     locus_group=None,
            ...     locus_type=None,
            ...     chromosome="X",
            ...     file_type="vgnc_public",
            ...     extension="json",
            ... ).gcs_path()
            'json/bolivian_squirrel_monkey/bolivian_squirrel_monkeyvgnc_gene_set_chrX.json'

            >>> # Ensembl mapping file
            >>> FileSpec(
            ...     species_id="All",
            ...     species_name="All",
            ...     locus_group=None,
            ...     locus_type=None,
            ...     chromosome=None,
            ...     file_type="vgnc_ensembl",
            ...     extension="txt",
            ... ).gcs_path()
            'ensembl/VGNC_to_Ensembl_mapping.txt'

            >>> # Locus type-specific file
            >>> FileSpec(
            ...     species_id=9466,
            ...     species_name="cow",
            ...     locus_group=None,
            ...     locus_type="gene_with_protein_product",
            ...     chromosome=None,
            ...     file_type="vgnc_public",
            ...     extension="json",
            ... ).gcs_path()
            'json/cow/locus_types/cow_gene_with_protein_product_All.json'
        """
        # Special case for Ensembl mapping file (all species)
        if self.file_type == "vgnc_ensembl" and self.species_id == "All":
            return "ensembl/VGNC_to_Ensembl_mapping.txt"

        normalized_name = _normalize_species_name(self.species_name)

        # Build path based on filter criteria
        if self.chromosome is not None:
            # Chromosome-specific file: json/{species}/{species}vgnc_gene_set_chr{chromosome}.{ext}
            filename = f"{normalized_name}vgnc_gene_set_chr{self.chromosome}.{self.extension}"
            return f"json/{normalized_name}/{filename}"

        if self.locus_type is not None:
            # Locus type-specific file: json/{species}/locus_types/{species}_{locus_type}_All.{ext}
            filename = f"{normalized_name}_{self.locus_type}_All.{self.extension}"
            return f"json/{normalized_name}/locus_types/{filename}"

        if self.locus_group is not None:
            # Locus group-specific file: json/{species}/locus_groups/{species}_{locus_group}_All.{ext}
            filename = f"{normalized_name}_{self.locus_group}_All.{self.extension}"
            return f"json/{normalized_name}/locus_groups/{filename}"

        # Default: species-specific file with no chromosome filter
        # This shouldn't normally happen in practice, but provide a sensible default
        filename = f"{normalized_name}_all.{self.extension}"
        return f"json/{normalized_name}/{filename}"
