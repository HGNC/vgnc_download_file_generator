"""Tests for VgncEnsembl generator."""

import json
from unittest.mock import MagicMock

from vgnc_download_file_generator.database.connection import DatabaseConnection
from vgnc_download_file_generator.generators.vgnc_ensembl import VgncEnsembl
from vgnc_download_file_generator.models.species import SpeciesInfo


class TestVgncEnsemblGetHeaders:
    """Tests for VgncEnsembl.get_headers() method."""

    def test_returns_ensembl_specific_headers(self) -> None:
        """Test that get_headers() returns correct Ensembl headers."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncEnsembl(
            db=db,
            species=species,
            locus_group=None,
            locus_type=None,
        )

        headers = generator.get_headers("txt")

        # Verify all expected headers are present
        expected_headers = [
            "VGNC ID",
            "Approved Symbol",
            "Approved Name",
            "Previous Symbols",
            "Synonyms",
            "Entrez Gene ID",
            "Refseq IDs",
            "Entrez Gene ID(supplied by NCBI)",
            "RefSeq(supplied by NCBI)",
            "Ensembl Gene ID",
            "Uniprot ID(supplied by UniProt)",
            "Locus Specific Databases",
        ]

        assert headers == expected_headers

    def test_headers_in_correct_order(self) -> None:
        """Test that headers are in the specified order."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncEnsembl(
            db=db,
            species=species,
            locus_group=None,
            locus_type=None,
        )

        headers = generator.get_headers("txt")

        # Verify exact order
        assert headers[0] == "VGNC ID"
        assert headers[5] == "Entrez Gene ID"
        assert headers[9] == "Ensembl Gene ID"
        assert headers[-1] == "Locus Specific Databases"


class TestVgncEnsemblStreamRows:
    """VgncEnsembl.stream_rows() uses the shared drop-safe keyset paginator.

    Regression context: the Cloud Run "Server has gone away" (2013/2006)
    failure came from a long-lived server-side cursor. No generator may use
    one; the pagination mechanics are shared and covered elsewhere, so these
    tests pin only this generator's specific filters.
    """

    def _generator(self, db):
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")
        return VgncEnsembl(db=db, species=species, locus_group=None, locus_type=None)

    def test_does_not_use_streaming_cursor(self, paginating_db) -> None:
        """No server-side cursor is held open for the ensembl stream."""
        db = paginating_db([1, 2], 5)
        list(self._generator(db).stream_rows())
        db.get_streaming_cursor.assert_not_called()

    def test_filters_by_approved_status(self, paginating_db) -> None:
        """The query carries the Approved status filters."""
        db = paginating_db([1, 2], 5)
        list(self._generator(db).stream_rows())
        joined_sql = " ".join(db._cursor.executed)
        assert "gf.status_id" in joined_sql   # PUBLIC_STATUS_IDS [6, 11, 12]
        assert "gs.status" in joined_sql       # status = 'Approved'

    def test_applies_species_filter_to_query(self, paginating_db) -> None:
        """The taxon_id filter reaches the query."""
        db = paginating_db([1, 2], 5)
        list(self._generator(db).stream_rows())
        joined_sql = " ".join(db._cursor.executed)
        assert "gf.taxon_id" in joined_sql


class TestVgncEnsemblGenerateTsv:
    """Tests for VgncEnsembl TSV generation."""

    def test_generate_tsv_rows_writes_headers(self) -> None:
        """Test that generate_tsv_rows() yields header row first."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncEnsembl(
            db=db,
            species=species,
            locus_group=None,
            locus_type=None,
        )

        # Mock stream_rows to return empty
        generator.stream_rows = lambda chunk_size=5000: iter([])  # type: ignore[method-assign]  # noqa: ARG005

        # Generate TSV rows
        tsv_lines = list(generator.generate_tsv_rows())

        # Should have at least headers
        assert len(tsv_lines) >= 1

        # First line should be headers
        headers_line = tsv_lines[0]
        assert "VGNC ID" in headers_line
        assert "Ensembl Gene ID" in headers_line
        # Headers should end with newline
        assert headers_line.endswith("\n")
        # Strip newline for comparison
        assert "\t".join(generator.get_headers("txt")) == headers_line.rstrip("\n")

    def test_generate_tsv_rows_joins_fields_with_tabs(self) -> None:
        """Test that fields are joined with TAB delimiter."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncEnsembl(
            db=db,
            species=species,
            locus_group=None,
            locus_type=None,
        )

        # Mock stream_rows to return test data
        test_data = [
            [{"VGNC ID": "VGNC:12345", "Approved Symbol": "GENE1", "Ensembl Gene ID": "ENSG0001"}]
        ]

        def mock_stream_rows(chunk_size=5000):  # noqa: ARG001
            return iter(test_data)

        generator.stream_rows = mock_stream_rows  # type: ignore[method-assign]

        # Generate TSV rows
        tsv_lines = list(generator.generate_tsv_rows())

        # Second line should have data joined by tabs
        data_line = tsv_lines[1]
        assert "\t" in data_line
        assert "VGNC:12345" in data_line
        assert "GENE1" in data_line


class TestVgncEnsemblGenerateJson:
    """Tests for VgncEnsembl JSON generation."""

    def test_generate_json_rows_produces_valid_json(self) -> None:
        """Test that generate_json_rows() produces valid JSON strings."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncEnsembl(
            db=db,
            species=species,
            locus_group=None,
            locus_type=None,
        )

        # Mock stream_rows to return test data
        test_data = [
            [{"VGNC ID": "VGNC:12345", "Approved Symbol": "GENE1", "Ensembl Gene ID": "ENSG0001"}]
        ]

        def mock_stream_rows(chunk_size=5000):  # noqa: ARG001
            return iter(test_data)

        generator.stream_rows = mock_stream_rows  # type: ignore[method-assign]

        # Generate JSON rows (now yields only JSON objects)
        json_objects = list(generator.generate_json_rows())

        # Should have at least one JSON object
        assert len(json_objects) >= 1

        # Each line should be a valid JSON object
        for json_str in json_objects:
            obj = json.loads(json_str)
            assert isinstance(obj, dict)

        # Can wrap in brackets to make valid JSON array
        full_json = "[" + ",".join(json_objects) + "]"
        parsed = json.loads(full_json)
        assert isinstance(parsed, list)


class TestVgncEnsemblUniprotArray:
    """Ensembl JSON must render uniprot_ids as an array (mirrors VgncPublic)."""

    _UNIPROT = "Uniprot ID(supplied by UniProt)"

    def _generator_with(self, rows: list[dict]) -> VgncEnsembl:
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")
        gen = VgncEnsembl(db=db, species=species)
        gen.stream_rows = lambda chunk_size=5000, batch_size=5000: iter([rows])  # type: ignore[method-assign]  # noqa: ARG005
        return gen

    def test_json_uniprot_rendered_as_array(self) -> None:
        gen = self._generator_with([{"VGNC ID": "VGNC:1", self._UNIPROT: "Q9H0A9|P12345"}])
        obj = json.loads(next(gen.generate_json_rows()))
        assert obj[self._UNIPROT] == ["Q9H0A9", "P12345"]
        assert isinstance(obj[self._UNIPROT], list)

    def test_json_uniprot_single_value_is_array(self) -> None:
        gen = self._generator_with([{"VGNC ID": "VGNC:1", self._UNIPROT: "Q9H0A9"}])
        obj = json.loads(next(gen.generate_json_rows()))
        assert obj[self._UNIPROT] == ["Q9H0A9"]

    def test_json_uniprot_none_is_null(self) -> None:
        gen = self._generator_with([{"VGNC ID": "VGNC:1", self._UNIPROT: None}])
        obj = json.loads(next(gen.generate_json_rows()))
        assert obj[self._UNIPROT] is None

    def test_json_ensembl_gene_id_stays_string(self) -> None:
        """Ensembl Gene ID is NOT arrayified; it stays a plain string."""
        gen = self._generator_with([{"VGNC ID": "VGNC:1", "Ensembl Gene ID": "ENSACAG00000001234"}])
        obj = json.loads(next(gen.generate_json_rows()))
        assert obj["Ensembl Gene ID"] == "ENSACAG00000001234"
        assert isinstance(obj["Ensembl Gene ID"], str)
