"""Tests for VgncPublic.stream_rows() method."""
import contextlib
import os
import random
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest

from vgnc_download_file_generator.database.connection import DatabaseConnection
from vgnc_download_file_generator.generators.vgnc_public import VgncPublic
from vgnc_download_file_generator.models.species import SpeciesInfo


def _no_compile(*_args, **_kwargs):
    """Stand-in for compile_query_for_mysql (unused when fetch_sub is mocked)."""
    return "", ()


class TestVgncPublicStreamRows:
    """stream_rows() delegates to the shared, drop-safe keyset paginator.

    Regression guard for the Cloud Run "Server has gone away" (2013/2006)
    failure: no generator may hold one server-side cursor open for the whole
    stream. These cover the pagination mechanics once for the shared
    ``BaseFileGenerator._paginate_gene_stream``; the per-generator stream tests
    only assert their own filters.
    """

    def _generator(self, db: Any, taxon_id: int = 9593) -> VgncPublic:
        species = SpeciesInfo(taxon_id=taxon_id, display_name="Test Species", is_live="Y")
        return VgncPublic(db=db, species=species, locus_group=None, locus_type=None)

    def test_stream_rows_does_not_use_streaming_cursor(self, paginating_db) -> None:
        """No server-side cursor may be held open for the gene stream."""
        db = paginating_db([1, 2, 3], 2)
        gen = self._generator(db)
        list(gen.stream_rows(chunk_size=5000, batch_size=2))

        db.get_streaming_cursor.assert_not_called()

    def test_stream_rows_checks_out_connection_per_batch(self, paginating_db) -> None:
        """A fresh connection is checked out per page and returned to the pool."""
        db = paginating_db([1, 2, 3], 2)
        gen = self._generator(db)
        list(gen.stream_rows(chunk_size=5000, batch_size=2))

        # Pages served: [1,2] then [3] (short -> loop stops, no empty page
        # query) => 2 checkouts, and each was returned to the pool.
        assert db.get_connection.call_count == 2
        for conn in db._conns:
            assert conn.close.called, "connection was not returned to the pool"

    def test_stream_rows_paginates_all_rows_in_order(self, paginating_db) -> None:
        """Every gene is yielded exactly once, ascending, with no gaps/dupes."""
        db = paginating_db([1, 2, 3, 4, 5], 2)
        gen = self._generator(db)
        chunks = list(gen.stream_rows(chunk_size=100, batch_size=2))

        ids = [row["vgnc_id"] for chunk in chunks for row in chunk]
        assert ids == ["VGNC:1", "VGNC:2", "VGNC:3", "VGNC:4", "VGNC:5"]


    def test_stream_rows_advances_keyset_after_id(
        self, paginating_db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The paginator must advance after_genefam_id across pages (no infinite loop)."""
        from vgnc_download_file_generator.database import queries_split

        real = queries_split.build_gene_id_page_query
        recorded: list = []

        def spy(filters=None, after_genefam_id=None, limit=None):  # type: ignore[no-untyped-def]
            recorded.append(after_genefam_id)
            return real(filters=filters, after_genefam_id=after_genefam_id, limit=limit)

        monkeypatch.setattr(queries_split, "build_gene_id_page_query", spy)

        db = paginating_db([1, 2, 3, 4, 5], 2)
        list(self._generator(db).stream_rows(chunk_size=100, batch_size=2))

        # Pages: [1,2] (after=None), [3,4] (after=2), [5] (after=4).
        assert recorded == [None, 2, 4]

    def test_stream_rows_empty_dataset_yields_nothing(self, paginating_db) -> None:
        """An empty result set yields no chunks and still releases its connection."""
        db = paginating_db([], 5)
        chunks = list(self._generator(db).stream_rows(chunk_size=100, batch_size=5))

        assert chunks == []
        assert db.get_connection.call_count == 1  # one page query -> empty -> stop
        for conn in db._conns:
            assert conn.close.called, "connection was not returned to the pool"

    def test_stream_rows_exact_multiple_termination(self, paginating_db) -> None:
        """A count exactly divisible by batch_size terminates via one trailing empty page."""
        db = paginating_db([1, 2, 3, 4], 2)
        chunks = list(self._generator(db).stream_rows(chunk_size=100, batch_size=2))

        ids = [row["vgnc_id"] for chunk in chunks for row in chunk]
        assert ids == ["VGNC:1", "VGNC:2", "VGNC:3", "VGNC:4"]
        # Full pages [1,2],[3,4] then an empty page -> 3 checkouts.
        assert db.get_connection.call_count == 3


class TestVgncPublicRuntimeValidation:
    """Runtime ID-format validation wired into _process_batch (Task 4)."""

    def _generator(self, mode="strict", grace=5):
        from vgnc_download_file_generator.validation import RecordValidator

        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")
        gen = VgncPublic(db=db, species=species)
        gen._validator = RecordValidator(mode=mode, grace=grace)  # type: ignore[attr-defined]
        return gen

    def test_process_batch_raises_on_systematic_swap(self) -> None:
        """A swapped xref column (ncbi holds Ensembl values) must abort the batch."""
        from vgnc_download_file_generator.database.queries_split import (
            merge_gene_results,
        )

        gene_batch = [{"genefam_id": i, "assigned_id": f"VGNC:{i}"} for i in range(10)]
        # Simulate the original bug: ncbi_gene_id holds Ensembl IDs.
        swapped_xrefs = [
            {"genefam_id": i, "ncbi_gene_id": f"ENSG00000{i:06d}", "ensembl_gene_id": str(i)}
            for i in range(10)
        ]
        def fetch_sub(_ids, _cur, _cfn):
            return (swapped_xrefs, [], [])

        gen = self._generator(mode="strict", grace=5)
        column_map = gen._get_column_map()

        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            list(
                gen._process_batch(
                    gene_batch, MagicMock(), column_map, _no_compile,
                    fetch_sub, merge_gene_results,
                )
            )

    def test_process_batch_passes_valid_records(self) -> None:
        """Well-formed records stream through without raising."""
        from vgnc_download_file_generator.database.queries_split import (
            merge_gene_results,
        )

        gene_batch = [{"genefam_id": i, "assigned_id": f"VGNC:{i}"} for i in range(20)]
        valid_xrefs = [
            {"genefam_id": i, "ncbi_gene_id": str(i), "ensembl_gene_id": f"ENSG00000{i:06d}"}
            for i in range(20)
        ]
        def fetch_sub(_ids, _cur, _cfn):
            return (valid_xrefs, [], [])

        gen = self._generator(mode="strict", grace=0)
        column_map = gen._get_column_map()

        rows = list(
            gen._process_batch(
                gene_batch, MagicMock(), column_map, lambda *_a, **_k: ("", ()),
                fetch_sub, merge_gene_results,
            )
        )
        assert len(rows) == 20


class TestVgncPublicLocationSortable:
    """_process_batch must derive location_sortable from the chromosome (Spec Task 6)."""

    def _generator(self):
        from vgnc_download_file_generator.validation import RecordValidator

        db = MagicMock(spec=DatabaseConnection)
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")
        gen = VgncPublic(db=db, species=species)
        gen._validator = RecordValidator(mode="strict", grace=50)  # type: ignore[attr-defined]
        return gen

    def test_process_batch_derives_padded_location_sortable(self) -> None:
        """Single-digit chrom is padded; two-digit and X unchanged; no coordinates."""
        from vgnc_download_file_generator.database.queries_split import (
            merge_gene_results,
        )

        gene_batch = [
            {"genefam_id": 1, "assigned_id": "VGNC:1", "chromosome": "5"},
            {"genefam_id": 2, "assigned_id": "VGNC:2", "chromosome": "18"},
            {"genefam_id": 3, "assigned_id": "VGNC:3", "chromosome": "X"},
        ]

        def fetch_sub(_ids, _cur, _cfn):
            return ([], [], [])

        gen = self._generator()
        column_map = gen._get_column_map()
        rows = list(
            gen._process_batch(
                gene_batch, MagicMock(), column_map, _no_compile,
                fetch_sub, merge_gene_results,
            )
        )
        by_id = {r["vgnc_id"]: r for r in rows}

        assert by_id["VGNC:1"]["location"] == "5"
        assert by_id["VGNC:1"]["location_sortable"] == "05"
        assert by_id["VGNC:2"]["location"] == "18"
        assert by_id["VGNC:2"]["location_sortable"] == "18"
        assert by_id["VGNC:3"]["location"] == "X"
        assert by_id["VGNC:3"]["location_sortable"] == "X"

    def test_process_batch_locationless_gene_has_none_location_sortable(self) -> None:
        """A gene with no location emits None for both location and location_sortable."""
        from vgnc_download_file_generator.database.queries_split import (
            merge_gene_results,
        )

        gene_batch = [{"genefam_id": 1, "assigned_id": "VGNC:1", "chromosome": None}]

        def fetch_sub(_ids, _cur, _cfn):
            return ([], [], [])

        gen = self._generator()
        column_map = gen._get_column_map()
        rows = list(
            gen._process_batch(
                gene_batch, MagicMock(), column_map, _no_compile,
                fetch_sub, merge_gene_results,
            )
        )

        assert rows[0]["location"] is None
        assert rows[0]["location_sortable"] is None


@pytest.mark.integration
class TestVgncPublicStreamRowsPaginationIntegration:
    """Keyset-pagination parity against a real MySQL (connection-drop fix).

    Drives the real ``stream_rows`` keyset loop through a real
    ``DatabaseConnection`` against an ephemeral schema. Proves the walk covers
    every gene exactly once (plus preserves family-join fan-out), in ascending
    ``genefam_id`` page order, with the taxon filter honoured -- i.e. no gaps,
    no dupes, no cross-page splits. (The sub-queries are stubbed; the gene-data
    SQL access path -- the thing that changed -- is what matters here.)

    Requires a local MySQL reachable via ``MYSQL_TEST_DSN`` (default
    ``root:root@127.0.0.1:3306``); skipped unless ``--integration`` is passed.
    """

    @pytest.fixture
    def mysql_stream_db(self, monkeypatch: pytest.MonkeyPatch) -> Iterator[DatabaseConnection]:
        import MySQLdb as _mysql

        from vgnc_download_file_generator.config import DatabaseConfig

        dsn = os.environ.get("MYSQL_TEST_DSN", "root:root@127.0.0.1:3306")
        creds, hostport = dsn.rsplit("@", 1)
        user, passwd = creds.split(":", 1)
        host, port = hostport.split(":", 1)
        schema = f"test_vgnc_stream_{os.getpid()}_{random.randint(1000, 9999)}"

        admin = _mysql.connect(host=host, user=user, passwd=passwd, port=int(port))
        cur = admin.cursor()
        try:
            cur.execute(f"CREATE DATABASE `{schema}`")
            cur.execute(f"USE `{schema}`")
            # Gene-data query tables (LEFT JOINs -> empty stubs are fine except
            # where we seed fan-out). Columns match what the SELECT references.
            for stmt in (
                "CREATE TABLE genefam (genefam_id INT PRIMARY KEY, taxon_id INT, "
                "assigned_id VARCHAR(28), assigned_symbol VARCHAR(64), "
                "assigned_name VARCHAR(255), status_id INT)",
                "CREATE TABLE gene_status (id INT PRIMARY KEY, status VARCHAR(32))",
                "CREATE TABLE gene_has_locus_type (genefam_id INT, locus_type_id INT)",
                "CREATE TABLE locus_type (id INT PRIMARY KEY, type VARCHAR(32), locus_group_id INT)",
                "CREATE TABLE locus_group (id INT PRIMARY KEY, name VARCHAR(64))",
                "CREATE TABLE gene_has_location (gene_id INT, location_id INT, assembly_id INT)",
                "CREATE TABLE gene_location (id INT PRIMARY KEY, chr_id INT, "
                "start INT, `end` INT, strand INT, band VARCHAR(32))",
                "CREATE TABLE chromosomes (chr_id INT PRIMARY KEY, taxon_id INT, display_name VARCHAR(32))",
                "CREATE TABLE assembly (id INT PRIMARY KEY, taxon_id INT, is_vgnc_default INT, is_current INT)",
                "CREATE TABLE assembly_has_chr (assembly_id INT, chr_id INT)",
                "CREATE TABLE gene_has_family (genefam_id INT, family_id INT)",
                "CREATE TABLE family_new (id INT PRIMARY KEY, name VARCHAR(64))",
            ):
                cur.execute(stmt)

            cur.executemany("INSERT INTO gene_status VALUES (%s, %s)",
                            [(6, "Approved"), (11, "Approved-N"), (12, "Approved-M")])
            # Seven genes for taxon 9593 (status_id in PUBLIC_STATUS_IDS [6,11,12]),
            # ascending genefam_id. Gene 103 will fan out to two families.
            cur.executemany(
                "INSERT INTO genefam VALUES (%s, 9593, %s, %s, %s, 6)",
                [(gid, f"VGNC:{gid}", f"SYM{gid}", f"Name {gid}") for gid in range(101, 108)],
            )
            # Cross-taxon gene that the taxon filter MUST exclude.
            cur.execute("INSERT INTO genefam VALUES (201, 9999, 'VGNC:201', 'SYM201', 'Name 201', 6)")
            # Family fan-out for gene 103 -> two family rows.
            cur.executemany("INSERT INTO family_new VALUES (%s, %s)", [(1, "FamA"), (2, "FamB")])
            cur.executemany("INSERT INTO gene_has_family VALUES (%s, %s)", [(103, 1), (103, 2)])
            admin.commit()

            # Sub-queries are out of scope for this access-path test: stub them
            # so we don't need the xref/alias/date tables. stream_rows imports
            # fetch_sub_data_for_batch from the module at call time.
            monkeypatch.setattr(
                "vgnc_download_file_generator.database.queries_split.fetch_sub_data_for_batch",
                lambda _ids, _cur, _fn: ([], [], []),
            )

            db = DatabaseConnection(
                DatabaseConfig(
                    dbhost=host, dbuser=user, dbpasswd=passwd, dbport=int(port), dbname=schema
                )
            )
            try:
                yield db
            finally:
                db._pool.dispose()  # type: ignore[attr-defined]
        finally:
            with contextlib.suppress(Exception):
                cur.execute(f"DROP DATABASE IF EXISTS `{schema}`")
            cur.close()
            admin.close()

    def test_keyset_pagination_covers_all_genes_in_order(
        self, mysql_stream_db: DatabaseConnection
    ) -> None:
        """Pagination yields each gene once, ascending, with fan-out preserved."""
        species = SpeciesInfo(taxon_id=9593, display_name="Test Species", is_live="Y")
        gen = VgncPublic(db=mysql_stream_db, species=species, locus_group=None, locus_type=None)

        # batch_size=3 over 7 genes -> pages [101,102,103],[104,105,106],[107].
        rows = [row for chunk in gen.stream_rows(chunk_size=100, batch_size=3) for row in chunk]
        ids = [row["vgnc_id"] for row in rows]

        # Every target-taxon gene present, exactly once (103 twice via fan-out).
        assert sorted(set(ids)) == [f"VGNC:{gid}" for gid in range(101, 108)]
        assert ids.count("VGNC:103") == 2
        # 7 unique genes + 1 family-fan-out row for gene 103.
        assert len(ids) == 8
        # Cross-taxon gene excluded by the taxon filter.
        assert "VGNC:201" not in ids
        # Pages arrive in ascending keyset order (collapse the 103 duplicate).
        seen: list[str] = []
        for vid in ids:
            if not seen or seen[-1] != vid:
                seen.append(vid)
        assert seen == [f"VGNC:{gid}" for gid in range(101, 108)]
