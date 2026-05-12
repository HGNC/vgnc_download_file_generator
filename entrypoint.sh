#!/bin/bash
set -euo pipefail

CLI_CMD="uv run python -m vgnc_download_file_generator"

MODE="${VGNC_MODE:-species}"
SPECIES="${VGNC_SPECIES:-9913}"
FORMATS="${VGNC_FORMATS:-tsv,json}"

if [[ "${MODE}" == "all" ]]; then
    echo "[INFO] Generating cross-species combined files (mode=all)"
    ${CLI_CMD} --species "All" --formats "${FORMATS}"
    ${CLI_CMD} --species "All" --file-type "vgnc_ensembl" --formats "${FORMATS}"
    ${CLI_CMD} --species "All" --file-type "vgnc_withdrawn" --formats "${FORMATS}"
elif [[ "${MODE}" == "species" ]]; then
    echo "[INFO] Generating all files for species ${SPECIES} (mode=species)"
    exec ./generate_all_parallel.sh --species "${SPECIES}" --formats "${FORMATS}" --continue
else
    echo "[ERROR] Unknown VGNC_MODE: ${MODE}" >&2
    exit 1
fi
