#!/bin/bash
# VGNC Download File Generator - Setup Script
#
# This script sets up the development environment by:
# 1. Running uv sync to install Python dependencies
# 2. Checking for and optionally installing GNU parallel
#
# Usage:
#   ./setup.sh [--skip-parallel]
#
# Options:
#   --skip-parallel    Skip GNU parallel installation check
#   --help            Show this help message

set -euo pipefail

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================
# Helper Functions
# ============================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

show_help() {
    grep '^#' "$0" | sed 's/^#//' | sed 's/^ //' | sed '/^#!/d'
    exit 0
}

install_gnu_parallel() {
    echo ""
    log_warning "GNU parallel is not installed"
    echo ""
    echo "GNU parallel is required for: ./generate_all_parallel.sh"
    echo "It allows efficient parallel file generation."
    echo ""

    # Detect OS
    local os_type
    os_type="$(uname)"

    if [[ "$os_type" == "Darwin" ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            echo "Installing GNU parallel via Homebrew..."
            if brew install parallel; then
                log_success "GNU parallel installed via Homebrew"
            else
                log_error "Failed to install GNU parallel"
                log_error "Please install manually: brew install parallel"
                exit 1
            fi
        else
            log_error "Homebrew not found. Please install Homebrew first:"
            echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            echo ""
            echo "Then run this script again."
            exit 1
        fi

    elif [[ "$os_type" == "Linux" ]]; then
        # Linux - detect package manager
        if command -v apt-get &> /dev/null; then
            echo "Installing GNU parallel via apt..."
            if sudo apt-get update && sudo apt-get install -y parallel; then
                log_success "GNU parallel installed via apt"
            else
                log_error "Failed to install GNU parallel"
                log_error "Please install manually: sudo apt-get install parallel"
                exit 1
            fi

        elif command -v yum &> /dev/null; then
            echo "Installing GNU parallel via yum..."
            if sudo yum install -y parallel; then
                log_success "GNU parallel installed via yum"
            else
                log_error "Failed to install GNU parallel"
                log_error "Please install manually: sudo yum install parallel"
                exit 1
            fi

        elif command -v dnf &> /dev/null; then
            echo "Installing GNU parallel via dnf..."
            if sudo dnf install -y parallel; then
                log_success "GNU parallel installed via dnf"
            else
                log_error "Failed to install GNU parallel"
                log_error "Please install manually: sudo dnf install parallel"
                exit 1
            fi

        else
            log_warning "Unable to detect package manager"
            log_error "Please install GNU parallel manually:"
            echo "  Ubuntu/Debian: sudo apt-get install parallel"
            echo "  CentOS/RHEL:   sudo yum install parallel"
            echo "  Fedora:        sudo dnf install parallel"
            echo ""
            echo "Or download from: https://ftpmirror.gnu.org/parallel/"
            exit 1
        fi

    else
        log_error "Unsupported OS: $os_type"
        log_error "Please install GNU parallel manually"
        echo "  Download from: https://ftpmirror.gnu.org/parallel/"
        exit 1
    fi
}

# ============================================
# Parse Arguments
# ============================================

SKIP_PARALLEL=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-parallel)
            SKIP_PARALLEL=true
            shift
            ;;
        --help)
            show_help
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# ============================================
# Main Setup Process
# ============================================

echo ""
echo "=========================================="
echo "VGNC Download File Generator - Setup"
echo "=========================================="
echo ""

# ============================================
# Step 1: Check for uv
# ============================================

log_info "Checking for uv..."

if ! command -v uv &> /dev/null; then
    log_error "uv is not installed."
    echo ""
    echo "To install uv:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo ""
    exit 1
fi

log_success "uv is installed"

# ============================================
# Step 2: Install Python Dependencies
# ============================================

log_info "Installing Python dependencies with uv sync --all-extras..."

if uv sync --all-extras; then
    log_success "Python dependencies installed (including dev tools)"
else
    log_error "Failed to install Python dependencies"
    exit 1
fi

# ============================================
# Step 3: Check for GNU Parallel
# ============================================

if [[ "${SKIP_PARALLEL}" == true ]]; then
    log_info "Skipping GNU parallel check (--skip-parallel specified)"
else
    echo ""
    log_info "Checking for GNU parallel..."

    if command -v parallel &> /dev/null; then
        # Check if it's actually GNU parallel (not the moreutils parallel)
        if parallel --version 2>&1 | grep -q "GNU parallel"; then
            log_success "GNU parallel is already installed"
            parallel --version | head -n 1
        else
            log_warning "Found 'parallel' but it's not GNU parallel"
            log_warning "You may have the 'moreutils' parallel installed instead"
            log_warning "The generate_all_parallel.sh script requires GNU parallel"
            echo ""
            install_gnu_parallel
        fi
    else
        install_gnu_parallel
    fi
fi

# ============================================
# Step 4: Setup Complete
# ============================================

echo ""
echo "=========================================="
log_success "Setup complete!"
echo "=========================================="
echo ""

log_info "You can now:"
echo "  • Run tests:              uv run pytest"
echo "  • Generate files:         uv run python -m vgnc_download_file_generator --species 9913 --chromosome X"
echo "  • Parallel batch gen:     ./generate_all_parallel.sh --species \"9913,9606\""
echo "  • Dry run preview:        ./generate_all_parallel.sh --species 9913 --dry-run"
echo ""
