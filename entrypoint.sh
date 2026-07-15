#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

CLI_CMD="uv run python -m vgnc_download_file_generator"
DB_HELPER="uv run python ${SCRIPT_DIR}/db_query_helper.py"

MODE="${VGNC_MODE:-species}"
SPECIES="${VGNC_SPECIES:-9913}"
FORMATS="${VGNC_FORMATS:-tsv,json}"

IFS=',' read -ra FORMAT_ARRAY <<< "${FORMATS}"

LOCUS_TYPES=("gene with protein product" "RNA, long non-coding" "RNA, small nucleolar" "RNA, Y" "pseudogene" "unknown")
LOCUS_GROUPS=("protein-coding gene" "non-coding RNA" "pseudogene" "other")

discover_chromosomes() {
    local species_id="$1"
    local chromosomes
    chromosomes=$(${DB_HELPER} chromosomes "${species_id}" 2>/dev/null) || chromosomes=""
    echo "${chromosomes}"
}

generate_species_files() {
    local species_id="$1"
    local chromosomes

    echo "[INFO] Generating files for species ${species_id}"

    chromosomes=$(discover_chromosomes "${species_id}")

    if [[ -z "${chromosomes}" ]]; then
        echo "[INFO] No chromosomes found for species ${species_id}"
    fi

    local job_file
    job_file=$(mktemp)
    trap "rm -f ${job_file}" EXIT
    local job_count=0

    # All-chromosomes combined files
    for format in "${FORMAT_ARRAY[@]}"; do
        format=$(echo "${format}" | xargs)
        echo "--species \"${species_id}\" --formats \"${format}\"" >> "${job_file}"
        job_count=$((job_count + 1))
    done

    # Per-chromosome files
    if [[ -n "${chromosomes}" ]]; then
        IFS=',' read -ra chr_array <<< "${chromosomes}"
        for chr in "${chr_array[@]}"; do
            chr=$(echo "${chr}" | xargs)
            for format in "${FORMAT_ARRAY[@]}"; do
                format=$(echo "${format}" | xargs)
                echo "--species \"${species_id}\" --chromosome \"${chr}\" --formats \"${format}\"" >> "${job_file}"
                job_count=$((job_count + 1))
            done
        done
    fi

    # Per-locus-type files
    for locus_type in "${LOCUS_TYPES[@]}"; do
        for format in "${FORMAT_ARRAY[@]}"; do
            format=$(echo "${format}" | xargs)
            echo "--species \"${species_id}\" --locus-type \"${locus_type}\" --formats \"${format}\"" >> "${job_file}"
            job_count=$((job_count + 1))
        done
    done

    # Per-locus-group files
    for locus_group in "${LOCUS_GROUPS[@]}"; do
        for format in "${FORMAT_ARRAY[@]}"; do
            format=$(echo "${format}" | xargs)
            echo "--species \"${species_id}\" --locus-group \"${locus_group}\" --formats \"${format}\"" >> "${job_file}"
            job_count=$((job_count + 1))
        done
    done

    # Per-locus-type + chromosome files
    if [[ -n "${chromosomes}" ]]; then
        IFS=',' read -ra chr_array <<< "${chromosomes}"
        for chr in "${chr_array[@]}"; do
            chr=$(echo "${chr}" | xargs)
            for locus_type in "${LOCUS_TYPES[@]}"; do
                for format in "${FORMAT_ARRAY[@]}"; do
                    format=$(echo "${format}" | xargs)
                    echo "--species \"${species_id}\" --locus-type \"${locus_type}\" --chromosome \"${chr}\" --formats \"${format}\"" >> "${job_file}"
                    job_count=$((job_count + 1))
                done
            done
        done
    fi

    # Per-locus-group + chromosome files
    if [[ -n "${chromosomes}" ]]; then
        IFS=',' read -ra chr_array <<< "${chromosomes}"
        for chr in "${chr_array[@]}"; do
            chr=$(echo "${chr}" | xargs)
            for locus_group in "${LOCUS_GROUPS[@]}"; do
                for format in "${FORMAT_ARRAY[@]}"; do
                    format=$(echo "${format}" | xargs)
                    echo "--species \"${species_id}\" --locus-group \"${locus_group}\" --chromosome \"${chr}\" --formats \"${format}\"" >> "${job_file}"
                    job_count=$((job_count + 1))
                done
            done
        done
    fi

    echo "[INFO] Total jobs for species ${species_id}: ${job_count}"

    run_job() {
        eval "${CLI_CMD} $1"
    }
    export -f run_job

    local cpu_jobs
    if [[ "$(uname)" == "Darwin" ]]; then
        cpu_jobs=$(sysctl -n hw.ncpu 2>/dev/null || echo 4)
    else
        cpu_jobs=$(nproc 2>/dev/null || echo 4)
    fi
    local parallel_jobs=$((cpu_jobs - 1))
    [[ ${parallel_jobs} -lt 1 ]] && parallel_jobs=1

    set +e
    parallel --verbose --jobs "${parallel_jobs}" --retries 3 --timeout 3600 --keep-order \
        "eval ${CLI_CMD} {1}" :::: "${job_file}"
    local exit_code=$?
    set -e

    rm -f "${job_file}"
    trap - EXIT

    if [[ ${exit_code} -ne 0 ]]; then
        echo "[WARNING] Some jobs failed for species ${species_id} (exit code ${exit_code})"
    fi

    echo "[INFO] Completed species ${species_id}"
    return 0
}

discover_all_species() {
    local species_csv
    species_csv=$(${DB_HELPER} species 2>/dev/null) || species_csv=""
    echo "${species_csv}"
}

generate_all_species_files() {
    echo "[INFO] Generating cross-species combined files"
    ${CLI_CMD} --species "All" --formats "${FORMATS}"
    ${CLI_CMD} --species "All" --file-type "vgnc_ensembl" --formats "${FORMATS}"
    ${CLI_CMD} --species "All" --file-type "vgnc_withdrawn" --formats "${FORMATS}"

    echo "[INFO] Generating cross-species per-locus-type files"
    for locus_type in "${LOCUS_TYPES[@]}"; do
        for format in "${FORMAT_ARRAY[@]}"; do
            format=$(echo "${format}" | xargs)
            ${CLI_CMD} --species "All" --locus-type "${locus_type}" --formats "${format}"
        done
    done

    echo "[INFO] Generating cross-species per-locus-group files"
    for locus_group in "${LOCUS_GROUPS[@]}"; do
        for format in "${FORMAT_ARRAY[@]}"; do
            format=$(echo "${format}" | xargs)
            ${CLI_CMD} --species "All" --locus-group "${locus_group}" --formats "${format}"
        done
    done
}

if [[ "${MODE}" == "all" ]]; then
    generate_all_species_files
elif [[ "${MODE}" == "all-species" ]]; then
    generate_all_species_files

    echo "[INFO] Discovering species from database..."
    SPECIES_CSV=$(discover_all_species)

    if [[ -z "${SPECIES_CSV}" ]]; then
        echo "[WARN] No species found in database." >&2
        exit 0
    fi

    IFS=',' read -ra ALL_SPECIES <<< "${SPECIES_CSV}"
    echo "[INFO] Found ${#ALL_SPECIES[@]} species: ${SPECIES_CSV}"

    for species_id in "${ALL_SPECIES[@]}"; do
        echo "[INFO] --- Species ${species_id} ---"
        generate_species_files "${species_id}"
    done

    echo "[INFO] All species completed."
elif [[ "${MODE}" == "species" ]]; then
    generate_species_files "${SPECIES}"
else
    echo "[ERROR] Unknown VGNC_MODE: ${MODE}" >&2
    exit 1
fi
