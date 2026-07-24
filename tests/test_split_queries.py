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
