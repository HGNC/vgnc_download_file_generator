"""Split query architecture for gene data export.

This module provides an alternative to the complex build_gene_query that
splits the query into 4 simpler queries and merges results in Python.

This approach provides 2300x performance improvement by avoiding the
expensive CROSS JOIN behavior of multiple LEFT JOINs with complex conditions.
"""

from collections.abc import Iterator
from typing import Any

from sqlalchemy import bindparam
from sqlalchemy.sql.expression import TextClause, text


def build_gene_data_query(
    filters: dict[str, str | int | list[str]] | None = None,
) -> TextClause:
    """Build main gene data query with core joins only.

    This query fetches the core gene information including:
    - Basic gene data (genefam table)
    - Gene status (gene_status)
    - Locus type and group (locus_type, locus_group)
    - Genomic location (gene_has_location, assembly, gene_location, chromosomes).
      The gene_has_location join is restricted to the species' default VGNC
      assembly via a correlated EXISTS (assembly.is_vgnc_default = 1, matching
      taxon_id, and assembly.source = 'Ensembl') so each gene emits exactly one
      canonical location. is_vgnc_default is NOT unique per species (a species
      can carry a default NCBI + a default Ensembl assembly -- see VGNC:6926),
      so the Ensembl source pin selects the canonical default instead of one
      row per default assembly.
    - Gene family (gene_has_family, family_new)

    Xrefs, aliases, and dates are fetched in separate queries.

    Args:
        filters: Dictionary of filter criteria. Keys can be:
            - taxon_id: Filter by species taxonomy ID
            - chromosome: Filter by chromosome name (e.g., "X", "1")
            - locus_type: Filter by locus type
            - locus_group: Filter by locus group
            - status_id: Filter by gene status_id (int or list for IN clause)
            - status: Filter by gene status (string or list for IN clause)

    Returns:
        SQLAlchemy TextClause with bind parameters

    Example:
        >>> query = build_gene_data_query(filters={"taxon_id": 9913})
        >>> cursor.execute(*compile_query_for_mysql(query))
    """
    filters = filters or {}

    sql = """
        SELECT DISTINCT
            gf.genefam_id,
            gf.taxon_id,
            gf.assigned_id,
            gf.assigned_symbol,
            gf.assigned_name,
            gs.status AS gene_status,
            lt.type AS locus_type,
            lg.name AS locus_group,
            c.display_name AS chromosome,
            gl.start,
            gl.end,
            gl.strand,
            gl.band,
            fn.id AS gene_family_id,
            fn.name AS gene_family
        FROM genefam gf
        LEFT JOIN gene_has_locus_type ghtlt ON gf.genefam_id = ghtlt.genefam_id
        LEFT JOIN locus_type lt ON ghtlt.locus_type_id = lt.id
        LEFT JOIN locus_group lg ON lt.locus_group_id = lg.id
        LEFT JOIN gene_has_location ghl ON gf.genefam_id = ghl.gene_id
            AND EXISTS (
                SELECT 1 FROM assembly a
                WHERE a.id = ghl.assembly_id
                    AND a.is_vgnc_default = 1
                    AND a.taxon_id = gf.taxon_id
                    AND a.source = 'Ensembl'
            )
        LEFT JOIN gene_location gl ON ghl.location_id = gl.id
        LEFT JOIN chromosomes c ON gl.chr_id = c.chr_id
        LEFT JOIN gene_status gs ON gf.status_id = gs.id
        LEFT JOIN gene_has_family ghf ON gf.genefam_id = ghf.genefam_id
        LEFT JOIN family_new fn ON ghf.family_id = fn.id
        WHERE 1=1
    """

    # Build dynamic WHERE clauses
    where_clauses: list[str] = []
    bind_params: dict[str, str | int | tuple[str, ...]] = {}
    param_counter = 0

    if filters:
        # Filter by taxon_id - ensures both genes AND chromosomes belong to the species
        if "taxon_id" in filters:
            param_name = f"taxon_id_{param_counter}"
            where_clauses.append(f"gf.taxon_id = :{param_name}")
            bind_params[param_name] = filters["taxon_id"]  # type: ignore[assignment]
            # Also filter chromosomes to prevent cross-species contamination
            # For "Un" chromosome, allow NULL chromosomes (genes without location)
            chromosome_is_un = filters.get("chromosome") == "Un"
            if chromosome_is_un:
                where_clauses.append("(c.taxon_id = gf.taxon_id OR c.chr_id IS NULL)")
            else:
                where_clauses.append("c.taxon_id = gf.taxon_id")
            param_counter += 1

        # Filter by chromosome
        if "chromosome" in filters:
            chromosome_value = filters["chromosome"]
            # Special case: "Un" should match:
            # 1. Chromosomes with display_name starting with "Un" (e.g., Un0001, Un_1)
            # 2. Non-chromosome coord_systems (scaffolds, primary_assembly, etc.)
            # 3. Genes with NO location data (c.chr_id IS NULL)
            if chromosome_value == "Un":
                # Build OR condition for Un chromosome grouping
                # (c.chr_id IS NULL OR c.display_name LIKE 'Un%' OR c.coord_system NOT LIKE '%chromosome%')
                param_name_like = f"chromosome_like_{param_counter}"
                param_name_coord = f"chromosome_coord_{param_counter}"
                where_clauses.append(
                    f"(c.chr_id IS NULL OR c.display_name LIKE :{param_name_like} "
                    f"OR c.coord_system NOT LIKE :{param_name_coord})"
                )
                bind_params[param_name_like] = f"{chromosome_value}%"
                bind_params[param_name_coord] = "%chromosome%"
                param_counter += 2
            else:
                param_name = f"chromosome_{param_counter}"
                where_clauses.append(f"c.display_name = :{param_name}")
                bind_params[param_name] = chromosome_value  # type: ignore[assignment]
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

    # Append WHERE clauses
    if where_clauses:
        for clause in where_clauses:
            sql = f"{sql}\n          AND {clause}"

    # Create text construct with bind parameters
    if bind_params:
        bindparam_list: list[Any] = []
        for name, value in bind_params.items():
            if isinstance(value, tuple):
                bindparam_list.append(bindparam(name, value=value, expanding=True))
            else:
                bindparam_list.append(bindparam(name, value=value))
        query = text(sql).bindparams(*bindparam_list)
    else:
        query = text(sql)

    return query


def build_xrefs_query(genefam_ids: list[int] | None = None) -> TextClause:
    """Build query for all external database references (xrefs).

    Uses conditional aggregation to fetch all 6 xref types in a single query.

    IMPORTANT: map by ``database_resource.db_name`` (stable semantic key)
    instead of hardcoded ``external_db_id`` integers, which can vary across DB
    snapshots/clones.

    - NCBI Gene ID (db_name = ``ncbi_gene``)
    - Ensembl Gene ID (db_name = ``ensembl_gene``)
    - UniProt IDs (db_name = ``uniprot_protein``) -- one gene may have several
    - PubMed ID (db_name = ``pubmed``)
    - HGNC Orthologs (db_name = ``hgnc_ortholog``)
    - BGD ID (db_name = ``bgd_gene``)

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
                SEPARATOR '|'
            ) AS uniprot_ids,
            GROUP_CONCAT(
                DISTINCT CASE WHEN dr.db_name = 'pubmed' THEN x.xref END
                SEPARATOR '|'
            ) AS pubmed_id,
            MAX(CASE WHEN dr.db_name = 'hgnc_ortholog' THEN x.xref END) AS hgnc_orthologs,
            MAX(CASE WHEN dr.db_name = 'bgd_gene' THEN x.xref END) AS bgd_id
        FROM gene_has_xrefs ghx
        JOIN xref x ON ghx.xref_id = x.id
        JOIN database_resource dr ON x.external_db_id = dr.id
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

    Fetches:
    - alias_symbol: Non-previous alternative symbols
    - alias_name: Non-previous alternative names
    - prev_symbol: Previous symbols
    - prev_name: Previous names

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
            -- Non-previous symbols
            SELECT
                gas.genefam_id,
                als.symbol AS alias_symbol,
                NULL AS alias_name,
                NULL AS prev_symbol,
                NULL AS prev_name
            FROM gene_alt_symbol gas
            JOIN alt_symbol als ON gas.symbol_id = als.id
            JOIN nomenclature_type nt ON als.nomenclature_type_id = nt.id
            WHERE nt.type != 'Previous'
    """

    if genefam_ids:
        sql += f"              AND gas.genefam_id IN :{p1}"

    sql += """
            UNION ALL

            -- Non-previous names
            SELECT
                gan.genefam_id,
                NULL AS alias_symbol,
                aln.name AS alias_name,
                NULL AS prev_symbol,
                NULL AS prev_name
            FROM gene_alt_name gan
            JOIN alt_name aln ON gan.name_id = aln.id
            JOIN nomenclature_type nt ON aln.nomenclature_type_id = nt.id
            WHERE nt.type != 'Previous'
    """

    if genefam_ids:
        sql += f"              AND gan.genefam_id IN :{p2}"

    sql += """
            UNION ALL

            -- Previous symbols
            SELECT
                gas.genefam_id,
                NULL AS alias_symbol,
                NULL AS alias_name,
                als.symbol AS prev_symbol,
                NULL AS prev_name
            FROM gene_alt_symbol gas
            JOIN alt_symbol als ON gas.symbol_id = als.id
            JOIN nomenclature_type nt ON als.nomenclature_type_id = nt.id
            WHERE nt.type = 'Previous'
    """

    if genefam_ids:
        sql += f"              AND gas.genefam_id IN :{p3}"

    sql += """
            UNION ALL

            -- Previous names
            SELECT
                gan.genefam_id,
                NULL AS alias_symbol,
                NULL AS alias_name,
                NULL AS prev_symbol,
                aln.name AS prev_name
            FROM gene_alt_name gan
            JOIN alt_name aln ON gan.name_id = aln.id
            JOIN nomenclature_type nt ON aln.nomenclature_type_id = nt.id
            WHERE nt.type = 'Previous'
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
    """
    xrefs_query = build_xrefs_query(genefam_ids=genefam_ids)
    xrefs_sql, xrefs_params = compile_fn(xrefs_query)
    cursor.execute(xrefs_sql, xrefs_params)
    xrefs_db_headers = [desc[0] for desc in cursor.description] if cursor.description else []
    xrefs = [dict(zip(xrefs_db_headers, row, strict=False)) for row in cursor]

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
