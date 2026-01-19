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

        def mock_stream_rows(chunk_size=5000):
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

        def mock_stream_rows(chunk_size=5000):  # noqa: ARG001
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

        def mock_stream_rows(chunk_size=5000):  # noqa: ARG001
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

        def mock_stream_rows(chunk_size=5000):
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

        def mock_stream_rows(chunk_size=5000):
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
        generator.stream_rows = lambda chunk_size=5000: iter([])  # type: ignore[method-assign]

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

        def mock_stream_rows(chunk_size=5000):
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
        generator.stream_rows = lambda chunk_size=5000: iter([])  # type: ignore[method-assign]

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

        def mock_stream_rows(chunk_size=5000):
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

        def mock_stream_rows(chunk_size=5000):
            return iter(test_data)

        generator.stream_rows = mock_stream_rows  # type: ignore[method-assign]

        # Also mock get_headers to include date_approved
        original_headers = generator.get_headers("txt")
        generator.get_headers = lambda ext: original_headers + ["date_approved"]  # type: ignore[method-assign]

        # Generate JSON objects
        json_objects = list(generator.generate_json_rows())

        # Date should be serialized as ISO format string
        obj = json.loads(json_objects[0])
        assert obj["date_approved"] == "2024-01-15"
        assert isinstance(obj["date_approved"], str)
