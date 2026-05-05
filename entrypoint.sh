#!/bin/bash
set -euo pipefail

CLI_CMD="uv run python -m vgnc_download_file_generator"

SPECIES="${VGNC_SPECIES:-9913}"
FORMATS="${VGNC_FORMATS:-tsv,json}"

exec ./generate_all.sh --species "${SPECIES}" --formats "${FORMATS}" --continue
