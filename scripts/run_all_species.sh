#!/bin/bash
set -euo pipefail

PROJECT_ID="prj-ext-prod-hgnc-cloud-ls"
DEFAULT_DB_USER="prod-user-app"

usage() {
    cat <<'HELP'
Usage: run_all_species.sh [OPTIONS]

Execute the vgnc-download-files Cloud Run job in all-species mode, which
generates cross-species combined files and then discovers all species from
the database and generates per-species files -- all in a single execution.

Options:
  --db-name NAME     Database name (required, e.g. vgnc_public_2026_05_14)
  --db-user USER     MySQL username (default: prod-user-app)
  --project PROJECT  GCP project ID (default: prj-ext-prod-hgnc-cloud-ls)
  --region REGION    Cloud Run region (default: europe-west2)
  --job JOB          Cloud Run job name (default: vgnc-download-files)
  --dry-run          Print command without executing
  -h, --help         Show this help

Examples:

  # Full run
  run_all_species.sh --db-name vgnc_public_2026_05_14

  # Dry run
  run_all_species.sh --dry-run --db-name vgnc_public_2026_05_14
HELP
}

DB_NAME=""
DB_USER="${DEFAULT_DB_USER}"
REGION="europe-west2"
JOB="vgnc-download-files"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db-name)  DB_NAME="$2"; shift 2 ;;
        --db-user)  DB_USER="$2"; shift 2 ;;
        --project)  PROJECT_ID="$2"; shift 2 ;;
        --region)   REGION="$2"; shift 2 ;;
        --job)      JOB="$2"; shift 2 ;;
        --dry-run)  DRY_RUN=true; shift ;;
        -h|--help)  usage; exit 0 ;;
        *)          echo "Unknown option: $1" >&2; usage; exit 1 ;;
    esac
done

if [[ -z "${DB_NAME}" ]]; then
    echo "Error: --db-name is required." >&2
    echo >&2
    usage
    exit 1
fi

ENV_VARS="VGNC_MODE=all-species,DB_NAME=${DB_NAME},DB_USER=${DB_USER}"

if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY RUN] gcloud run jobs execute ${JOB} --region ${REGION} --wait --update-env-vars=${ENV_VARS}"
else
    gcloud run jobs execute "${JOB}" \
        --region "${REGION}" \
        --wait \
        --update-env-vars="${ENV_VARS}"
fi
