"""Split query architecture for gene data export.

This module provides an alternative to the complex build_gene_query that
splits the query into 4 simpler queries and merges results in Python.

This approach provides 2300x performance improvement by avoiding the
expensive CROSS JOIN behavior of multiple LEFT JOINs with complex conditions.
"""

import logging
import os
import re
from collections.abc import Iterator
from typing import Any

import MySQLdb
from sqlalchemy import bindparam
from sqlalchemy.sql.expression import TextClause, text

logger = logging.getLogger(__name__)

# Module-level cache for HGNC symbol fallback table resolution
# False = not yet checked, None = checked but not found, str = resolved table reference
_HGNC_SYMBOL_TABLE_CACHE: str | None | bool = False


def clear_hgnc_symbol_table_cache() -> None:
    """Reset the HGNC symbol table cache for test isolation.

    The cache persists at module level for the lifetime of the process.
    Call this in test setup/teardown to ensure each test starts with a
    clean resolution state.
    """
    global _HGNC_SYMBOL_TABLE_CACHE
    _HGNC_SYMBOL_TABLE_CACHE = False

_GENE_DATA_SELECT = '\n        SELECT DISTINCT\n            gf.genefam_id,\n            gf.taxon_id,\n            gf.assigned_id,\n            gf.assigned_symbol,\n            gf.assigned_name,\n            gs.status AS gene_status,\n            lt.type AS locus_type,\n            lg.name AS locus_group,\n            c.display_name AS chromosome,\n            gl.start,\n            gl.end,\n            gl.strand,\n            gl.band,\n            fn.id AS gene_family_id,\n            fn.name AS gene_family'
_GENE_FROM_JOINS_WHERE = 'FROM genefam gf\n        LEFT JOIN gene_has_locus_type ghtlt ON gf.genefam_id = ghtlt.genefam_id\n        LEFT JOIN locus_type lt ON ghtlt.locus_type_id = lt.id\n        LEFT JOIN locus_group lg ON lt.locus_group_id = lg.id\n        LEFT JOIN gene_has_location ghl ON gf.genefam_id = ghl.gene_id\n            AND ghl.location_id = (\n                SELECT ghl_pick.location_id\n                FROM gene_has_location ghl_pick\n                JOIN gene_location gl_pick ON gl_pick.id = ghl_pick.location_id\n                JOIN chromosomes c_pick ON c_pick.chr_id = gl_pick.chr_id\n                LEFT JOIN assembly a_pick ON a_pick.id = ghl_pick.assembly_id\n                WHERE ghl_pick.gene_id = gf.genefam_id\n                    AND c_pick.taxon_id = gf.taxon_id\n                    AND EXISTS (\n                        SELECT 1\n                        FROM assembly_has_chr ahc\n                        JOIN assembly a2 ON a2.id = ahc.assembly_id\n                        WHERE ahc.chr_id = c_pick.chr_id\n                            AND a2.is_vgnc_default = 1\n                            AND a2.taxon_id = gf.taxon_id\n                    )\n                ORDER BY\n                    CASE\n                        WHEN a_pick.is_vgnc_default = 1 THEN 0\n                        ELSE 1\n                    END,\n                    CASE\n                        WHEN a_pick.is_current = 1 THEN 0\n                        ELSE 1\n                    END,\n                    a_pick.id DESC,\n                    ghl_pick.location_id DESC\n                LIMIT 1\n            )\n        LEFT JOIN gene_location gl ON ghl.location_id = gl.id\n        LEFT JOIN chromosomes c ON gl.chr_id = c.chr_id\n            AND c.taxon_id = gf.taxon_id\n        LEFT JOIN gene_status gs ON gf.status_id = gs.id\n        LEFT JOIN gene_has_family ghf ON gf.genefam_id = ghf.genefam_id\n        LEFT JOIN family_new fn ON ghf.family_id = fn.id\n        WHERE 1=1\n    '


def _apply_gene_filters(
    filters: dict[str, str | int | list[str] | list[int]] | None,
) -> tuple[list[str], dict[str, str | int | tuple[str | int, ...]]]:
    """Build the WHERE-clause fragments + bind params shared by the gene queries.

    Applied identically by :func:`build_gene_data_query` and
    :func:`build_gene_id_page_query` so the id-page walk and the row fetch see
    exactly the same gene set.

    Supported keys: ``taxon_id``, ``locus_type``, ``locus_group``, ``status_id``
    (single value or list -> IN), ``status`` (single value or list -> IN).
    """
    filters = filters or {}
    where_clauses: list[str] = []
    bind_params: dict[str, str | int | tuple[str | int, ...]] = {}
    param_counter = 0

    if filters:
        # Filter by species taxon_id (gene rows). Chromosome taxon safety
        # is enforced in the LEFT JOIN ON clause so locationless genes remain.
        if "taxon_id" in filters:
            param_name = f"taxon_id_{param_counter}"
            where_clauses.append(f"gf.taxon_id = :{param_name}")
            bind_params[param_name] = filters["taxon_id"]  # type: ignore[assignment]
            param_counter += 1

        # Filter by locus_type
        if "locus_type" in filters:
            param_name = f"locus_type_{param_counter}"
            where_clauses.append(f"lt.type = :{param_name}")
            bind_params[param_name] = filters["locus_type"]  # type: ignore[assignment]
            param_counter += 1

        # Filter by locus_group
        if "locus_group" in filters:
            param_name = f"locus_group_{param_counter}"
            where_clauses.append(f"lg.name = :{param_name}")
            bind_params[param_name] = filters["locus_group"]  # type: ignore[assignment]
            param_counter += 1

        # Filter by status_id (supports single value or list for IN clause)
        if "status_id" in filters:
            param_name = f"status_id_{param_counter}"
            status_id_value = filters["status_id"]
            if isinstance(status_id_value, list):
                where_clauses.append(f"gf.status_id IN :{param_name}")
                bind_params[param_name] = tuple(status_id_value)
            else:
                where_clauses.append(f"gf.status_id = :{param_name}")
                bind_params[param_name] = status_id_value
            param_counter += 1

        # Filter by status (supports single value or list for IN clause)
        if "status" in filters:
            param_name = f"status_{param_counter}"
            status_value = filters["status"]
            if isinstance(status_value, list):
                where_clauses.append(f"gs.status IN :{param_name}")
                bind_params[param_name] = tuple(status_value)
            else:
                where_clauses.append(f"gs.status = :{param_name}")
                bind_params[param_name] = status_value
            param_counter += 1

    return where_clauses, bind_params


def _gene_bindparams(
    bind_params: dict[str, str | int | tuple[str | int, ...]],
) -> list[Any]:
    """Expand a {{name: value}} map into SQLAlchemy bindparam() objects.

    Tuple values become expanding IN-clause bind params.
    """
    bindparam_list: list[Any] = []
    for name, value in bind_params.items():
        if isinstance(value, tuple):
            bindparam_list.append(bindparam(name, value=value, expanding=True))
        else:
            bindparam_list.append(bindparam(name, value=value))
    return bindparam_list


def _assemble_gene_query(
    select_clause: str,
    filters: dict[str, str | int | list[str] | list[int]] | None,
    extra_where: list[str] | None = None,
    extra_params: dict[str, str | int | tuple[str | int, ...]] | None = None,
    trailing_sql: str = "",
) -> TextClause:
    """Assemble SELECT + shared FROM/JOINs/WHERE(+filters) into a TextClause.

    The gene-data query and the keyset id-page query share the exact same
    FROM/JOINs and WHERE-filter logic; only the SELECT projection and any
    trailing keyset/ORDER/LIMIT differ.

    Args:
        select_clause: The SELECT projection text (without trailing FROM).
        filters: Gene filters (taxon_id / locus / status...).
        extra_where: Extra WHERE fragments appended after the standard filters.
        extra_params: Bind params for ``extra_where``/``trailing_sql``.
        trailing_sql: SQL appended after all WHERE clauses (e.g. ORDER BY/LIMIT).
    """
    sql = f"{select_clause} {_GENE_FROM_JOINS_WHERE}"

    where_clauses, bind_params = _apply_gene_filters(filters)
    if extra_where:
        where_clauses = where_clauses + extra_where
    if extra_params:
        bind_params.update(extra_params)

    for clause in where_clauses:
        sql = f"{sql}\n          AND {clause}"

    sql = f"{sql}{trailing_sql}"

    if bind_params:
        return text(sql).bindparams(*_gene_bindparams(bind_params))
    return text(sql)


def build_gene_data_query(
    filters: dict[str, str | int | list[str] | list[int]] | None = None,
    genefam_ids: list[int] | None = None,
) -> TextClause:
    """Build main gene data query with core joins only.

    Fetches the core gene information (genefam, gene_status, locus_type/group,
    genomic location, gene family). Xrefs, aliases, and dates are fetched in
    separate queries.

    Args:
        filters: Filter criteria (taxon_id / locus_type / locus_group /
            status_id / status).
        genefam_ids: Optional list of genefam_ids. When given, the query is
            restricted to ``gf.genefam_id IN :genefam_ids``. This is how the
            keyset-paginated exporter fetches one bounded page of rows; without
            it the query returns the full filtered set (backward compatible).

    Returns:
        SQLAlchemy TextClause with bind parameters

    Example:
        >>> query = build_gene_data_query(filters={"taxon_id": 9913})
        >>> cursor.execute(*compile_query_for_mysql(query))
    """
    select_clause = _GENE_DATA_SELECT
    extra_where: list[str] = []
    extra_params: dict[str, str | int | tuple[str | int, ...]] = {}
    if genefam_ids is not None:
        extra_where.append("gf.genefam_id IN :genefam_ids")
        extra_params["genefam_ids"] = tuple(genefam_ids)
    return _assemble_gene_query(select_clause, filters, extra_where, extra_params)


def build_gene_id_page_query(
    filters: dict[str, str | int | list[str] | list[int]] | None = None,
    after_genefam_id: int | None = None,
    limit: int | None = None,
) -> TextClause:
    """Build a keyset id-page query for batched, connection-safe export.

    Returns one bounded page of distinct ``genefam_id`` values greater than
    ``after_genefam_id``, in ascending order, with the same filters as the main
    gene query. The exporter walks these pages so it never holds a single
    server-side cursor (and its MySQL connection) open for the whole dataset,
    which is what caused the Cloud Run ``(2013)``/``(2006)`` drops.

    The page is ``genefam_id``-keyed (the ``genefam`` PK), so pagination is
    stable and lossless: a gene's rows share one id, so advancing past the last
    id in a page never splits or skips a gene.

    Args:
        filters: Filter criteria (same keys as :func:`build_gene_data_query`).
        after_genefam_id: Exclusive lower bound (previous page's last id).
            When None, the first page starts from the lowest id.
        limit: Page size (max distinct genefam_ids returned).

    Returns:
        SQLAlchemy TextClause with bind parameters
    """
    select_clause = "\n        SELECT DISTINCT gf.genefam_id\n    "
    extra_where: list[str] = []
    extra_params: dict[str, str | int | tuple[str | int, ...]] = {}
    if after_genefam_id is not None:
        extra_where.append("gf.genefam_id > :after_genefam_id")
        extra_params["after_genefam_id"] = after_genefam_id
    trailing_sql = ""
    if limit is not None:
        trailing_sql = "\n        ORDER BY gf.genefam_id\n        LIMIT :limit"
        extra_params["limit"] = limit
    return _assemble_gene_query(select_clause, filters, extra_where, extra_params, trailing_sql)



def build_xrefs_query(genefam_ids: list[int] | None = None) -> TextClause:
    """Build query for all external database references (xrefs).

    Uses conditional aggregation to fetch all xref fields in a single query.

    IMPORTANT: map by ``database_resource.db_name`` (stable semantic key)
    instead of hardcoded ``external_db_id`` integers, which can vary across DB
    snapshots/clones.

    - NCBI Gene ID (db_name = ``ncbi_gene``)
    - Ensembl Gene ID (db_name = ``ensembl_gene``)
    - UniProt IDs (db_name = ``uniprot_protein``) -- one gene may have several
    - PubMed ID (db_name = ``pubmed``)
    - HGNC Orthologs (prefer HGNC xrefs from db_name in
      ``('hgnc_gene', 'hgnc_ortholog')`` and preserve multiple IDs with
      ``GROUP_CONCAT``; fall back to
      ``genefam_orthologs.db_id_a`` for genes where the ortholog section exists
      but the xref row is missing). The fallback join uses the indexed
      ``genefam_id_b`` FK (``go.genefam_id_b = ghx.genefam_id``) with
      ``go.vgnc_b IS NOT NULL`` to preserve the exact row set previously
      matched by the unindexed ``go.vgnc_b = gf.assigned_id`` string join.
    - BGD ID (db_name = ``bgd_gene``)
    - HORDE ID (db_name = ``horde``)

    No ``created_by`` filter is applied. A previous ``WHERE ghx.created_by = 1``
    silently dropped PubMed links (curated under a different editor id), so
    ``pubmed_id`` shipped as NULL for every gene. The ``MAX`` / ``GROUP_CONCAT
    DISTINCT`` aggregations already collapse duplicate links, so the editor
    filter is unnecessary as well as harmful.

    Args:
        genefam_ids: List of genefam_ids to filter (from main query results)

    Returns:
        SQLAlchemy TextClause with bind parameters

    Example:
        >>> ids = [1, 2, 3]
        >>> query = build_xrefs_query(genefam_ids=ids)
        >>> cursor.execute(*compile_query_for_mysql(query))
    """
    sql = """
        SELECT
            ghx.genefam_id,
            MAX(CASE WHEN dr.db_name = 'ncbi_gene' THEN x.xref END) AS ncbi_gene_id,
            MAX(CASE WHEN dr.db_name = 'ensembl_gene' THEN x.xref END) AS ensembl_gene_id,
            GROUP_CONCAT(
                DISTINCT CASE WHEN dr.db_name = 'uniprot_protein' THEN x.xref END
                ORDER BY x.xref
                SEPARATOR '|'
            ) AS uniprot_ids,
            GROUP_CONCAT(
                DISTINCT CASE WHEN dr.db_name = 'pubmed' THEN x.xref END
                ORDER BY x.xref
                SEPARATOR '|'
            ) AS pubmed_id,
            COALESCE(
                NULLIF(
                    GROUP_CONCAT(
                        DISTINCT CASE WHEN dr.db_name IN ('hgnc_gene', 'hgnc_ortholog') THEN x.xref END
                        ORDER BY x.xref
                        SEPARATOR '|'
                    ),
                    ''
                ),
                GROUP_CONCAT(
                    DISTINCT CASE WHEN go.db_id_a LIKE 'HGNC:%%' THEN go.db_id_a END
                    ORDER BY go.db_id_a
                    SEPARATOR '|'
                )
            ) AS hgnc_orthologs,
            MAX(CASE WHEN dr.db_name = 'bgd_gene' THEN x.xref END) AS bgd_id,
            MAX(CASE WHEN dr.db_name = 'horde' THEN x.xref END) AS horde_id
        FROM gene_has_xrefs ghx
        JOIN xref x ON ghx.xref_id = x.id
        JOIN database_resource dr ON x.external_db_id = dr.id
        LEFT JOIN genefam_orthologs go
            ON go.genefam_id_b = ghx.genefam_id
            AND go.taxon_a = 9606
            AND go.vgnc_b IS NOT NULL
    """

    if genefam_ids:
        sql += "          WHERE ghx.genefam_id IN :genefam_ids"

    sql += """
        GROUP BY ghx.genefam_id
    """

    if genefam_ids:
        query = text(sql).bindparams(
            bindparam("genefam_ids", value=tuple(genefam_ids), expanding=True)
        )
    else:
        query = text(sql)

    return query


def build_aliases_query(genefam_ids: list[int] | None = None) -> TextClause:
    """Build query for alias symbols and names using GROUP_CONCAT.

    Fetches, routing each output column by its exact nomenclature_type value
    (the vgnc_public nomenclature_type rows are: previous_symbol,
    previous_name, alias_symbol, alias_name):
    - alias_symbol: alt_symbol rows of nomenclature_type = 'alias_symbol'
    - alias_name:   alt_name   rows of nomenclature_type = 'alias_name'
    - prev_symbol:  alt_symbol rows of nomenclature_type = 'previous_symbol'
    - prev_name:    alt_name   rows of nomenclature_type = 'previous_name'

    Args:
        genefam_ids: List of genefam_ids to filter (from main query results)

    Returns:
        SQLAlchemy TextClause with bind parameters

    Example:
        >>> ids = [1, 2, 3]
        >>> query = build_aliases_query(genefam_ids=ids)
        >>> cursor.execute(*compile_query_for_mysql(query))
    """
    # Use unique parameter names for each UNION ALL section
    p1, p2, p3, p4 = ("genefam_ids_1", "genefam_ids_2", "genefam_ids_3", "genefam_ids_4")

    sql = """
        SELECT
            genefam_id,
            GROUP_CONCAT(alias_symbol ORDER BY alias_symbol SEPARATOR '|') AS alias_symbol,
            GROUP_CONCAT(alias_name ORDER BY alias_name SEPARATOR '|') AS alias_name,
            GROUP_CONCAT(prev_symbol ORDER BY prev_symbol SEPARATOR '|') AS prev_symbol,
            GROUP_CONCAT(prev_name ORDER BY prev_name SEPARATOR '|') AS prev_name
        FROM (
            -- Alias symbols (nomenclature_type = 'alias_symbol')
            SELECT
                gas.genefam_id,
                als.symbol AS alias_symbol,
                NULL AS alias_name,
                NULL AS prev_symbol,
                NULL AS prev_name
            FROM gene_alt_symbol gas
            JOIN alt_symbol als ON gas.symbol_id = als.id
            JOIN nomenclature_type nt ON als.nomenclature_type_id = nt.id
            WHERE nt.type = 'alias_symbol'
    """

    if genefam_ids:
        sql += f"              AND gas.genefam_id IN :{p1}"

    sql += """
            UNION ALL

            -- Alias names (nomenclature_type = 'alias_name')
            SELECT
                gan.genefam_id,
                NULL AS alias_symbol,
                aln.name AS alias_name,
                NULL AS prev_symbol,
                NULL AS prev_name
            FROM gene_alt_name gan
            JOIN alt_name aln ON gan.name_id = aln.id
            JOIN nomenclature_type nt ON aln.nomenclature_type_id = nt.id
            WHERE nt.type = 'alias_name'
    """

    if genefam_ids:
        sql += f"              AND gan.genefam_id IN :{p2}"

    sql += """
            UNION ALL

            -- Previous symbols (nomenclature_type = 'previous_symbol')
            SELECT
                gas.genefam_id,
                NULL AS alias_symbol,
                NULL AS alias_name,
                als.symbol AS prev_symbol,
                NULL AS prev_name
            FROM gene_alt_symbol gas
            JOIN alt_symbol als ON gas.symbol_id = als.id
            JOIN nomenclature_type nt ON als.nomenclature_type_id = nt.id
            WHERE nt.type = 'previous_symbol'
    """

    if genefam_ids:
        sql += f"              AND gas.genefam_id IN :{p3}"

    sql += """
            UNION ALL

            -- Previous names (nomenclature_type = 'previous_name')
            SELECT
                gan.genefam_id,
                NULL AS alias_symbol,
                NULL AS alias_name,
                NULL AS prev_symbol,
                aln.name AS prev_name
            FROM gene_alt_name gan
            JOIN alt_name aln ON gan.name_id = aln.id
            JOIN nomenclature_type nt ON aln.nomenclature_type_id = nt.id
            WHERE nt.type = 'previous_name'
    """

    if genefam_ids:
        sql += f"              AND gan.genefam_id IN :{p4}"

    sql += """
        ) AS all_aliases
        GROUP BY genefam_id
    """

    if genefam_ids:
        # Create a query with 4 unique bind params for the same value
        query = text(sql).bindparams(
            bindparam(p1, value=tuple(genefam_ids), expanding=True),
            bindparam(p2, value=tuple(genefam_ids), expanding=True),
            bindparam(p3, value=tuple(genefam_ids), expanding=True),
            bindparam(p4, value=tuple(genefam_ids), expanding=True),
        )
    else:
        query = text(sql)

    return query


def build_dates_query(genefam_ids: list[int] | None = None) -> TextClause:
    """Build query for date MIN/MAX aggregates.

    Fetches:
    - date_approved_reserved: MIN date from gene_history
    - date_modified: MAX date from gene_history
    - date_symbol_changed: MAX date where field_changed = 'assigned_symbol'
    - date_name_changed: MAX date where field_changed = 'assigned_name'

    Args:
        genefam_ids: List of genefam_ids to filter (from main query results)

    Returns:
        SQLAlchemy TextClause with bind parameters

    Example:
        >>> ids = [1, 2, 3]
        >>> query = build_dates_query(genefam_ids=ids)
        >>> cursor.execute(*compile_query_for_mysql(query))
    """
    # Use unique parameter names for each UNION section
    p1, p2 = ("genefam_ids_1", "genefam_ids_2")

    sql = """
        SELECT
            genefam_id,
            MIN(date) AS date_approved_reserved,
            MAX(date) AS date_modified,
            MAX(CASE WHEN field_changed = 'assigned_symbol' THEN date END) AS date_symbol_changed,
            MAX(CASE WHEN field_changed = 'assigned_name' THEN date END) AS date_name_changed
        FROM (
            SELECT gh.genefam_id, gh.date, NULL AS field_changed
            FROM gene_history gh
    """

    if genefam_ids:
        sql += f"          WHERE gh.genefam_id IN :{p1}"

    sql += """
            UNION ALL

            SELECT gh.genefam_id, gh.date, ct.field_changed
            FROM gene_history gh
            JOIN change_type ct ON gh.type_id = ct.id
    """

    if genefam_ids:
        sql += f"          WHERE gh.genefam_id IN :{p2}"

    sql += """
        ) AS all_dates
        GROUP BY genefam_id
    """

    if genefam_ids:
        query = text(sql).bindparams(
            bindparam(p1, value=tuple(genefam_ids), expanding=True),
            bindparam(p2, value=tuple(genefam_ids), expanding=True),
        )
    else:
        query = text(sql)

    return query


def _quote_identifier(identifier: str) -> str:
    """Return a safely backtick-quoted SQL identifier (db/table name)."""
    if not re.fullmatch(r"[A-Za-z0-9_]+", identifier):
        raise ValueError(f"invalid SQL identifier: {identifier!r}")
    return f"`{identifier}`"


def _format_hgnc_table_reference(table_reference: str) -> str:
    """Format ``table`` or ``db.table`` into a safely quoted SQL reference."""
    parts = [p for p in table_reference.strip().split('.') if p]
    if len(parts) == 1:
        return _quote_identifier(parts[0])
    if len(parts) == 2:
        return f"{_quote_identifier(parts[0])}.{_quote_identifier(parts[1])}"
    raise ValueError(f"invalid table reference: {table_reference!r}")


def _hgnc_table_exists(cursor: Any, quoted_table: str) -> bool:
    """Check if a quoted table (e.g. `pub_hgnc` or `db`.`table`) exists.

    Args:
        cursor: Database cursor for executing the existence check
        quoted_table: Backtick-quoted table reference (single or two-part)

    Returns:
        True if the table exists and is accessible; False otherwise
    """
    try:
        # Use LIMIT 0 to verify table exists without fetching data
        cursor.execute(f"SELECT 1 FROM {quoted_table} LIMIT 0")
        cursor.fetchall()  # Consume any results
        return True
    except (MySQLdb.OperationalError, MySQLdb.ProgrammingError):
        return False


def _resolve_hgnc_symbol_fallback_table(cursor: Any) -> str | None:
    """Resolve the SQL table used for exact-symbol HGNC fallback.

    Uses module-level caching to avoid repeated metadata queries per batch.
    Resolution order:
    1) ``HGNC_SYMBOL_FALLBACK_TABLE`` env var (``table`` or ``db.table``) -
       validated for existence; warns and falls back if explicitly set but missing.
    2) ``pub_hgnc`` in the current DB schema.
    3) Latest visible ``g4public[_YYYY_MM_DD].pub_hgnc`` schema.

    Returns:
        Backtick-quoted SQL table reference, or ``None`` when unavailable.
    """
    global _HGNC_SYMBOL_TABLE_CACHE

    # Return cached result if already resolved in this run
    if _HGNC_SYMBOL_TABLE_CACHE is not False:
        return _HGNC_SYMBOL_TABLE_CACHE  # type: ignore[return-value]

    # 1) Check for explicit override via environment
    override = os.environ.get("HGNC_SYMBOL_FALLBACK_TABLE", "").strip()
    if override:
        try:
            quoted = _format_hgnc_table_reference(override)
        except ValueError:
            logger.warning(
                "HGNC_SYMBOL_FALLBACK_TABLE=%r is not a valid SQL identifier; "
                "falling back to auto-detection",
                override,
            )
            quoted = None

        if quoted:
            if _hgnc_table_exists(cursor, quoted):
                _HGNC_SYMBOL_TABLE_CACHE = quoted
                return quoted
            logger.warning(
                "HGNC_SYMBOL_FALLBACK_TABLE=%r resolved to table=%r which does "
                "not exist or is not accessible; falling back to auto-detection",
                override,
                quoted,
            )

    # 2) Check current schema for pub_hgnc
    try:
        cursor.execute("SHOW TABLES LIKE 'pub_hgnc'")
        if cursor.fetchone():
            # Double-check the table is actually queryable
            quoted = _quote_identifier("pub_hgnc")
            if _hgnc_table_exists(cursor, quoted):
                _HGNC_SYMBOL_TABLE_CACHE = quoted
                return quoted
    except (MySQLdb.OperationalError, MySQLdb.ProgrammingError) as exc:
        logger.debug(
            "HGNC symbol fallback detection: SHOW TABLES query failed; "
            "continuing to information_schema path: %s",
            exc,
        )

    # 3) Check information_schema for g4public*.pub_hgnc
    try:
        cursor.execute(
            """
            SELECT table_schema
            FROM information_schema.tables
            WHERE table_name = 'pub_hgnc'
              AND table_schema REGEXP '^g4public(_[0-9]{4}_[0-9]{2}_[0-9]{2})?$'
            ORDER BY
              CASE
                WHEN table_schema REGEXP '^g4public_[0-9]{4}_[0-9]{2}_[0-9]{2}$' THEN 0
                WHEN table_schema = 'g4public' THEN 1
                ELSE 2
              END,
              table_schema DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if row and row[0]:
            schema_name = str(row[0])
            quoted = f"{_quote_identifier(schema_name)}.{_quote_identifier('pub_hgnc')}"
            if _hgnc_table_exists(cursor, quoted):
                _HGNC_SYMBOL_TABLE_CACHE = quoted
                return quoted
    except (MySQLdb.OperationalError, MySQLdb.ProgrammingError) as exc:
        logger.debug(
            "HGNC symbol fallback detection: information_schema query failed: %s",
            exc,
        )

    # Resolution failed - cache None and log at info level for observability
    logger.info(
        "HGNC symbol fallback disabled: no accessible pub_hgnc table found; "
        "hgnc_orthologs will only come from xrefs (hgnc_gene/hgnc_ortholog) and genefam_orthologs"
    )
    _HGNC_SYMBOL_TABLE_CACHE = None
    return None


def _validate_hgnc_symbol_table(quoted_table: str) -> None:
    """Validate that a string is a properly backtick-quoted SQL identifier.

    Used for defense-in-depth validation of the hgnc_symbol_table parameter
    before SQL interpolation.

    Args:
        quoted_table: Backtick-quoted table reference (`table` or `db`.`table`)

    Raises:
        ValueError: If the format is invalid
    """
    if not quoted_table or not isinstance(quoted_table, str):
        raise ValueError(f"hgnc_symbol_table must be a non-empty string: {quoted_table!r}")
    
    # Acceptable formats: `table` or `db`.`table`
    # Check it starts and ends with backtick
    if not (quoted_table.startswith("`") and quoted_table.endswith("`")):
        raise ValueError(f"hgnc_symbol_table must be properly backtick-quoted: {quoted_table!r}")
    
    # Validate content using _format_hgnc_table_reference on the unquoted value
    # Strip outer backticks
    inner = quoted_table[1:-1]
    # Handle db`.`table format (split on `.[` to find the separator)
    if "`.`" in inner:
        # Format: `db`.`table` -> inner = db`.`table
        db_part, table_part = inner.split("`.`", 1)
        _quote_identifier(db_part)  # Validate each part
        _quote_identifier(table_part)
    else:
        # Single table name
        _quote_identifier(inner)


def _build_hgnc_symbol_fallback_query(
    genefam_ids: list[int],
    *,
    hgnc_symbol_table: str,
) -> TextClause:
    """Build exact-HGNC-symbol fallback query (website step 3 parity).

    Matches VGNC ``assigned_symbol`` to HGNC ``gd_app_sym`` and returns
    pipe-delimited HGNC IDs per gene.

    Args:
        genefam_ids: List of genefam_ids to filter
        hgnc_symbol_table: Pre-validated, safely backtick-quoted table reference

    Returns:
        SQLAlchemy TextClause with bind parameters
    """
    # Defense-in-depth validation
    _validate_hgnc_symbol_table(hgnc_symbol_table)

    sql = f"""
        SELECT
            gf.genefam_id,
            GROUP_CONCAT(DISTINCT CONCAT('HGNC:', ph.gd_hgnc_id) ORDER BY ph.gd_hgnc_id SEPARATOR '|') AS hgnc_orthologs
        FROM genefam gf
        JOIN {hgnc_symbol_table} ph ON ph.gd_app_sym = gf.assigned_symbol
        WHERE gf.genefam_id IN :genefam_ids
        GROUP BY gf.genefam_id
    """

    return text(sql).bindparams(
        bindparam("genefam_ids", value=tuple(genefam_ids), expanding=True)
    )


def _pipe_values(value: Any) -> list[str]:
    """Split a pipe-delimited value into non-empty tokens."""
    if value is None:
        return []
    return [token for token in str(value).split("|") if token]


def _merge_pipe_values(primary: Any, secondary: Any) -> str | None:
    """Merge two pipe-delimited values, preserving order and removing duplicates.

    Primary values (from xrefs/orthologs) come before secondary (symbol fallback).
    """
    merged: list[str] = []
    seen: set[str] = set()

    for token in _pipe_values(primary) + _pipe_values(secondary):
        if token not in seen:
            seen.add(token)
            merged.append(token)

    return "|".join(merged) if merged else None


def fetch_sub_data_for_batch(
    genefam_ids: list[int],
    cursor: Any,
    compile_fn: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch xrefs, aliases, and dates for a single batch of genefam_ids.

    Runs the three sub-queries (xrefs, aliases, dates) for the given batch
    of IDs and returns the results as lists of dicts. This avoids holding
    sub-query results for the entire dataset in memory at once.

    Args:
        genefam_ids: List of genefam_ids for this batch
        cursor: A database cursor (regular, not streaming) for executing queries
        compile_fn: The compile_query_for_mysql function

    Returns:
        Tuple of (xrefs, aliases, dates) lists

    Raises:
        MySQLdb.OperationalError: If the HGNC symbol fallback query fails with an
            operational error (connection issue, etc.). The error is re-raised to
            enforce fail-fast behavior since silent degradation would ship
            incomplete HGNC ortholog data that breaks website parity.
        MySQLdb.ProgrammingError: If the HGNC symbol fallback query fails with a
            programming error (schema mismatch, missing column, etc.). Re-raised
            to catch schema bugs early rather than silently shipping incomplete data.
    """
    xrefs_query = build_xrefs_query(genefam_ids=genefam_ids)
    xrefs_sql, xrefs_params = compile_fn(xrefs_query)
    cursor.execute(xrefs_sql, xrefs_params)
    xrefs_db_headers = [desc[0] for desc in cursor.description] if cursor.description else []
    xrefs = [dict(zip(xrefs_db_headers, row, strict=False)) for row in cursor]

    # Website parity fallback (step 3): exact HGNC symbol match.
    # This is additive + deduplicated, mirroring website behavior where symbol
    # matches can add a human homolog not already seen from xrefs / ortholog rows.
    hgnc_symbol_table = _resolve_hgnc_symbol_fallback_table(cursor)
    if hgnc_symbol_table:
        symbol_query = _build_hgnc_symbol_fallback_query(
            genefam_ids,
            hgnc_symbol_table=hgnc_symbol_table,
        )
        symbol_sql, symbol_params = compile_fn(symbol_query)
        cursor.execute(symbol_sql, symbol_params)
        symbol_headers = [desc[0] for desc in cursor.description] if cursor.description else []
        symbol_rows = [dict(zip(symbol_headers, row, strict=False)) for row in cursor]

        xrefs_by_gene = {row["genefam_id"]: row for row in xrefs}
        for row in symbol_rows:
            genefam_id = row["genefam_id"]
            symbol_hgnc = row.get("hgnc_orthologs")
            if not symbol_hgnc:
                continue

            existing = xrefs_by_gene.get(genefam_id)
            if existing is None:
                xrefs_by_gene[genefam_id] = {
                    "genefam_id": genefam_id,
                    "hgnc_orthologs": symbol_hgnc,
                }
            else:
                existing["hgnc_orthologs"] = _merge_pipe_values(
                    existing.get("hgnc_orthologs"), symbol_hgnc
                )

        xrefs = list(xrefs_by_gene.values())

    aliases_query = build_aliases_query(genefam_ids=genefam_ids)
    aliases_sql, aliases_params = compile_fn(aliases_query)
    cursor.execute(aliases_sql, aliases_params)
    aliases_db_headers = [desc[0] for desc in cursor.description] if cursor.description else []
    aliases = [dict(zip(aliases_db_headers, row, strict=False)) for row in cursor]

    dates_query = build_dates_query(genefam_ids=genefam_ids)
    dates_sql, dates_params = compile_fn(dates_query)
    cursor.execute(dates_sql, dates_params)
    dates_db_headers = [desc[0] for desc in cursor.description] if cursor.description else []
    dates = [dict(zip(dates_db_headers, row, strict=False)) for row in cursor]

    return xrefs, aliases, dates


def merge_gene_results(
    gene_data: list[dict[str, Any]],
    xrefs: list[dict[str, Any]],
    aliases: list[dict[str, Any]],
    dates: list[dict[str, Any]],
) -> Iterator[dict[str, Any]]:
    """Merge results from split queries into complete gene records.

    Uses efficient dict lookups (O(1) per record) instead of nested loops.

    Args:
        gene_data: Main gene data from build_gene_data_query
        xrefs: Xref data from build_xrefs_query
        aliases: Alias data from build_aliases_query
        dates: Date data from build_dates_query

    Yields:
        Merged gene dictionaries with all fields combined

    Example:
        >>> gene_data = [{"genefam_id": 1, "assigned_symbol": "GENE1"}]
        >>> xrefs = [{"genefam_id": 1, "ncbi_gene_id": "12345"}]
        >>> aliases = [{"genefam_id": 1, "alias_symbol": "ALIAS1"}]
        >>> dates = [{"genefam_id": 1, "date_approved_reserved": "2020-01-01"}]
        >>> result = list(merge_gene_results(gene_data, xrefs, aliases, dates))
    """
    # Convert lists to dicts for O(1) lookup
    xrefs_dict = {row["genefam_id"]: row for row in xrefs}
    aliases_dict = {row["genefam_id"]: row for row in aliases}
    dates_dict = {row["genefam_id"]: row for row in dates}

    for gene_row in gene_data:
        genefam_id = gene_row["genefam_id"]

        # Start with gene data (copy to avoid mutating original)
        merged = gene_row.copy()

        # Add xref data if available
        if genefam_id in xrefs_dict:
            xref_row = xrefs_dict[genefam_id]
            # Merge all fields except genefam_id (already in gene_row)
            for key, value in xref_row.items():
                if key != "genefam_id":
                    merged[key] = value

        # Add alias data if available
        if genefam_id in aliases_dict:
            alias_row = aliases_dict[genefam_id]
            for key, value in alias_row.items():
                if key != "genefam_id":
                    merged[key] = value

        # Add date data if available
        if genefam_id in dates_dict:
            date_row = dates_dict[genefam_id]
            for key, value in date_row.items():
                if key != "genefam_id":
                    merged[key] = value

        yield merged
