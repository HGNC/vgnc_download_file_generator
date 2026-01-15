"""Tests for SQLAlchemy ORM models."""

from sqlalchemy import inspect

from vgnc_download_file_generator.database.schema import (
    Chromosome,
    Genefam,
    GeneLocation,
    GeneStatus,
    LocusGroup,
    LocusType,
    Species,
)


class TestSpeciesModel:
    """Tests for Species ORM model."""

    def test_table_name_correct(self) -> None:
        """Test that Species model uses correct table name."""
        assert Species.__tablename__ == "species"

    def test_has_required_columns(self) -> None:
        """Test that Species has all required columns."""
        mapper = inspect(Species)
        columns = [c.key for c in mapper.columns]

        assert "taxon_id" in columns
        assert "display_name" in columns
        assert "is_live" in columns
        assert "genefam_prefix" in columns

    def test_primary_key_is_taxon_id(self) -> None:
        """Test that taxon_id is the primary key."""
        mapper = inspect(Species)
        primary_keys = [c.key for c in mapper.primary_key]

        assert primary_keys == ["taxon_id"]

    def test_is_live_enum_values(self) -> None:
        """Test that is_live has correct enum values."""
        mapper = inspect(Species)
        is_live_col = mapper.columns["is_live"]

        # Check enum values
        enum_type = is_live_col.type
        assert hasattr(enum_type, "enums")
        assert enum_type.enums == ["Y", "N", "C", "T", "F"]


class TestGeneStatusModel:
    """Tests for GeneStatus ORM model."""

    def test_table_name_correct(self) -> None:
        """Test that GeneStatus model uses correct table name."""
        assert GeneStatus.__tablename__ == "gene_status"

    def test_has_required_columns(self) -> None:
        """Test that GeneStatus has all required columns."""
        mapper = inspect(GeneStatus)
        columns = [c.key for c in mapper.columns]

        assert "id" in columns
        assert "status" in columns
        assert "display" in columns

    def test_primary_key_is_id(self) -> None:
        """Test that id is the primary key."""
        mapper = inspect(GeneStatus)
        primary_keys = [c.key for c in mapper.primary_key]

        assert primary_keys == ["id"]


class TestLocusGroupModel:
    """Tests for LocusGroup ORM model."""

    def test_table_name_correct(self) -> None:
        """Test that LocusGroup model uses correct table name."""
        assert LocusGroup.__tablename__ == "locus_group"

    def test_has_required_columns(self) -> None:
        """Test that LocusGroup has all required columns."""
        mapper = inspect(LocusGroup)
        columns = [c.key for c in mapper.columns]

        assert "id" in columns
        assert "name" in columns


class TestLocusTypeModel:
    """Tests for LocusType ORM model."""

    def test_table_name_correct(self) -> None:
        """Test that LocusType model uses correct table name."""
        assert LocusType.__tablename__ == "locus_type"

    def test_has_required_columns(self) -> None:
        """Test that LocusType has all required columns."""
        mapper = inspect(LocusType)
        columns = [c.key for c in mapper.columns]

        assert "id" in columns
        assert "type" in columns
        assert "locus_group_id" in columns

    def test_has_foreign_key_to_locus_group(self) -> None:
        """Test that locus_group_id is a foreign key to locus_group."""
        mapper = inspect(LocusType)
        locus_group_id_col = mapper.columns["locus_group_id"]

        # Check foreign key
        assert len(locus_group_id_col.foreign_keys) > 0
        fk = list(locus_group_id_col.foreign_keys)[0]
        assert fk.column.table.name == "locus_group"


class TestChromosomeModel:
    """Tests for Chromosome ORM model."""

    def test_table_name_correct(self) -> None:
        """Test that Chromosome model uses correct table name."""
        assert Chromosome.__tablename__ == "chromosomes"

    def test_has_required_columns(self) -> None:
        """Test that Chromosome has all required columns."""
        mapper = inspect(Chromosome)
        columns = [c.key for c in mapper.columns]

        assert "chr_id" in columns
        assert "taxon_id" in columns
        assert "display_name" in columns
        assert "coord_system" in columns

    def test_has_foreign_key_to_species(self) -> None:
        """Test that taxon_id is a foreign key to species."""
        mapper = inspect(Chromosome)
        taxon_id_col = mapper.columns["taxon_id"]

        assert len(taxon_id_col.foreign_keys) > 0


class TestGenefamModel:
    """Tests for Genefam ORM model."""

    def test_table_name_correct(self) -> None:
        """Test that Genefam model uses correct table name."""
        assert Genefam.__tablename__ == "genefam"

    def test_has_required_columns(self) -> None:
        """Test that Genefam has all required columns."""
        mapper = inspect(Genefam)
        columns = [c.key for c in mapper.columns]

        assert "genefam_id" in columns
        assert "taxon_id" in columns
        assert "assigned_id" in columns
        assert "assigned_symbol" in columns
        assert "assigned_name" in columns
        assert "status_id" in columns

    def test_has_relationship_to_status(self) -> None:
        """Test that Genefam has relationship to GeneStatus."""
        mapper = inspect(Genefam)

        assert "status" in mapper.relationships

    def test_has_foreign_key_to_gene_status(self) -> None:
        """Test that status_id is a foreign key to gene_status."""
        mapper = inspect(Genefam)
        status_id_col = mapper.columns["status_id"]

        assert len(status_id_col.foreign_keys) > 0


class TestGeneLocationModel:
    """Tests for GeneLocation ORM model."""

    def test_table_name_correct(self) -> None:
        """Test that GeneLocation model uses correct table name."""
        assert GeneLocation.__tablename__ == "gene_location"

    def test_has_required_columns(self) -> None:
        """Test that GeneLocation has all required columns."""
        mapper = inspect(GeneLocation)
        columns = [c.key for c in mapper.columns]

        assert "id" in columns
        assert "chr_id" in columns
        assert "start" in columns
        assert "end" in columns
        assert "strand" in columns
        assert "band" in columns

    def test_has_foreign_key_to_chromosome(self) -> None:
        """Test that chr_id is a foreign key to chromosomes."""
        mapper = inspect(GeneLocation)
        chr_id_col = mapper.columns["chr_id"]

        assert len(chr_id_col.foreign_keys) > 0
