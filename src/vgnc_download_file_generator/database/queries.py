"""Database query builders for VGNC data export.

This module provides functions to build SQL queries for extracting
data from the VGNC database, optimized for streaming with server-side cursors.
"""

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


def build_gene_query(filters: dict[str, str | int | list[str]] | None = None) -> TextClause:
    """Build SQL query for gene data with complex JOINs and dynamic filtering.

    This query joins multiple tables to get comprehensive gene information:
    - genefam (base table with gene entries)
    - gene_has_locus_type → locus_type → locus_group (gene classification)
    - gene_has_location → gene_location → chromosomes (genomic location)
    - gene_status (approval status)

    Supports filtering by: taxon_id, chromosome, locus_type, locus_group, status

    Args:
        filters: Dictionary of filter criteria. Keys can be:
            - taxon_id: Filter by species taxonomy ID
            - chromosome: Filter by chromosome name (e.g., "X", "1")
            - locus_type: Filter by locus type (e.g., "gene_with_protein_product")
            - locus_group: Filter by locus group (e.g., "protein-coding_gene")
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
    sql = """
        SELECT DISTINCT
            gf.genefam_id,
            gf.taxon_id,
            gf.assigned_id,
            gf.assigned_symbol,
            gf.assigned_name,
            gs.status AS gene_status,
            gs.display AS status_display,
            lt.type AS locus_type,
            lg.name AS locus_group,
            c.display_name AS chromosome,
            gl.start,
            gl.end,
            gl.strand,
            gl.band
        FROM genefam gf
        LEFT JOIN gene_has_locus_type ghtlt ON gf.genefam_id = ghtlt.genefam_id
        LEFT JOIN locus_type lt ON ghtlt.locus_type_id = lt.id
        LEFT JOIN locus_group lg ON lt.locus_group_id = lg.id
        LEFT JOIN gene_has_location ghl ON gf.genefam_id = ghl.gene_id
        LEFT JOIN gene_location gl ON ghl.location_id = gl.id
        LEFT JOIN chromosomes c ON gl.chr_id = c.chr_id
        LEFT JOIN gene_status gs ON gf.status_id = gs.id
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
