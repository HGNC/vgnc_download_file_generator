"""Tests for split query architecture.

Tests the new approach of splitting the complex build_gene_query into
multiple simpler queries and merging results in Python.
"""



from sqlalchemy.sql.expression import TextClause

from vgnc_download_file_generator.database.queries_split import (
    build_aliases_query,
    build_dates_query,
    build_gene_data_query,
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

    def test_chromosome_filter(self) -> None:
        """Test chromosome filter is applied correctly."""
        query = build_gene_data_query(filters={"chromosome": "X"})
        sql = query.text

        assert "c.display_name" in sql
        assert ":chromosome" in sql

    def test_build_gene_data_query_filters_ghl_to_default_assembly(self) -> None:
        """The default-assembly filter must RESTRICT gene_has_location rows.

        A predicate on a separate ``LEFT JOIN assembly a ...`` is inert when no
        ``a.*`` column is selected and ``gene_location``/``chromosomes`` join off
        ``ghl`` directly -- every location row still emits one output row (the
        ABHD12 / VGNC:14936 4-row bug). The filter must live on the ``ghl`` JOIN
        itself as a correlated EXISTS, so non-default-assembly location rows are
        excluded.
        """
        query = build_gene_data_query(filters={"taxon_id": 9913})
        sql = query.text

        # The assembly filter must be a correlated EXISTS on the ghl join
        assert "EXISTS" in sql
        assert "FROM assembly a" in sql
        assert "a.id = ghl.assembly_id" in sql
        assert "a.is_vgnc_default = 1" in sql
        assert "a.taxon_id = gf.taxon_id" in sql

    def test_build_gene_data_query_has_no_inert_assembly_join(self) -> None:
        """There must NOT be a standalone LEFT JOIN assembly whose columns are
        never selected / depended on -- that filter is a no-op (regression guard
        for the inert-join bug found in review)."""
        query = build_gene_data_query(filters=None)
        sql = query.text

        assert "LEFT JOIN assembly a ON ghl.assembly_id = a.id" not in sql

    def test_build_gene_data_query_pins_default_assembly_to_ensembl_source(self) -> None:
        """The default-assembly EXISTS must pin assembly.source = 'Ensembl'.

        is_vgnc_default is NOT unique per species: VGNC:6926 has two default
        assemblies (NCBI Pan_tro_3.0 + Ensembl Pan_tro_3.0), which produced two
        location rows (chromosome 14 and 1). The canonical default is the
        Ensembl-sourced one, so the EXISTS must include a.source = 'Ensembl'.
        """
        query = build_gene_data_query(filters={"taxon_id": 9913})
        sql = query.text
        assert "a.source = 'Ensembl'" in sql

    def test_default_assembly_filter_collapses_to_one_row_per_gene(self) -> None:
        """Behavioral proof (in-memory SQLite) that restricting gene_has_location
        to the species' Ensembl-sourced default assembly yields exactly one
        canonical row per gene, even when a species has MORE THAN ONE default
        assembly.

        Mirrors the VGNC:6926 production diagnostic (Pan troglodytes, taxon 9598):
        a default NCBI Pan_tro_3.0 assembly (chr 14) AND a default Ensembl
        Pan_tro_3.0 assembly (chr 1), both is_vgnc_default = 1, plus two
        non-default NCBI assemblies. is_vgnc_default alone is not unique, so the
        canonical location is the default assembly sourced from 'Ensembl'. A gene
        with no such location is still preserved (LEFT JOIN, NULL location).

        (The production query is MySQL-specific, so this runs the load-bearing
        relational logic -- the EXISTS with the source pin -- in isolation.)
        """
        import sqlite3

        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE genefam (genefam_id INTEGER, taxon_id INTEGER, assigned_id TEXT);
            CREATE TABLE gene_has_location (gene_id INTEGER, location_id INTEGER, assembly_id INTEGER);
            CREATE TABLE assembly (id INTEGER, taxon_id INTEGER, is_vgnc_default INTEGER, source TEXT);
            CREATE TABLE gene_location (id INTEGER, chr_id INTEGER, start INTEGER, end INTEGER);
            CREATE TABLE chromosomes (chr_id INTEGER, display_name TEXT, taxon_id INTEGER);
            """
        )
        # Gene 1 (VGNC:6926): two DEFAULT assemblies (NCBI + Ensembl) + two
        # non-default NCBI ones. The Ensembl default (assembly 23, chr 1) wins.
        cur.execute("INSERT INTO genefam VALUES (1, 9598, 'VGNC:6926')")
        cur.executemany(
            "INSERT INTO assembly VALUES (?, ?, ?, ?)",
            [(3, 9598, 1, "NCBI"), (23, 9598, 1, "Ensembl"), (27, 9598, 0, "NCBI"), (104, 9598, 0, "NCBI")],
        )
        cur.executemany(
            "INSERT INTO gene_has_location VALUES (?, ?, ?)",
            [(1, 412433, 3), (1, 486777, 23), (1, 584093, 27), (1, 1546350, 104)],
        )
        cur.executemany(
            "INSERT INTO gene_location VALUES (?, ?, ?, ?)",
            [(412433, 14, 21176277, 21566347), (486777, 1, 136605058, 136605999),
             (584093, 14, 18212875, 18594504), (1546350, 14, 28669951, 29052657)],
        )
        cur.executemany(
            "INSERT INTO chromosomes VALUES (?, ?, ?)",
            [(14, "14", 9598), (1, "1", 9598)],
        )
        # Gene 2: no location at all.
        cur.execute("INSERT INTO genefam VALUES (2, 9598, 'VGNC:99999')")

        rows = cur.execute(
            """
            SELECT gf.genefam_id, gf.assigned_id, c.display_name, gl.start
            FROM genefam gf
            LEFT JOIN gene_has_location ghl ON gf.genefam_id = ghl.gene_id
                AND EXISTS (SELECT 1 FROM assembly a
                            WHERE a.id = ghl.assembly_id
                              AND a.is_vgnc_default = 1
                              AND a.taxon_id = gf.taxon_id
                              AND a.source = 'Ensembl')
            LEFT JOIN gene_location gl ON ghl.location_id = gl.id
            LEFT JOIN chromosomes c ON gl.chr_id = c.chr_id
            """
        ).fetchall()
        conn.close()

        by_gene: dict[int, list] = {}
        for gid, _aid, chr_, start in rows:
            by_gene.setdefault(gid, []).append((chr_, start))

        # Gene collapses to exactly one row: the Ensembl default (chr 1).
        assert len(by_gene[1]) == 1, f"gene 1 should have 1 row, got {len(by_gene[1])}"
        assert by_gene[1][0][0] == "1", "must be the Ensembl default's chromosome"
        assert by_gene[1][0][1] == 136605058  # Ensembl default's start
        # Locationless gene is still emitted (LEFT JOIN preserved), with NULL location.
        assert len(by_gene[2]) == 1, "locationless gene must be preserved"
        assert by_gene[2][0][0] is None

    def test_chromosome_filter_un_uses_like(self) -> None:
        """Test that 'Un' chromosome uses LIKE for prefix matching.

        The 'Un' chromosome should match all chromosomes starting with 'Un'
        (e.g., Un0001, Un_1, Un_random) using LIKE pattern matching.
        """
        query = build_gene_data_query(filters={"chromosome": "Un"})
        sql = query.text

        # Should use LIKE for prefix matching
        assert "LIKE" in sql
        assert "c.display_name" in sql
        # The parameter should be 'Un%' for prefix matching
        assert ":chromosome" in sql

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


class TestBuildXrefsQuery:
    """Tests for build_xrefs_query - external database references."""

    def test_returns_text_clause(self) -> None:
        """Test that the query returns a SQLAlchemy TextClause."""
        query = build_xrefs_query()
        assert isinstance(query, TextClause)

    def test_returns_all_xref_columns(self) -> None:
        """Test that all 6 xref types are in the query."""
        query = build_xrefs_query()
        sql = query.text

        # Should have all 6 xref types
        assert "ncbi_gene_id" in sql
        assert "ensembl_gene_id" in sql
        assert "uniprot_ids" in sql
        assert "pubmed_id" in sql
        assert "hgnc_orthologs" in sql
        assert "bgd_id" in sql

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

    def test_xrefs_pubmed_uses_pubmed_resource_name(self) -> None:
        """PubMed mapping must use db_name='pubmed'."""
        query = build_xrefs_query()
        sql = query.text
        assert "dr.db_name = 'pubmed' THEN x.xref END) AS pubmed_id" in sql

    def test_xrefs_hgnc_ortholog_uses_hgnc_ortholog_resource_name(self) -> None:
        """HGNC ortholog mapping must use db_name='hgnc_ortholog'."""
        query = build_xrefs_query()
        sql = query.text
        assert "dr.db_name = 'hgnc_ortholog' THEN x.xref END) AS hgnc_orthologs" in sql

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
