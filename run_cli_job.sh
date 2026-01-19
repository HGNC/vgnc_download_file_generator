#!/bin/bash
# Wrapper script for executing CLI jobs from generate_all_parallel.sh
# This script is called by GNU parallel with job arguments

# Set DYLD_LIBRARY_PATH for MySQL client library on macOS
if [[ "$(uname)" == "Darwin" ]]; then
    if [[ -f "/usr/local/mysql-8.0.42-macos15-arm64/lib/libmysqlclient.21.dylib" ]]; then
        export DYLD_LIBRARY_PATH="/usr/local/mysql-8.0.42-macos15-arm64/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
    elif [[ -f "/opt/homebrew/opt/mysql-client/lib/libmysqlclient.21.dylib" ]]; then
        export DYLD_LIBRARY_PATH="/opt/homebrew/opt/mysql-client/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
    elif [[ -f "/usr/local/mysql/lib/libmysqlclient.21.dylib" ]]; then
        export DYLD_LIBRARY_PATH="/usr/local/mysql/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
    fi
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
eval "${CLI_CMD} $*"
