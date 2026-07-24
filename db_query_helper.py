#!/usr/bin/env python3
"""Helper script for database queries used by entrypoint.sh.

This script queries the database for species information
and outputs results in a comma-separated format for use in bash scripts.

Usage:
    python db_query_helper.py species          # Get all species IDs
"""

import sys
from pathlib import Path

# Explicitly load .env file from the script's directory
# This is necessary because the script may be called from a different directory
_script_dir = Path(__file__).parent
_env_file = _script_dir / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file, override=True)


def get_all_species():
    """Query database for all distinct taxon IDs.

    Returns:
        Comma-separated string of taxon IDs
    """
    from vgnc_download_file_generator.config import get_settings
    from vgnc_download_file_generator.database.connection import DatabaseConnection

    config = get_settings()
    db = DatabaseConnection(config.database)

    query = """
        SELECT DISTINCT taxon_id
        FROM genefam
        WHERE taxon_id IS NOT NULL
        ORDER BY taxon_id;
    """

    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(query)
    species_ids = [str(row[0]) for row in cursor.fetchall()]
    cursor.close()
    conn.close()

    return ",".join(species_ids)


def main():
    """Main entry point for the helper script."""
    if len(sys.argv) < 2:
        print("Usage: python db_query_helper.py species", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1].lower()

    try:
        if command == "species":
            result = get_all_species()
            print(result, end="")
        else:
            print(f"Error: Unknown command '{command}'", file=sys.stderr)
            print("Valid commands: species", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
