"""Tests for VgncPublic JSON generation."""

import json
from unittest.mock import MagicMock

from vgnc_download_file_generator.database.connection import DatabaseConnection
from vgnc_download_file_generator.generators.vgnc_public import VgncPublic
from vgnc_download_file_generator.models.species import SpeciesInfo


class TestVgncPublicGenerateJson:
    """Tests for VgncPublic JSON generation."""

    def test_generate_json_rows_produces_valid_json(self) -> None:
        """Test that generate_json_rows() produces valid JSON strings."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock stream_rows to return test data
        test_data = [
            [{"vgnc_id": "VGNC:12345", "symbol": "GENE1", "name": "Gene 1"}]
        ]

        def mock_stream_rows(_chunk_size=5000):
            return iter(test_data)

        generator.stream_rows = mock_stream_rows  # type: ignore[method-assign]

        # Generate JSON rows (now yields only JSON objects, no brackets)
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

    def test_json_keys_are_lowercase_underscore(self) -> None:
        """Test that JSON keys use lowercase_underscore format."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock stream_rows to return test data
        test_data = [
            [{"vgnc_id": "VGNC:12345", "symbol": "GENE1", "name": "Gene 1", "ncbi_id": "12345"}]
        ]

        def mock_stream_rows(_chunk_size=5000):
            return iter(test_data)

        generator.stream_rows = mock_stream_rows  # type: ignore[method-assign]

        # Generate JSON rows (now yields only JSON objects)
        json_objects = list(generator.generate_json_rows())

        # Parse the first JSON object to check keys
        obj = json.loads(json_objects[0])

        # Check that keys are lowercase_underscore
        # Check some expected keys
        assert "vgnc_id" in obj
        assert "symbol" in obj
        assert "name" in obj
        assert "ncbi_id" in obj

    def test_json_field_values_match_tsv_headers(self) -> None:
        """Test that JSON fields match the TSV header values."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock stream_rows to return test data
        test_data = [
            [
                {
                    "vgnc_id": "VGNC:12345",
                    "symbol": "TEST1",
                    "name": "Test Gene",
                    "status": "Approved",
                }
            ]
        ]

        def mock_stream_rows(_chunk_size=5000):
            return iter(test_data)

        generator.stream_rows = mock_stream_rows  # type: ignore[method-assign]

        # Generate JSON rows (now yields only JSON objects)
        json_objects = list(generator.generate_json_rows())

        # Wrap in brackets and join with commas to make valid JSON array
        if json_objects:
            json_str = "[" + ",".join(json_objects) + "]"
            data = json.loads(json_str)

            if data:
                obj = data[0]
                assert obj["vgnc_id"] == "VGNC:12345"
                assert obj["symbol"] == "TEST1"
                assert obj["name"] == "Test Gene"
                assert obj["status"] == "Approved"

    def test_handles_null_values_in_json(self) -> None:
        """Test that NULL values are handled correctly in JSON."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock stream_rows to return data with None values
        test_data = [
            [{"vgnc_id": "VGNC:12345", "symbol": None, "name": "Gene 1", "ncbi_id": None}]
        ]

        def mock_stream_rows(_chunk_size=5000):
            return iter(test_data)

        generator.stream_rows = mock_stream_rows  # type: ignore[method-assign]

        # Generate JSON rows (now yields only JSON objects)
        json_objects = list(generator.generate_json_rows())

        # Wrap in brackets and join with commas to make valid JSON array
        if json_objects:
            json_str = "[" + ",".join(json_objects) + "]"
            data = json.loads(json_str)

            if data:
                obj = data[0]
                # None values should be null in JSON
                assert obj["vgnc_id"] == "VGNC:12345"
                assert obj["symbol"] is None
                assert obj["name"] == "Gene 1"
                assert obj["ncbi_id"] is None

    def test_handles_multiple_rows(self) -> None:
        """Test that JSON generation handles multiple rows correctly."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock stream_rows to return multiple rows
        test_data = [
            [
                {"vgnc_id": "VGNC:1", "symbol": "GENE1"},
                {"vgnc_id": "VGNC:2", "symbol": "GENE2"},
                {"vgnc_id": "VGNC:3", "symbol": "GENE3"},
            ]
        ]

        def mock_stream_rows(_chunk_size=5000):
            return iter(test_data)

        generator.stream_rows = mock_stream_rows  # type: ignore[method-assign]

        # Generate JSON rows (now yields only JSON objects)
        json_objects = list(generator.generate_json_rows())

        # Wrap in brackets and join with commas to make valid JSON array
        json_str = "[" + ",".join(json_objects) + "]"
        data = json.loads(json_str)

        # Should have 3 objects
        assert len(data) == 3
        assert data[0]["symbol"] == "GENE1"
        assert data[1]["symbol"] == "GENE2"
        assert data[2]["symbol"] == "GENE3"

    def test_json_uses_generator_for_streaming(self) -> None:
        """Test that generate_json_rows() returns a generator for streaming."""
        from collections.abc import Generator

        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock stream_rows to return empty
        generator.stream_rows = lambda _chunk_size=5000: iter([])  # type: ignore[method-assign]

        # Generate JSON rows
        result = generator.generate_json_rows()

        # Should return a generator
        assert isinstance(result, Generator)

    def test_special_case_columns_included(self) -> None:
        """Test that special case columns (taxon_id, bgd_id, primary_db_id) are included."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9913, display_name="Zebrafish", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock stream_rows to return data with zebrafish columns
        test_data = [
            [
                {
                    "vgnc_id": "VGNC:12345",
                    "symbol": "GENE1",
                    "bgd_id": "ZDB-GENE-12345",  # Zebrafish special column
                    "pubmed_id": "12345678",
                }
            ]
        ]

        def mock_stream_rows(_chunk_size=5000):
            return iter(test_data)

        generator.stream_rows = mock_stream_rows  # type: ignore[method-assign]

        # Generate JSON rows (now yields only JSON objects)
        json_objects = list(generator.generate_json_rows())

        # Wrap in brackets and join with commas to make valid JSON array
        if json_objects:
            json_str = "[" + ",".join(json_objects) + "]"
            data = json.loads(json_str)

            if data:
                obj = data[0]
                # Should have bgd_id for zebrafish
                assert "bgd_id" in obj
                assert obj["bgd_id"] == "ZDB-GENE-12345"

    def test_empty_dataset_produces_empty_array(self) -> None:
        """Test that empty dataset produces empty JSON array."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock stream_rows to return empty
        generator.stream_rows = lambda _chunk_size=5000: iter([])  # type: ignore[method-assign]

        # Generate JSON rows (now yields only JSON objects, no brackets)
        json_objects = list(generator.generate_json_rows())

        # Should have no objects when stream is empty
        assert len(json_objects) == 0

    def test_unicode_preserved_in_json(self) -> None:
        """Test that unicode characters are preserved in JSON output."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock stream_rows to return data with unicode
        test_data = [
            [{"vgnc_id": "VGNC:12345", "symbol": "CAFÉ", "name": "Café Gene"}]
        ]

        def mock_stream_rows(_chunk_size=5000):
            return iter(test_data)

        generator.stream_rows = mock_stream_rows  # type: ignore[method-assign]

        # Generate JSON rows (now yields only JSON objects)
        json_objects = list(generator.generate_json_rows())

        # Wrap in brackets and join with commas to make valid JSON array
        if json_objects:
            json_str = "[" + ",".join(json_objects) + "]"
            data = json.loads(json_str)

            if data:
                obj = data[0]
                # Unicode should be preserved
                assert obj["symbol"] == "CAFÉ"
                assert obj["name"] == "Café Gene"

    def test_date_objects_converted_to_iso_strings(self) -> None:
        """Test that date objects are converted to ISO format strings for JSON."""
        from datetime import date

        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock stream_rows to return test data with date objects
        test_date = date(2024, 1, 15)
        test_data = [
            [{"vgnc_id": "VGNC:12345", "symbol": "GENE1", "name": "Gene 1", "date_approved": test_date}]
        ]

        def mock_stream_rows(_chunk_size=5000):
            return iter(test_data)

        generator.stream_rows = mock_stream_rows  # type: ignore[method-assign]

        # Also mock get_headers to include date_approved
        original_headers = generator.get_headers("txt")
        generator.get_headers = lambda _ext: original_headers + ["date_approved"]  # type: ignore[method-assign]

        # Generate JSON objects
        json_objects = list(generator.generate_json_rows())

        # Date should be serialized as ISO format string
        obj = json.loads(json_objects[0])
        assert obj["date_approved"] == "2024-01-15"
        assert isinstance(obj["date_approved"], str)


class TestVgncPublicUniprotArray:
    """uniprot_ids must render as a JSON array; ensembl_gene_id stays a string."""

    def _generator_with(self, rows: list[dict]) -> VgncPublic:
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")
        gen = VgncPublic(db=db, species=species, chromosome=None, locus_group=None, locus_type=None)
        gen.stream_rows = lambda _chunk_size=5000, _batch_size=5000: iter([rows])  # type: ignore[method-assign]
        return gen

    def test_json_uniprot_ids_rendered_as_array(self) -> None:
        """A pipe-separated GROUP_CONCAT string becomes a JSON array."""
        gen = self._generator_with([{"vgnc_id": "VGNC:1", "uniprot_ids": "Q9H0A9|P12345"}])
        obj = json.loads(next(gen.generate_json_rows()))
        assert obj["uniprot_ids"] == ["Q9H0A9", "P12345"]
        assert isinstance(obj["uniprot_ids"], list)

    def test_json_uniprot_ids_single_value_is_array(self) -> None:
        """A single UniProt ID is still wrapped in a one-element array."""
        gen = self._generator_with([{"vgnc_id": "VGNC:1", "uniprot_ids": "Q9H0A9"}])
        obj = json.loads(next(gen.generate_json_rows()))
        assert obj["uniprot_ids"] == ["Q9H0A9"]

    def test_json_uniprot_ids_none_is_null(self) -> None:
        """No UniProt data (NULL from GROUP_CONCAT) stays JSON null, consistent
        with other scalar fields."""
        gen = self._generator_with([{"vgnc_id": "VGNC:1", "uniprot_ids": None}])
        obj = json.loads(next(gen.generate_json_rows()))
        assert obj["uniprot_ids"] is None

    def test_json_uniprot_ids_empty_string_is_empty_array(self) -> None:
        """An empty string round-trips to an empty array."""
        gen = self._generator_with([{"vgnc_id": "VGNC:1", "uniprot_ids": ""}])
        obj = json.loads(next(gen.generate_json_rows()))
        assert obj["uniprot_ids"] == []

    def test_json_ensembl_gene_id_stays_string(self) -> None:
        """ensembl_gene_id must NOT be arrayified; it stays a plain string."""
        gen = self._generator_with([{"vgnc_id": "VGNC:1", "ensembl_gene_id": "ENSACAG00000001234"}])
        obj = json.loads(next(gen.generate_json_rows()))
        assert obj["ensembl_gene_id"] == "ENSACAG00000001234"
        assert isinstance(obj["ensembl_gene_id"], str)

class TestVgncPublicPubmedArray:
    """pubmed_id must render as a JSON array (a gene may have several refs)."""

    def _generator_with(self, rows: list[dict]) -> VgncPublic:
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")
        gen = VgncPublic(db=db, species=species, chromosome=None, locus_group=None, locus_type=None)
        gen.stream_rows = lambda _chunk_size=5000, _batch_size=5000: iter([rows])  # type: ignore[method-assign]
        return gen

    def test_json_pubmed_id_rendered_as_array(self) -> None:
        """A pipe-separated GROUP_CONCAT string becomes a JSON array."""
        gen = self._generator_with([{"vgnc_id": "VGNC:1", "pubmed_id": "40407593|123"}])
        obj = json.loads(next(gen.generate_json_rows()))
        assert obj["pubmed_id"] == ["40407593", "123"]
        assert isinstance(obj["pubmed_id"], list)

    def test_json_pubmed_id_single_value_is_array(self) -> None:
        """A single PubMed ID is still wrapped in a one-element array."""
        gen = self._generator_with([{"vgnc_id": "VGNC:1", "pubmed_id": "40407593"}])
        obj = json.loads(next(gen.generate_json_rows()))
        assert obj["pubmed_id"] == ["40407593"]

    def test_json_pubmed_id_none_is_null(self) -> None:
        """No PubMed data (NULL from GROUP_CONCAT) stays JSON null."""
        gen = self._generator_with([{"vgnc_id": "VGNC:1", "pubmed_id": None}])
        obj = json.loads(next(gen.generate_json_rows()))
        assert obj["pubmed_id"] is None

    def test_json_pubmed_id_empty_string_is_empty_array(self) -> None:
        """An empty string round-trips to an empty array."""
        gen = self._generator_with([{"vgnc_id": "VGNC:1", "pubmed_id": ""}])
        obj = json.loads(next(gen.generate_json_rows()))
        assert obj["pubmed_id"] == []
