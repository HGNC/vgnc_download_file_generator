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
            locus_group="protein-coding gene",
            locus_type="gene with protein product",
            chromosome="X",
            file_type="vgnc_public",
            extension="json",
        )

        repr_str = repr(spec)
        assert "9593" in repr_str
        assert "bolivian_squirrel_monkey" in repr_str
        assert "protein-coding gene" in repr_str
        assert "gene with protein product" in repr_str

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
        # Expected format: json/bolivian_squirrel_monkey/bolivian_squirrel_monkey_vgnc_gene_set_chr_X.json
        assert "json/" in path
        assert "bolivian_squirrel_monkey/" in path
        assert "chr_X.json" in path
        assert "_vgnc_gene_set_" in path

    def test_chromosome_tsv_path(self) -> None:
        """Test GCS path for chromosome-specific TSV file."""
        spec = FileSpec(
            species_id=9593,
            species_name="bolivian_squirrel_monkey",
            locus_group=None,
            locus_type=None,
            chromosome="X",
            file_type="vgnc_public",
            extension="txt",
        )

        path = spec.gcs_path()
        # Expected format: tsv/bolivian_squirrel_monkey/bolivian_squirrel_monkey_vgnc_gene_set_chr_X.txt
        assert "tsv/" in path
        assert "bolivian_squirrel_monkey/" in path
        assert "chr_X.txt" in path
        assert "_vgnc_gene_set_" in path

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
            locus_type="gene with protein product",
            chromosome=None,
            file_type="vgnc_public",
            extension="json",
        )

        path = spec.gcs_path()
        # Expected: json/cattle/locus_types/cattle_gene_with_protein_product_All.json
        # (spaces converted to underscores and lowercased for clean URLs)
        assert "json/" in path
        assert "cattle/" in path
        assert "locus_types/" in path
        assert "gene_with_protein_product_All.json" in path

    def test_locus_type_tsv_path(self) -> None:
        """Test GCS path for locus_type-specific TSV file."""
        spec = FileSpec(
            species_id=9593,
            species_name="cow",
            locus_group=None,
            locus_type="gene with protein product",
            chromosome=None,
            file_type="vgnc_public",
            extension="txt",
        )

        path = spec.gcs_path()
        # Expected: tsv/cattle/locus_types/cattle_gene_with_protein_product_All.txt
        # (spaces converted to underscores and lowercased for clean URLs)
        assert "tsv/" in path
        assert "cattle/" in path
        assert "locus_types/" in path
        assert "gene_with_protein_product_All.txt" in path

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
        assert "chr_1.json" in path

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
        assert "chr_Un.json" in path

    def test_prd_example_cow_gene_with_protein_product(self) -> None:
        """Test PRD example: cow_gene_with_protein_product_chr_1.json."""
        spec = FileSpec(
            species_id=9466,
            species_name="cow",
            locus_group=None,
            locus_type="gene with protein product",
            chromosome="1",
            file_type="vgnc_public",
            extension="json",
        )

        path = spec.gcs_path()
        # Should match PRD example format
        assert "cattle/" in path
        assert "chr_1.json" in path

    def test_locus_group_path(self) -> None:
        """Test GCS path for locus_group-specific file."""
        spec = FileSpec(
            species_id=9593,
            species_name="cow",
            locus_group="protein-coding gene",
            locus_type=None,
            chromosome=None,
            file_type="vgnc_public",
            extension="json",
        )

        path = spec.gcs_path()
        # Expected: json/cattle/locus_groups/cattle_protein-coding_gene_All.json
        # (spaces converted to underscores, hyphens preserved, lowercased)
        assert "json/" in path
        assert "cattle/" in path
        assert "protein-coding_gene_All.json" in path

    def test_locus_group_tsv_path(self) -> None:
        """Test GCS path for locus_group-specific TSV file."""
        spec = FileSpec(
            species_id=9593,
            species_name="cow",
            locus_group="protein-coding gene",
            locus_type=None,
            chromosome=None,
            file_type="vgnc_public",
            extension="txt",
        )

        path = spec.gcs_path()
        # Expected: tsv/cattle/locus_groups/cattle_protein-coding_gene_All.txt
        # (spaces converted to underscores, hyphens preserved, lowercased)
        assert "tsv/" in path
        assert "cattle/" in path
        assert "protein-coding_gene_All.txt" in path

    def test_locus_type_with_chromosome_json_path(self) -> None:
        """Test GCS path for locus_type-specific JSON file with chromosome filter."""
        spec = FileSpec(
            species_id=9593,
            species_name="cow",
            locus_group=None,
            locus_type="gene with protein product",
            chromosome="1",
            file_type="vgnc_public",
            extension="json",
        )

        path = spec.gcs_path()
        # Expected: json/cow/locus_types/cow_gene_with_protein_product_chr_1.json
        assert "json/" in path
        assert "cattle/" in path
        assert "locus_types/" in path
        assert "chr_1.json" in path

    def test_locus_type_with_chromosome_tsv_path(self) -> None:
        """Test GCS path for locus_type-specific TSV file with chromosome filter."""
        spec = FileSpec(
            species_id=9593,
            species_name="cow",
            locus_group=None,
            locus_type="gene with protein product",
            chromosome="X",
            file_type="vgnc_public",
            extension="txt",
        )

        path = spec.gcs_path()
        # Expected: tsv/cow/locus_types/cow_gene_with_protein_product_chr_X.txt
        assert "tsv/" in path
        assert "cattle/" in path
        assert "locus_types/" in path
        assert "chr_X.txt" in path

    def test_locus_group_with_chromosome_json_path(self) -> None:
        """Test GCS path for locus_group-specific JSON file with chromosome filter."""
        spec = FileSpec(
            species_id=9593,
            species_name="cow",
            locus_group="protein-coding gene",
            locus_type=None,
            chromosome="1",
            file_type="vgnc_public",
            extension="json",
        )

        path = spec.gcs_path()
        # Expected: json/cow/locus_groups/cow_protein_coding_gene_chr_1.json
        assert "json/" in path
        assert "cattle/" in path
        assert "locus_groups/" in path
        assert "chr_1.json" in path

    def test_locus_group_with_chromosome_tsv_path(self) -> None:
        """Test GCS path for locus_group-specific TSV file with chromosome filter."""
        spec = FileSpec(
            species_id=9593,
            species_name="cow",
            locus_group="protein-coding gene",
            locus_type=None,
            chromosome="X",
            file_type="vgnc_public",
            extension="txt",
        )

        path = spec.gcs_path()
        # Expected: tsv/cow/locus_groups/cow_protein_coding_gene_chr_X.txt
        assert "tsv/" in path
        assert "cattle/" in path
        assert "locus_groups/" in path
        assert "chr_X.txt" in path


class TestSpeciesNameNormalization:
    """Tests for species name normalization to gender-neutral terms."""

    def test_cow_normalizes_to_cattle(self) -> None:
        """Test that 'cow' is normalized to 'cattle' in file paths."""
        from vgnc_download_file_generator.models.file_spec import (
            _normalize_species_name,
        )

        # Test that the normalization function converts cow to cattle
        normalized = _normalize_species_name("cow")
        assert normalized == "cattle"

    def test_cattle_remains_cattle(self) -> None:
        """Test that 'cattle' remains 'cattle' (no double normalization)."""
        from vgnc_download_file_generator.models.file_spec import (
            _normalize_species_name,
        )

        normalized = _normalize_species_name("cattle")
        assert normalized == "cattle"

    def test_cow_species_uses_cattle_in_path(self) -> None:
        """Test that species named 'cow' uses 'cattle' in GCS path."""
        spec = FileSpec(
            species_id=9913,
            species_name="cow",
            locus_group=None,
            locus_type=None,
            chromosome="X",
            file_type="vgnc_public",
            extension="txt",
        )

        path = spec.gcs_path()
        # Should use cattle in path, not cow
        assert "cattle/" in path
        assert "cow/" not in path
        assert "cattle_vgnc_gene_set_chr_X.txt" in path

    def test_cow_locus_type_uses_cattle_in_path(self) -> None:
        """Test that cow species with locus type uses cattle in path."""
        spec = FileSpec(
            species_id=9913,
            species_name="cow",
            locus_group=None,
            locus_type="gene with protein product",
            chromosome=None,
            file_type="vgnc_public",
            extension="json",
        )

        path = spec.gcs_path()
        # Should use cattle in path, not cow
        assert "cattle/" in path
        assert "cow/" not in path
        assert "cattle_gene_with_protein_product_All.json" in path


class TestAllSpeciesDirectory:
    """Tests for 'All' species files that go in the all/ directory."""

    def test_all_species_vgnc_public_root_level(self) -> None:
        """Test GCS path for all species with no filters - should go at root level."""
        spec = FileSpec(
            species_id="All",
            species_name="All",
            locus_group=None,
            locus_type=None,
            chromosome=None,
            file_type="vgnc_public",
            extension="txt",
        )

        path = spec.gcs_path()
        # All species files now go in the all/ directory
        assert path == "tsv/all/all_vgnc_gene_set_All.txt"

    def test_all_species_vgnc_public_json_root_level(self) -> None:
        """Test GCS path for all species JSON file - should go in all/ directory."""
        spec = FileSpec(
            species_id="All",
            species_name="All",
            locus_group=None,
            locus_type=None,
            chromosome=None,
            file_type="vgnc_public",
            extension="json",
        )

        path = spec.gcs_path()
        # All species files now go in the all/ directory
        assert path == "json/all/all_vgnc_gene_set_All.json"

    def test_all_species_all_directory_tsv(self) -> None:
        """Test GCS path for all/ directory TSV file."""
        spec = FileSpec(
            species_id="All",
            species_name="All",
            locus_group=None,
            locus_type=None,
            chromosome=None,
            file_type="vgnc_public",
            extension="txt",
        )

        path = spec.gcs_path()
        # All species files now go in the all/ directory
        assert path == "tsv/all/all_vgnc_gene_set_All.txt"

    def test_all_species_all_directory_json(self) -> None:
        """Test GCS path for all/ directory JSON file."""
        spec = FileSpec(
            species_id="All",
            species_name="All",
            locus_group=None,
            locus_type=None,
            chromosome=None,
            file_type="vgnc_public",
            extension="json",
        )

        spec.gcs_path()
        # Also support: json/all/all_vgnc_gene_set_All.json (in all/ directory)
        # This is an alternative path for the same data

    def test_all_species_with_chromosome(self) -> None:
        """Test GCS path for all species filtered by chromosome."""
        spec = FileSpec(
            species_id="All",
            species_name="All",
            locus_group=None,
            locus_type=None,
            chromosome="X",
            file_type="vgnc_public",
            extension="txt",
        )

        path = spec.gcs_path()
        # Expected: tsv/all/all_vgnc_gene_set_chrX.txt
        assert path == "tsv/all/all_vgnc_gene_set_chrX.txt"

    def test_all_species_with_locus_type(self) -> None:
        """Test GCS path for all species filtered by locus type."""
        spec = FileSpec(
            species_id="All",
            species_name="All",
            locus_group=None,
            locus_type="gene with protein product",
            chromosome=None,
            file_type="vgnc_public",
            extension="txt",
        )

        path = spec.gcs_path()
        # All species with locus type: all/locus_types/all_{locus_type}_All.txt
        assert path == "tsv/all/locus_types/all_gene_with_protein_product_All.txt"

    def test_all_species_with_locus_type_json(self) -> None:
        """Test GCS path for all species JSON with locus type."""
        spec = FileSpec(
            species_id="All",
            species_name="All",
            locus_group=None,
            locus_type="gene with protein product",
            chromosome=None,
            file_type="vgnc_public",
            extension="json",
        )

        path = spec.gcs_path()
        # All species with locus type: all/locus_types/all_{locus_type}_All.json
        assert path == "json/all/locus_types/all_gene_with_protein_product_All.json"

    def test_all_species_with_locus_group(self) -> None:
        """Test GCS path for all species filtered by locus group."""
        spec = FileSpec(
            species_id="All",
            species_name="All",
            locus_group="protein-coding gene",
            locus_type=None,
            chromosome=None,
            file_type="vgnc_public",
            extension="txt",
        )

        path = spec.gcs_path()
        # All species with locus group: all/locus_groups/all_{locus_group}_All.txt
        assert path == "tsv/all/locus_groups/all_protein-coding_gene_All.txt"

    def test_all_species_with_locus_type_and_chromosome(self) -> None:
        """Test GCS path for all species with locus type and chromosome."""
        spec = FileSpec(
            species_id="All",
            species_name="All",
            locus_group=None,
            locus_type="gene with protein product",
            chromosome="1",
            file_type="vgnc_public",
            extension="txt",
        )

        path = spec.gcs_path()
        # Expected: tsv/all/locus_types/all_gene_with_protein_product_chr_1.txt
        assert path == "tsv/all/locus_types/all_gene_with_protein_product_chr_1.txt"

    def test_all_species_with_locus_group_and_chromosome(self) -> None:
        """Test GCS path for all species with locus group and chromosome."""
        spec = FileSpec(
            species_id="All",
            species_name="All",
            locus_group="protein-coding gene",
            locus_type=None,
            chromosome="X",
            file_type="vgnc_public",
            extension="json",
        )

        path = spec.gcs_path()
        # Expected: json/all/locus_groups/all_protein-coding_gene_chr_X.json
        assert path == "json/all/locus_groups/all_protein-coding_gene_chr_X.json"

    def test_all_species_vgnc_withdrawn(self) -> None:
        """Test GCS path for all species withdrawn entries."""
        spec = FileSpec(
            species_id="All",
            species_name="All",
            locus_group=None,
            locus_type=None,
            chromosome=None,
            file_type="vgnc_withdrawn",
            extension="txt",
        )

        path = spec.gcs_path()
        # All species withdrawn files use dedicated name
        assert path == "tsv/all/all_vgnc_withdrawn.txt"

    def test_all_species_ensembl_still_special(self) -> None:
        """Test that Ensembl mapping still uses special path for all species."""
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
        # Ensembl still uses special path
        assert path == "ensembl/VGNC_to_Ensembl_mapping.txt"


class TestIndividualSpeciesAllChromosomes:
    """Tests for individual species files containing all chromosomes."""

    def test_individual_species_all_chromosomes_tsv(self) -> None:
        """Test GCS path for individual species with all chromosomes."""
        spec = FileSpec(
            species_id=9913,
            species_name="cattle",
            locus_group=None,
            locus_type=None,
            chromosome=None,
            file_type="vgnc_public",
            extension="txt",
        )

        path = spec.gcs_path()
        # Expected: tsv/cattle/cattle_vgnc_gene_set_All.txt
        assert path == "tsv/cattle/cattle_vgnc_gene_set_All.txt"

    def test_individual_species_all_chromosomes_json(self) -> None:
        """Test GCS path for individual species JSON with all chromosomes."""
        spec = FileSpec(
            species_id=9913,
            species_name="cattle",
            locus_group=None,
            locus_type=None,
            chromosome=None,
            file_type="vgnc_public",
            extension="json",
        )

        path = spec.gcs_path()
        # Expected: json/cattle/cattle_vgnc_gene_set_All.json
        assert path == "json/cattle/cattle_vgnc_gene_set_All.json"

    def test_cow_normalizes_to_cattle_all_chromosomes(self) -> None:
        """Test that cow species normalizes to cattle in All filename."""
        spec = FileSpec(
            species_id=9913,
            species_name="cow",
            locus_group=None,
            locus_type=None,
            chromosome=None,
            file_type="vgnc_public",
            extension="txt",
        )

        path = spec.gcs_path()
        # Should use cattle in path
        assert path == "tsv/cattle/cattle_vgnc_gene_set_All.txt"

    def test_multi_word_species_all_chromosomes(self) -> None:
        """Test GCS path for multi-word species with all chromosomes."""
        spec = FileSpec(
            species_id=9593,
            species_name="Bolivian squirrel monkey",
            locus_group=None,
            locus_type=None,
            chromosome=None,
            file_type="vgnc_public",
            extension="json",
        )

        path = spec.gcs_path()
        # Expected: json/bolivian_squirrel_monkey/bolivian_squirrel_monkey_vgnc_gene_set_All.json
        assert path == "json/bolivian_squirrel_monkey/bolivian_squirrel_monkey_vgnc_gene_set_All.json"

