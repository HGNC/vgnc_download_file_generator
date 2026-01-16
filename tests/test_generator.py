"""Tests for BaseFileGenerator abstract class."""

from abc import ABC
from unittest.mock import MagicMock

from vgnc_download_file_generator.database.connection import DatabaseConnection
from vgnc_download_file_generator.generator import BaseFileGenerator
from vgnc_download_file_generator.models.species import SpeciesInfo


class TestBaseFileGeneratorAbstract:
    """Tests for BaseFileGenerator abstract class."""

    def test_cannot_instantiate_base_class_directly(self) -> None:
        """Test that BaseFileGenerator cannot be instantiated directly."""

        class ConcreteGenerator(BaseFileGenerator):
            """Minimal concrete implementation for testing."""

            def get_headers(self, extension: str) -> list[str]:  # noqa: ARG002
                return ["header1", "header2"]

            def stream_rows(self, chunk_size: int = 5000):  # noqa: ARG002
                return []

        # Should be able to instantiate concrete subclass
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")
        generator = ConcreteGenerator(
            db=db,
            species=species,
            chromosome="X",
            locus_group=None,
            locus_type=None,
        )

        assert generator is not None
        assert generator.species == species

    def test_is_abstract_base_class(self) -> None:
        """Test that BaseFileGenerator is an abstract base class."""
        assert issubclass(BaseFileGenerator, ABC)

    def test_get_headers_is_abstract(self) -> None:
        """Test that get_headers must be implemented by subclasses."""

        # Check that get_headers is marked as abstract
        assert hasattr(BaseFileGenerator, "get_headers")

    def test_stream_rows_is_abstract(self) -> None:
        """Test that stream_rows must be implemented by subclasses."""

        # Check that stream_rows is marked as abstract
        assert hasattr(BaseFileGenerator, "stream_rows")

    def test_init_stores_parameters(self) -> None:
        """Test that __init__ stores database and species parameters."""

        class ConcreteGenerator(BaseFileGenerator):
            """Minimal concrete implementation for testing."""

            def get_headers(self, extension: str) -> list[str]:  # noqa: ARG002
                return []

            def stream_rows(self, chunk_size: int = 5000):  # noqa: ARG002
                return []

        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = ConcreteGenerator(
            db=db,
            species=species,
            chromosome="X",
            locus_group="protein-coding gene",
            locus_type="gene with protein product",
        )

        assert generator.db == db
        assert generator.species == species
        assert generator.chromosome == "X"
        assert generator.locus_group == "protein-coding gene"
        assert generator.locus_type == "gene with protein product"


class TestGenerateFilenameMethod:
    """Tests for generate_filename method."""

    def test_generates_json_filename(self) -> None:
        """Test generate_filename for JSON files."""

        class ConcreteGenerator(BaseFileGenerator):
            def get_headers(self, extension: str) -> list[str]:  # noqa: ARG002
                return []

            def stream_rows(self, chunk_size: int = 5000):  # noqa: ARG002
                return []

        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Bolivian squirrel monkey", is_live="Y")

        generator = ConcreteGenerator(
            db=db,
            species=species,
            chromosome="X",
            locus_group=None,
            locus_type=None,
        )

        filename = generator.generate_filename("json")

        # Should match FileSpec logic for GCS path
        assert "json/" in filename
        assert "bolivian_squirrel_monkey" in filename
        assert "chrX.json" in filename

    def test_generates_txt_filename(self) -> None:
        """Test generate_filename for TXT files."""

        class ConcreteGenerator(BaseFileGenerator):
            def get_headers(self, extension: str) -> list[str]:  # noqa: ARG002
                return []

            def stream_rows(self, chunk_size: int = 5000):  # noqa: ARG002
                return []

        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="cow", is_live="Y")

        generator = ConcreteGenerator(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type="gene with protein product",
        )

        filename = generator.generate_filename("txt")

        # Should match FileSpec logic for GCS path
        assert "json/" in filename
        assert "cow/" in filename
        assert "locus_types/" in filename
        assert "gene_with_protein_product_All.txt" in filename

    def test_generates_filename_for_ensembl(self) -> None:
        """Test generate_filename for Ensembl files."""

        class ConcreteGenerator(BaseFileGenerator):
            def get_headers(self, extension: str) -> list[str]:  # noqa: ARG002
                return []

            def stream_rows(self, chunk_size: int = 5000):  # noqa: ARG002
                return []

        db = MagicMock(spec=DatabaseConnection)
        # Use "All" as taxon_id for Ensembl files
        species = SpeciesInfo(taxon_id="All", display_name="All", is_live="Y")  # type: ignore[arg-type]

        generator = ConcreteGenerator(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        filename = generator.generate_filename("txt")

        # For Ensembl (All species), should return the mapping file path
        assert "ensembl/" in filename
        assert "VGNC_to_Ensembl_mapping.txt" in filename
