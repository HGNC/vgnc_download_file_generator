#!/bin/bash
# Wrapper script for executing CLI jobs from generate_all_parallel.sh
# This script is called by GNU parallel with job arguments

# Directory containing this script (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Always run from the script directory so the Python CLI's .env loader
# (which searches cwd and parents) reliably finds the project's .env file
# regardless of where GNU parallel invokes us from.
cd "${SCRIPT_DIR}"

# Set DYLD_LIBRARY_PATH for MySQL client library on macOS
if [[ "$(uname)" == "Darwin" ]]; then
    # Try common MySQL installation paths (version-agnostic check)
    for mysql_lib_path in \
        "/opt/homebrew/opt/mysql-client/lib" \
        "/usr/local/mysql/lib" \
        "/usr/local/mysql-8.0.42-macos15-arm64/lib"
    do
        if [[ -d "${mysql_lib_path}" ]] && compgen -G "${mysql_lib_path}/libmysqlclient"*.dylib > /dev/null; then
            export DYLD_LIBRARY_PATH="${mysql_lib_path}${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
            break
        fi
    done
fi

# ============================================
# GCP Proxy Configuration
# ============================================
# Google Cloud Storage client respects these standard proxy environment variables.
# Set them in your .env file or environment to route GCS traffic through a proxy.
#
# Common proxy formats:
#   http://proxy.example.com:8080
#   http://username:password@proxy.example.com:8080
#   socks5://proxy.example.com:1080
#
# Set in .env or export before running:
#   export HTTP_PROXY=http://proxy.example.com:8080
#   export HTTPS_PROXY=http://proxy.example.com:8080
#   export NO_PROXY=localhost,127.0.0.1,.internal.com

if [[ -n "${HTTP_PROXY:-}" ]]; then
    export HTTP_PROXY
fi
if [[ -n "${HTTPS_PROXY:-}" ]]; then
    export HTTPS_PROXY
fi
if [[ -n "${http_proxy:-}" ]]; then
    export http_proxy
fi
if [[ -n "${https_proxy:-}" ]]; then
    export https_proxy
fi
if [[ -n "${NO_PROXY:-}" ]]; then
    export NO_PROXY
fi
if [[ -n "${no_proxy:-}" ]]; then
    export no_proxy
fi

# Get CLI command from environment or use default
if [[ -n "${VGNC_CLI:-}" ]]; then
    CLI_CMD="${VGNC_CLI}"
elif command -v vgnc-download-file-generator &> /dev/null; then
    CLI_CMD="vgnc-download-file-generator"
else
    CLI_CMD="uv run python -m vgnc_download_file_generator"
fi

# Execute the CLI with the job arguments
# Arguments are passed as a single string that needs to be evaluated
eval "exec ${CLI_CMD} $*"
