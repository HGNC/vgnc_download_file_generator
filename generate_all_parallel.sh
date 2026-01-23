#!/bin/bash
# VGNC Download File Generator - Parallel Batch Generation Script
#
# This script generates all VGNC download files using GNU parallel
# for efficient parallel execution.
#
# Usage:
#   ./generate_all_parallel.sh [options]
#
# Options:
#   --species "taxon_id1,taxon_id2"  Only generate for specified species
#   --chromosomes "chr1,chr2,X"      Only generate specified chromosomes
#                                    If not provided, discovers from database
#   --formats "tsv,json"              Output formats (default: tsv,json)
#   --jobs N                         Number of parallel jobs (default: auto-detect)
#   --timeout N                      Job timeout in seconds (default: 3600)
#   --force                          Regenerate even if files exist
#   --dry-run                        Show what would be generated
#   --continue                       Continue on errors (default: stop after retries)
#   --skip-withdrawn                  Skip withdrawn entries
#   --skip-ensembl                    Skip Ensembl mapping
#
# Examples:
#   ./generate_all_parallel.sh --species "9913,9606"
#   ./generate_all_parallel.sh --species "9913" --chromosomes "1,2,X" --jobs 4
#   ./generate_all_parallel.sh --species "9913" --dry-run
#
# Environment Variables:
#   APP_DATABASE__DBHOST    Database host (default: localhost)
#   APP_DATABASE__DBPORT    Database port (default: 3306)
#   APP_DATABASE__DBNAME    Database name (default: vgnc)
#   APP_DATABASE__DBUSER    Database user (default: root)
#   APP_DATABASE__DBPASS    Database password (required)

set -euo pipefail

# ============================================
# Configuration
# ============================================

# Script version
VERSION="2.0.0"

# Directory containing this script (for finding helper scripts)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Set DYLD_LIBRARY_PATH for MySQL client library on macOS
# This is needed because the Python MySQLdb module needs to find libmysqlclient.21.dylib
# This must be done before defining CLI_CMD so subprocesses inherit it
if [[ "$(uname)" == "Darwin" ]]; then
    # Try common MySQL installation paths
    if [[ -f "/usr/local/mysql-8.0.42-macos15-arm64/lib/libmysqlclient.21.dylib" ]]; then
        export DYLD_LIBRARY_PATH="/usr/local/mysql-8.0.42-macos15-arm64/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
    elif [[ -f "/opt/homebrew/opt/mysql-client/lib/libmysqlclient.21.dylib" ]]; then
        export DYLD_LIBRARY_PATH="/opt/homebrew/opt/mysql-client/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
    elif [[ -f "/usr/local/mysql/lib/libmysqlclient.21.dylib" ]]; then
        export DYLD_LIBRARY_PATH="/usr/local/mysql/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
    fi
fi

# CLI command (use full path or alias)
if [[ -n "${VGNC_CLI:-}" ]]; then
    CLI_CMD="${VGNC_CLI}"
elif command -v vgnc-download-file-generator &> /dev/null; then
    CLI_CMD="vgnc-download-file-generator"
else
    # Fallback to using uv run
    CLI_CMD="uv run python -m vgnc_download_file_generator"
fi

# Python helper command for database queries
PYTHON_HELPER="uv run python ${SCRIPT_DIR}/db_query_helper.py"

# Database credentials
DB_HOST="${APP_DATABASE__DBHOST:-localhost}"
DB_PORT="${APP_DATABASE__DBPORT:-3306}"
DB_NAME="${APP_DATABASE__DBNAME:-vgnc}"
DB_USER="${APP_DATABASE__DBUSER:-root}"
DB_PASS="${APP_DATABASE__DBPASS:-}"

# Default parallel job settings
DEFAULT_TIMEOUT=3600  # 1 hour per job
DEFAULT_RETRIES=3

# Common locus types
DEFAULT_LOCUS_TYPES=(
    "gene with protein product"
    "pseudogene"
)

# Common locus groups
DEFAULT_LOCUS_GROUPS=(
    "protein-coding gene"
    "pseudogene"
)

# ============================================
# Detect CPU Cores for Auto Job Detection
# ============================================

detect_cpu_cores() {
    local cpu_count

    # Try different methods based on OS
    if [[ "$(uname)" == "Darwin" ]]; then
        # macOS: Use sysctl to get logical CPU count
        # For performance cores on Apple Silicon, use hw.perflevel0.physicalcpu
        if cpu_count=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null); then
            : # Successfully got performance cores
        elif cpu_count=$(sysctl -n hw.ncpu); then
            : # Fallback to total CPU count
        else
            cpu_count=4  # Conservative default
        fi
    else
        # Linux: Use nproc
        if command -v nproc &> /dev/null; then
            cpu_count=$(nproc)
        else
            cpu_count=4  # Conservative default
        fi
    fi

    echo "$cpu_count"
}

# Calculate default job count (CPU cores - 2, minimum 1)
calculate_default_jobs() {
    local cpu_cores
    cpu_cores=$(detect_cpu_cores)
    local jobs=$((cpu_cores - 2))

    if [[ $jobs -lt 1 ]]; then
        jobs=1
    fi

    echo "$jobs"
}

# ============================================
# Check for GNU Parallel
# ============================================

check_gnu_parallel() {
    if ! command -v parallel &> /dev/null; then
        log_error "GNU parallel is not installed."
        echo ""
        echo "To install GNU parallel:"
        echo "  macOS:   brew install parallel"
        echo "  Ubuntu/Debian: sudo apt-get install parallel"
        echo "  CentOS/RHEL:   sudo yum install parallel"
        echo ""
        echo "Or install from: https://ftpmirror.gnu.org/parallel/"
        exit 1
    fi
}

# ============================================
# Parse Arguments
# ============================================

SPECIES_FILTER=""
CHROMOSOME_FILTER=""  # Empty means discover from database
FORMATS="tsv,json"
JOBS=""  # Empty means auto-detect
TIMEOUT="${DEFAULT_TIMEOUT}"
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
        --jobs)
            JOBS="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
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
VGNC Download File Generator - Parallel Batch Generation v${VERSION}

Usage: $0 [options]

Options:
  --species IDS        Only generate for specified species (comma-separated taxon IDs)
  --chromosomes CHRS   Only generate specified chromosomes (comma-separated)
                       If not provided, chromosomes will be discovered from database
  --formats FMTS       Output formats: tsv,json (default: tsv,json)
  --jobs N             Number of parallel jobs (default: auto-detect based on CPU cores)
  --timeout N          Job timeout in seconds (default: 3600)
  --force              Regenerate even if files exist
  --dry-run            Show what would be generated without running
  --continue           Continue on errors after retries exhausted
  --skip-withdrawn     Skip withdrawn entries generation
  --skip-ensembl       Skip Ensembl mapping generation
  --help               Show this help message

Environment Variables:
  APP_DATABASE__DBHOST    Database host (default: localhost)
  APP_DATABASE__DBPORT    Database port (default: 3306)
  APP_DATABASE__DBNAME    Database name (default: vgnc)
  APP_DATABASE__DBUSER    Database user (default: root)
  APP_DATABASE__DBPASS    Database password (required)

Examples:
  # Auto-detect parallelism, generate for specific species
  $0 --species "9913,9606,9598"

  # Override job count and chromosomes
  $0 --species "9913" --chromosomes "1,2,X,Y" --jobs 4

  # Preview what would be generated
  $0 --species "9913" --dry-run

NOTE: This script requires GNU parallel to be installed.
      On macOS: brew install parallel
      On Ubuntu/Debian: sudo apt-get install parallel

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

# Check for GNU parallel (skip in dry-run mode)
if [[ -z "${DRY_RUN_FLAG}" ]]; then
    check_gnu_parallel
fi

# Auto-detect job count if not specified
if [[ -z "${JOBS}" ]]; then
    JOBS=$(calculate_default_jobs)
fi

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

# Convert comma-separated list to array
csv_to_array() {
    local IFS=','
    read -ra ADDR <<< "$1"
    printf '%s\n' "${ADDR[@]}"
}

# Query database for chromosomes of a specific species
get_chromosomes_for_species() {
    local species_id="$1"

    # Change to script directory to ensure .env file is found
    local original_pwd="$(pwd)"
    cd "${SCRIPT_DIR}" || return 1

    # Use Python helper script to query database
    local chromosomes
    chromosomes=$(${PYTHON_HELPER} chromosomes "${species_id}" 2>/dev/null)

    cd "${original_pwd}" || return 1

    if [[ -z "${chromosomes}" ]]; then
        log_error "No chromosomes found for species ${species_id}"
        return 1
    fi

    echo "${chromosomes}"
    return 0
}

# Query database for all species (auto-discovery for default behavior)
get_all_species() {
    # Change to script directory to ensure .env file is found
    local original_pwd="$(pwd)"
    cd "${SCRIPT_DIR}" || return 1

    # Use Python helper script to query database
    local species
    species=$(${PYTHON_HELPER} species 2>/dev/null)

    cd "${original_pwd}" || return 1

    if [[ -z "${species}" ]]; then
        log_error "No species found in database"
        log_error "This may be due to:"
        log_error "  1. MySQL database not accessible"
        log_error "  2. MySQL client library not found (libmysqlclient.21.dylib)"
        log_error "  3. Database credentials not configured in .env file"
        log_error ""
        log_error "To fix MySQL client library issues on macOS with Homebrew:"
        log_error "  brew link mysql-client --force"
        log_error "  or export DYLD_LIBRARY_PATH=\$(brew --prefix mysql-client)/lib"
        return 1
    fi

    cd "${original_pwd}" || return 1

    if [[ -z "${species}" ]]; then
        log_error "No species found in database"
        return 1
    fi

    echo "${species}"
    return 0
}

# ============================================
# Validation
# ============================================

log_step "VGNC Download File Generator - Parallel Generation v${VERSION}"

log_info "Using CLI command: ${CLI_CMD}"
log_info "Parallel jobs: ${JOBS} (auto-detected from CPU cores)"
log_info "Job timeout: ${TIMEOUT}s"
log_info "Retries: ${DEFAULT_RETRIES}"

# ============================================
# Job Generation
# ============================================

JOB_FILE=$(mktemp)
trap "rm -f ${JOB_FILE}" EXIT

log_step "Generating Job List"

# Job counter
JOB_COUNT=0

# Split formats into array for individual job generation
IFS=',' read -ra FORMAT_ARRAY <<< "${FORMATS}"

# ============================================
# Step 1: "All" Species Files
# ============================================

log_info "Adding 'All' species jobs..."

# 1a. VGNC Public - All species (no chromosome filter)
for FORMAT in "${FORMAT_ARRAY[@]}"; do
    FORMAT=$(echo "${FORMAT}" | xargs)  # Trim whitespace
    echo "--species All --formats \"${FORMAT}\" ${DRY_RUN_FLAG}" >> "${JOB_FILE}"
    JOB_COUNT=$((JOB_COUNT + 1))
done

# 1b. Ensembl Mapping
if [[ "${SKIP_ENSEMBL}" != true ]]; then
    for FORMAT in "${FORMAT_ARRAY[@]}"; do
        FORMAT=$(echo "${FORMAT}" | xargs)
        echo "--species All --file-type vgnc_ensembl --formats \"${FORMAT}\" ${DRY_RUN_FLAG}" >> "${JOB_FILE}"
        JOB_COUNT=$((JOB_COUNT + 1))
    done
else
    log_info "Skipping Ensembl mapping (--skip-ensembl specified)"
fi

# 1c. Withdrawn Entries
if [[ "${SKIP_WITHDRAWN}" != true ]]; then
    for FORMAT in "${FORMAT_ARRAY[@]}"; do
        FORMAT=$(echo "${FORMAT}" | xargs)
        echo "--species All --file-type vgnc_withdrawn --formats \"${FORMAT}\" ${DRY_RUN_FLAG}" >> "${JOB_FILE}"
        JOB_COUNT=$((JOB_COUNT + 1))
    done
else
    log_info "Skipping withdrawn entries (--skip-withdrawn specified)"
fi

# ============================================
# Step 2: Per-Species Chromosome Files
# ============================================

# Auto-discover species if not specified (default behavior: generate ALL files)
if [[ -z "${SPECIES_FILTER}" ]]; then
    log_info "No --species specified, auto-discovering all species from database..."

    if [[ -z "${DRY_RUN_FLAG}" ]]; then
        DISCOVERED_SPECIES=$(get_all_species)

        if [[ $? -ne 0 ]]; then
            log_error "Failed to discover species from database"
            if [[ "${CONTINUE_ON_ERROR}" == true ]]; then
                log_info "Continuing without per-species files"
                SPECIES_FILTER=""
            else
                exit 1
            fi
        else
            SPECIES_FILTER="${DISCOVERED_SPECIES}"
            log_info "Discovered species: ${SPECIES_FILTER}"
        fi
    else
        # Dry run mode - can't query DB, use example species
        SPECIES_FILTER="9913,9606,9598"
        log_info "Dry run: using example species: ${SPECIES_FILTER}"
    fi
fi

if [[ -n "${SPECIES_FILTER}" ]]; then
    log_info "Adding per-species chromosome jobs for: ${SPECIES_FILTER}"

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
            if [[ -z "${DRY_RUN_FLAG}" ]]; then
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
            else
                # Dry run mode - can't query DB
                CHROMOSOME_LIST="1,2,X,Y,Un"
                log_info "Dry run: using example chromosomes: ${CHROMOSOME_LIST}"
            fi
        fi

        # Generate for each chromosome
        IFS=',' read -ra CHROMOSOME_ARRAY <<< "${CHROMOSOME_LIST}"
        for CHROMOSOME in "${CHROMOSOME_ARRAY[@]}"; do
            CHROMOSOME=$(echo "${CHROMOSOME}" | xargs)  # Trim whitespace

            # Split formats into individual jobs
            for FORMAT in "${FORMAT_ARRAY[@]}"; do
                FORMAT=$(echo "${FORMAT}" | xargs)
                echo "--species \"${SPECIES_ID}\" --chromosome \"${CHROMOSOME}\" --formats \"${FORMAT}\" ${DRY_RUN_FLAG}" >> "${JOB_FILE}"
                JOB_COUNT=$((JOB_COUNT + 1))
            done
        done
    done
else
    log_info "No species available for per-species file generation"
    log_info "This may indicate a database connection issue or no species in the database"
fi

# ============================================
# Step 3: Per-Species Locus Type Files
# ============================================

if [[ -n "${SPECIES_FILTER}" ]]; then
    log_info "Adding per-species locus type jobs for: ${SPECIES_FILTER}"

    IFS=',' read -ra SPECIES_ARRAY <<< "${SPECIES_FILTER}"
    for SPECIES_ID in "${SPECIES_ARRAY[@]}"; do
        SPECIES_ID=$(echo "${SPECIES_ID}" | xargs)

        for LOCUS_TYPE in "${DEFAULT_LOCUS_TYPES[@]}"; do
            # Split formats into individual jobs
            for FORMAT in "${FORMAT_ARRAY[@]}"; do
                FORMAT=$(echo "${FORMAT}" | xargs)
                echo "--species \"${SPECIES_ID}\" --locus-type \"${LOCUS_TYPE}\" --formats \"${FORMAT}\" ${DRY_RUN_FLAG}" >> "${JOB_FILE}"
                JOB_COUNT=$((JOB_COUNT + 1))
            done
        done
    done
else
    log_info "No species available for locus type file generation"
fi

# ============================================
# Step 4: Per-Species Locus Group Files
# ============================================

if [[ -n "${SPECIES_FILTER}" ]]; then
    log_info "Adding per-species locus group jobs for: ${SPECIES_FILTER}"

    IFS=',' read -ra SPECIES_ARRAY <<< "${SPECIES_FILTER}"
    for SPECIES_ID in "${SPECIES_ARRAY[@]}"; do
        SPECIES_ID=$(echo "${SPECIES_ID}" | xargs)

        for LOCUS_GROUP in "${DEFAULT_LOCUS_GROUPS[@]}"; do
            # Split formats into individual jobs
            for FORMAT in "${FORMAT_ARRAY[@]}"; do
                FORMAT=$(echo "${FORMAT}" | xargs)
                echo "--species \"${SPECIES_ID}\" --locus-group \"${LOCUS_GROUP}\" --formats \"${FORMAT}\" ${DRY_RUN_FLAG}" >> "${JOB_FILE}"
                JOB_COUNT=$((JOB_COUNT + 1))
            done
        done
    done
else
    log_info "No species available for locus group file generation"
fi

log_info "Total jobs to execute: ${JOB_COUNT}"

# ============================================
# Execute Jobs with GNU Parallel
# ============================================

if [[ -n "${DRY_RUN_FLAG}" ]]; then
    log_step "Dry Run - Job List Preview"
    echo ""
    cat "${JOB_FILE}"
    echo ""
    log_info "Dry run completed. No files were actually generated."
    log_info "To run for real, remove the --dry-run flag."
    exit 0
fi

log_step "Executing Jobs with GNU Parallel"

# Job log file for tracking
JOB_LOG="parallel_joblog_$(date +%Y%m%d_%H%M%S).log"

# Build GNU parallel command
PARALLEL_CMD="parallel"

# Progress bar
PARALLEL_CMD="${PARALLEL_CMD} --bar"

# Job limit
PARALLEL_CMD="${PARALLEL_CMD} --jobs ${JOBS}"

# Retries
PARALLEL_CMD="${PARALLEL_CMD} --retries ${DEFAULT_RETRIES}"

# Job logging
PARALLEL_CMD="${PARALLEL_CMD} --joblog ${JOB_LOG}"

# Timeout
PARALLEL_CMD="${PARALLEL_CMD} --timeout ${TIMEOUT}"

# Continue on error if requested
if [[ "${CONTINUE_ON_ERROR}" == true ]]; then
    PARALLEL_CMD="${PARALLEL_CMD} --keep-order"
fi

# Read jobs from file and execute
log_info "Starting parallel execution..."
log_info "Job log: ${JOB_LOG}"
echo ""

# Export a function that can execute the CLI with the job arguments
export -f run_cli_job 2>/dev/null || true
run_cli_job() {
    eval "${CLI_CMD} $1"
}
export -f run_cli_job

set +e  # Don't exit on error with parallel
# Use the wrapper script to execute jobs with proper DYLD_LIBRARY_PATH and argument handling
eval "${PARALLEL_CMD}" "${SCRIPT_DIR}/run_cli_job.sh {1}" :::: "${JOB_FILE}"
PARALLEL_EXIT_CODE=$?
set -e

# ============================================
# Post-Execution Analysis
# ============================================

echo ""
log_step "Execution Complete"

# Analyze job log
if [[ -f "${JOB_LOG}" ]]; then
    TOTAL_JOBS=$(tail -n +2 "${JOB_LOG}" | wc -l | tr -d ' ')
    SUCCESS_JOBS=$(tail -n +2 "${JOB_LOG}" | awk '$7 == 0' | wc -l | tr -d ' ')
    FAILED_JOBS=$(tail -n +2 "${JOB_LOG}" | awk '$7 != 0' | wc -l | tr -d ' ')

    log_success "Jobs completed: ${SUCCESS_JOBS}/${TOTAL_JOBS}"

    if [[ ${FAILED_JOBS} -gt 0 ]]; then
        log_error "Jobs failed: ${FAILED_JOBS}/${TOTAL_JOBS}"
        echo ""
        echo "Failed jobs:"
        tail -n +2 "${JOB_LOG}" | awk '$7 != 0 {print "  Command: " $9 " (Exit: " $7 ")" }'

        if [[ "${CONTINUE_ON_ERROR}" == true ]]; then
            log_info "Continue mode: Some jobs failed but execution completed"
            exit 0
        else
            log_error "Jobs failed. Check ${JOB_LOG} for details."
            exit 1
        fi
    else
        log_success "All jobs completed successfully!"
    fi
else
    log_info "Job log not found (may have been cleaned up)"
fi

exit ${PARALLEL_EXIT_CODE}
