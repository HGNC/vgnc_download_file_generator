"""Tests for VgncPublic TSV generation."""

from unittest.mock import MagicMock

from vgnc_download_file_generator.database.connection import DatabaseConnection
from vgnc_download_file_generator.generators.vgnc_public import VgncPublic
from vgnc_download_file_generator.models.species import SpeciesInfo


class TestVgncPublicGenerateTsv:
    """Tests for VgncPublic TSV generation."""

    def test_generate_tsv_rows_writes_headers(self) -> None:
        """Test that generate_tsv_rows() yields header row first."""
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
        generator.stream_rows = lambda chunk_size=5000: iter([])  # type: ignore[method-assign]  # noqa: ARG005

        # Generate TSV rows
        tsv_lines = list(generator.generate_tsv_rows())

        # Should have at least headers
        assert len(tsv_lines) >= 1

        # First line should be headers
        headers_line = tsv_lines[0]
        assert "vgnc_id" in headers_line
        assert "symbol" in headers_line
        assert "\t".join(generator.get_headers("txt")) == headers_line

    def test_generate_tsv_rows_joins_fields_with_tabs(self) -> None:
        """Test that fields are joined with TAB delimiter."""
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

    def test_generate_tsv_rows_handles_null_values(self) -> None:
        """Test that NULL values are converted to empty strings."""
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

        def mock_stream_rows(chunk_size=5000):  # noqa: ARG001
            return iter(test_data)

        generator.stream_rows = mock_stream_rows  # type: ignore[method-assign]

        # Generate TSV rows
        tsv_lines = list(generator.generate_tsv_rows())

        # Data line should have empty strings for None values
        data_line = tsv_lines[1]
        fields = data_line.split("\t")

        # Find the indices of vgnc_id, symbol, name, ncbi_id
        headers = generator.get_headers("txt")
        vgnc_id_idx = headers.index("vgnc_id")
        symbol_idx = headers.index("symbol")
        name_idx = headers.index("name")
        ncbi_id_idx = headers.index("ncbi_id")

        assert fields[vgnc_id_idx] == "VGNC:12345"
        assert fields[symbol_idx] == ""  # None converted to empty string
        assert fields[name_idx] == "Gene 1"
        assert fields[ncbi_id_idx] == ""  # None converted to empty string

    def test_generate_tsv_rows_handles_multiple_chunks(self) -> None:
        """Test that generate_tsv_rows() handles multiple chunks from stream."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")

        generator = VgncPublic(
            db=db,
            species=species,
            chromosome=None,
            locus_group=None,
            locus_type=None,
        )

        # Mock stream_rows to return multiple chunks
        test_data = [
            [{"vgnc_id": "VGNC:1", "symbol": "GENE1"}],
            [{"vgnc_id": "VGNC:2", "symbol": "GENE2"}],
            [{"vgnc_id": "VGNC:3", "symbol": "GENE3"}],
        ]

        def mock_stream_rows(chunk_size=5000):  # noqa: ARG001
            return iter(test_data)

        generator.stream_rows = mock_stream_rows  # type: ignore[method-assign]

        # Generate TSV rows
        tsv_lines = list(generator.generate_tsv_rows())

        # Should have headers + 3 data rows
        assert len(tsv_lines) == 4
        assert "VGNC:1" in tsv_lines[1]
        assert "VGNC:2" in tsv_lines[2]
        assert "VGNC:3" in tsv_lines[3]

    def test_generate_tsv_rows_returns_generator(self) -> None:
        """Test that generate_tsv_rows() returns a generator for streaming."""
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
        generator.stream_rows = lambda chunk_size=5000: iter([])  # type: ignore[method-assign]  # noqa: ARG005

        # Generate TSV rows
        result = generator.generate_tsv_rows()

        # Should return a generator
        assert isinstance(result, Generator)

    def test_generate_tsv_rows_preserves_unicode(self) -> None:
        """Test that TSV generation preserves UTF-8 unicode characters."""
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

        def mock_stream_rows(chunk_size=5000):  # noqa: ARG001
            return iter(test_data)

        generator.stream_rows = mock_stream_rows  # type: ignore[method-assign]

        # Generate TSV rows
        tsv_lines = list(generator.generate_tsv_rows())

        # Data line should preserve unicode characters
        data_line = tsv_lines[1]
        assert "CAFÉ" in data_line
        assert "Café Gene" in data_line
