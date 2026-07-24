"""Tests for VgncPublic file generator."""

from unittest.mock import MagicMock

from vgnc_download_file_generator.database.connection import DatabaseConnection
from vgnc_download_file_generator.generators.vgnc_public import VgncPublic
from vgnc_download_file_generator.models.species import SpeciesInfo


class TestVgncPublicGenerateFilename:
    """Tests for VgncPublic.generate_filename() method."""

    def test_all_species_generates_root_level_tsv_path(self) -> None:
        """Test that 'All' species generates tsv/all/all_vgnc_gene_set_All.txt path."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id="All", display_name="All", is_live="Y")  # type: ignore[arg-type]

        generator = VgncPublic(
            db=db,
            species=species,
            locus_group=None,
            locus_type=None,
        )

        filename = generator.generate_filename("txt")

        # Should generate all/ directory path for all species
        assert filename == "tsv/all/all_vgnc_gene_set_All.txt"

    def test_all_species_generates_root_level_json_path(self) -> None:
        """Test that 'All' species generates json/all/all_vgnc_gene_set_All.json path."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id="All", display_name="All", is_live="Y")  # type: ignore[arg-type]

        generator = VgncPublic(
            db=db,
            species=species,
            locus_group=None,
            locus_type=None,
        )

        filename = generator.generate_filename("json")

        # Should generate all/ directory path for all species
        assert filename == "json/all/all_vgnc_gene_set_All.json"

    def test_all_species_does_not_generate_ensembl_path(self) -> None:
        """Test that VgncPublic with 'All' species does NOT generate ensembl path."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id="All", display_name="All", is_live="Y")  # type: ignore[arg-type]

        generator = VgncPublic(
            db=db,
            species=species,
            locus_group=None,
            locus_type=None,
        )

        filename = generator.generate_filename("txt")

        # Should NOT be the Ensembl mapping path
        assert filename != "ensembl/VGNC_to_Ensembl_mapping.txt"
        # Should not contain 'ensembl' at all
        assert "ensembl" not in filename.lower()

    def test_individual_species_all_genes_generates_correct_path(self) -> None:
        """Test that individual species all-genes file path is correct."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9913, display_name="cattle", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            locus_group=None,
            locus_type=None,
        )

        filename = generator.generate_filename("txt")

        # Should generate species-specific all-genes path
        assert "tsv/cattle/" in filename
        assert "_All.txt" in filename


class TestVgncPublicGetHeaders:
    """Tests for VgncPublic.get_headers() method."""

    def test_standard_headers_for_normal_species(self) -> None:
        """Test that standard headers are returned for normal species."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Bolivian squirrel monkey", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            locus_group=None,
            locus_type=None,
        )

        headers = generator.get_headers("txt")

        # Should have 24 standard headers
        assert len(headers) == 24

        # Check key headers are present
        assert "vgnc_id" in headers
        assert "symbol" in headers
        assert "name" in headers
        assert "locus_group" in headers
        assert "locus_type" in headers
        assert "status" in headers
        assert "location" in headers
        assert "location_sortable" in headers
        assert "alias_symbol" in headers
        assert "alias_name" in headers
        assert "prev_symbol" in headers
        assert "prev_name" in headers
        assert "gene_group" in headers
        assert "gene_group_id" in headers
        assert "date_approved_reserved" in headers
        assert "date_symbol_changed" in headers
        assert "date_name_changed" in headers
        assert "date_modified" in headers
        assert "ncbi_id" in headers
        assert "ensembl_gene_id" in headers
        assert "uniprot_ids" in headers
        assert "pubmed_id" in headers
        assert "horde_id" in headers
        assert "hgnc_orthologs" in headers

    def test_all_species_adds_taxon_id_first(self) -> None:
        """Test that 'All' species adds taxon_id as first column."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id="All", display_name="All", is_live="Y")  # type: ignore[arg-type]

        generator = VgncPublic(
            db=db,
            species=species,
            locus_group=None,
            locus_type=None,
        )

        headers = generator.get_headers("txt")

        # Should have 25 headers (24 standard + taxon_id)
        assert len(headers) == 25

        # taxon_id should be first
        assert headers[0] == "taxon_id"

        # Check that vgnc_id is now second
        assert headers[1] == "vgnc_id"

    def test_all_species_does_not_include_primary_db_id(self) -> None:
        """primary_db_id must not be shipped in TSV or JSON for any species."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id="All", display_name="All", is_live="Y")  # type: ignore[arg-type]

        generator = VgncPublic(
            db=db,
            species=species,
            locus_group=None,
            locus_type=None,
        )

        headers = generator.get_headers("txt")
        assert "primary_db_id" not in headers
        # Last header is the final standard column, not primary_db_id.
        assert headers[-1] == "hgnc_orthologs"

    def test_zebrafish_adds_bgd_id_before_pubmed_id(self) -> None:
        """Test that Zebrafish (taxon 9913) adds bgd_id before pubmed_id."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9913, display_name="Zebrafish", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            locus_group=None,
            locus_type=None,
        )

        headers = generator.get_headers("txt")

        # Should have 25 headers (24 standard + bgd_id)
        assert len(headers) == 25

        # Find pubmed_id index
        pubmed_idx = headers.index("pubmed_id")

        # bgd_id should be immediately before pubmed_id
        assert headers[pubmed_idx - 1] == "bgd_id"

    def test_json_extension_returns_same_headers(self) -> None:
        """Test that JSON extension returns the same headers as TSV."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            locus_group=None,
            locus_type=None,
        )

        txt_headers = generator.get_headers("txt")
        json_headers = generator.get_headers("json")

        # Headers should be the same regardless of extension
        assert txt_headers == json_headers

    def test_combined_all_and_zebrafish(self) -> None:
        """Test headers for 'All' species with Zebrafish taxon (should have all extras)."""
        # This is an edge case - 'All' species with taxon_id as string
        # Zebrafish detection should still work
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9913, display_name="All", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            locus_group=None,
            locus_type=None,
        )

        headers = generator.get_headers("txt")

        # Should detect both 'All' species and Zebrafish
        # 24 standard + taxon_id + bgd_id = 26
        assert len(headers) == 26

        # taxon_id should be first
        assert headers[0] == "taxon_id"

        # bgd_id should be before pubmed_id
        pubmed_idx = headers.index("pubmed_id")
        assert headers[pubmed_idx - 1] == "bgd_id"

        # Last header is the final standard column, not primary_db_id.
        assert headers[-1] == "hgnc_orthologs"


class TestFormatLocationSortable:
    """location_sortable = location (chromosome) with only single-digit numeric
    chromosomes zero-padded; multi-digit numerics and non-numeric labels are
    unchanged. Coordinates must never appear. (Spec Task 6.)"""

    def test_pads_single_digit_numerics(self) -> None:
        from vgnc_download_file_generator.generators.vgnc_public import (
            format_location_sortable,
        )

        for chromosome, expected in [("1", "01"), ("2", "02"), ("5", "05"), ("9", "09")]:
            assert format_location_sortable(chromosome) == expected

    def test_leaves_two_digit_numerics_unchanged(self) -> None:
        from vgnc_download_file_generator.generators.vgnc_public import (
            format_location_sortable,
        )

        for chromosome in ["10", "11", "18", "22", "29"]:
            assert format_location_sortable(chromosome) == chromosome

    def test_leaves_non_numeric_labels_unchanged(self) -> None:
        """X, Y, MT and scaffold labels are NOT numbered, so never padded."""
        from vgnc_download_file_generator.generators.vgnc_public import (
            format_location_sortable,
        )

        for chromosome in ["X", "Y", "MT", "Un", "Un0001", "Z"]:
            assert format_location_sortable(chromosome) == chromosome

    def test_never_appends_coordinates(self) -> None:
        """Regression guard: no ':' or start coordinate may appear in the value."""
        from vgnc_download_file_generator.generators.vgnc_public import (
            format_location_sortable,
        )

        for chromosome in ["1", "5", "18", "X", "MT"]:
            value = format_location_sortable(chromosome)
            assert value is not None
            assert ":" not in value
            # Value must be the chromosome (optionally zero-padded), never a
            # coordinate like "5:101040473".
            assert value.endswith(chromosome)

    def test_passes_none_and_empty_through(self) -> None:
        from vgnc_download_file_generator.generators.vgnc_public import (
            format_location_sortable,
        )

        assert format_location_sortable(None) is None
        assert format_location_sortable("") == ""
