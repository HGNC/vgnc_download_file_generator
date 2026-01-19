"""Dataclass for file specification with GCS path construction.

This module provides the FileSpec dataclass for defining download file
specifications and constructing GCS storage paths.
"""

from dataclasses import dataclass
from typing import Literal


def _normalize_species_name(name: str) -> str:
    """Normalize species name for use in file paths.

    Converts spaces to underscores while preserving special characters
    like apostrophes. Also normalizes gender-specific terms to gender-neutral
    equivalents (e.g., "cow" -> "cattle").

    Args:
        name: Raw species display name

    Returns:
        Normalized species name with spaces replaced by underscores and
        gender-specific terms converted to gender-neutral equivalents

    Examples:
        >>> _normalize_species_name("Bolivian squirrel monkey")
        'bolivian_squirrel_monkey'
        >>> _normalize_species_name("Mark's goat")
        "mark's_goat"
        >>> _normalize_species_name("cow")
        'cattle'
        >>> _normalize_species_name("cattle")
        'cattle'
    """
    # Normalize gender-specific terms to gender-neutral equivalents
    # This mapping converts common gender-specific species names to their
    # gender-neutral forms for more inclusive file naming
    gender_neutral_mapping = {
        "cow": "cattle",
    }

    # Check if the name (case-insensitive) matches a gender-specific term
    name_lower = name.lower()
    if name_lower in gender_neutral_mapping:
        return gender_neutral_mapping[name_lower]

    # Convert to lowercase and replace spaces with underscores
    # Keep special characters like apostrophes
    return name_lower.replace(" ", "_")


@dataclass(frozen=True)
class FileSpec:
    """File specification for VGNC download files.

    Defines the parameters for a download file and provides methods to
    construct the corresponding GCS storage path.

    Attributes:
        species_id: Species taxonomy ID (int) or 'All' for combined files
        species_name: Display name of the species (e.g., "Bolivian squirrel monkey")
        locus_group: Optional locus group filter (e.g., "protein-coding gene")
        locus_type: Optional locus type filter (e.g., "gene with protein product")
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

            >>> # Chromosome-specific TSV file
            >>> FileSpec(
            ...     species_id=9593,
            ...     species_name="Bolivian squirrel monkey",
            ...     locus_group=None,
            ...     locus_type=None,
            ...     chromosome="X",
            ...     file_type="vgnc_public",
            ...     extension="txt",
            ... ).gcs_path()
            'tsv/bolivian_squirrel_monkey/bolivian_squirrel_monkeyvgnc_gene_set_chrX.txt'

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

            >>> # Locus type-specific JSON file
            >>> FileSpec(
            ...     species_id=9466,
            ...     species_name="cow",
            ...     locus_group=None,
            ...     locus_type="gene with protein product",
            ...     chromosome=None,
            ...     file_type="vgnc_public",
            ...     extension="json",
            ... ).gcs_path()
            'json/cow/locus_types/cow_gene_with_protein_product_All.json'
        """
        # Special case for Ensembl mapping file (all species)
        if self.file_type == "vgnc_ensembl" and self.species_id == "All":
            return "ensembl/VGNC_to_Ensembl_mapping.txt"

        # Determine subdirectory based on file extension
        subdir = "json" if self.extension == "json" else "tsv"

        normalized_name = _normalize_species_name(self.species_name)

        # Build path based on filter criteria
        # Check locus_type first (highest priority)
        if self.locus_type is not None:
            # Convert spaces to underscores for clean URLs
            locus_type_normalized = self.locus_type.replace(" ", "_")
            if self.chromosome is not None:
                # Locus type + chromosome: {species}_{locus_type}_chr_{chromosome}.{ext}
                filename = f"{normalized_name}_{locus_type_normalized}_chr_{self.chromosome}.{self.extension}"
            else:
                # Locus type all chromosomes: {species}_{locus_type}_All.{ext}
                filename = f"{normalized_name}_{locus_type_normalized}_All.{self.extension}"
            return f"{subdir}/{normalized_name}/locus_types/{filename}"

        # Check locus_group next
        if self.locus_group is not None:
            # Convert spaces and hyphens to underscores for clean URLs
            locus_group_normalized = self.locus_group.replace(" ", "_").replace("-", "_")
            if self.chromosome is not None:
                # Locus group + chromosome: {species}_{locus_group}_chr_{chromosome}.{ext}
                filename = f"{normalized_name}_{locus_group_normalized}_chr_{self.chromosome}.{self.extension}"
            else:
                # Locus group all chromosomes: {species}_{locus_group}_All.{ext}
                filename = f"{normalized_name}_{locus_group_normalized}_All.{self.extension}"
            return f"{subdir}/{normalized_name}/locus_groups/{filename}"

        # Chromosome-only (no locus filter)
        if self.chromosome is not None:
            # Chromosome-specific file: {subdir}/{species}/{species}_vgnc_gene_set_chr_{chromosome}.{ext}
            filename = f"{normalized_name}_vgnc_gene_set_chr_{self.chromosome}.{self.extension}"
            return f"{subdir}/{normalized_name}/{filename}"

        # Default: species-specific file with no chromosome filter
        # This shouldn't normally happen in practice, but provide a sensible default
        filename = f"{normalized_name}_all.{self.extension}"
        return f"{subdir}/{normalized_name}/{filename}"
