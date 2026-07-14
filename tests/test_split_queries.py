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

    def test_default_assembly_filter_collapses_to_one_row_per_gene(self) -> None:
        """Behavioral proof (in-memory SQLite) that restricting
        gene_has_location to the species' default assembly yields exactly one
        row per gene even when the gene has locations on multiple assemblies,
        while still preserving genes that have no location at all.

        This validates the EXISTS join pattern that
        ``test_build_gene_data_query_filters_ghl_to_default_assembly`` asserts
        is present in the production query. (The production query itself is
        MySQL-specific -- CONCAT/CAST -- so it cannot run on SQLite; this test
        exercises the load-bearing relational logic in isolation.)
        """
        import sqlite3

        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE genefam (genefam_id INTEGER, taxon_id INTEGER, assigned_id TEXT);
            CREATE TABLE gene_has_location (gene_id INTEGER, location_id INTEGER, assembly_id INTEGER);
            CREATE TABLE assembly (id INTEGER, taxon_id INTEGER, is_vgnc_default INTEGER);
            CREATE TABLE gene_location (id INTEGER, chr_id INTEGER, start INTEGER, end INTEGER);
            CREATE TABLE chromosomes (chr_id INTEGER, display_name TEXT, taxon_id INTEGER);
            """
        )
        # Gene 1 (VGNC:14936 analog): 4 locations on 4 assemblies; only assembly 1 is default.
        cur.execute("INSERT INTO genefam VALUES (1, 9913, 'VGNC:14936')")
        cur.executemany(
            "INSERT INTO assembly VALUES (?, ?, ?)",
            [(1, 9913, 1), (2, 9913, 0), (3, 9913, 0), (4, 9913, 0)],
        )
        cur.executemany(
            "INSERT INTO gene_has_location VALUES (?, ?, ?)",
            [(1, 101, 1), (1, 102, 2), (1, 103, 3), (1, 104, 4)],
        )
        cur.executemany(
            "INSERT INTO gene_location VALUES (?, ?, ?, ?)",
            [(101, 7, 1000, 2000), (102, 8, 3000, 4000), (103, 9, 5000, 6000), (104, 10, 7000, 8000)],
        )
        cur.executemany(
            "INSERT INTO chromosomes VALUES (?, ?, ?)",
            [(7, "1", 9913), (8, "1", 9913), (9, "1", 9913), (10, "1", 9913)],
        )
        # Gene 2: no location at all.
        cur.execute("INSERT INTO genefam VALUES (2, 9913, 'VGNC:99999')")

        rows = cur.execute(
            """
            SELECT gf.genefam_id, gf.assigned_id, c.display_name, gl.start
            FROM genefam gf
            LEFT JOIN gene_has_location ghl ON gf.genefam_id = ghl.gene_id
                AND EXISTS (SELECT 1 FROM assembly a
                            WHERE a.id = ghl.assembly_id
                              AND a.is_vgnc_default = 1
                              AND a.taxon_id = gf.taxon_id)
            LEFT JOIN gene_location gl ON ghl.location_id = gl.id
            LEFT JOIN chromosomes c ON gl.chr_id = c.chr_id
            """
        ).fetchall()
        conn.close()

        by_gene: dict[int, list] = {}
        for gid, _aid, chr_, start in rows:
            by_gene.setdefault(gid, []).append((chr_, start))

        # Multi-assembly gene collapses to exactly one row (the default assembly).
        assert len(by_gene[1]) == 1, f"gene 1 should have 1 row, got {len(by_gene[1])}"
        assert by_gene[1][0][1] == 1000  # default assembly's start
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

    def test_xrefs_ncbi_uses_external_db_id_2(self) -> None:
        """In the VGNC DB external_db_id = 2 is the NCBI/Entrez Gene ID.

        The old code mapped external_db_id = 1 -> ncbi, which shipped Ensembl
        IDs into the ncbi_id column. Confirm the corrected mapping.
        """
        query = build_xrefs_query()
        sql = query.text
        assert "external_db_id = 2 THEN x.xref END) AS ncbi_gene_id" in sql

    def test_xrefs_ensembl_uses_external_db_id_1(self) -> None:
        """In the VGNC DB external_db_id = 1 is the Ensembl Gene ID.

        The old code mapped external_db_id = 2 -> ensembl, shipping NCBI IDs
        into the ensembl_gene_id column. Confirm the corrected mapping.
        """
        query = build_xrefs_query()
        sql = query.text
        assert "external_db_id = 1 THEN x.xref END) AS ensembl_gene_id" in sql

    def test_xrefs_uniprot_uses_group_concat(self) -> None:
        """uniprot_ids must aggregate multiple UniProt IDs per gene.

        A gene can have several UniProt IDs (external_db_id IN (3, 15)); the
        old MAX(...) collapsed them to a single value. Use GROUP_CONCAT with a
        pipe separator so JSON can render them as an array.
        """
        query = build_xrefs_query()
        sql = query.text

        assert "GROUP_CONCAT(DISTINCT CASE WHEN x.external_db_id IN (3, 15)" in sql
        assert "SEPARATOR '|')" in sql
        assert "AS uniprot_ids" in sql
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
