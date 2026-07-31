"""Tests for split query architecture.

Tests the new approach of splitting the complex build_gene_query into
multiple simpler queries and merging results in Python.
"""



import os
import random
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.sql.expression import TextClause

from vgnc_download_file_generator.database.queries_split import (
    build_aliases_query,
    build_dates_query,
    build_gene_data_query,
    build_gene_id_page_query,
    build_xrefs_query,
    merge_gene_results,
)


class TestBuildGeneDataQuery:
    """Tests for build_gene_data_query - main gene core data query."""

    def test_returns_text_clause(self) -> None:
        """Test that the query returns a SQLAlchemy TextClause."""
        query = build_gene_data_query(filters=None)
        assert isinstance(query, TextClause)

    def test_basic_query_structure(self) -> None:
        """Test that the query has correct basic structure."""
        query = build_gene_data_query(filters=None)
        sql = query.text

        # Should select from genefam
        assert "FROM genefam gf" in sql

        # Should have core JOINs
        assert "LEFT JOIN gene_status gs" in sql
        assert "LEFT JOIN gene_has_location ghl" in sql
        assert "LEFT JOIN gene_location gl" in sql
        assert "LEFT JOIN chromosomes c" in sql

        # Should NOT have xref JOINs (those are in separate query)
        assert "gene_has_xrefs" not in sql

    def test_taxon_id_filter(self) -> None:
        """Test taxon_id filter is applied correctly."""
        query = build_gene_data_query(filters={"taxon_id": 9913})
        sql = query.text

        # Should have WHERE clause for genefam
        assert "gf.taxon_id" in sql
        assert ":taxon_id" in sql
        # Should also filter chromosomes by same taxon_id to prevent cross-species contamination
        assert "c.taxon_id = gf.taxon_id" in sql

    def test_species_all_chromosome_query_keeps_locationless_genes(self) -> None:
        """Species-scoped all-chromosome output must keep locationless genes.

        Regression guard for genes that exist in all_vgnc_gene_set_All but were
        missing from species *_vgnc_gene_set_All files. Species filtering should
        constrain gene rows (gf.taxon_id) without turning the LEFT JOIN to
        chromosomes into an effective INNER JOIN.
        """
        import sqlite3

        query = build_gene_data_query(filters={"taxon_id": 9598})

        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE genefam (
                genefam_id INTEGER,
                taxon_id INTEGER,
                assigned_id TEXT,
                assigned_symbol TEXT,
                assigned_name TEXT,
                status_id INTEGER
            );
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

        # Two genes in taxon 9598: one located, one locationless.
        cur.executemany(
            "INSERT INTO genefam VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, 9598, "VGNC:1", "GENE1", "Gene 1", 6),
                (2, 9598, "VGNC:2", "GENE2", "Gene 2", 6),
                (3, 9606, "VGNC:3", "GENE3", "Gene 3", 6),
            ],
        )
        cur.execute("INSERT INTO assembly VALUES (23, 9598, 1, 'Ensembl', 1)")
        cur.execute("INSERT INTO assembly_has_chr VALUES (23, 1)")
        cur.execute("INSERT INTO gene_has_location VALUES (1, 101, 23)")
        cur.execute("INSERT INTO gene_location VALUES (101, 1, 100, 200, '+', 'q1')")
        cur.execute("INSERT INTO chromosomes VALUES (1, 9598, '1', 'chromosome')")

        rows = cur.execute(query.text, {"taxon_id_0": 9598}).fetchall()
        conn.close()

        returned_ids = sorted({row[2] for row in rows})
        assert returned_ids == ["VGNC:1", "VGNC:2"]

    def test_species_all_chromosome_uses_default_assembly_chr_link_fallback(self) -> None:
        """If no Ensembl-default location row exists, use default-assembly chr links.

        Mirrors VGNC:30914: the gene's stored location is on a non-default
        assembly, but its chromosome belongs to the species default assembly via
        assembly_has_chr. The species all-chromosome query should emit the gene
        with that chromosome instead of dropping it / nulling location.
        """
        import sqlite3

        query = build_gene_data_query(filters={"taxon_id": 9913})

        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE genefam (
                genefam_id INTEGER,
                taxon_id INTEGER,
                assigned_id TEXT,
                assigned_symbol TEXT,
                assigned_name TEXT,
                status_id INTEGER
            );
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

        # Gene location is on a non-default assembly (29), but chromosome 4 is
        # present on the default assembly (108) via assembly_has_chr.
        cur.executemany(
            "INSERT INTO genefam VALUES (?, ?, ?, ?, ?, ?)",
            [
                (10, 9913, "VGNC:10", "GENE10", "Gene 10", 6),
                (11, 9606, "VGNC:11", "GENE11", "Gene 11", 6),
            ],
        )
        cur.executemany(
            "INSERT INTO assembly VALUES (?, ?, ?, ?, ?)",
            [
                (29, 9913, 0, 'NCBI', 0),
                (108, 9913, 1, 'Ensembl', 1),
            ],
        )
        cur.execute("INSERT INTO gene_has_location VALUES (10, 501, 29)")
        cur.execute("INSERT INTO gene_location VALUES (501, 4, 106251294, 106252640, '+', 'q1')")
        cur.execute("INSERT INTO chromosomes VALUES (4, 9913, '4', 'chromosome')")
        cur.execute("INSERT INTO assembly_has_chr VALUES (108, 4)")

        rows = cur.execute(query.text, {"taxon_id_0": 9913}).fetchall()
        conn.close()

        gene10_rows = [row for row in rows if row[2] == "VGNC:10"]
        assert len(gene10_rows) == 1
        assert gene10_rows[0][8] == "4"  # chromosome

    def test_chromosome_filter_is_ignored(self) -> None:
        """Chromosome splitting is retired; chromosome filter input is ignored."""
        query = build_gene_data_query(filters={"chromosome": "X"})
        sql = query.text

        # Query still joins chromosomes for location output, but no WHERE bind
        # should be emitted for chromosome-based filtering.
        assert "LEFT JOIN chromosomes c" in sql
        assert ":chromosome" not in sql

    def test_build_gene_data_query_filters_ghl_by_default_assembly_chr_membership(self) -> None:
        """The location filter must live on the ghl JOIN (not as inert joins).

        It should use assembly_has_chr + default-assembly checks so rows are kept
        when the location chromosome belongs to the species default assembly.
        """
        query = build_gene_data_query(filters={"taxon_id": 9913})
        sql = query.text

        assert "LEFT JOIN gene_has_location ghl" in sql
        assert "EXISTS" in sql
        assert "assembly_has_chr ahc" in sql
        assert "a2.is_vgnc_default = 1" in sql
        assert "a2.taxon_id = gf.taxon_id" in sql

    def test_build_gene_data_query_has_no_inert_assembly_join(self) -> None:
        """There must NOT be a standalone LEFT JOIN assembly whose columns are
        never selected / depended on -- that filter is a no-op (regression guard
        for the inert-join bug found in review)."""
        query = build_gene_data_query(filters=None)
        sql = query.text

        assert "LEFT JOIN assembly a ON ghl.assembly_id = a.id" not in sql

    def test_build_gene_data_query_is_source_agnostic_for_default_assembly_lookup(self) -> None:
        """Default-assembly lookup must be source-agnostic (no Ensembl pin)."""
        query = build_gene_data_query(filters={"taxon_id": 9913})
        sql = query.text

        # Source-agnostic: do not hardcode Ensembl.
        assert "a.source = 'Ensembl'" not in sql
        # Query should not need fallback branching when source-agnostic selection
        # is always used.
        assert "NOT EXISTS" not in sql
        assert "assembly_has_chr ahc" in sql

    def test_default_location_selection_collapses_to_one_row_per_gene(self) -> None:
        """Dual-default species collapse to one row with source-agnostic ranking.

        If both default assemblies have locations, choose deterministically by
        row ranking (default first, then current). This proves the query does
        not assume Ensembl is canonical.
        """
        import sqlite3

        query = build_gene_data_query(filters={"taxon_id": 9598})

        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE genefam (
                genefam_id INTEGER,
                taxon_id INTEGER,
                assigned_id TEXT,
                assigned_symbol TEXT,
                assigned_name TEXT,
                status_id INTEGER
            );
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

        # Two defaults (NCBI + Ensembl) both have locations; NCBI is marked
        # current so source-agnostic ranking should choose it.
        cur.execute("INSERT INTO genefam VALUES (1, 9598, 'VGNC:6926', 'G1', 'Gene 1', 6)")
        cur.executemany(
            "INSERT INTO assembly VALUES (?, ?, ?, ?, ?)",
            [
                (3, 9598, 1, 'NCBI', 1),
                (23, 9598, 1, 'Ensembl', 0),
                (27, 9598, 0, 'NCBI', 0),
                (104, 9598, 0, 'NCBI', 0),
            ],
        )
        cur.executemany(
            "INSERT INTO gene_has_location VALUES (?, ?, ?)",
            [(1, 412433, 3), (1, 486777, 23), (1, 584093, 27), (1, 1546350, 104)],
        )
        cur.executemany(
            "INSERT INTO gene_location VALUES (?, ?, ?, ?, ?, ?)",
            [
                (412433, 14, 21176277, 21566347, '+', 'q1'),
                (486777, 1, 136605058, 136605999, '+', 'q1'),
                (584093, 14, 18212875, 18594504, '+', 'q1'),
                (1546350, 14, 28669951, 29052657, '+', 'q1'),
            ],
        )
        cur.executemany(
            "INSERT INTO chromosomes VALUES (?, ?, ?, ?)",
            [(14, 9598, '14', 'chromosome'), (1, 9598, '1', 'chromosome')],
        )
        cur.executemany(
            "INSERT INTO assembly_has_chr VALUES (?, ?)",
            [(3, 14), (23, 1), (23, 14)],
        )

        # Gene 2: no location.
        cur.execute("INSERT INTO genefam VALUES (2, 9598, 'VGNC:99999', 'G2', 'Gene 2', 6)")

        rows = cur.execute(query.text, {"taxon_id_0": 9598}).fetchall()
        conn.close()

        by_gene: dict[str, list[tuple[str | None, int | None]]] = {}
        for row in rows:
            assigned_id = row[2]
            chromosome = row[8]
            start = row[9]
            by_gene.setdefault(assigned_id, []).append((chromosome, start))

        assert len(by_gene['VGNC:6926']) == 1
        # Source-agnostic ranking picks the current default row (assembly 3, chr14)
        assert by_gene['VGNC:6926'][0][0] == '14'
        assert by_gene['VGNC:6926'][0][1] == 21176277

        assert len(by_gene['VGNC:99999']) == 1
        assert by_gene['VGNC:99999'][0][0] is None

    def test_chromosome_filter_un_is_ignored(self) -> None:
        """Legacy 'Un' chromosome selector is also ignored."""
        query = build_gene_data_query(filters={"chromosome": "Un"})
        sql = query.text

        assert ":chromosome" not in sql
        assert "LIKE" not in sql

    def test_locus_type_filter(self) -> None:
        """Test locus_type filter is applied correctly."""
        query = build_gene_data_query(filters={"locus_type": "gene with protein product"})
        sql = query.text

        assert "lt.type" in sql

    def test_locus_group_filter(self) -> None:
        """Test locus_group filter is applied correctly."""
        query = build_gene_data_query(filters={"locus_group": "protein-coding gene"})
        sql = query.text

        assert "lg.name" in sql

    def test_status_filter_single_value(self) -> None:
        """Test status filter with single value."""
        query = build_gene_data_query(filters={"status": "Approved"})
        sql = query.text

        assert "gs.status" in sql

    def test_status_filter_multiple_values(self) -> None:
        """Test status filter with multiple values (IN clause)."""
        query = build_gene_data_query(filters={"status": ["Approved", "Entry Withdrawn"]})
        sql = query.text

        # Should use IN clause for multiple values
        assert "IN" in sql

    def test_status_id_filter_single_value(self) -> None:
        """Test status_id filter with single value."""
        query = build_gene_data_query(filters={"status_id": 6})
        sql = query.text

        assert "gf.status_id" in sql

    def test_status_id_filter_multiple_values(self) -> None:
        """Test status_id filter with multiple values (IN clause)."""
        query = build_gene_data_query(filters={"status_id": [6, 11, 12]})
        sql = query.text

        # Should use IN clause for multiple values
        assert "gf.status_id" in sql
        assert "IN" in sql


class TestBuildGeneIdPageQuery:
    """Keyset ID-page query for batched gene export (connection-drop fix).

    The export no longer holds one server-side cursor open for the whole
    dataset; instead it walks ``genefam_id`` in bounded pages. These tests pin
    the access path the generator relies on.
    """

    def test_returns_text_clause(self) -> None:
        """The page query is a SQLAlchemy TextClause."""
        query = build_gene_id_page_query(filters=None, after_genefam_id=0, limit=5000)
        assert isinstance(query, TextClause)

    def test_selects_distinct_genefam_id_only(self) -> None:
        """Page query selects only the distinct PK used as the keyset."""
        sql = build_gene_id_page_query(filters=None, after_genefam_id=0, limit=5000).text
        assert "SELECT DISTINCT gf.genefam_id" in sql
        # Must not drag the wide projection (those come from build_gene_data_query)
        assert "assigned_symbol" not in sql
        assert "ncbi_gene_id" not in sql

    def test_has_keyset_after_order_and_limit(self) -> None:
        """Page query carries the keyset predicate, ordering, and LIMIT."""
        sql = build_gene_id_page_query(filters=None, after_genefam_id=123, limit=5000).text
        assert "gf.genefam_id > :after_genefam_id" in sql
        assert "ORDER BY gf.genefam_id" in sql
        assert "LIMIT :limit" in sql

    def test_inherits_filters(self) -> None:
        """taxon_id / status_id filters are routed into the page query too."""
        sql = build_gene_id_page_query(
            filters={"taxon_id": 9913, "status_id": [6, 11, 12]},
            after_genefam_id=0,
            limit=5000,
        ).text
        assert "gf.taxon_id" in sql
        assert "gf.status_id" in sql
        assert "IN" in sql

    def test_reuses_same_core_joins(self) -> None:
        """Page query shares the location/status JOINs of the main query."""
        sql = build_gene_id_page_query(filters=None, after_genefam_id=0, limit=10).text
        assert "FROM genefam gf" in sql
        assert "LEFT JOIN gene_status gs" in sql
        assert "LEFT JOIN gene_has_location ghl" in sql


class TestBuildGeneDataQueryGenefamIdsFilter:
    """build_gene_data_query must accept an optional genefam_ids IN filter."""

    def test_genefam_ids_adds_in_clause(self) -> None:
        """Passing genefam_ids adds an expanding IN clause on the PK."""
        query = build_gene_data_query(filters=None, genefam_ids=[1, 2, 3])
        sql = query.text
        assert "gf.genefam_id IN :genefam_ids" in sql

    def test_no_genefam_ids_is_backward_compatible(self) -> None:
        """Omitting genefam_ids leaves the query unchanged (no IN clause)."""
        query = build_gene_data_query(filters=None)
        sql = query.text
        assert "genefam_ids" not in sql

    def test_genefam_ids_combined_with_taxon_filter(self) -> None:
        """genefam_ids composes with the normal taxon_id filter."""
        query = build_gene_data_query(filters={"taxon_id": 9913}, genefam_ids=[10, 11])
        sql = query.text
        assert "gf.taxon_id" in sql
        assert "gf.genefam_id IN :genefam_ids" in sql


class TestBuildXrefsQuery:
    """Tests for build_xrefs_query - external database references."""

    def test_returns_text_clause(self) -> None:
        """Test that the query returns a SQLAlchemy TextClause."""
        query = build_xrefs_query()
        assert isinstance(query, TextClause)

    def test_returns_all_xref_columns(self) -> None:
        """Test that all 7 xref types are in the query."""
        query = build_xrefs_query()
        sql = query.text

        # Should have all 7 xref types
        assert "ncbi_gene_id" in sql
        assert "ensembl_gene_id" in sql
        assert "uniprot_ids" in sql
        assert "pubmed_id" in sql
        assert "hgnc_orthologs" in sql
        assert "bgd_id" in sql
        assert "horde_id" in sql

    def test_uses_conditional_aggregation(self) -> None:
        """Test that query uses conditional aggregation pattern."""
        query = build_xrefs_query()
        sql = query.text

        # Should use CASE WHEN or MAX with conditional logic
        assert "CASE" in sql or "MAX" in sql

    def test_xrefs_ncbi_uses_ncbi_gene_resource_name(self) -> None:
        """Map NCBI by stable database_resource.db_name, not hardcoded IDs."""
        query = build_xrefs_query()
        sql = query.text
        assert "dr.db_name = 'ncbi_gene' THEN x.xref END) AS ncbi_gene_id" in sql

    def test_xrefs_ensembl_uses_ensembl_gene_resource_name(self) -> None:
        """Map Ensembl by stable database_resource.db_name, not numeric ID."""
        query = build_xrefs_query()
        sql = query.text
        assert "dr.db_name = 'ensembl_gene' THEN x.xref END) AS ensembl_gene_id" in sql

    def test_xrefs_uniprot_uses_group_concat(self) -> None:
        """uniprot_ids must aggregate UniProt values by db_name=uniprot_protein."""
        query = build_xrefs_query()
        sql = query.text

        assert "GROUP_CONCAT" in sql
        assert "dr.db_name = 'uniprot_protein'" in sql
        assert "SEPARATOR '|'" in sql
        assert "AS uniprot_ids" in sql

    def test_xrefs_pubmed_uses_group_concat(self) -> None:
        """pubmed_id aggregates via GROUP_CONCAT (a gene may have several PubMed
        refs), not MAX (which keeps only one)."""
        query = build_xrefs_query()
        sql = query.text
        # PubMed must no longer be a single-value MAX aggregation.
        assert "MAX(CASE WHEN dr.db_name = 'pubmed'" not in sql
        assert "dr.db_name = 'pubmed'" in sql
        assert "AS pubmed_id" in sql
        # Both multi-valued fields (uniprot + pubmed) use GROUP_CONCAT + '|'.
        assert sql.count("GROUP_CONCAT") >= 2
        assert sql.count("SEPARATOR '|'") >= 2

    def test_xrefs_horde_uses_horde_resource_name(self) -> None:
        """HORDE id maps by stable db_name='horde' (database_resource id=31)."""
        query = build_xrefs_query()
        sql = query.text
        assert "MAX(CASE WHEN dr.db_name = 'horde' THEN x.xref END) AS horde_id" in sql

    def test_xrefs_hgnc_ortholog_uses_hgnc_ortholog_resource_name(self) -> None:
        """HGNC ortholog mapping uses xref db_name with ortholog-table fallback."""
        query = build_xrefs_query()
        sql = query.text
        assert "dr.db_name = 'hgnc_ortholog' THEN x.xref END" in sql
        assert "COALESCE(" in sql
        assert "JOIN genefam_orthologs go" in sql
        assert "go.db_id_a" in sql

    def test_xrefs_joins_database_resource(self) -> None:
        """The query must join database_resource to resolve stable db_name values."""
        query = build_xrefs_query()
        sql = query.text
        assert "JOIN database_resource dr ON x.external_db_id = dr.id" in sql
        assert "created_by" not in sql, (
            "created_by=1 is a stale legacy filter that silently drops PubMed "
            "xrefs (created by a different editor). Aggregations dedupe links."
        )

    def test_xrefs_no_where_when_no_genefam_ids(self) -> None:
        """With no genefam_ids filter there must be no WHERE clause at all."""
        sql = build_xrefs_query().text
        # No genefam_ids -> nothing to filter on; FROM/JOIN/GROUP BY only.
        assert "WHERE" not in sql

    def test_xrefs_where_is_only_genefam_id_filter(self) -> None:
        """With genefam_ids the only predicate is `genefam_id IN (...)`."""
        sql = build_xrefs_query(genefam_ids=[1, 2, 3]).text
        assert sql.count("WHERE") == 1
        assert "ghx.genefam_id IN" in sql
        assert "created_by" not in sql
    def test_groups_by_genefam_id(self) -> None:
        """Test that query groups by genefam_id."""
        query = build_xrefs_query()
        sql = query.text

        assert "GROUP BY" in sql
        assert "genefam_id" in sql

    def test_filters_by_genefam_ids(self) -> None:
        """Test that query filters by genefam_id list."""
        query = build_xrefs_query(genefam_ids=[1, 2, 3])
        sql = query.text

        # Should have IN clause for genefam_ids
        assert "IN" in sql


@pytest.mark.integration
class TestBuildXrefsQueryOrthologFallback:
    """Regression guard: hgnc_orthologs falls back to genefam_orthologs.

    Some genes have HGNC orthologs in ``genefam_orthologs`` (ortholog section
    on the gene symbol report) but no ``hgnc_ortholog`` xref rows. The export
    must still populate ``hgnc_orthologs`` for those genes.
    """

    @pytest.fixture
    def mysql_xrefs_schema(self) -> Iterator[object]:
        import MySQLdb

        dsn = os.environ.get("MYSQL_TEST_DSN", "root:root@127.0.0.1:3306")
        creds, hostport = dsn.rsplit("@", 1)
        user, passwd = creds.split(":", 1)
        host, port = hostport.split(":", 1)
        schema = f"test_vgnc_xref_orth_{os.getpid()}_{random.randint(1000, 9999)}"

        conn = MySQLdb.connect(host=host, user=user, passwd=passwd, port=int(port))
        cur = conn.cursor()
        try:
            cur.execute(f"CREATE DATABASE `{schema}`")
            cur.execute(f"USE `{schema}`")
            for stmt in (
                "CREATE TABLE genefam (genefam_id INT PRIMARY KEY, assigned_id VARCHAR(28), taxon_id INT)",
                "CREATE TABLE gene_has_xrefs (genefam_id INT, xref_id INT)",
                "CREATE TABLE xref (id INT PRIMARY KEY, external_db_id INT, xref VARCHAR(255))",
                "CREATE TABLE database_resource (id INT PRIMARY KEY, db_name VARCHAR(128))",
                "CREATE TABLE genefam_orthologs (go_id INT PRIMARY KEY, taxon_a INT, taxon_b INT, db_id_a VARCHAR(255), vgnc_b VARCHAR(28), genefam_id_b INT)",
            ):
                cur.execute(stmt)
            # Create index on genefam_id_b (the index used by the re-keyed join).
            # In production this is genefam_orthologs_idx_genefam_id_b.
            cur.execute(
                "CREATE INDEX genefam_orthologs_idx_genefam_id_b "
                "ON genefam_orthologs(genefam_id_b)"
            )

            # VGNC:59454-like setup: normal xrefs exist, but no hgnc_ortholog xref
            # row. HGNC id exists only in genefam_orthologs.
            # Gene 63410: has ortholog with vgnc_b set -> should backfill
            # Gene 63411: has ortholog with vgnc_b=NULL but genefam_id_b set -> should NOT backfill
            cur.executemany(
                "INSERT INTO genefam VALUES (%s, %s, %s)",
                [
                    (63410, 'VGNC:59454', 9685),
                    (63411, 'VGNC:59455', 9685),
                ],
            )
            cur.executemany(
                "INSERT INTO database_resource VALUES (%s, %s)",
                [(2, "ncbi_gene"), (25, "hgnc_ortholog")],
            )
            cur.executemany(
                "INSERT INTO xref VALUES (%s, %s, %s)",
                [(1, 2, '101088636'), (2, 2, '101088637')],
            )
            cur.executemany(
                "INSERT INTO gene_has_xrefs VALUES (%s, %s)",
                [(63410, 1), (63411, 2)],
            )
            # Ortholog for gene 63410: vgnc_b=VGNC:59454, genefam_id_b=63410 -> should match
            # Ortholog for gene 63411: vgnc_b=NULL, genefam_id_b=63411 -> should NOT match (excluded by vgnc_b IS NOT NULL)
            cur.executemany(
                "INSERT INTO genefam_orthologs "
                "(go_id, taxon_a, taxon_b, db_id_a, vgnc_b, genefam_id_b) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                [
                    (1, 9606, 9685, 'HGNC:20', 'VGNC:59454', 63410),
                    (2, 9606, 9685, 'HGNC:21', None, 63411),
                ],
            )
            conn.commit()
            yield conn
        finally:
            cur.execute(f"DROP DATABASE IF EXISTS `{schema}`")
            cur.close()
            conn.close()

    def test_falls_back_to_genefam_orthologs_when_xref_missing(
        self, mysql_xrefs_schema: object
    ) -> None:
        """Output-parity guard: genes with vgnc_b set get backfill; vgnc_b=NULL do not.

        Gene 63410: ortholog row has vgnc_b='VGNC:59454', genefam_id_b=63410
            -> should get hgnc_orthologs='HGNC:20'
        Gene 63411: ortholog row has vgnc_b=NULL, genefam_id_b=63411
            -> should NOT backfill (vgnc_b IS NOT NULL excludes it)

        This test must stay green on both current HEAD and after the re-key:
        it enforces that the output set doesn't change.
        """
        from vgnc_download_file_generator.database.queries import (
            compile_query_for_mysql,
        )

        cur = mysql_xrefs_schema.cursor()  # type: ignore[attr-defined]
        query = build_xrefs_query(genefam_ids=[63410, 63411])
        sql, params = compile_query_for_mysql(query)
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = {row[0]: dict(zip(cols, row, strict=False)) for row in cur.fetchall()}
        cur.close()

        # Gene 63410: vgnc_b is set -> should backfill
        assert rows[63410]["ncbi_gene_id"] == "101088636"
        assert rows[63410]["hgnc_orthologs"] == "HGNC:20"

        # Gene 63411: vgnc_b is NULL -> should NOT backfill (preserves current behavior)
        assert rows[63411]["ncbi_gene_id"] == "101088637"
        assert rows[63411]["hgnc_orthologs"] is None

    def test_ortholog_explain_access_path_uses_genefam_id_b(
        self, mysql_xrefs_schema: object
    ) -> None:
        """Access-path guard: join uses genefam_id_b (indexed), not vgnc_b (unindexed).

        RED test on current gcp HEAD: fails because the query joins on
        go.vgnc_b = gf.assigned_id (unindexed), not go.genefam_id_b = ghx.genefam_id (indexed).

        This test also verifies via information_schema that an index whose
        leading column is genefam_id_b exists (the fixture creates it,
        so this assertion fails only if the fixture itself is broken).
        """
        # 1. Assert the query text joins on genefam_id_b, not vgnc_b
        query = build_xrefs_query()
        sql = query.text

        # Must join on genefam_id_b (indexed access path)
        assert "genefam_id_b" in sql, (
            "build_xrefs_query() must join genefam_orthologs on genefam_id_b "
            "(the indexed FK); currently joins on unindexed vgnc_b"
        )
        # Must NOT join on vgnc_b using equality (unindexed, causes full table scan)
        # "go.vgnc_b IS NOT NULL" is fine - it's a post-index predicate
        assert "go.vgnc_b =" not in sql.replace(" ", ""), (
            "build_xrefs_query() must NOT join on go.vgnc_b = ... (unindexed); "
            "use genefam_id_b instead. go.vgnc_b IS NOT NULL is allowed as a "
            "post-index predicate to preserve the current row set."
        )

        # 2. Verify the index exists (information_schema guard)
        cur = mysql_xrefs_schema.cursor()  # type: ignore[attr-defined]
        cur.execute("""
            SELECT index_name, seq_in_index, column_name
            FROM information_schema.statistics
            WHERE table_schema = DATABASE()
              AND table_name = 'genefam_orthologs'
              AND seq_in_index = 1
            ORDER BY index_name, seq_in_index
        """)
        leading_columns = [row[2] for row in cur.fetchall()]
        cur.close()

        assert "genefam_id_b" in leading_columns, (
            f"genefam_orthologs must have an index whose leading column is "
            f"genefam_id_b; got leading columns: {leading_columns}"
        )


class TestBuildAliasesQuery:
    """Tests for build_aliases_query - GROUP_CONCAT for aliases."""

    def test_returns_text_clause(self) -> None:
        """Test that the query returns a SQLAlchemy TextClause."""
        query = build_aliases_query()
        assert isinstance(query, TextClause)

    def test_returns_all_alias_columns(self) -> None:
        """Test that all 4 alias types are in the query."""
        query = build_aliases_query()
        sql = query.text

        assert "alias_symbol" in sql
        assert "alias_name" in sql
        assert "prev_symbol" in sql
        assert "prev_name" in sql

    def test_uses_group_concat(self) -> None:
        """Test that query uses GROUP_CONCAT."""
        query = build_aliases_query()
        sql = query.text

        assert "GROUP_CONCAT" in sql

    def test_groups_by_genefam_id(self) -> None:
        """Test that query groups by genefam_id."""
        query = build_aliases_query()
        sql = query.text

        assert "GROUP BY" in sql
        assert "genefam_id" in sql

    def test_filters_by_genefam_ids(self) -> None:
        """Test that query filters by genefam_id list."""
        query = build_aliases_query(genefam_ids=[1, 2, 3])
        sql = query.text

        assert "IN" in sql


class TestBuildDatesQuery:
    """Tests for build_dates_query - date MIN/MAX aggregates."""

    def test_returns_text_clause(self) -> None:
        """Test that the query returns a SQLAlchemy TextClause."""
        query = build_dates_query()
        assert isinstance(query, TextClause)

    def test_returns_all_date_columns(self) -> None:
        """Test that all 4 date fields are in the query."""
        query = build_dates_query()
        sql = query.text

        assert "date_approved_reserved" in sql
        assert "date_modified" in sql
        assert "date_symbol_changed" in sql
        assert "date_name_changed" in sql

    def test_uses_min_max_aggregation(self) -> None:
        """Test that query uses MIN/MAX aggregation."""
        query = build_dates_query()
        sql = query.text

        assert "MIN" in sql or "MAX" in sql

    def test_groups_by_genefam_id(self) -> None:
        """Test that query groups by genefam_id."""
        query = build_dates_query()
        sql = query.text

        assert "GROUP BY" in sql
        assert "genefam_id" in sql

    def test_filters_by_genefam_ids(self) -> None:
        """Test that query filters by genefam_id list."""
        query = build_dates_query(genefam_ids=[1, 2, 3])
        sql = query.text

        assert "IN" in sql


class TestMergeGeneResults:
    """Tests for merge_gene_results - Python-side merge logic."""

    def test_merges_single_row_perfect_match(self) -> None:
        """Test merging when all queries return matching data."""
        # Query 1: Main gene data
        gene_data = [
            {"genefam_id": 1, "assigned_symbol": "GENE1", "taxon_id": 9913}
        ]

        # Query 2: Xrefs
        xrefs = [
            {"genefam_id": 1, "ncbi_gene_id": "12345", "ensembl_gene_id": "ENSBTAG0000001"}
        ]

        # Query 3: Aliases
        aliases = [
            {"genefam_id": 1, "alias_symbol": "ALIAS1|ALIAS2", "prev_symbol": "OLD1"}
        ]

        # Query 4: Dates
        dates = [
            {"genefam_id": 1, "date_approved_reserved": "2020-01-01", "date_modified": "2024-01-01"}
        ]

        result = list(merge_gene_results(gene_data, xrefs, aliases, dates))

        assert len(result) == 1
        assert result[0]["genefam_id"] == 1
        assert result[0]["assigned_symbol"] == "GENE1"
        assert result[0]["ncbi_gene_id"] == "12345"
        assert result[0]["alias_symbol"] == "ALIAS1|ALIAS2"
        assert result[0]["date_approved_reserved"] == "2020-01-01"

    def test_handles_missing_xrefs(self) -> None:
        """Test that missing xrefs result in None/empty values."""
        gene_data = [{"genefam_id": 1, "assigned_symbol": "GENE1"}]
        xrefs = []  # No xrefs
        aliases = [{"genefam_id": 1, "alias_symbol": ""}]
        dates = [{"genefam_id": 1, "date_approved_reserved": "2020-01-01"}]

        result = list(merge_gene_results(gene_data, xrefs, aliases, dates))

        assert result[0]["genefam_id"] == 1
        # Xref fields should be None or empty
        assert result[0].get("ncbi_gene_id") is None or result[0].get("ncbi_gene_id") == ""

    def test_handles_missing_aliases(self) -> None:
        """Test that missing aliases result in None/empty values."""
        gene_data = [{"genefam_id": 1, "assigned_symbol": "GENE1"}]
        xrefs = [{"genefam_id": 1, "ncbi_gene_id": "12345"}]
        aliases = []  # No aliases
        dates = [{"genefam_id": 1, "date_approved_reserved": "2020-01-01"}]

        result = list(merge_gene_results(gene_data, xrefs, aliases, dates))

        assert result[0]["genefam_id"] == 1
        # Alias fields should be None or empty
        assert result[0].get("alias_symbol") is None or result[0].get("alias_symbol") == ""

    def test_handles_missing_dates(self) -> None:
        """Test that missing dates result in None/empty values."""
        gene_data = [{"genefam_id": 1, "assigned_symbol": "GENE1"}]
        xrefs = [{"genefam_id": 1, "ncbi_gene_id": "12345"}]
        aliases = [{"genefam_id": 1, "alias_symbol": ""}]
        dates = []  # No dates

        result = list(merge_gene_results(gene_data, xrefs, aliases, dates))

        assert result[0]["genefam_id"] == 1
        # Date fields should be None or empty
        assert result[0].get("date_approved_reserved") is None or result[0].get("date_approved_reserved") == ""

    def test_preserves_all_gene_data_rows(self) -> None:
        """Test that all rows from gene_data are preserved."""
        gene_data = [
            {"genefam_id": 1, "assigned_symbol": "GENE1"},
            {"genefam_id": 2, "assigned_symbol": "GENE2"},
            {"genefam_id": 3, "assigned_symbol": "GENE3"},
        ]
        xrefs = [{"genefam_id": 1, "ncbi_gene_id": "12345"}]
        aliases = [{"genefam_id": 2, "alias_symbol": "ALIAS2"}]
        dates = [{"genefam_id": 3, "date_approved_reserved": "2020-01-01"}]

        result = list(merge_gene_results(gene_data, xrefs, aliases, dates))

        assert len(result) == 3
        assert result[0]["assigned_symbol"] == "GENE1"
        assert result[1]["assigned_symbol"] == "GENE2"
        assert result[2]["assigned_symbol"] == "GENE3"

    def test_returns_iterator(self) -> None:
        """Test that merge_gene_results returns an iterator."""
        from collections.abc import Iterator

        gene_data = [{"genefam_id": 1, "assigned_symbol": "GENE1"}]
        xrefs = [{"genefam_id": 1}]
        aliases = [{"genefam_id": 1}]
        dates = [{"genefam_id": 1}]

        result = merge_gene_results(gene_data, xrefs, aliases, dates)
        assert isinstance(result, Iterator)

    def test_efficient_dict_lookup(self) -> None:
        """Test that merge uses efficient dict lookups (not nested loops)."""
        # This is a performance test - we can't directly test implementation,
        # but we can verify it handles larger datasets quickly
        gene_data = [{"genefam_id": i, "assigned_symbol": f"GENE{i}"} for i in range(1, 101)]
        xrefs = [{"genefam_id": i, "ncbi_gene_id": str(i)} for i in range(1, 101, 2)]  # Every other gene
        aliases = [{"genefam_id": i, "alias_symbol": f"ALIAS{i}"} for i in range(1, 101, 3)]  # Every 3rd gene
        dates = [{"genefam_id": i, "date_approved_reserved": "2020-01-01"} for i in range(1, 101, 5)]  # Every 5th gene

        result = list(merge_gene_results(gene_data, xrefs, aliases, dates))

        assert len(result) == 100
        # Spot check a few
        assert result[0]["assigned_symbol"] == "GENE1"
        assert result[99]["assigned_symbol"] == "GENE100"


# Production nomenclature_type rows, verified against the live vgnc_public
# database (they are NOT 'Previous'/'Alias' -- see spec
# fix-prev-symbol-routing.md).
_NOMENCLATURE_TYPES: list[tuple[int, str]] = [
    (1, "previous_symbol"),
    (2, "previous_name"),
    (3, "alias_symbol"),
    (4, "alias_name"),
]


@pytest.mark.integration
class TestBuildAliasesQueryRouting:
    """Behavioral test: prev vs alias routing by nomenclature_type.

    Runs the REAL build_aliases_query against an ephemeral MySQL schema seeded
    with the four production nomenclature_type values. This is the regression
    guard for the bug where prev_symbol / prev_name shipped empty because the
    query filtered on the literal 'Previous', which does not exist in the
    database -- every previous value leaked into the alias fields.

    The query uses MySQL-only ``GROUP_CONCAT ... SEPARATOR``, so it cannot run
    on the in-memory SQLite harness used elsewhere in this file; a real MySQL
    (local or CI) is required. Connect via ``MYSQL_TEST_DSN`` (default
    ``root:root@127.0.0.1:3306``); skipped unless ``--integration`` is passed.
    """

    @pytest.fixture
    def mysql_aliases_schema(self) -> Iterator[object]:
        """Create an ephemeral MySQL schema seeded with one gene of each type.

        Yields a MySQLdb connection already USE'd onto the ephemeral schema.
        Drops the schema on teardown.
        """
        import MySQLdb

        dsn = os.environ.get("MYSQL_TEST_DSN", "root:root@127.0.0.1:3306")
        creds, hostport = dsn.rsplit("@", 1)
        user, passwd = creds.split(":", 1)
        host, port = hostport.split(":", 1)
        schema = f"test_vgnc_aliases_{os.getpid()}_{random.randint(1000, 9999)}"

        conn = MySQLdb.connect(host=host, user=user, passwd=passwd, port=int(port))
        cur = conn.cursor()
        try:
            cur.execute(f"CREATE DATABASE `{schema}`")
            cur.execute(f"USE `{schema}`")
            for stmt in (
                "CREATE TABLE nomenclature_type (id INT PRIMARY KEY, type VARCHAR(45))",
                "CREATE TABLE alt_symbol "
                "(id INT PRIMARY KEY, symbol VARCHAR(45), nomenclature_type_id INT)",
                "CREATE TABLE alt_name "
                "(id INT PRIMARY KEY, name VARCHAR(255), nomenclature_type_id INT)",
                "CREATE TABLE gene_alt_symbol "
                "(id INT PRIMARY KEY, genefam_id INT, symbol_id INT)",
                "CREATE TABLE gene_alt_name "
                "(id INT PRIMARY KEY, genefam_id INT, name_id INT)",
            ):
                cur.execute(stmt)
            cur.executemany(
                "INSERT INTO nomenclature_type VALUES (%s, %s)", _NOMENCLATURE_TYPES
            )
            # Gene 1 carries exactly one value of EACH nomenclature type.
            cur.executemany(
                "INSERT INTO alt_symbol VALUES (%s, %s, %s)",
                [(10, "PREV_SYM", 1), (11, "ALIAS_SYM", 3)],
            )
            cur.executemany(
                "INSERT INTO alt_name VALUES (%s, %s, %s)",
                [(20, "Previous name", 2), (21, "Alias name", 4)],
            )
            cur.executemany(
                "INSERT INTO gene_alt_symbol VALUES (%s, %s, %s)",
                [(1, 1, 10), (2, 1, 11)],
            )
            cur.executemany(
                "INSERT INTO gene_alt_name VALUES (%s, %s, %s)",
                [(1, 1, 20), (2, 1, 21)],
            )
            conn.commit()
            yield conn
        finally:
            cur.execute(f"DROP DATABASE IF EXISTS `{schema}`")
            cur.close()
            conn.close()

    @staticmethod
    def _fetch_aliases(conn: object, genefam_id: int) -> dict[str, str | None]:
        """Run build_aliases_query for one gene and return its row as a dict."""
        from vgnc_download_file_generator.database.queries import (
            compile_query_for_mysql,
        )

        cur = conn.cursor()  # type: ignore[attr-defined]
        query = build_aliases_query(genefam_ids=[genefam_id])
        sql, params = compile_query_for_mysql(query)
        cur.execute(sql, params)
        cols = [desc[0] for desc in cur.description]
        row = dict(zip(cols, cur.fetchone(), strict=False))
        cur.close()
        return row

    def test_routes_each_nomenclature_type_to_correct_output(
        self, mysql_aliases_schema: object
    ) -> None:
        """prev_* and alias_* must each hold only their own nomenclature type.

        Fails on the buggy query: prev_symbol/prev_name come back NULL (no type
        equals 'Previous') and the previous values leak into the alias fields.
        """
        row = self._fetch_aliases(mysql_aliases_schema, genefam_id=1)

        assert row["prev_symbol"] == "PREV_SYM", (
            f"prev_symbol should be PREV_SYM, got {row['prev_symbol']!r} "
            f"(alias_symbol={row['alias_symbol']!r})"
        )
        assert row["prev_name"] == "Previous name", (
            f"prev_name should be 'Previous name', got {row['prev_name']!r} "
            f"(alias_name={row['alias_name']!r})"
        )
        assert row["alias_symbol"] == "ALIAS_SYM"
        assert row["alias_name"] == "Alias name"

    def test_previous_value_does_not_leak_into_alias(
        self, mysql_aliases_schema: object
    ) -> None:
        """A previous symbol/name must never appear in the alias fields."""
        row = self._fetch_aliases(mysql_aliases_schema, genefam_id=1)

        alias_symbols = (row["alias_symbol"] or "").split("|")
        alias_names = (row["alias_name"] or "").split("|")
        assert "PREV_SYM" not in alias_symbols
        assert "Previous name" not in alias_names


# Trimmed real-data extract of the vgnc_public_2026_07_05 snapshot: only the
# five tables read by build_aliases_query. Lets the test exercise the real
# nomenclature_type values and distributions without the 262 MB full dump.
_ALIASES_FIXTURE = Path(__file__).parent / "fixtures" / "vgnc_aliases_snapshot.sql"


@pytest.mark.integration
class TestBuildAliasesQueryRealSnapshot:
    """Real-data cross-check of build_aliases_query vs the production snapshot.

    Loads the trimmed vgnc_public_2026_07_05 extract into an ephemeral MySQL,
    runs the REAL query, and asserts the output matches an independent Python
    re-derivation for EVERY gene (different code path than the SQL, so a routing
    bug like the old '= Previous' literal is caught). Also pins the headline
    cases:
      - gene 697   : alias-only gene (alias_symbol=CYP5A1).
      - gene 13195 : previous-only gene (prev_symbol=H1FNT).
      - gene 91593 (VGNC:81821): the SAME name string appears in BOTH alias_name
        and prev_name because curators stored it under both nomenclature types
        -- proves routing is by nomenclature_type, not by string value.
    """

    # Minimal column layout matching the fixture's named-column INSERTs.
    _DDL = (
        "CREATE TABLE nomenclature_type (id INT PRIMARY KEY, type VARCHAR(45))",
        "CREATE TABLE alt_symbol "
        "(id INT PRIMARY KEY, symbol VARCHAR(45), nomenclature_type_id INT)",
        "CREATE TABLE alt_name "
        "(id INT PRIMARY KEY, name VARCHAR(255), nomenclature_type_id INT)",
        "CREATE TABLE gene_alt_symbol "
        "(id INT PRIMARY KEY, genefam_id INT, symbol_id INT)",
        "CREATE TABLE gene_alt_name "
        "(id INT PRIMARY KEY, genefam_id INT, name_id INT)",
    )

    @pytest.fixture
    def snapshot_db(self) -> Iterator[Any]:
        """Ephemeral MySQL schema loaded with the real alias snapshot data."""
        import MySQLdb

        dsn = os.environ.get("MYSQL_TEST_DSN", "root:root@127.0.0.1:3306")
        creds, hostport = dsn.rsplit("@", 1)
        user, passwd = creds.split(":", 1)
        host, port = hostport.split(":", 1)
        schema = f"test_vgnc_alias_snap_{os.getpid()}_{random.randint(1000, 9999)}"

        conn = MySQLdb.connect(host=host, user=user, passwd=passwd, port=int(port))
        cur = conn.cursor()
        try:
            cur.execute(f"CREATE DATABASE `{schema}`")
            cur.execute(f"USE `{schema}`")
            for stmt in self._DDL:
                cur.execute(stmt)
            # Load the real-data fixture (one INSERT statement per line).
            for line in _ALIASES_FIXTURE.read_text().splitlines():
                line = line.strip()
                if line.startswith("INSERT INTO"):
                    cur.execute(line)
            conn.commit()
            yield conn
        finally:
            cur.execute(f"DROP DATABASE IF EXISTS `{schema}`")
            cur.close()
            conn.close()

    @staticmethod
    def _query_rows(conn: Any) -> dict[int, dict[str, set[str]]]:
        """Run build_aliases_query for all genes; return genefam_id -> field sets."""
        from vgnc_download_file_generator.database.queries import (
            compile_query_for_mysql,
        )

        cur = conn.cursor()
        sql, params = compile_query_for_mysql(build_aliases_query())
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]

        def to_set(pipe_value: object) -> set[str]:
            return {v for v in str(pipe_value or "").split("|") if v}

        out: dict[int, dict[str, set[str]]] = {}
        for row in cur.fetchall():
            r = dict(zip(cols, row, strict=False))
            gid = r["genefam_id"]
            out[gid] = {
                "alias_symbol": to_set(r["alias_symbol"]),
                "alias_name": to_set(r["alias_name"]),
                "prev_symbol": to_set(r["prev_symbol"]),
                "prev_name": to_set(r["prev_name"]),
            }
        cur.close()
        return out

    @staticmethod
    def _expected_rows(conn: Any) -> dict[int, dict[str, set[str]]]:
        """Independently re-derive the expected field sets from the raw tables.

        Pure-Python grouping (a different code path than the SQL), so it is a
        genuine oracle for the query's routing.
        """
        cur = conn.cursor()
        cur.execute("SELECT id, type FROM nomenclature_type")
        type_str = {int(i): t for i, t in cur.fetchall()}
        # nomenclature_type value -> output column name. The DB uses
        # 'previous_symbol'/'previous_name' but the download columns are
        # 'prev_symbol'/'prev_name' -- this mapping is exactly what the original
        # bug got wrong (it assumed a literal 'Previous' instead).
        field_for_type = {
            "previous_symbol": "prev_symbol",
            "previous_name": "prev_name",
            "alias_symbol": "alias_symbol",
            "alias_name": "alias_name",
        }
        cur.execute("SELECT id, symbol, nomenclature_type_id FROM alt_symbol")
        sym = {int(i): (s, int(t)) for i, s, t in cur.fetchall()}
        cur.execute("SELECT id, name, nomenclature_type_id FROM alt_name")
        name = {int(i): (n, int(t)) for i, n, t in cur.fetchall()}

        out: dict[int, dict[str, set[str]]] = {}
        for table, lookup, key_for in (
            ("gene_alt_symbol", sym, "symbol_id"),
            ("gene_alt_name", name, "name_id"),
        ):
            cur.execute(f"SELECT genefam_id, {key_for} FROM {table}")
            for gid, ref in cur.fetchall():
                gid, ref = int(gid), int(ref)
                value, tid = lookup[ref]
                field = field_for_type[type_str[tid]]
                out.setdefault(gid, {
                    "alias_symbol": set(), "alias_name": set(),
                    "prev_symbol": set(), "prev_name": set(),
                })[field].add(value)
        cur.close()
        return out

    def test_nomenclature_types_are_the_real_production_values(
        self, snapshot_db: Any
    ) -> None:
        """The fixture carries the four real nomenclature_type strings."""
        cur = snapshot_db.cursor()
        cur.execute("SELECT type FROM nomenclature_type ORDER BY id")
        types = [r[0] for r in cur.fetchall()]
        cur.close()
        assert types == [
            "previous_symbol", "previous_name", "alias_symbol", "alias_name",
        ]

    def test_query_matches_independent_derivation_for_every_gene(
        self, snapshot_db: Any
    ) -> None:
        """SQL routing must equal a Python re-derivation for all genes.

        This is the comprehensive guard: a wrong filter literal (e.g. the old
        'Previous') would route previous values into alias fields and leave
        prev_* empty, diverging from this oracle.
        """
        actual = self._query_rows(snapshot_db)
        expected = self._expected_rows(snapshot_db)
        assert set(actual) == set(expected), "gene sets differ"
        for gid in expected:
            assert actual[gid] == expected[gid], f"routing mismatch for gene {gid}"

    def test_alias_only_gene_routes_to_alias_fields(self, snapshot_db: Any) -> None:
        """Gene 697 carries only alias-typed rows -> alias_* set, prev_* empty."""
        row = self._query_rows(snapshot_db)[697]
        assert row["alias_symbol"] == {"CYP5A1"}
        assert row["prev_symbol"] == set()
        # Its alias_name is the cytochrome name; prev_name must be empty.
        assert row["prev_name"] == set()

    def test_previous_only_gene_routes_to_prev_fields(self, snapshot_db: Any) -> None:
        """Gene 13195 carries only previous-typed rows -> prev_* set, alias_* empty."""
        row = self._query_rows(snapshot_db)[13195]
        assert row["prev_symbol"] == {"H1FNT"}
        assert row["alias_symbol"] == set()
        assert row["prev_name"] == {"H1 histone family member N, testis specific"}

    def test_dual_type_name_appears_in_both_fields(self, snapshot_db: Any) -> None:
        """VGNC:81821 (gene 91593): same string stored as both alias_name and
        previous_name must surface in BOTH fields (per-type routing)."""
        row = self._query_rows(snapshot_db)[91593]
        cyto = "cytochrome P450 family 5 subfamily A member 1"
        assert row["alias_symbol"] == {"CYP5A1"}
        assert cyto in row["alias_name"]
        assert cyto in row["prev_name"]
