"""Dataclass for species information.

This module provides a simple dataclass for representing species information
retrieved from the VGNC database.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SpeciesInfo:
    """Species information from the VGNC database.

    Attributes:
        taxon_id: NCBI taxonomy ID for the species
        display_name: Display name of the species (e.g., "Bolivian squirrel monkey")
        is_live: Species status from the database (Y/N/C/T/F)
    """

    taxon_id: int
    display_name: str
    is_live: str
