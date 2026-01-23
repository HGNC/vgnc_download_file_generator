"""Database query builders for VGNC data export.

This module provides functions to build SQL queries for extracting
data from the VGNC database, optimized for streaming with server-side cursors.
"""

import re
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.sql.expression import TextClause


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


def compile_query_for_mysql(query: TextClause) -> tuple[str, tuple[Any, ...]]:
    """Compile SQLAlchemy TextClause to MySQLdb-compatible format.

    Converts SQLAlchemy's named parameter syntax (:param_name) to MySQLdb's
    format string syntax (%s) and returns both the query string and parameters.

    Args:
        query: SQLAlchemy TextClause with bind parameters

    Returns:
        Tuple of (query_string, params_tuple) for use with cursor.execute()

    Example:
        >>> query = build_gene_data_query(filters={"taxon_id": 9913})
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
