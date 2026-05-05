#!/bin/bash
# VGNC Download File Generator - Batch Generation Script
#
# This script mimics a future --generate-all feature by calling the CLI
# multiple times to generate all VGNC download files.
#
# Usage:
#   ./generate_all.sh [options]
#
# Options:
#   --species "taxon_id1,taxon_id2"  Only generate for specified species
#   --chromosomes "chr1,chr2,X"      Only generate specified chromosomes
#                                    If not provided, discovers from database
#   --formats "tsv,json"              Output formats (default: tsv,json)
#   --force                           Regenerate even if files exist
#   --dry-run                         Show what would be generated
#   --continue                        Continue on errors (default: stop)
#   --skip-withdrawn                  Skip withdrawn entries
#   --skip-ensembl                    Skip Ensembl mapping
#
# Examples:
#   ./generate_all.sh --species "9913,9606"            # Generate all chromosomes for species
#   ./generate_all.sh --species "9913" --chromosomes "1,2,X"  # Specific chromosomes
#   ./generate_all.sh --species "9913" --formats tsv   # Only TSV files
#   ./generate_all.sh --species "9913" --dry-run       # Preview what will be generated
#
# Environment Variables:
#   DB_HOST       Database host (default: localhost)
#   DB_PORT       Database port (default: 3306)
#   DB_NAME       Database name (default: vgnc)
#   DB_USER       Database user (default: root)
#   DB_PASSWORD   Database password (required)

set -euo pipefail

# ============================================
# Configuration
# ============================================

# Script version
VERSION="1.0.0"

# CLI command (use full path or alias)
# Can be overridden by VGNC_CLI environment variable
if [[ -n "${VGNC_CLI:-}" ]]; then
    CLI_CMD="${VGNC_CLI}"
elif command -v vgnc-download-file-generator &> /dev/null; then
    CLI_CMD="vgnc-download-file-generator"
else
    # Fallback to using uv run
    CLI_CMD="uv run python -m vgnc_download_file_generator"
fi

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-3306}"
DB_NAME="${DB_NAME:-vgnc}"
DB_USER="${DB_USER:-root}"
DB_PASS="${DB_PASSWORD:-}"

# Common locus types (space-separated as required by CLI)
DEFAULT_LOCUS_TYPES=(
    "gene with protein product"
    "pseudogene"
)

# ============================================
# Parse Arguments
# ============================================

SPECIES_FILTER=""
CHROMOSOME_FILTER=""  # Empty means discover from database
FORMATS="tsv,json"
FORCE_FLAG=""
DRY_RUN_FLAG=""
CONTINUE_ON_ERROR=false
SKIP_WITHDRAWN=false
SKIP_ENSEMBL=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --species)
            SPECIES_FILTER="$2"
            shift 2
            ;;
        --chromosomes)
            CHROMOSOME_FILTER="$2"
            shift 2
            ;;
        --formats)
            FORMATS="$2"
            shift 2
            ;;
        --force)
            FORCE_FLAG="--force"
            shift
            ;;
        --dry-run)
            DRY_RUN_FLAG="--dry-run"
            shift
            ;;
        --continue)
            CONTINUE_ON_ERROR=true
            shift
            ;;
        --skip-withdrawn)
            SKIP_WITHDRAWN=true
            shift
            ;;
        --skip-ensembl)
            SKIP_ENSEMBL=true
            shift
            ;;
        --help)
            cat << EOF
VGNC Download File Generator - Batch Generation Script v${VERSION}

Usage: $0 [options]

Options:
  --species IDS        Only generate for specified species (comma-separated taxon IDs)
  --chromosomes CHRS   Only generate specified chromosomes (comma-separated)
                       If not provided, chromosomes will be discovered from database
  --formats FMTS       Output formats: tsv,json (default: tsv,json)
  --force              Regenerate even if files exist
  --dry-run            Show what would be generated without running
  --continue           Continue on errors (default: stop)
  --skip-withdrawn     Skip withdrawn entries generation
  --skip-ensembl       Skip Ensembl mapping generation
  --help               Show this help message

Environment Variables:
  DB_HOST       Database host (default: localhost)
  DB_PORT       Database port (default: 3306)
  DB_NAME       Database name (default: vgnc)
  DB_USER       Database user (default: root)
  DB_PASSWORD   Database password (required)

Examples:
  # Generate all files for specific species (discovers chromosomes from database)
  $0 --species "9913,9606,9598"

  # Generate only specific chromosomes for a species
  $0 --species "9913" --chromosomes "1,2,X,Y"

  # Generate only TSV files
  $0 --species "9913" --formats tsv

  # Preview what would be generated
  $0 --species "9913" --dry-run

NOTE: Chromosome discovery requires mysql-client to be installed.
      On macOS: brew install mysql-client
      On Ubuntu/Debian: sudo apt-get install mysql-client

EOF
            exit 0
            ;;
        *)
            echo "Error: Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# ============================================
# Helper Functions
# ============================================

log_info() {
    echo "[INFO] $*"
}

log_success() {
    echo "[SUCCESS] $*"
}

log_error() {
    echo "[ERROR] $*" >&2
}

log_step() {
    echo ""
    echo "=========================================="
    echo "$*"
    echo "=========================================="
}

run_cli() {
    local cmd="$CLI_CMD $*"

    if [[ -n "${DRY_RUN_FLAG}" ]]; then
        log_info "Would run: ${cmd}"
        return 0
    fi

    log_info "Running: ${cmd}"

    if eval "${cmd}"; then
        log_success "Command completed successfully"
        return 0
    else
        local exit_code=$?
        log_error "Command failed with exit code ${exit_code}"

        if [[ "${CONTINUE_ON_ERROR}" == true ]]; then
            log_info "Continuing despite error..."
            return 0
        else
            return ${exit_code}
        fi
    fi
}

# Convert comma-separated list to array
csv_to_array() {
    local IFS=','
    read -ra ADDR <<< "$1"
    printf '%s\n' "${ADDR[@]}"
}

# Query database for chromosomes of a specific species
# Uses the same query pattern as the Python application
get_chromosomes_for_species() {
    local species_id="$1"

    # Check if mysql client is available
    if ! command -v mysql &> /dev/null; then
        log_error "mysql client not found. Please install mysql-client or use --chromosomes flag."
        log_error "On macOS: brew install mysql-client"
        log_error "On Ubuntu/Debian: sudo apt-get install mysql-client"
        return 1
    fi

    # Build the SQL query
    # This query gets all chromosomes for a species that have gene locations
    # Groups all Un* scaffolds (Un0001, Un0002, etc.) as "Un"
    local query="
        SELECT DISTINCT
            CASE
                WHEN c.display_name LIKE 'Un%' THEN 'Un'
                WHEN c.display_name LIKE 'Un_%' THEN 'Un'
                ELSE c.display_name
            END as chromosome_name
        FROM chromosomes c
        JOIN gene_location gl ON c.chr_id = gl.chr_id
        JOIN genefam gf ON gl.gene_id = gf.genefam_id
        WHERE gf.taxon_id = ${species_id}
        ORDER BY chromosome_name;
    "

    # Execute query and return results as comma-separated list
    local chromosomes
    chromosomes=$(mysql -h"${DB_HOST}" -P"${DB_PORT}" -u"${DB_USER}" -p"${DB_PASS}" "${DB_NAME}" -N -s -e "${query}" 2>/dev/null)

    if [[ -z "${chromosomes}" ]]; then
        log_error "No chromosomes found for species ${species_id}"
        return 1
    fi

    # Convert newlines to commas
    echo "$chromosomes" | tr '\n' ',' | sed 's/,$//'
    return 0
}

# ============================================
# Validation
# ============================================

log_step "VGNC Download File Generator - Batch Generation v${VERSION}"

log_info "Using CLI command: ${CLI_CMD}"

# ============================================
# Main Generation
# ============================================

TOTAL_STEPS=0
COMPLETED_STEPS=0

# Count total steps (rough estimate)
if [[ -z "${SPECIES_FILTER}" ]]; then
    log_info "Generating files for ALL species"
else
    log_info "Generating files for species: ${SPECIES_FILTER}"
fi

# ============================================
# Step 1: Generate "All" Species Files
# ============================================

log_step "Step 1: Generating 'All' Species Files"

# 1a. VGNC Public - All species (no chromosome filter)
log_info "Generating VGNC Public files for all species..."
run_cli --species "All" --formats "${FORMATS}" ${DRY_RUN_FLAG}
COMPLETED_STEPS=$((COMPLETED_STEPS + 1))

# 1b. Ensembl Mapping
if [[ "${SKIP_ENSEMBL}" != true ]]; then
    log_info "Generating Ensembl mapping..."
    run_cli --species "All" --file-type "vgnc_ensembl" --formats "${FORMATS}" ${DRY_RUN_FLAG}
    COMPLETED_STEPS=$((COMPLETED_STEPS + 1))
else
    log_info "Skipping Ensembl mapping (--skip-ensembl specified)"
fi

# 1c. Withdrawn Entries
if [[ "${SKIP_WITHDRAWN}" != true ]]; then
    log_info "Generating withdrawn entries..."
    run_cli --species "All" --file-type "vgnc_withdrawn" --formats "${FORMATS}" ${DRY_RUN_FLAG}
    COMPLETED_STEPS=$((COMPLETED_STEPS + 1))
else
    log_info "Skipping withdrawn entries (--skip-withdrawn specified)"
fi

# ============================================
# Step 2: Generate Per-Species Chromosome Files
# ============================================

log_step "Step 2: Generating Per-Species Chromosome Files"

if [[ -n "${SPECIES_FILTER}" ]]; then
    # Generate for specified species
    log_info "Generating for species: ${SPECIES_FILTER}"

    IFS=',' read -ra SPECIES_ARRAY <<< "${SPECIES_FILTER}"
    for SPECIES_ID in "${SPECIES_ARRAY[@]}"; do
        SPECIES_ID=$(echo "${SPECIES_ID}" | xargs)  # Trim whitespace

        # Determine which chromosomes to use
        if [[ -n "${CHROMOSOME_FILTER}" ]]; then
            # Use user-provided chromosome list
            CHROMOSOME_LIST="${CHROMOSOME_FILTER}"
            log_info "Using user-provided chromosomes: ${CHROMOSOME_FILTER}"
        else
            # Discover chromosomes from database
            log_info "Discovering chromosomes for species ${SPECIES_ID} from database..."
            CHROMOSOME_LIST=$(get_chromosomes_for_species "${SPECIES_ID}")

            if [[ $? -ne 0 ]]; then
                log_error "Failed to discover chromosomes for species ${SPECIES_ID}"
                if [[ "${CONTINUE_ON_ERROR}" == true ]]; then
                    continue
                else
                    exit 1
                fi
            fi
            log_info "Found chromosomes: ${CHROMOSOME_LIST}"
        fi

        # Generate for each chromosome
        IFS=',' read -ra CHROMOSOME_ARRAY <<< "${CHROMOSOME_LIST}"
        for CHROMOSOME in "${CHROMOSOME_ARRAY[@]}"; do
            CHROMOSOME=$(echo "${CHROMOSOME}" | xargs)  # Trim whitespace

            log_info "Generating species ${SPECIES_ID}, chromosome ${CHROMOSOME}..."
            run_cli --species "${SPECIES_ID}" --chromosome "${CHROMOSOME}" --formats "${FORMATS}" ${DRY_RUN_FLAG}
            COMPLETED_STEPS=$((COMPLETED_STEPS + 1))
        done
    done
else
    log_info "No specific species specified (--species not provided)"
    log_info "To generate per-species files, use: --species \"9913,9606,9598\""
fi

# ============================================
# Step 3: Generate Per-Species Locus Type Files
# ============================================

log_step "Step 3: Generating Per-Species Locus Type Files"

if [[ -n "${SPECIES_FILTER}" ]]; then
    IFS=',' read -ra SPECIES_ARRAY <<< "${SPECIES_FILTER}"
    for SPECIES_ID in "${SPECIES_ARRAY[@]}"; do
        SPECIES_ID=$(echo "${SPECIES_ID}" | xargs)

        for LOCUS_TYPE in "${DEFAULT_LOCUS_TYPES[@]}"; do
            log_info "Generating species ${SPECIES_ID}, locus type '${LOCUS_TYPE}'..."
            run_cli --species "${SPECIES_ID}" --locus-type "${LOCUS_TYPE}" --formats "${FORMATS}" ${DRY_RUN_FLAG}
            COMPLETED_STEPS=$((COMPLETED_STEPS + 1))
        done
    done
else
    log_info "No specific species specified, skipping locus type files"
fi

# ============================================
# Completion Summary
# ============================================

log_step "Generation Complete"

if [[ -n "${DRY_RUN_FLAG}" ]]; then
    log_info "Dry run completed. No files were actually generated."
    log_info "To run for real, remove the --dry-run flag."
else
    log_success "All generation tasks completed!"
    log_info "Total commands executed: ${COMPLETED_STEPS}"
fi

exit 0
