#!/bin/bash
set -euo pipefail

PROJECT_ID="prj-ext-prod-hgnc-cloud-ls"
INSTANCE_NAME="prod-db-main"
DEFAULT_DB_USER="prod-user-app"

usage() {
    cat <<'HELP'
Usage: run_all_species.sh [OPTIONS]

Execute the vgnc-download-files Cloud Run job for every species discovered
from the database, plus the cross-species "all" files.

Uses gcloud to connect to Cloud SQL for species discovery, so no local
mysql client or direct network access is needed -- just authenticated gcloud.

Options:
  --db-name NAME         Database name (required, e.g. vgnc_public_2026_05_14)
  --db-user USER         MySQL username (default: prod-user-app)
  --project PROJECT      GCP project ID (default: prj-ext-prod-hgnc-cloud-ls)
  --instance INSTANCE    Cloud SQL instance name (default: prod-db-main)
  --region REGION        Cloud Run region (default: europe-west2)
  --job JOB              Cloud Run job name (default: vgnc-download-files)
  --parallel N           Max parallel executions (default: 5)
  --skip-all             Skip the cross-species "all" files
  --skip-species         Skip per-species files
  --dry-run              Print commands without executing
  -h, --help             Show this help

Examples:

  # Full run
  run_all_species.sh --db-name vgnc_public_2026_05_14

  # Only per-species files, 3 at a time
  run_all_species.sh --skip-all --parallel 3 --db-name vgnc_public_2026_05_14

  # Dry run to see what would execute
  run_all_species.sh --dry-run --db-name vgnc_public_2026_05_14
HELP
}

DB_NAME=""
DB_USER="${DEFAULT_DB_USER}"
REGION="europe-west2"
JOB="vgnc-download-files"
PARALLEL=5
SKIP_ALL=false
SKIP_SPECIES=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db-name)      DB_NAME="$2"; shift 2 ;;
        --db-user)      DB_USER="$2"; shift 2 ;;
        --project)      PROJECT_ID="$2"; shift 2 ;;
        --instance)     INSTANCE_NAME="$2"; shift 2 ;;
        --region)       REGION="$2"; shift 2 ;;
        --job)          JOB="$2"; shift 2 ;;
        --parallel)     PARALLEL="$2"; shift 2 ;;
        --skip-all)     SKIP_ALL=true; shift ;;
        --skip-species) SKIP_SPECIES=true; shift ;;
        --dry-run)      DRY_RUN=true; shift ;;
        -h|--help)      usage; exit 0 ;;
        *)              echo "Unknown option: $1" >&2; usage; exit 1 ;;
    esac
done

if [[ -z "${DB_NAME}" ]]; then
    echo "Error: --db-name is required." >&2
    echo >&2
    usage
    exit 1
fi

run_cmd() {
    local description="$1"
    shift
    if [[ "${DRY_RUN}" == "true" ]]; then
        echo "[DRY RUN] ${description}"
        echo "  $*"
        echo
    else
        echo "[INFO] ${description}"
        "$@"
        echo "[INFO] Done: ${description}"
        echo
    fi
}

discover_species() {
    local query="SELECT DISTINCT taxon_id FROM genefam WHERE taxon_id IS NOT NULL ORDER BY taxon_id;"
    gcloud sql execute "${INSTANCE_NAME}" "${DB_NAME}" \
        --project="${PROJECT_ID}" \
        --sql="${query}" \
        --format="value(taxon_id)"
}

COMMON_ENV="DB_NAME=${DB_NAME},DB_USER=${DB_USER}"

if [[ "${SKIP_ALL}" != "true" ]]; then
    run_cmd "Generating cross-species combined files (mode=all)" \
        gcloud run jobs execute "${JOB}" \
            --region "${REGION}" \
            --wait \
            --update-env-vars="VGNC_MODE=all,${COMMON_ENV}"
fi

if [[ "${SKIP_SPECIES}" != "true" ]]; then
    echo "[INFO] Discovering species from ${DB_NAME} on ${INSTANCE_NAME}..."
    SPECIES_LIST=$(discover_species) || {
        echo "Error: Failed to query database for species." >&2
        exit 1
    }

    if [[ -z "${SPECIES_LIST}" ]]; then
        echo "[WARN] No species found in database." >&2
        exit 0
    fi

    SPECIES_COUNT=$(echo "${SPECIES_LIST}" | wc -l | tr -d ' ')
    echo "[INFO] Found ${SPECIES_COUNT} species: ${SPECIES_LIST//$'\n'/, }"
    echo

    echo "[INFO] Launching per-species jobs (max ${PARALLEL} parallel)..."
    echo

    echo "${SPECIES_LIST}" | xargs -P "${PARALLEL}" -I {} bash -c "
        run_all_species_inner() {
            local taxon_id=\"\$1\"
            echo \"[INFO] Starting species \${taxon_id}...\"
            if [[ \"${DRY_RUN}\" == \"true\" ]]; then
                echo \"[DRY RUN] gcloud run jobs execute ${JOB} --region ${REGION} --wait --update-env-vars=VGNC_MODE=species,VGNC_SPECIES=\${taxon_id},${COMMON_ENV}\"
            else
                gcloud run jobs execute ${JOB} \
                    --region ${REGION} \
                    --wait \
                    --update-env-vars=\"VGNC_MODE=species,VGNC_SPECIES=\${taxon_id},${COMMON_ENV}\"
            fi
            echo \"[INFO] Completed species \${taxon_id}\"
        }
        run_all_species_inner {}
    "

    echo "[INFO] All per-species jobs completed."
fi

echo
echo "[INFO] All done."
