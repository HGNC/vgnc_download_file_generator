"""Database query builders for VGNC data export.

This module provides functions to build SQL queries for extracting
data from the VGNC database, optimized for streaming with server-side cursors.
"""

import re
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.sql.expression import TextClause


def build_species_query(
    is_live_values: tuple[str, ...] = ("Y", "T", "F"),
    human_taxon_id: int = 9606,
) -> TextClause:
    """Build SQL query for discovering live non-human species.

    This query filters the species table to find:
    - Species with is_live status in the specified values (default: Y, T, F)
    - Excludes human (taxon_id = 9606)

    The query is designed for server-side cursor streaming and does not
    include a LIMIT clause.

    Args:
        is_live_values: Tuple of is_live enum values to include (default: Y, T, F)
        human_taxon_id: Taxon ID to exclude (default: 9606 for human)

    Returns:
        SQLAlchemy text construct with bind parameters for safe execution

    Example:
        >>> query = build_species_query()
        >>> cursor = conn.get_streaming_cursor()
        >>> cursor.execute(query, {"is_live_values": ("Y", "T", "F"), "human_taxon_id": 9606})
    """
    # Build the query with bind parameters for safety
    # Using tuple comparison for IN clause
    sql = """
        SELECT
            taxon_id,
            genefam_prefix,
            primary_db_table,
            display_name,
            ensembl_species_name,
            is_live,
            created
        FROM species
        WHERE is_live IN :is_live_values
          AND taxon_id != :human_taxon_id
    """

    # Create text construct with bind parameters
    # Use the function parameters as initial values for the bind params
    query = text(sql).bindparams(
        bindparam("is_live_values", value=is_live_values, expanding=True),  # For IN clause with tuple
        bindparam("human_taxon_id", value=human_taxon_id),
    )

    return query


def build_species_display_name_query(taxon_id: int) -> TextClause:
    """Build SQL query to get species display name by taxon_id.

    Args:
        taxon_id: Species taxonomy ID

    Returns:
        SQLAlchemy text construct with bind parameters for safe execution

    Example:
        >>> query = build_species_display_name_query(9913)
        >>> cursor = conn.get_streaming_cursor()
        >>> cursor.execute(query, {"taxon_id": 9913})
        >>> result = cursor.fetchone()
        >>> display_name = result[0] if result else None
    """
    sql = """
        SELECT display_name
        FROM species
        WHERE taxon_id = :taxon_id
    """

    query = text(sql).bindparams(bindparam("taxon_id", value=taxon_id))

    return query


def build_gene_query(filters: dict[str, str | int | list[str]] | None = None) -> TextClause:
    """Build SQL query for gene data with complex JOINs and dynamic filtering.

    This query joins multiple tables to get comprehensive gene information:
    - genefam (base table with gene entries)
    - gene_has_locus_type → locus_type → locus_group (gene classification)
    - gene_has_location → gene_location → chromosomes (genomic location)
    - gene_status (approval status)
    - gene_has_family → family_new (gene family information)
    - gene_has_xrefs → xref → database_resource (external IDs like NCBI, Ensembl, UniProt)
    - genefam_orthologs (HGNC orthologs)

    Supports filtering by: taxon_id, chromosome, locus_type, locus_group, status

    Args:
        filters: Dictionary of filter criteria. Keys can be:
            - taxon_id: Filter by species taxonomy ID
            - chromosome: Filter by chromosome name (e.g., "X", "1")
            - locus_type: Filter by locus type (e.g., "gene with protein product")
            - locus_group: Filter by locus group (e.g., "protein-coding gene")
            - status: Filter by gene status (string or list of strings for IN clause)

    Returns:
        SQLAlchemy text construct with bind parameters for safe execution

    Example:
        >>> # Get all genes
        >>> query = build_gene_query()
        >>>
        >>> # Filter by species
        >>> query = build_gene_query(filters={"taxon_id": 9593})
        >>>
        >>> # Multiple filters
        >>> query = build_gene_query(filters={
        ...     "taxon_id": 9593,
        ...     "chromosome": "X",
        ...     "status": "Approved"
        ... })
        >>>
        >>> # Status with IN clause (list of values)
        >>> query = build_gene_query(filters={
        ...     "status": ["Entry Withdrawn", "Symbol Withdrawn"]
        ... })
    """
    filters = filters or {}

    # Build the base query with all necessary JOINs
    # The JOINs connect:
    # genefam → gene_has_locus_type → locus_type → locus_group
    # genefam → gene_has_location → gene_location → chromosomes
    # genefam → gene_status
    # genefam → gene_has_family → family_new (for gene family info)
    # genefam → gene_has_xrefs → xref → database_resource (for external IDs)
    # Subqueries for alias_symbol, alias_name, prev_symbol, prev_name
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
            fn.name AS gene_family,
            ncbi.xref AS ncbi_gene_id,
            ensembl.xref AS ensembl_gene_id,
            uniprot.xref AS uniprot_ids,
            pubmed.xref AS pubmed_id,
            hgnc_db.xref AS hgnc_orthologs,
            bgd.xref AS bgd_id,
            date_approved.date_approved_reserved,
            date_modified.date_modified,
            date_symbol.date_symbol_changed,
            date_name.date_name_changed,
            alias_symbols.alias_symbol,
            alias_names.alias_name,
            prev_symbols.prev_symbol,
            prev_names.prev_name,
            CONCAT(
                COALESCE(c.display_name, ''),
                ':',
                COALESCE(CAST(gl.start AS CHAR), '')
            ) AS location_sortable
        FROM genefam gf
        LEFT JOIN gene_has_locus_type ghtlt ON gf.genefam_id = ghtlt.genefam_id
        LEFT JOIN locus_type lt ON ghtlt.locus_type_id = lt.id
        LEFT JOIN locus_group lg ON lt.locus_group_id = lg.id
        LEFT JOIN gene_has_location ghl ON gf.genefam_id = ghl.gene_id
        LEFT JOIN gene_location gl ON ghl.location_id = gl.id
        LEFT JOIN chromosomes c ON gl.chr_id = c.chr_id
        LEFT JOIN gene_status gs ON gf.status_id = gs.id
        LEFT JOIN gene_has_family ghf ON gf.genefam_id = ghf.genefam_id
        LEFT JOIN family_new fn ON ghf.family_id = fn.id
        LEFT JOIN gene_has_xrefs ghx_ncbi ON gf.genefam_id = ghx_ncbi.genefam_id
            AND ghx_ncbi.created_by = 1
        LEFT JOIN xref ncbi ON ghx_ncbi.xref_id = ncbi.id
            AND ncbi.external_db_id = 1
        LEFT JOIN gene_has_xrefs ghx_ensembl ON gf.genefam_id = ghx_ensembl.genefam_id
            AND ghx_ensembl.created_by = 1
            AND ghx_ensembl.xref_id != ghx_ncbi.xref_id
        LEFT JOIN xref ensembl ON ghx_ensembl.xref_id = ensembl.id
            AND ensembl.external_db_id = 2
        LEFT JOIN gene_has_xrefs ghx_uniprot ON gf.genefam_id = ghx_uniprot.genefam_id
            AND ghx_uniprot.created_by = 1
            AND ghx_uniprot.xref_id != ghx_ncbi.xref_id
            AND ghx_uniprot.xref_id != ghx_ensembl.xref_id
        LEFT JOIN xref uniprot ON ghx_uniprot.xref_id = uniprot.id
            AND uniprot.external_db_id IN (3, 15)
        LEFT JOIN gene_has_xrefs ghx_pubmed ON gf.genefam_id = ghx_pubmed.genefam_id
            AND ghx_pubmed.created_by = 1
            AND ghx_pubmed.xref_id NOT IN (ghx_ncbi.xref_id, ghx_ensembl.xref_id, ghx_uniprot.xref_id)
        LEFT JOIN xref pubmed ON ghx_pubmed.xref_id = pubmed.id
            AND pubmed.external_db_id = 28
        LEFT JOIN gene_has_xrefs ghx_hgnc ON gf.genefam_id = ghx_hgnc.genefam_id
            AND ghx_hgnc.created_by = 1
        LEFT JOIN xref hgnc_db ON ghx_hgnc.xref_id = hgnc_db.id
            AND hgnc_db.external_db_id = 5
        LEFT JOIN gene_has_xrefs ghx_bgd ON gf.genefam_id = ghx_bgd.genefam_id
            AND ghx_bgd.created_by = 1
            AND ghx_bgd.xref_id NOT IN (ghx_ncbi.xref_id, ghx_ensembl.xref_id, ghx_uniprot.xref_id, ghx_pubmed.xref_id, ghx_hgnc.xref_id)
        LEFT JOIN xref bgd ON ghx_bgd.xref_id = bgd.id
            AND bgd.external_db_id = 24
        LEFT JOIN (
            SELECT
                gas.genefam_id,
                GROUP_CONCAT(als.symbol ORDER BY als.symbol SEPARATOR '|') AS alias_symbol
            FROM gene_alt_symbol gas
            JOIN alt_symbol als ON gas.symbol_id = als.id
            JOIN nomenclature_type nt_alias ON als.nomenclature_type_id = nt_alias.id
            WHERE nt_alias.type != 'Previous'
            GROUP BY gas.genefam_id
        ) alias_symbols ON gf.genefam_id = alias_symbols.genefam_id
        LEFT JOIN (
            SELECT
                gan.genefam_id,
                GROUP_CONCAT(aln.name ORDER BY aln.name SEPARATOR '|') AS alias_name
            FROM gene_alt_name gan
            JOIN alt_name aln ON gan.name_id = aln.id
            JOIN nomenclature_type nt_alias ON aln.nomenclature_type_id = nt_alias.id
            WHERE nt_alias.type != 'Previous'
            GROUP BY gan.genefam_id
        ) alias_names ON gf.genefam_id = alias_names.genefam_id
        LEFT JOIN (
            SELECT
                gas.genefam_id,
                GROUP_CONCAT(als.symbol ORDER BY als.symbol SEPARATOR '|') AS prev_symbol
            FROM gene_alt_symbol gas
            JOIN alt_symbol als ON gas.symbol_id = als.id
            JOIN nomenclature_type nt_prev ON als.nomenclature_type_id = nt_prev.id
            WHERE nt_prev.type = 'Previous'
            GROUP BY gas.genefam_id
        ) prev_symbols ON gf.genefam_id = prev_symbols.genefam_id
        LEFT JOIN (
            SELECT
                gan.genefam_id,
                GROUP_CONCAT(aln.name ORDER BY aln.name SEPARATOR '|') AS prev_name
            FROM gene_alt_name gan
            JOIN alt_name aln ON gan.name_id = aln.id
            JOIN nomenclature_type nt_prev ON aln.nomenclature_type_id = nt_prev.id
            WHERE nt_prev.type = 'Previous'
            GROUP BY gan.genefam_id
        ) prev_names ON gf.genefam_id = prev_names.genefam_id
        LEFT JOIN (
            SELECT
                gh.genefam_id,
                MIN(gh.date) AS date_approved_reserved
            FROM gene_history gh
            GROUP BY gh.genefam_id
        ) date_approved ON gf.genefam_id = date_approved.genefam_id
        LEFT JOIN (
            SELECT
                gh.genefam_id,
                MAX(gh.date) AS date_modified
            FROM gene_history gh
            GROUP BY gh.genefam_id
        ) date_modified ON gf.genefam_id = date_modified.genefam_id
        LEFT JOIN (
            SELECT
                gh.genefam_id,
                MAX(gh.date) AS date_symbol_changed
            FROM gene_history gh
            JOIN change_type ct ON gh.type_id = ct.id
            WHERE ct.field_changed = 'assigned_symbol'
            GROUP BY gh.genefam_id
        ) date_symbol ON gf.genefam_id = date_symbol.genefam_id
        LEFT JOIN (
            SELECT
                gh.genefam_id,
                MAX(gh.date) AS date_name_changed
            FROM gene_history gh
            JOIN change_type ct ON gh.type_id = ct.id
            WHERE ct.field_changed = 'assigned_name'
            GROUP BY gh.genefam_id
        ) date_name ON gf.genefam_id = date_name.genefam_id
        WHERE 1=1
    """

    # Build dynamic WHERE clauses based on filters
    where_clauses: list[str] = []
    bind_params: dict[str, str | int | tuple[str, ...]] = {}
    param_counter = 0

    if filters:
        # Filter by taxon_id (species)
        if "taxon_id" in filters:
            param_name = f"taxon_id_{param_counter}"
            where_clauses.append(f"gf.taxon_id = :{param_name}")
            bind_params[param_name] = filters["taxon_id"]  # type: ignore[assignment]
            param_counter += 1

        # Filter by chromosome
        if "chromosome" in filters:
            param_name = f"chromosome_{param_counter}"
            where_clauses.append(f"c.display_name = :{param_name}")
            bind_params[param_name] = filters["chromosome"]  # type: ignore[assignment]
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

        # Filter by status (supports single value or list for IN clause)
        if "status" in filters:
            param_name = f"status_{param_counter}"
            status_value = filters["status"]
            if isinstance(status_value, list):
                # Use IN clause for list of statuses
                where_clauses.append(f"gs.status IN :{param_name}")
                bind_params[param_name] = tuple(status_value)
            else:
                # Use equality for single status
                where_clauses.append(f"gs.status = :{param_name}")
                bind_params[param_name] = status_value
            param_counter += 1

    # Append WHERE clauses to base query
    if where_clauses:
        for clause in where_clauses:
            sql = f"{sql}\n          AND {clause}"

    # Create text construct with bind parameters
    if bind_params:
        # Build list of bindparam objects
        # Use expanding=True for tuple parameters (IN clauses)
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


def compile_query_for_mysql(query: TextClause) -> tuple[str, tuple[Any, ...]]:
    """Compile SQLAlchemy TextClause to MySQLdb-compatible format.

    Converts SQLAlchemy's named parameter syntax (:param_name) to MySQLdb's
    format string syntax (%s) and returns both the query string and parameters.

    Args:
        query: SQLAlchemy TextClause with bind parameters

    Returns:
        Tuple of (query_string, params_tuple) for use with cursor.execute()

    Example:
        >>> query = build_gene_query(filters={"taxon_id": 9913})
        >>> sql, params = compile_query_for_mysql(query)
        >>> cursor.execute(sql, params)
    """
    # Get the raw SQL text
    sql_text = query.text

    # Find all parameters BEFORE we do any replacements
    param_order: list[str] = []
    found_params = re.findall(r":(\w+)\b", sql_text)

    for param_name in found_params:
        if param_name not in param_order:
            param_order.append(param_name)

    # Extract bind parameters from the TextClause
    # TextClause has a ._bindparams attribute that's a dict of bindparam objects
    params_dict: dict[str, Any] = {}
    expanded_params: dict[str, list[Any]] = {}  # Track expanded params separately

    if hasattr(query, "_bindparams") and query._bindparams:
        for key, param in query._bindparams.items():
            # For expanding parameters (IN clauses), we need to expand them
            if hasattr(param, "expanding") and param.expanding:
                # This is a tuple/list that needs to be expanded in the query
                value = param.value
                if isinstance(value, (tuple, list)):
                    # Store expanded values for later
                    expanded_params[key] = list(value)
                    # Replace :param with multiple %s placeholders wrapped in parentheses
                    placeholders = "(" + ", ".join(["%s"] * len(value)) + ")"
                    # Find and replace the parameter reference
                    # The pattern matches :param_name even with quotes
                    pattern = rf":{key}\b"
                    sql_text = re.sub(pattern, placeholders, sql_text)
                else:
                    # Single value, not expanding
                    params_dict[key] = value
            else:
                params_dict[key] = param.value

    # Build the params list in order
    params_list: list[Any] = []
    for param_name in param_order:
        if param_name in expanded_params:
            # Add all expanded values for this parameter
            params_list.extend(expanded_params[param_name])
        elif param_name in params_dict:
            params_list.append(params_dict[param_name])

    # Replace all remaining :param_name with %s
    sql_text = re.sub(r":\w+\b", "%s", sql_text)

    return sql_text, tuple(params_list)
