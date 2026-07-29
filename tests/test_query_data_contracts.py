"""Real-data contract + behavioral cross-checks for the query layer.

The prev_symbol/prev_name bug was caused by a hardcoded literal ('Previous')
that did not exist in the database. This module guards the *whole family* of
such assumptions: the ``db_name`` values, ``status_id`` lists, ``field_changed``
values, and ``nomenclature_type`` values that the SQL embeds.

Two layers of defence:

1. **Contract tests** -- load the real lookup tables from the
   vgnc_public_2026_07_05 snapshot and assert every value the code depends on
   actually exists (catches *database drift*, e.g. a status_id renumbered or a
   db_name renamed).
2. **Behavioral cross-checks** -- run the REAL query (with its embedded
   literals) against real data and compare to an independent Python
   re-derivation. These are the primary guards: a wrong literal routes data to
   the wrong column and the oracle disagrees.

Integration tests need MySQL (MySQL-only GROUP_CONCAT) and are gated behind
``--integration`` via ``MYSQL_TEST_DSN`` (default ``root:root@127.0.0.1:3306``).
"""

import os
import random
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from vgnc_download_file_generator.database.queries_split import (
    build_dates_query,
    build_xrefs_query,
)
from vgnc_download_file_generator.generator import (
    PUBLIC_STATUS_IDS,
    WITHDRAWN_STATUS_IDS,
)

_FIX = Path(__file__).parent / "fixtures"
_DICT_FIXTURE = _FIX / "vgnc_dictionary_snapshot.sql"
_XREFS_FIXTURE = _FIX / "vgnc_xrefs_sample.sql"
_DATES_FIXTURE = _FIX / "vgnc_dates_sample.sql"

# Minimal column layouts matching each fixture's named-column INSERTs.
_DICT_DDL = (
    "CREATE TABLE nomenclature_type (id INT PRIMARY KEY, type VARCHAR(45))",
    "CREATE TABLE database_resource (id INT PRIMARY KEY, db_name VARCHAR(128), "
    "db_display_name VARCHAR(128), url VARCHAR(255), external_link_template VARCHAR(255), "
    "priority INT, class VARCHAR(32))",
    "CREATE TABLE gene_status (id INT PRIMARY KEY, status VARCHAR(45), display VARCHAR(128))",
    "CREATE TABLE change_type (id INT PRIMARY KEY, field_changed VARCHAR(255))",
)
# Includes the full dict DDL because the dictionary fixture (all four lookup
# tables) is co-loaded to populate database_resource.
_XREFS_DDL = _DICT_DDL + (
    "CREATE TABLE genefam (genefam_id INT PRIMARY KEY, assigned_id VARCHAR(28), taxon_id INT)",
    "CREATE TABLE xref (id INT PRIMARY KEY, external_db_id INT, xref VARCHAR(255), "
    "status VARCHAR(45))",
    "CREATE TABLE gene_has_xrefs (genefam_id INT, xref_id INT, created_by INT, "
    "curated INT, created DATE, modified DATE)",
    "CREATE TABLE genefam_orthologs (go_id INT PRIMARY KEY, taxon_a INT, taxon_b INT, "
    "db_id_a VARCHAR(255), vgnc_b VARCHAR(28))",
)
# Includes the full dict DDL; change_type is populated from the dict fixture.
_DATES_DDL = _DICT_DDL + (
    "CREATE TABLE gene_history (id INT PRIMARY KEY, log TEXT, date DATE, genefam_id INT, "
    "editor_id INT, type_id INT)",
)
@contextmanager
def _ephemeral_mysql(
    ddl: tuple[str, ...], fixtures: tuple[Path, ...]
) -> Iterator[Any]:
    """Create an ephemeral MySQL schema, run DDL, load fixture INSERTs.

    Drops the schema on teardown. Each fixture line starting with
    ``INSERT INTO`` is executed verbatim.
    """
    import MySQLdb

    dsn = os.environ.get("MYSQL_TEST_DSN", "root:root@127.0.0.1:3306")
    creds, hostport = dsn.rsplit("@", 1)
    user, passwd = creds.split(":", 1)
    host, port = hostport.split(":", 1)
    schema = f"test_vgnc_ctr_{os.getpid()}_{random.randint(1000, 9999)}"

    conn = MySQLdb.connect(host=host, user=user, passwd=passwd, port=int(port))
    cur = conn.cursor()
    try:
        cur.execute(f"CREATE DATABASE `{schema}`")
        cur.execute(f"USE `{schema}`")
        for stmt in ddl:
            cur.execute(stmt)
        for fx in fixtures:
            for line in fx.read_text().splitlines():
                line = line.strip()
                if line.startswith("INSERT INTO"):
                    cur.execute(line)
        conn.commit()
        yield conn
    finally:
        cur.execute(f"DROP DATABASE IF EXISTS `{schema}`")
        cur.close()
        conn.close()


def _load_lines(conn: Any, sql: str) -> None:
    """Execute arbitrary INSERT statements on an already-connected cursor."""
    cur = conn.cursor()
    for line in sql.splitlines():
        line = line.strip()
        if line.startswith("INSERT INTO"):
            cur.execute(line)
    cur.close()


# ===========================================================================
# Contract tests: every hardcoded literal the SQL embeds must exist in the
# real lookup tables. Catches database drift (renumbered/renamed values).
# ===========================================================================

# db_name values used in build_xrefs_query CASE WHEN branches.
_XREF_DB_NAMES = {
    "ncbi_gene", "ensembl_gene", "uniprot_protein", "pubmed",
    "hgnc_ortholog", "bgd_gene", "horde",
}
# status_id lists are imported from the generators (single source of truth)
# PUBLIC_STATUS_IDS / WITHDRAWN_STATUS_IDS imported above

# field_changed values used in build_dates_query.
_DATE_FIELDS = {"assigned_symbol", "assigned_name"}
# nomenclature_type values used in build_aliases_query.
_NOMENCLATURE_TYPES = {
    "previous_symbol", "previous_name", "alias_symbol", "alias_name",
}


@pytest.mark.integration
class TestCodeAssumptionsMatchRealDictionary:
    """The values hardcoded in the SQL must exist in the real snapshot."""

    @pytest.fixture
    def dict_db(self) -> Iterator[Any]:
        with _ephemeral_mysql(_DICT_DDL, (_DICT_FIXTURE,)) as conn:
            yield conn

    def test_xref_db_names_all_exist(self, dict_db: Any) -> None:
        """Each db_name literal in build_xrefs_query is a real resource."""
        cur = dict_db.cursor()
        cur.execute("SELECT db_name FROM database_resource")
        present = {r[0] for r in cur.fetchall()}
        cur.close()
        missing = _XREF_DB_NAMES - present
        assert not missing, f"db_name literals missing from database_resource: {missing}"

    def test_nomenclature_types_all_exist(self, dict_db: Any) -> None:
        """Each nomenclature_type literal in build_aliases_query is real."""
        cur = dict_db.cursor()
        cur.execute("SELECT type FROM nomenclature_type")
        present = {r[0] for r in cur.fetchall()}
        cur.close()
        assert present == _NOMENCLATURE_TYPES

    def test_date_field_changed_values_all_exist(self, dict_db: Any) -> None:
        """Each field_changed literal in build_dates_query is real."""
        cur = dict_db.cursor()
        cur.execute("SELECT field_changed FROM change_type")
        present = {r[0] for r in cur.fetchall()}
        cur.close()
        assert _DATE_FIELDS.issubset(present)

    def test_public_status_ids_exist_and_mean_approved(self, dict_db: Any) -> None:
        """[6,11,12] (public/ensembl files) exist and all display as Approved."""
        cur = dict_db.cursor()
        cur.execute("SELECT id, status, display FROM gene_status")
        rows = {int(i): (s, d) for i, s, d in cur.fetchall()}
        cur.close()
        for sid in PUBLIC_STATUS_IDS:
            assert sid in rows, f"gene_status id {sid} no longer exists"
        approved = {sid: rows[sid] for sid in PUBLIC_STATUS_IDS}
        assert all(d == "Approved" for _, d in approved.values()), (
            f"public status_ids must all display 'Approved': {approved}"
        )

    def test_withdrawn_status_ids_exist_and_mean_withdrawn(self, dict_db: Any) -> None:
        """[2,3] (withdrawn file) exist and are the withdrawn statuses."""
        cur = dict_db.cursor()
        cur.execute("SELECT id, status, display FROM gene_status")
        rows = {int(i): (s, d) for i, s, d in cur.fetchall()}
        cur.close()
        for sid in WITHDRAWN_STATUS_IDS:
            assert sid in rows, f"gene_status id {sid} no longer exists"
        withdrawn = {sid: rows[sid] for sid in WITHDRAWN_STATUS_IDS}
        assert all("Withdrawn" in s for s, _ in withdrawn.values()), (
            f"withdrawn status_ids must be Withdrawn: {withdrawn}"
        )


# ===========================================================================
# Behavioral cross-check: build_xrefs_query routes db_name -> output column.
# Runs the REAL query vs an independent Python re-derivation.
# ===========================================================================

# db_name -> (output column, 'single' uses MAX / 'multi' uses GROUP_CONCAT).
_XREF_FIELD_FOR = {
    "ncbi_gene": ("ncbi_gene_id", "single"),
    "ensembl_gene": ("ensembl_gene_id", "single"),
    "hgnc_ortholog": ("hgnc_orthologs", "single"),
    "bgd_gene": ("bgd_id", "single"),
    "horde": ("horde_id", "single"),
    "uniprot_protein": ("uniprot_ids", "multi"),
    "pubmed": ("pubmed_id", "multi"),
}


@pytest.mark.integration
class TestBuildXrefsQueryRealSnapshot:
    """Cross-check xref routing (db_name -> column) on real snapshot data."""

    @pytest.fixture
    def xrefs_db(self) -> Iterator[Any]:
        with _ephemeral_mysql(_XREFS_DDL, (_DICT_FIXTURE, _XREFS_FIXTURE)) as conn:
            # build_xrefs_query joins genefam (for ortholog fallback), so seed
            # minimal gene rows for all genefam_ids present in xref fixture data.
            _load_lines(
                conn,
                "INSERT INTO genefam (genefam_id, assigned_id, taxon_id) "
                "SELECT DISTINCT genefam_id, CONCAT('VGNC:', genefam_id), 9999 "
                "FROM gene_has_xrefs;",
            )

            # PubMed has zero real rows in this snapshot, so synthesise one
            # link for gene 110150 to exercise the pubmed_id code path
            # (database_resource id 23 = 'pubmed', loaded from the dict fixture).
            _load_lines(
                conn,
                "INSERT INTO xref (id, external_db_id, xref, status) "
                "VALUES (9999991, 23, '12345678', 'Current');\n"
                "INSERT INTO gene_has_xrefs (genefam_id, xref_id, created_by, "
                "curated, created, modified) VALUES "
                "(110150, 9999991, 1, 0, '2024-01-01', '2024-01-01');",
            )
            yield conn

    @staticmethod
    def _expected(conn: Any) -> dict[int, dict[str, list[str]]]:
        """Independent Python re-derivation: gene -> {db_name: [xref values]}."""
        cur = conn.cursor()
        cur.execute("SELECT id, db_name FROM database_resource")
        db_name = {int(i): n for i, n in cur.fetchall()}
        cur.execute("SELECT id, external_db_id, xref FROM xref")
        xref = {int(i): (v, int(db)) for i, db, v in cur.fetchall()}
        cur.execute("SELECT genefam_id, xref_id FROM gene_has_xrefs")
        out: dict[int, dict[str, list[str]]] = {}
        for gid, xid in cur.fetchall():
            gid, xid = int(gid), int(xid)
            value, db = xref[xid]
            out.setdefault(gid, {}).setdefault(db_name[db], []).append(value)
        cur.close()
        return out

    @staticmethod
    def _actual(conn: Any) -> dict[int, dict[str, Any]]:
        from vgnc_download_file_generator.database.queries import (
            compile_query_for_mysql,
        )

        cur = conn.cursor()
        sql, params = compile_query_for_mysql(build_xrefs_query())
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        out: dict[int, dict[str, Any]] = {}
        for row in cur.fetchall():
            r = dict(zip(cols, row, strict=False))
            out[int(r["genefam_id"])] = r
        cur.close()
        return out

    def test_each_output_column_is_exercised_by_some_gene(self, xrefs_db: Any) -> None:
        """Every db_name -> column mapping routes at least one value."""
        actual = self._actual(xrefs_db)
        for db_name, (col, _) in _XREF_FIELD_FOR.items():
            populated = [g for g, r in actual.items() if r.get(col)]
            assert populated, (
                f"no gene populates {col} (db_name={db_name!r}); "
                "the routing literal may be wrong"
            )

    def test_query_matches_independent_derivation(self, xrefs_db: Any) -> None:
        """SQL xref routing must equal a Python re-derivation for every gene."""
        actual = self._actual(xrefs_db)
        expected = self._expected(xrefs_db)
        assert set(actual) == set(expected)
        for gid, exp_by_db in expected.items():
            row = actual[gid]
            for db_name, (col, kind) in _XREF_FIELD_FOR.items():
                vals = exp_by_db.get(db_name, [])
                if kind == "multi":
                    got = {v for v in str(row.get(col) or "").split("|") if v}
                    assert got == set(vals), (
                        f"gene {gid} {col}: {got} != {set(vals)}"
                    )
                else:
                    got = row.get(col)
                    if vals:
                        assert got in vals, (
                            f"gene {gid} {col}: {got!r} not in {vals}"
                        )
                    else:
                        assert got in (None, ""), f"gene {gid} {col}: expected empty"


# ===========================================================================
# Behavioral cross-check: build_dates_query routes field_changed -> date cols.
# ===========================================================================


@pytest.mark.integration
class TestBuildDatesQueryRealSnapshot:
    """Cross-check date routing (field_changed -> *_changed) on real data."""

    @pytest.fixture
    def dates_db(self) -> Iterator[Any]:
        with _ephemeral_mysql(_DATES_DDL, (_DICT_FIXTURE, _DATES_FIXTURE)) as conn:
            yield conn

    @staticmethod
    def _expected(conn: Any) -> dict[int, dict[str, str | None]]:
        cur = conn.cursor()
        cur.execute("SELECT id, field_changed FROM change_type")
        fc = {int(i): f for i, f in cur.fetchall()}
        cur.execute("SELECT genefam_id, date, type_id FROM gene_history")
        agg: dict[int, dict[str, list[str]]] = {}
        for gid, d, tid in cur.fetchall():
            gid, tid = int(gid), int(tid)
            ds = str(d)
            buckets = agg.setdefault(
                gid, {"all": [], "sym": [], "name": []}
            )
            buckets["all"].append(ds)
            if fc.get(tid) == "assigned_symbol":
                buckets["sym"].append(ds)
            if fc.get(tid) == "assigned_name":
                buckets["name"].append(ds)
        cur.close()
        out: dict[int, dict[str, str | None]] = {}
        for gid, b in agg.items():
            out[gid] = {
                "date_approved_reserved": min(b["all"]) if b["all"] else None,
                "date_modified": max(b["all"]) if b["all"] else None,
                "date_symbol_changed": max(b["sym"]) if b["sym"] else None,
                "date_name_changed": max(b["name"]) if b["name"] else None,
            }
        return out

    @staticmethod
    def _actual(conn: Any) -> dict[int, dict[str, str | None]]:
        from vgnc_download_file_generator.database.queries import (
            compile_query_for_mysql,
        )

        cur = conn.cursor()
        sql, params = compile_query_for_mysql(build_dates_query())
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        out: dict[int, dict[str, str | None]] = {}
        for row in cur.fetchall():
            r = dict(zip(cols, row, strict=False))
            gid = int(r["genefam_id"])
            out[gid] = {
                "date_approved_reserved": (
                    str(r["date_approved_reserved"])
                    if r["date_approved_reserved"] is not None
                    else None
                ),
                "date_modified": (
                    str(r["date_modified"]) if r["date_modified"] is not None else None
                ),
                "date_symbol_changed": (
                    str(r["date_symbol_changed"])
                    if r["date_symbol_changed"] is not None
                    else None
                ),
                "date_name_changed": (
                    str(r["date_name_changed"])
                    if r["date_name_changed"] is not None
                    else None
                ),
            }
        cur.close()
        return out

    def test_query_matches_independent_derivation(self, dates_db: Any) -> None:
        """SQL date routing must equal a Python re-derivation for every gene."""
        actual = self._actual(dates_db)
        expected = self._expected(dates_db)
        assert set(actual) == set(expected)
        for gid, exp in expected.items():
            assert actual[gid] == exp, f"gene {gid}: {actual[gid]} != {exp}"

    def test_symbol_and_name_change_dates_are_populated(self, dates_db: Any) -> None:
        """At least one gene has a symbol change AND a name change date.

        Guards the field_changed literals: a wrong literal would leave
        date_symbol_changed / date_name_changed NULL for everyone.
        """
        actual = self._actual(dates_db)
        sym_genes = [g for g, r in actual.items() if r["date_symbol_changed"]]
        name_genes = [g for g, r in actual.items() if r["date_name_changed"]]
        assert sym_genes, "no gene has a date_symbol_changed (field_changed literal?)"
        assert name_genes, "no gene has a date_name_changed (field_changed literal?)"


# ===========================================================================
# Behavioral check: build_gene_data_query status_id IN-filter semantics.
# Uses in-memory SQLite (no MySQL needed): the filter is pure SQL.
# ===========================================================================


@pytest.mark.unit
class TestStatusIdFilterSemantics:
    """The hardcoded status_id lists must actually filter gene rows.

    Mirrors the generators: vgnc_public/ensembl use [6,11,12], withdrawn uses
    [2,3]. Seeds genes of every status and asserts exactly the right set is
    returned -- a behavioral guard, not a substring check.
    """

    @staticmethod
    def _run(tax: int, status_ids: list[int]) -> set[int]:
        import sqlite3

        from vgnc_download_file_generator.database.queries_split import (
            build_gene_data_query,
        )

        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE genefam (genefam_id INTEGER, taxon_id INTEGER, assigned_id TEXT,
                assigned_symbol TEXT, assigned_name TEXT, status_id INTEGER);
            CREATE TABLE gene_has_locus_type (genefam_id INTEGER, locus_type_id INTEGER);
            CREATE TABLE locus_type (id INTEGER, type TEXT, locus_group_id INTEGER);
            CREATE TABLE locus_group (id INTEGER, name TEXT);
            CREATE TABLE gene_has_location (gene_id INTEGER, location_id INTEGER, assembly_id INTEGER);
            CREATE TABLE assembly (id INTEGER, taxon_id INTEGER, is_vgnc_default INTEGER, source TEXT, is_current INTEGER);
            CREATE TABLE assembly_has_chr (assembly_id INTEGER, chr_id INTEGER);
            CREATE TABLE gene_location (id INTEGER, chr_id INTEGER, start INTEGER, end INTEGER, strand TEXT, band TEXT);
            CREATE TABLE chromosomes (chr_id INTEGER, taxon_id INTEGER, display_name TEXT, coord_system TEXT);
            CREATE TABLE gene_status (id INTEGER, status TEXT);
            CREATE TABLE gene_has_family (genefam_id INTEGER, family_id INTEGER);
            CREATE TABLE family_new (id INTEGER, name TEXT);
            """
        )
        # status_id 1..12 all present, one gene each, all in the same taxon.
        cur.executemany(
            "INSERT INTO genefam VALUES (?, ?, ?, ?, ?, ?)",
            [(i, tax, f"VGNC:{i}", f"G{i}", f"Gene {i}", i) for i in range(1, 13)],
        )
        from vgnc_download_file_generator.database.queries import (
            compile_query_for_mysql,
        )

        q = build_gene_data_query(filters={"taxon_id": tax, "status_id": status_ids})
        # compile_query_for_mysql expands the IN list to (%s,%s,%s); convert to
        # SQLite's positional "?" and bind the params tuple in order.
        sql, params = compile_query_for_mysql(q)
        rows = cur.execute(sql.replace("%s", "?"), params).fetchall()
        conn.close()
        return {r[0] for r in rows}

    def test_public_filter_keeps_only_6_11_12(self) -> None:
        """[6,11,12] returns exactly the genes with those status_ids."""
        kept = self._run(9913, PUBLIC_STATUS_IDS)
        assert kept == set(PUBLIC_STATUS_IDS)

    def test_withdrawn_filter_keeps_only_2_3(self) -> None:
        """[2,3] returns exactly the genes with those status_ids."""
        kept = self._run(9913, WITHDRAWN_STATUS_IDS)
        assert kept == set(WITHDRAWN_STATUS_IDS)
