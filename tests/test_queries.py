"""Tests for database query builders."""


from sqlalchemy.sql.expression import TextClause


class TestBuildSpeciesDisplayNameQuery:
    """Tests for build_species_display_name_query function."""

    def test_generates_sql_with_correct_select(self) -> None:
        """Test that generated SQL selects display_name."""
        from vgnc_download_file_generator.database.queries import (
            build_species_display_name_query,
        )

        query = build_species_display_name_query(9913)

        # Check query selects display_name
        query_str = str(query)
        assert "SELECT" in query_str.upper()
        assert "display_name" in query_str

    def test_filters_by_taxon_id(self) -> None:
        """Test that query filters by taxon_id."""
        from vgnc_download_file_generator.database.queries import (
            build_species_display_name_query,
        )

        query = build_species_display_name_query(9913)

        # Check query filters by taxon_id
        query_str = str(query)
        assert "WHERE" in query_str.upper()
        assert "taxon_id" in query_str.lower()

    def test_uses_bind_params_for_taxon_id(self) -> None:
        """Test that query uses bind parameters for taxon_id."""
        from vgnc_download_file_generator.database.queries import (
            build_species_display_name_query,
        )

        query = build_species_display_name_query(9913)

        # Check query uses bind parameters
        query_str = str(query)
        assert ":taxon_id" in query_str or "taxon_id" in query_str

    def test_selects_from_species_table(self) -> None:
        """Test that query selects from species table."""
        from vgnc_download_file_generator.database.queries import (
            build_species_display_name_query,
        )

        query = build_species_display_name_query(9913)

        # Check it queries species table
        query_str = str(query)
        assert "FROM species" in query_str or "FROM `species`" in query_str

    def test_returns_text_construct(self) -> None:
        """Test that function returns SQLAlchemy text construct."""
        from vgnc_download_file_generator.database.queries import (
            build_species_display_name_query,
        )

        query = build_species_display_name_query(9913)

        assert isinstance(query, TextClause)


class TestCompileQueryForMysql:
    """Tests for compile_query_for_mysql function."""

    def test_converts_named_params_to_positional(self) -> None:
        """Test that named parameters are converted to %s placeholders."""
        from sqlalchemy import text

        from vgnc_download_file_generator.database.queries import (
            compile_query_for_mysql,
        )

        query = text("SELECT * FROM table WHERE id = :id AND name = :name")
        sql, params = compile_query_for_mysql(query)

        # Should use %s placeholders
        assert "%s" in sql
        # Should not have named params
        assert ":id" not in sql
        assert ":name" not in sql

    def test_returns_tuple_of_params(self) -> None:
        """Test that function returns tuple of parameters."""
        from sqlalchemy import bindparam, text

        from vgnc_download_file_generator.database.queries import (
            compile_query_for_mysql,
        )

        query = text("SELECT * FROM table WHERE id = :id").bindparams(bindparam("id", value=123))
        sql, params = compile_query_for_mysql(query)

        assert isinstance(params, tuple)
        assert len(params) == 1
        assert params[0] == 123

    def test_handles_expanding_params_for_in_clause(self) -> None:
        """Test that expanding parameters (IN clauses) are handled correctly."""
        from sqlalchemy import bindparam, text

        from vgnc_download_file_generator.database.queries import (
            compile_query_for_mysql,
        )

        query = text("SELECT * FROM table WHERE id IN :ids").bindparams(
            bindparam("ids", value=(1, 2, 3), expanding=True)
        )
        sql, params = compile_query_for_mysql(query)

        # Should expand to multiple placeholders
        assert "(%s, %s, %s)" in sql
        # Should have all three values
        assert len(params) == 3
        assert params == (1, 2, 3)

    def test_preserves_param_order(self) -> None:
        """Test that parameter order is preserved in the output tuple."""
        from sqlalchemy import bindparam, text

        from vgnc_download_file_generator.database.queries import (
            compile_query_for_mysql,
        )

        query = text("SELECT * FROM table WHERE a = :a AND b = :b AND c = :c").bindparams(
            bindparam("a", value=1),
            bindparam("b", value=2),
            bindparam("c", value=3),
        )
        sql, params = compile_query_for_mysql(query)

        # Order should be a, b, c
        assert params == (1, 2, 3)
