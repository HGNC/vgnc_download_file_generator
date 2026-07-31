#!/usr/bin/env python3
"""Run EXPLAIN on build_xrefs_query() to verify indexed access path.

Task T3 verification: confirm genefam_orthologs join uses index access
(type != 'ALL') with key = genefam_orthologs_idx_genefam_id_b.

Usage:
    python scripts/explain_ortholog_join.py [database_name]

Default database: vgnc_public
Override via: MYSQL_TEST_DATABASE env var, or first CLI argument
"""

import os
import sys
from typing import Any

import MySQLdb

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vgnc_download_file_generator.database.queries import compile_query_for_mysql
from vgnc_download_file_generator.database.queries_split import build_xrefs_query

EXPECTED_ACCESS_TYPES = {"ref", "eq_ref", "range"}
EXPECTED_KEY = "genefam_orthologs_idx_genefam_id_b"


def get_connection(database: str) -> Any:
    """Get MySQL connection using MYSQL_TEST_DSN or defaults."""
    dsn = os.environ.get("MYSQL_TEST_DSN", "root:root@127.0.0.1:3306")

    # Parse DSN format: user:password@host:port
    parts = dsn.split("@")
    user_pass = parts[0].split(":") if parts else ["root", "root"]
    host_port = parts[1].split(":") if len(parts) > 1 else ["127.0.0.1", "3306"]

    user = user_pass[0] if len(user_pass) > 0 else "root"
    password = user_pass[1] if len(user_pass) > 1 else "root"
    host = host_port[0] if len(host_port) > 0 else "127.0.0.1"
    port = int(host_port[1]) if len(host_port) > 1 else 3306

    return MySQLdb.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
    )


def explain_xrefs_query(database: str) -> int:
    """Run EXPLAIN on build_xrefs_query() and analyze the plan.

    Returns:
        0 if all checks pass, 1 otherwise.
    """
    conn = get_connection(database)
    cur = conn.cursor()

    print("=" * 80)
    print(f"EXPLAIN for build_xrefs_query() (database: {database})")
    print("=" * 80)

    # Get the query
    query = build_xrefs_query()
    sql, params = compile_query_for_mysql(query)

    # Prepend EXPLAIN
    explain_sql = f"EXPLAIN {sql}"

    print(f"SQL: {explain_sql[:200]}...")
    print()

    cur.execute(explain_sql, params)

    # Get column names
    columns = [desc[0] for desc in cur.description] if cur.description else []
    rows = cur.fetchall()

    # Print formatted table
    col_widths = {col: len(col) for col in columns}
    for row in rows:
        for i, col in enumerate(columns):
            col_widths[col] = max(col_widths[col], len(str(row[i])))

    # Header
    header = " | ".join(col.ljust(col_widths[col]) for col in columns)
    print(header)
    print("-" * len(header))

    # Rows
    for row in rows:
        print(" | ".join(str(row[i]).ljust(col_widths[col]) for i, col in enumerate(columns)))

    print()
    print("=" * 80)
    print("ANALYSIS")
    print("=" * 80)

    # Find the genefam_orthologs row
    go_row = None
    for row in rows:
        row_dict = dict(zip(columns, row, strict=True))
        table_name = row_dict.get("table", "")
        if table_name == "genefam_orthologs" or table_name == "go":
            go_row = row_dict
            break

    if not go_row:
        print("ERROR: Could not find genefam_orthologs table in EXPLAIN output!")
        cur.close()
        conn.close()
        return 1

    print("genefam_orthologs access:")
    print(f"  type: {go_row.get('type')}")
    print(f"  key:  {go_row.get('key')}")
    print(f"  ref:  {go_row.get('ref')}")
    print(f"  rows: {go_row.get('rows')}")
    print(f"  Extra: {go_row.get('Extra')}")
    print()

    # Track check results
    checks_passed = True

    # Check access type
    access_type = go_row.get("type")
    if access_type == "ALL":
        print("FAIL: access type is 'ALL' (full table scan) - regression still present!")
        checks_passed = False
    elif access_type in EXPECTED_ACCESS_TYPES:
        print(f"PASS: access type is '{access_type}' (indexed access, expected: {EXPECTED_ACCESS_TYPES})")
    else:
        print(f"FAIL: unexpected access type '{access_type}' (expected one of: {EXPECTED_ACCESS_TYPES})")
        checks_passed = False

    # Check key
    key_used = go_row.get("key")
    if key_used == EXPECTED_KEY:
        print(f"PASS: using expected index '{EXPECTED_KEY}'")
    else:
        print(f"FAIL: using key '{key_used}', expected '{EXPECTED_KEY}'")
        checks_passed = False

    print()
    print("=" * 80)
    if checks_passed:
        print("CONCLUSION: Indexed access path VERIFIED for genefam_orthologs join")
        print("            type=ref | eq_ref | range AND key=genefam_orthologs_idx_genefam_id_b")
    else:
        print("CONCLUSION: FAILED - genefam_orthologs join does NOT use verified indexed access path")
        print("            Check for regressions in build_xrefs_query() join predicates")
    print("=" * 80)

    cur.close()
    conn.close()
    return 0 if checks_passed else 1


if __name__ == "__main__":
    # Determine database: CLI arg > MYSQL_TEST_DATABASE env var > "vgnc_public" default
    if len(sys.argv) > 1:
        database = sys.argv[1]
    else:
        database = os.environ.get("MYSQL_TEST_DATABASE", "vgnc_public")

    sys.exit(explain_xrefs_query(database))
