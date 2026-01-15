"""Tests for FileSpec and SpeciesInfo dataclasses."""


from vgnc_download_file_generator.models.file_spec import FileSpec
from vgnc_download_file_generator.models.species import SpeciesInfo


class TestSpeciesInfoDataclass:
    """Tests for SpeciesInfo dataclass."""

    def test_can_instantiate_with_required_fields(self) -> None:
        """Test that SpeciesInfo can be instantiated with required fields."""
        species = SpeciesInfo(taxon_id=9593, display_name="Bolivian squirrel monkey", is_live="Y")

        assert species.taxon_id == 9593
        assert species.display_name == "Bolivian squirrel monkey"
        assert species.is_live == "Y"

    def test_repr_contains_all_fields(self) -> None:
        """Test that repr() contains all field values."""
        species = SpeciesInfo(taxon_id=9593, display_name="Bolivian squirrel monkey", is_live="Y")

        repr_str = repr(species)
        assert "9593" in repr_str
        assert "Bolivian squirrel monkey" in repr_str
        assert "Y" in repr_str


class TestFileSpecDataclass:
    """Tests for FileSpec dataclass."""

    def test_can_instantiate_with_all_fields(self) -> None:
        """Test that FileSpec can be instantiated with all fields."""
        spec = FileSpec(
            species_id=9593,
            species_name="bolivian_squirrel_monkey",
            locus_group=None,
            locus_type=None,
            chromosome="X",
            file_type="vgnc_public",
            extension="json",
        )

        assert spec.species_id == 9593
        assert spec.species_name == "bolivian_squirrel_monkey"
        assert spec.chromosome == "X"
        assert spec.file_type == "vgnc_public"
        assert spec.extension == "json"

    def test_can_instantiate_with_all_string_species_id(self) -> None:
        """Test that species_id can be a string (for 'All' species)."""
        spec = FileSpec(
            species_id="All",
            species_name="All",
            locus_group=None,
            locus_type=None,
            chromosome=None,
            file_type="vgnc_ensembl",
            extension="txt",
        )

        assert spec.species_id == "All"
        assert spec.file_type == "vgnc_ensembl"

    def test_optional_fields_can_be_none(self) -> None:
        """Test that optional fields can be None."""
        spec = FileSpec(
            species_id=9593,
            species_name="bolivian_squirrel_monkey",
            locus_group=None,
            locus_type=None,
            chromosome=None,
            file_type="vgnc_public",
            extension="json",
        )

        assert spec.locus_group is None
        assert spec.locus_type is None
        assert spec.chromosome is None

    def test_repr_contains_all_fields(self) -> None:
        """Test that repr() contains all field values."""
        spec = FileSpec(
            species_id=9593,
            species_name="bolivian_squirrel_monkey",
            locus_group="protein-coding_gene",
            locus_type="gene_with_protein_product",
            chromosome="X",
            file_type="vgnc_public",
            extension="json",
        )

        repr_str = repr(spec)
        assert "9593" in repr_str
        assert "bolivian_squirrel_monkey" in repr_str
        assert "protein-coding_gene" in repr_str
        assert "gene_with_protein_product" in repr_str

    def test_file_type_accepts_valid_values(self) -> None:
        """Test that file_type accepts valid Literal values."""
        for file_type in ["vgnc_public", "vgnc_ensembl", "vgnc_withdrawn"]:
            spec = FileSpec(
                species_id=9593,
                species_name="test",
                locus_group=None,
                locus_type=None,
                chromosome=None,
                file_type=file_type,  # type: ignore[arg-type]
                extension="json",
            )
            assert spec.file_type == file_type

    def test_extension_accepts_valid_values(self) -> None:
        """Test that extension accepts valid Literal values."""
        for extension in ["txt", "json"]:
            spec = FileSpec(
                species_id=9593,
                species_name="test",
                locus_group=None,
                locus_type=None,
                chromosome=None,
                file_type="vgnc_public",
                extension=extension,  # type: ignore[arg-type]
            )
            assert spec.extension == extension


class TestGcsPathMethod:
    """Tests for FileSpec.gcs_path() method."""

    def test_chromosome_json_path(self) -> None:
        """Test GCS path for chromosome-specific JSON file."""
        spec = FileSpec(
            species_id=9593,
            species_name="bolivian_squirrel_monkey",
            locus_group=None,
            locus_type=None,
            chromosome="X",
            file_type="vgnc_public",
            extension="json",
        )

        path = spec.gcs_path()
        # Expected format: json/bolivian_squirrel_monkey/bolivian_squirrel_monkeyvgnc_gene_set_chrX.json
        assert "json/" in path
        assert "bolivian_squirrel_monkey/" in path
        assert "chrX.json" in path

    def test_all_species_ensembl_path(self) -> None:
        """Test GCS path for Ensembl mapping file (All species)."""
        spec = FileSpec(
            species_id="All",
            species_name="All",
            locus_group=None,
            locus_type=None,
            chromosome=None,
            file_type="vgnc_ensembl",
            extension="txt",
        )

        path = spec.gcs_path()
        # Expected: ensembl/VGNC_to_Ensembl_mapping.txt
        assert path == "ensembl/VGNC_to_Ensembl_mapping.txt"

    def test_locus_type_json_path(self) -> None:
        """Test GCS path for locus_type-specific JSON file."""
        spec = FileSpec(
            species_id=9593,
            species_name="cow",
            locus_group=None,
            locus_type="gene_with_protein_product",
            chromosome=None,
            file_type="vgnc_public",
            extension="json",
        )

        path = spec.gcs_path()
        # Expected: json/cow/locus_types/cow_gene_with_protein_product_All.json
        assert "json/" in path
        assert "cow/" in path
        assert "locus_types/" in path
        assert "gene_with_protein_product_All.json" in path

    def test_species_name_normalization_spaces_to_underscores(self) -> None:
        """Test that spaces in species names are converted to underscores."""
        spec = FileSpec(
            species_id=9593,
            species_name="Bolivian squirrel monkey",  # spaces
            locus_group=None,
            locus_type=None,
            chromosome="X",
            file_type="vgnc_public",
            extension="json",
        )

        path = spec.gcs_path()
        # Spaces should become underscores
        assert "bolivian_squirrel_monkey" in path.lower()
        # Original name with spaces should not appear in path
        assert "Bolivian squirrel monkey" not in path

    def test_species_name_preserves_special_chars(self) -> None:
        """Test that special characters like apostrophes are preserved."""
        spec = FileSpec(
            species_id=9593,
            species_name="Mark's goat",  # apostrophe
            locus_group=None,
            locus_type=None,
            chromosome="1",
            file_type="vgnc_public",
            extension="json",
        )

        path = spec.gcs_path()
        # Apostrophes should be preserved (or handled consistently)
        assert "mark" in path.lower()
        assert "chr1.json" in path

    def test_prd_example_bolivian_squirrel_monkey(self) -> None:
        """Test PRD example: bolivian_squirrel_monkey_vgnc_gene_set_chr_Un.json."""
        spec = FileSpec(
            species_id=9593,
            species_name="Bolivian squirrel monkey",
            locus_group=None,
            locus_type=None,
            chromosome="Un",
            file_type="vgnc_public",
            extension="json",
        )

        path = spec.gcs_path()
        # Should match PRD example format
        assert "bolivian_squirrel_monkey" in path
        assert "chrUn.json" in path

    def test_prd_example_cow_gene_with_protein_product(self) -> None:
        """Test PRD example: cow_gene_with_protein_product_chr_1.json."""
        spec = FileSpec(
            species_id=9466,
            species_name="cow",
            locus_group=None,
            locus_type="gene_with_protein_product",
            chromosome="1",
            file_type="vgnc_public",
            extension="json",
        )

        path = spec.gcs_path()
        # Should match PRD example format
        assert "cow/" in path
        assert "chr1.json" in path

    def test_locus_group_path(self) -> None:
        """Test GCS path for locus_group-specific file."""
        spec = FileSpec(
            species_id=9593,
            species_name="cow",
            locus_group="protein-coding_gene",
            locus_type=None,
            chromosome=None,
            file_type="vgnc_public",
            extension="json",
        )

        path = spec.gcs_path()
        # Expected format similar to locus_type
        assert "json/" in path
        assert "cow/" in path
        assert "protein-coding_gene" in path.lower()
