"""SQLAlchemy ORM models for VGNC database.

This module defines SQLAlchemy ORM models for key database tables
based on the schema documented in .taskmaster/docs/vgnc_public.sql.
"""

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class Species(Base):
    """ORM model for the species table.

    Attributes:
        taxon_id: Primary key - NCBI taxonomy ID
        display_name: Species display name (e.g., "Bolivian squirrel monkey")
        is_live: Species status enum (Y/N/C/T/F) - live species are Y/T/F
        genefam_prefix: VGNC prefix for this species
    """

    __tablename__ = "species"

    taxon_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    genefam_prefix: Mapped[str | None] = mapped_column(String(11))
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_live: Mapped[str] = mapped_column(
        Enum("Y", "N", "C", "T", "F", name="is_live"), default="C"
    )


class GeneStatus(Base):
    """ORM model for the gene_status table.

    Attributes:
        id: Primary key
        status: Status code (e.g., "Approved", "Entry Withdrawn")
        display: Display string for the status
    """

    __tablename__ = "gene_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(45), nullable=False)
    display: Mapped[str] = mapped_column(String(45), nullable=False)


class LocusGroup(Base):
    """ORM model for the locus_group table.

    Attributes:
        id: Primary key
        name: Locus group name (e.g., "protein-coding_gene", "pseudogene")
    """

    __tablename__ = "locus_group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(45), nullable=False)


class LocusType(Base):
    """ORM model for the locus_type table.

    Attributes:
        id: Primary key
        type: Locus type (e.g., "gene_with_protein_product", "pseudogene")
        locus_group_id: Foreign key to locus_group table
    """

    __tablename__ = "locus_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(45), nullable=False)
    locus_group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("locus_group.id"), nullable=False
    )

    # Relationship to LocusGroup
    locus_group: Mapped[LocusGroup] = relationship("LocusGroup")


class Chromosome(Base):
    """ORM model for the chromosomes table.

    Attributes:
        chr_id: Primary key
        taxon_id: Foreign key to species table
        display_name: Chromosome display name (e.g., "1", "X", "MT", "Un")
        coord_system: Coordinate system name
        refseq_accession: RefSeq accession
        genbank_accession: GenBank accession
        ensembl_accession: Ensembl accession
    """

    __tablename__ = "chromosomes"

    chr_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    taxon_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("species.taxon_id"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    coord_system: Mapped[str | None] = mapped_column(String(128))
    refseq_accession: Mapped[str | None] = mapped_column(String(128))
    genbank_accession: Mapped[str] = mapped_column(String(128), nullable=False)
    ensembl_accession: Mapped[str | None] = mapped_column(String(128))

    # Relationships
    species: Mapped[Species] = relationship("Species")
    gene_locations: Mapped[list["GeneLocation"]] = relationship(
        "GeneLocation", back_populates="chromosome"
    )


class Genefam(Base):
    """ORM model for the genefam table.

    This is the main gene families table containing VGNC gene entries.

    Attributes:
        genefam_id: Primary key
        taxon_id: Foreign key to species table
        assigned_id: VGNC ID (e.g., "VGNC:12345")
        assigned_symbol: Gene symbol
        assigned_name: Gene name
        status_id: Foreign key to gene_status table
        editor_id: Foreign key to editor table
        hcop_support_level: HCOP support level
    """

    __tablename__ = "genefam"

    genefam_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    taxon_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("species.taxon_id"), nullable=False
    )
    assigned_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    assigned_symbol: Mapped[str | None] = mapped_column(String(45))
    assigned_name: Mapped[str | None] = mapped_column(String(255))
    status_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("gene_status.id"), nullable=False
    )
    editor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    hcop_support_level: Mapped[int | None] = mapped_column(Integer)

    # Relationships
    status: Mapped[GeneStatus] = relationship("GeneStatus")
    species: Mapped[Species] = relationship("Species")


class GeneLocation(Base):
    """ORM model for the gene_location table.

    Attributes:
        id: Primary key
        chr_id: Foreign key to chromosomes table
        start: Start position
        end: End position
        strand: Strand (1 for forward, -1 for reverse)
        band: Cytogenetic band
    """

    __tablename__ = "gene_location"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chr_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chromosomes.chr_id"), nullable=False
    )
    start: Mapped[int | None] = mapped_column(Integer)
    end: Mapped[int | None] = mapped_column(Integer)
    strand: Mapped[int | None] = mapped_column(Integer)
    band: Mapped[str | None] = mapped_column(String(40))

    # Relationships
    chromosome: Mapped[Chromosome] = relationship(
        "Chromosome", back_populates="gene_locations"
    )
