#!/usr/bin/env python3
"""Helper script for database queries used by entrypoint.sh.

This script queries the database for species and chromosome information
and outputs results in a comma-separated format for use in bash scripts.

Usage:
    python db_query_helper.py species          # Get all species IDs
    python db_query_helper.py chromosomes 9913  # Get chromosomes for species
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


def get_chromosomes_for_species(species_id: int) -> str:
    """Query database for chromosomes of a specific species.

    Groups all non-chromosome data (coord_system not equal to 'chromosome')
    into a single 'Un' chromosome entry. Only actual chromosomes with
    coord_system = 'chromosome' are kept as separate files.

    Also checks for genes WITHOUT location data and includes 'Un' in the
    chromosome list if such genes exist. This ensures all genes are captured
    in some file.

    Joins with gene_has_location, gene_location, and genefam to ensure only
    chromosomes with actual gene data are returned. If the species has genes but
    no chromosome/location data, returns 'Un' as a fallback.

    Args:
        species_id: Taxon ID of the species

    Returns:
        Comma-separated string of chromosome names
    """
    from vgnc_download_file_generator.config import get_settings
    from vgnc_download_file_generator.database.connection import DatabaseConnection

    config = get_settings()
    db = DatabaseConnection(config.database)

    query = """
        SELECT DISTINCT c.display_name
        FROM genefam gf
        JOIN gene_has_location ghl ON gf.genefam_id = ghl.gene_id
        JOIN gene_location gl ON ghl.location_id = gl.id
        JOIN chromosomes c ON gl.chr_id = c.chr_id
        WHERE gf.taxon_id = %s
          AND c.taxon_id = gf.taxon_id
          AND c.coord_system LIKE '%%chromosome%%'
          AND c.display_name NOT LIKE 'Un%%'
          AND c.display_name NOT LIKE 'Un_%%'
        ORDER BY c.display_name;
    """

    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(query, (species_id,))
    chromosomes = [row[0] for row in cursor.fetchall()]
    cursor.close()

    # Check if there are genes that should go in Un file:
    # 1. Genes on non-chromosome coord_systems (scaffolds, contigs)
    # 2. Genes on chromosomes with display_name starting with Un/Un_
    # 3. Genes with NO location data at all
    un_check_query = """
        SELECT 1
        FROM genefam gf
        LEFT JOIN gene_has_location ghl ON gf.genefam_id = ghl.gene_id
        LEFT JOIN gene_location gl ON ghl.location_id = gl.id
        LEFT JOIN chromosomes c ON gl.chr_id = c.chr_id
        WHERE gf.taxon_id = %s
          AND (
            ghl.gene_id IS NULL  -- No location data at all
            OR (c.chr_id IS NOT NULL AND (
                c.coord_system NOT LIKE '%%chromosome%%'  -- Non-chromosome coord_system
                OR c.display_name LIKE 'Un%%'  -- Display name starts with Un
                OR c.display_name LIKE 'Un_%%'  -- Display name starts with Un_
            ))
          )
        LIMIT 1
    """
    cursor = conn.cursor()
    cursor.execute(un_check_query, (species_id,))
    has_un_genes = cursor.fetchone() is not None
    cursor.close()
    conn.close()

    # If there are any genes that should be in Un file, add 'Un' to the list
    if has_un_genes:
        chromosomes.append('Un')

    return ",".join(chromosomes)


def main():
    """Main entry point for the helper script."""
    if len(sys.argv) < 2:
        print("Usage: python db_query_helper.py species | chromosomes <species_id>", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1].lower()

    try:
        if command == "species":
            result = get_all_species()
            print(result, end="")
        elif command == "chromosomes":
            if len(sys.argv) < 3:
                print("Error: chromosomes command requires species_id argument", file=sys.stderr)
                sys.exit(1)
            species_id = int(sys.argv[2])
            result = get_chromosomes_for_species(species_id)
            print(result, end="")
        else:
            print(f"Error: Unknown command '{command}'", file=sys.stderr)
            print("Valid commands: species, chromosomes", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
