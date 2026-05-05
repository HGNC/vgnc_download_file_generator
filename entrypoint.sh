#!/bin/bash
set -euo pipefail

export APP_DATABASE__DBHOST="${DB_HOST:-${APP_DATABASE__DBHOST:-}}"
export APP_DATABASE__DBPORT="${DB_PORT:-${APP_DATABASE__DBPORT:-3306}}"
export APP_DATABASE__DBNAME="${DB_NAME:-${APP_DATABASE__DBNAME:-}}"
export APP_DATABASE__DBUSER="${DB_USER:-${APP_DATABASE__DBUSER:-}}"
export APP_DATABASE__DBPASS="${DB_PASSWORD:-${APP_DATABASE__DBPASS:-}}"
export APP_GCS__BUCKET_NAME="${GCS_BUCKET:-${APP_GCS__BUCKET_NAME:-}}"
export APP_GCS__PROJECT_ID="${GCS_PROJECT_ID:-${APP_GCS__PROJECT_ID:-}}"
export APP_GCS__PATH_PREFIX="${GCS_PREFIX:-${APP_GCS__PATH_PREFIX:-vgnc/}}"

CLI_CMD="uv run python -m vgnc_download_file_generator"

SPECIES="${VGNC_SPECIES:-9913}"
FORMATS="${VGNC_FORMATS:-tsv,json}"

exec ./generate_all.sh --species "${SPECIES}" --formats "${FORMATS}" --continue
