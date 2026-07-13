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
        # Headers should end with newline
        assert headers_line.endswith("\n")
        # Strip newline for comparison
        assert "\t".join(generator.get_headers("txt")) == headers_line.rstrip("\n")

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

    def test_generate_tsv_rows_includes_newlines(self) -> None:
        """Test that each TSV row ends with a newline character for proper line separation."""
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
            [{"vgnc_id": "VGNC:1", "symbol": "GENE1", "name": "Gene 1"}],
            [{"vgnc_id": "VGNC:2", "symbol": "GENE2", "name": "Gene 2"}],
        ]

        def mock_stream_rows(chunk_size=5000):  # noqa: ARG001
            return iter(test_data)

        generator.stream_rows = mock_stream_rows  # type: ignore[method-assign]

        # Generate TSV rows
        tsv_lines = list(generator.generate_tsv_rows())

        # Each line should end with a newline character
        assert len(tsv_lines) == 3, "Should have header + 2 data rows"
        assert tsv_lines[0].endswith("\n"), "Header row should end with newline"
        assert tsv_lines[1].endswith("\n"), "First data row should end with newline"
        assert tsv_lines[2].endswith("\n"), "Second data row should end with newline"

        # Verify proper line separation when concatenated
        combined = "".join(tsv_lines)
        split_lines = combined.split("\n")
        # Should have 4 lines: header, data1, data2, and empty string from trailing newline
        assert len(split_lines) == 4
        assert split_lines[0].startswith("vgnc_id")
        assert "VGNC:1" in split_lines[1]
        assert "VGNC:2" in split_lines[2]
        assert split_lines[3] == ""  # Trailing newline produces empty string


class TestVgncPublicTsvUniprotPipe:
    """TSV must keep uniprot_ids as a pipe-separated string (not arrayified)."""

    def test_tsv_uniprot_ids_remains_pipe_separated_string(self) -> None:
        """uniprot_ids arrives as a GROUP_CONCAT pipe string; TSV emits it as-is."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")
        generator = VgncPublic(
            db=db, species=species, chromosome=None, locus_group=None, locus_type=None
        )
        generator.stream_rows = lambda chunk_size=5000, batch_size=5000: iter(  # type: ignore[method-assign]  # noqa: ARG005
            [[{"vgnc_id": "VGNC:1", "uniprot_ids": "Q9H0A9|P12345"}]]
        )

        tsv_lines = list(generator.generate_tsv_rows())
        headers = generator.get_headers("txt")
        idx = headers.index("uniprot_ids")
        data_fields = tsv_lines[1].rstrip("\n").split("\t")

        assert data_fields[idx] == "Q9H0A9|P12345"

    def test_tsv_uniprot_ids_none_is_empty_cell(self) -> None:
        """A NULL uniprot_ids renders as an empty TSV cell (not 'None'/'[]')."""
        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")
        generator = VgncPublic(
            db=db, species=species, chromosome=None, locus_group=None, locus_type=None
        )
        generator.stream_rows = lambda chunk_size=5000, batch_size=5000: iter(  # type: ignore[method-assign]  # noqa: ARG005
            [[{"vgnc_id": "VGNC:1", "uniprot_ids": None}]]
        )

        tsv_lines = list(generator.generate_tsv_rows())
        headers = generator.get_headers("txt")
        idx = headers.index("uniprot_ids")
        data_fields = tsv_lines[1].rstrip("\n").split("\t")

        assert data_fields[idx] == ""
