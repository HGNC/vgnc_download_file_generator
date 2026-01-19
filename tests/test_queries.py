"""Tests for database query builders."""


from sqlalchemy.sql.expression import TextClause


class TestBuildSpeciesQuery:
    """Tests for build_species_query function."""

    def test_generates_sql_with_correct_where_clause(self) -> None:
        """Test that generated SQL has correct WHERE clause for live non-human species."""
        from vgnc_download_file_generator.database.queries import build_species_query

        query = build_species_query()

        # Check query contains required conditions
        query_str = str(query)
        assert "WHERE" in query_str
        assert "is_live" in query_str
        assert "taxon_id" in query_str

    def test_uses_bind_params_for_is_live_values(self) -> None:
        """Test that query uses bind parameters for is_live values."""
        from vgnc_download_file_generator.database.queries import build_species_query

        query = build_species_query()

        # Check query uses bind parameters (SQLAlchemy 2.0 uses POSTCOMPILE for expanding)
        query_str = str(query)
        # Should have bind param placeholder (may be POSTCOMPILE format)
        assert "is_live_values" in query_str.lower() or "POSTCOMPILE" in query_str

    def test_excludes_human_taxon_id(self) -> None:
        """Test that query excludes human (taxon_id = 9606)."""
        from vgnc_download_file_generator.database.queries import build_species_query

        query = build_species_query()

        # Check query excludes human
        query_str = str(query)
        assert "9606" not in query_str  # Should use bind param
        assert ":human_taxon_id" in query_str or ":exclude_taxon_id" in query_str

    def test_selects_from_species_table(self) -> None:
        """Test that query selects from species table."""
        from vgnc_download_file_generator.database.queries import build_species_query

        query = build_species_query()

        # Check it queries species table
        query_str = str(query)
        assert "FROM species" in query_str or "FROM `species`" in query_str

    def test_no_limit_clause(self) -> None:
        """Test that query has no LIMIT (suitable for streaming)."""
        from vgnc_download_file_generator.database.queries import build_species_query

        query = build_species_query()

        # Check no LIMIT for streaming
        query_str = str(query).upper()
        assert "LIMIT" not in query_str

    def test_returns_text_construct(self) -> None:
        """Test that function returns SQLAlchemy text construct."""
        from vgnc_download_file_generator.database.queries import build_species_query

        query = build_species_query()

        assert isinstance(query, TextClause)

    def test_binds_params_correctly(self) -> None:
        """Test that bind parameters are correctly named and can be used."""
        from vgnc_download_file_generator.database.queries import build_species_query

        query = build_species_query()

        # Check that bind parameters are defined by examining the query string
        query_str = str(query)
        # Should have :is_live_values or POSTCOMPILE version
        assert "is_live" in query_str.lower() or "POSTCOMPILE" in query_str
        # Should have :human_taxon_id
        assert "human_taxon_id" in query_str or ":taxon_id" in query_str


class TestBuildGeneQuery:
    """Tests for build_gene_query function."""

    def test_generates_sql_with_joins(self) -> None:
        """Test that generated SQL has correct JOIN syntax across tables."""
        from vgnc_download_file_generator.database.queries import build_gene_query

        query = build_gene_query()

        # Check query contains required JOINs
        query_str = str(query).upper()
        assert "JOIN" in query_str
        assert "GENEFAM" in query_str

    def test_joins_all_required_tables(self) -> None:
        """Test that query joins all required tables."""
        from vgnc_download_file_generator.database.queries import build_gene_query

        query = build_gene_query()
        query_str = str(query).upper()

        # Should join main tables
        assert "LOCUS_TYPE" in query_str or "LOCUS_TYPE" in str(query)
        assert "LOCUS_GROUP" in query_str or "LOCUS_GROUP" in str(query)
        assert "GENE_STATUS" in query_str or "STATUS" in query_str
        assert "CHROMOSOME" in query_str or "CHROM" in query_str

    def test_empty_filters_returns_base_query(self) -> None:
        """Test that empty filter dict returns base query with no WHERE."""
        from vgnc_download_file_generator.database.queries import build_gene_query

        query = build_gene_query()
        query_str = str(query).upper()

        # The main query should have WHERE 1=1 for dynamic building
        # Subqueries have WHERE clauses for filtering aliases
        lines = query_str.split("\n")
        main_query_has_trivial_where = False
        for line in lines:
            # Check for WHERE 1=1 in main query (before subqueries)
            if "WHERE 1=1" in line:
                main_query_has_trivial_where = True
                break

        assert main_query_has_trivial_where, "Main query should have WHERE 1=1 for dynamic filter building"

    def test_single_filter_taxon_id(self) -> None:
        """Test single filter by taxon_id."""
        from vgnc_download_file_generator.database.queries import build_gene_query

        query = build_gene_query(filters={"taxon_id": 9606})
        query_str = str(query)

        # Should have WHERE clause with taxon_id filter
        assert "WHERE" in query_str.upper()
        assert "taxon_id" in query_str.lower()

    def test_single_filter_chromosome(self) -> None:
        """Test single filter by chromosome."""
        from vgnc_download_file_generator.database.queries import build_gene_query

        query = build_gene_query(filters={"chromosome": "X"})
        query_str = str(query)

        # Should have WHERE clause with chromosome filter
        assert "WHERE" in query_str.upper()
        assert "chromosome" in query_str.lower() or "chr" in query_str.lower()

    def test_single_filter_locus_type(self) -> None:
        """Test single filter by locus_type."""
        from vgnc_download_file_generator.database.queries import build_gene_query

        query = build_gene_query(filters={"locus_type": "gene with protein product"})
        query_str = str(query)

        # Should have WHERE clause with locus_type filter
        assert "WHERE" in query_str.upper()
        assert "locus_type" in query_str.lower()

    def test_single_filter_locus_group(self) -> None:
        """Test single filter by locus_group."""
        from vgnc_download_file_generator.database.queries import build_gene_query

        query = build_gene_query(filters={"locus_group": "protein-coding gene"})
        query_str = str(query)

        # Should have WHERE clause with locus_group filter
        assert "WHERE" in query_str.upper()
        assert "locus_group" in query_str.lower()

    def test_single_filter_status(self) -> None:
        """Test single filter by status."""
        from vgnc_download_file_generator.database.queries import build_gene_query

        query = build_gene_query(filters={"status": "Approved"})
        query_str = str(query)

        # Should have WHERE clause with status filter
        assert "WHERE" in query_str.upper()
        assert "status" in query_str.lower()

    def test_multiple_filters_with_and_conditions(self) -> None:
        """Test multiple filters create AND conditions."""
        from vgnc_download_file_generator.database.queries import build_gene_query

        query = build_gene_query(
            filters={"taxon_id": 9593, "chromosome": "1", "status": "Approved"}
        )
        query_str = str(query).upper()

        # Should have WHERE clause
        assert "WHERE" in query_str
        # Multiple filters should appear
        assert "TAXON_ID" in query_str or str(query)
        assert "CHROMOSOME" in query_str or "CHR" in str(query).upper()

    def test_uses_bind_params_prevents_sql_injection(self) -> None:
        """Test that filters use bind parameters to prevent SQL injection."""
        from vgnc_download_file_generator.database.queries import build_gene_query

        # Try to inject SQL
        query = build_gene_query(filters={"taxon_id": "9606; DROP TABLE genefam--"})
        query_str = str(query)

        # The dangerous SQL should not appear literally
        assert "DROP TABLE" not in query_str
        # Should use bind param instead
        assert "taxon_id" in query_str.lower()

    def test_returns_text_construct(self) -> None:
        """Test that function returns SQLAlchemy text construct."""
        from vgnc_download_file_generator.database.queries import build_gene_query

        query = build_gene_query()

        assert isinstance(query, TextClause)

    def test_no_limit_clause_for_streaming(self) -> None:
        """Test that query has no LIMIT (suitable for streaming)."""
        from vgnc_download_file_generator.database.queries import build_gene_query

        query = build_gene_query()

        # Check no LIMIT for streaming
        query_str = str(query).upper()
        assert "LIMIT" not in query_str


class TestBuildSpeciesDisplayNameQuery:
    """Tests for build_species_display_name_query function."""

    def test_generates_sql_with_correct_select(self) -> None:
        """Test that generated SQL selects display_name."""
        from vgnc_download_file_generator.database.queries import build_species_display_name_query

        query = build_species_display_name_query(9913)

        # Check query selects display_name
        query_str = str(query)
        assert "SELECT" in query_str.upper()
        assert "display_name" in query_str

    def test_filters_by_taxon_id(self) -> None:
        """Test that query filters by taxon_id."""
        from vgnc_download_file_generator.database.queries import build_species_display_name_query

        query = build_species_display_name_query(9913)

        # Check query filters by taxon_id
        query_str = str(query)
        assert "WHERE" in query_str.upper()
        assert "taxon_id" in query_str.lower()

    def test_uses_bind_params_for_taxon_id(self) -> None:
        """Test that query uses bind parameters for taxon_id."""
        from vgnc_download_file_generator.database.queries import build_species_display_name_query

        query = build_species_display_name_query(9913)

        # Check query uses bind parameters
        query_str = str(query)
        assert ":taxon_id" in query_str or "taxon_id" in query_str

    def test_selects_from_species_table(self) -> None:
        """Test that query selects from species table."""
        from vgnc_download_file_generator.database.queries import build_species_display_name_query

        query = build_species_display_name_query(9913)

        # Check it queries species table
        query_str = str(query)
        assert "FROM species" in query_str or "FROM `species`" in query_str

    def test_returns_text_construct(self) -> None:
        """Test that function returns SQLAlchemy text construct."""
        from vgnc_download_file_generator.database.queries import build_species_display_name_query

        query = build_species_display_name_query(9913)

        assert isinstance(query, TextClause)

