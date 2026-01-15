"""Tests for VgncPublic file generator."""

from unittest.mock import MagicMock

from vgnc_download_file_generator.database.connection import DatabaseConnection
from vgnc_download_file_generator.generators.vgnc_public import VgncPublic
from vgnc_download_file_generator.models.species import SpeciesInfo


class TestVgncPublicGetHeaders:
    """Tests for VgncPublic.get_headers() method."""

    def test_standard_headers_for_normal_species(self) -> None:
        """Test that standard headers are returned for normal species."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Bolivian squirrel monkey", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome="X",
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
        assert "gene_family" in headers
        assert "gene_family_id" in headers
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
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        headers = generator.get_headers("txt")

        # Should have 26 headers (24 standard + taxon_id + primary_db_id)
        assert len(headers) == 26

        # taxon_id should be first
        assert headers[0] == "taxon_id"

        # Check that vgnc_id is now second
        assert headers[1] == "vgnc_id"

    def test_all_species_adds_primary_db_id_last(self) -> None:
        """Test that 'All' species adds primary_db_id as last column."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id="All", display_name="All", is_live="Y")  # type: ignore[arg-type]

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        headers = generator.get_headers("txt")

        # primary_db_id should be last
        assert headers[-1] == "primary_db_id"

    def test_zebrafish_adds_bgd_id_before_pubmed_id(self) -> None:
        """Test that Zebrafish (taxon 9913) adds bgd_id before pubmed_id."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9913, display_name="Zebrafish", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome=None,
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
            chromosome=None,
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
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        headers = generator.get_headers("txt")

        # Should detect both 'All' species and Zebrafish
        # 24 standard + taxon_id + primary_db_id + bgd_id = 27
        assert len(headers) == 27

        # taxon_id should be first
        assert headers[0] == "taxon_id"

        # bgd_id should be before pubmed_id
        pubmed_idx = headers.index("pubmed_id")
        assert headers[pubmed_idx - 1] == "bgd_id"

        # primary_db_id should be last
        assert headers[-1] == "primary_db_id"
