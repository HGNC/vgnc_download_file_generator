# Quick Start Guide

Get up and running with the VGNC Download File Generator in 5 minutes.

## Prerequisites

Before you begin, ensure you have:

- **Python 3.13+** installed
- **MySQL database** access with VGNC data
- **Google Cloud account** with:
  - A GCS bucket created
  - Service account key or Application Default Credentials configured
- **GNU parallel** (for batch generation)

## 1. Install the Application

### Option A: Quick setup with the setup script (recommended)

```bash
# Clone the repository
git clone <repository-url>
cd vgnc_download_file_generator

# Run the setup script
./setup.sh
```

The setup script will:

- Install Python dependencies via `uv sync`
- Check for and optionally install GNU parallel

### Option B: Manual setup

```bash
# Install dependencies (recommended: uv)
uv sync

# Or with pip
pip install -e .

# Install GNU parallel manually
brew install parallel  # macOS
sudo apt-get install parallel  # Ubuntu/Debian
```

## 2. Configure Environment

Create a `.env` file in the project root:

```bash
# Database Configuration
APP_DATABASE_DBHOST=localhost
APP_DATABASE_DBUSER=your_username
APP_DATABASE_DBPASSWD=your_password
APP_DATABASE_DBPORT=3306
APP_DATABASE_DBNAME=vgnc

# Google Cloud Storage
APP_GCS_BUCKET_NAME=your-gcs-bucket
APP_GCS_PROJECT_ID=your-project-id

# Optional: Runtime Configuration
APP_RUNTIME_CHUNK_SIZE=5000
APP_RUNTIME_MAX_WORKERS=4
```

### Alternative: Use GCP Secret Manager

If using Secret Manager for database credentials:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

The application will automatically fetch credentials from the secret named `vgnc-db-credentials`.

## 3. Run Your First Generation

The **recommended way** to generate files is using the parallel batch script, which efficiently generates all files in parallel.

### Generate All Files (Default)

```bash
# Generate ALL files for all species (auto-discovers from database)
./generate_all_parallel.sh
```

This generates:

- **"All" species files**: Combined TSV and JSON with all species
- **Ensembl mapping file**: VGNC to Ensembl gene ID mapping
- **Withdrawn entries file**: All withdrawn entries
- **Per-species chromosome files**: For each species (auto-discovered)
- **Per-species locus type files**: Protein-coding and pseudogene files
- **Per-species locus group files**: Protein-coding gene and pseudogene files

### Generate for Specific Species

```bash
# Generate files for specific species only
./generate_all_parallel.sh --species "9913,9606,9598"
```

### Preview Before Generating

```bash
# See what would be generated (no files created)
./generate_all_parallel.sh --dry-run
```

## 4. Verify Output

Check your GCS bucket:

```bash
# List JSON files in the bucket
gsutil ls gs://your-gcs-bucket/json/

# List TSV files in the bucket
gsutil ls gs://your-gcs-bucket/tsv/

# Download a sample file
gsutil cp gs://your-gcs-bucket/json/cattle/cattle_vgnc_gene_set_chr_X.json ./
```

## Parallel Script Options

| Option | Description | Default |
| :--- | :--- | :--- |
| `--species` | Comma-separated species taxon IDs | Auto-discover from database |
| `--chromosomes` | Comma-separated chromosome list | Auto-discover from database |
| `--formats` | Output formats | `tsv,json` |
| `--jobs` | Number of parallel jobs | Auto-detect (CPU cores - 2) |
| `--timeout` | Job timeout in seconds | `3600` (1 hour) |
| `--continue` | Continue after retries exhausted | Stop on failure |
| `--skip-withdrawn` | Skip withdrawn entries generation | Generate withdrawn |
| `--skip-ensembl` | Skip Ensembl mapping generation | Generate Ensembl |
| `--dry-run` | Show what would be generated | Execute jobs |

### Parallel Script Features

- **Auto-detection**: Automatically detects CPU cores and calculates optimal job count
- **Format splitting**: Creates separate jobs for TSV and JSON for better parallelization
- **Retries**: 3 automatic retries on transient failures
- **Progress tracking**: Real-time progress bar
- **Job logging**: Creates timestamped job log files for tracking

### Recent Improvements

- **Empty file detection**: Automatically skips files with no data before GCS upload
- **"Un" chromosome handling**: Captures genes on:
  - Scaffolds and contigs (non-chromosome coord_systems like `NW_*`, `PJAA_*`)
  - Chromosomes with display names starting with "Un" (e.g., Un0001, Un_1)
  - Genes without any location data (NULL chromosome)
- **Locus group support**: Generates files for both locus types and locus groups
- **Data integrity**: Cross-species chromosome contamination prevention via taxon_id filtering
- **Split query architecture**: 2300x performance improvement over monolithic queries

### Recommended Settings

| Environment | CPUs | Suggested Jobs | Command |
| :--- | :--- | :--- | :--- |
| MacBook M4 Pro | ~12 | 10 | `./generate_all_parallel.sh --species "9913,9606"` |
| GCP 8 vCPU | 8 | 6 | `./generate_all_parallel.sh --species "9913,9606" --jobs 6` |

## Single File Generation (CLI)

For generating individual files, use the CLI directly:

```bash
# Option 1: Direct command
vgnc-download-file-generator --species 9913 --chromosome X --formats tsv,json

# Option 2: Shorter alias
vgnc-generator --species 9913 --chromosome X --formats tsv,json

# Option 3: Python module (if entry points not in PATH)
uv run python -m vgnc_download_file_generator --species 9913 --chromosome X --formats tsv,json
```

### CLI Options

| Option | Description | Example |
| :--- | :--- | :--- |
| `--species` | Species taxon ID or "All" | `--species 9913` |
| `--chromosome` | Chromosome identifier ("Un" for scaffolds/unlocated) | `--chromosome X` |
| `--locus-type` | Locus type filter | `--locus-type "gene with protein product"` |
| `--locus-group` | Locus group filter | `--locus-group "protein-coding gene"` |
| `--file-type` | File generator type | `--file-type vgnc_ensembl` |
| `--formats` | Output formats (comma-separated) | `--formats tsv,json` |
| `--compress` | Enable gzip compression | `--compress` |
| `--dry-run` | Show what would be generated | `--dry-run` |

## Common Use Cases

### Generate "Un" Chromosome (Scaffolds and Unlocated Genes)

```bash
# Generate file for scaffolds, contigs, and genes without location
vgnc-download-file-generator --species 9796 --chromosome Un --formats tsv,json
```

The "Un" chromosome file includes:
- Genes on scaffolds/contigs (coord_system != 'chromosome')
- Genes on chromosomes with display_name starting with "Un"
- Genes without any location data

### Generate Specific Chromosomes

```bash
# Restrict to specific chromosomes
./generate_all_parallel.sh --chromosomes "1,2,X,Y"
```

### Generate Ensembl Mapping Only

```bash
# Skip default files, only generate Ensembl mapping
./generate_all_parallel.sh --skip-withdrawn --species "All" --file-type vgnc_ensembl
```

### Generate Locus Type Files

```bash
# Protein-coding genes for specific species
vgnc-download-file-generator --species 9913 --locus-type "gene with protein product" --formats tsv,json
```

### Generate Locus Group Files

```bash
# Protein-coding genes for specific species
vgnc-download-file-generator --species 9913 --locus-group "protein-coding gene" --formats tsv,json
```

### Generate Withdrawn Entries

```bash
# All withdrawn entries
vgnc-download-file-generator --species All --file-type vgnc_withdrawn --formats tsv
```

## Python API Quick Start

```python
from vgnc_download_file_generator import (
    AppConfig,
    DatabaseConnection,
    GCSStreamWriter,
    VgncPublic,
)

# Load configuration
config = AppConfig()

# Initialize components
db = DatabaseConnection(config.database)
gcs = GCSStreamWriter(
    config.gcs.bucket_name,
    config.gcs.project_id
)

# Create generator for cow, chromosome X
from vgnc_download_file_generator.models.species import SpeciesInfo

species = SpeciesInfo(taxon_id=9913, display_name="cow", is_live="Y")
generator = VgncPublic(db, species, chromosome="X")

# Stream directly to GCS
tsv_path = generator.generate_filename("txt")
with gcs.open_write_stream(tsv_path, "text/tab-separated-values") as f:
    for line in generator.generate_tsv_rows():
        f.write(line)

print(f"Generated: {tsv_path}")
```

## Troubleshooting

### Database Connection Failed

```bash
# Verify credentials
mysql -h localhost -u your_username -p vgnc

# Check .env file syntax
cat .env
```

### GCS Authentication Error

```bash
# Verify credentials are set
echo $GOOGLE_APPLICATION_CREDENTIALS

# Test GCS access
gsutil ls gs://your-gcs-bucket
```

### Import Errors

```bash
# Reinstall dependencies
uv sync

# Verify Python version
python --version  # Should be 3.13+
```

## Next Steps

- Read [INSTALLATION.md](INSTALLATION.md) for detailed setup options
- Read [README.md](README.md) for full API documentation
- Check test coverage: `uv run pytest --cov`

## Support

For issues or questions:

- Open an issue on GitHub
- Check existing documentation
- Review test files for usage examples
