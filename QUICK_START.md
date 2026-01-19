# Quick Start Guide

Get up and running with the VGNC Download File Generator in 5 minutes.

## Prerequisites

Before you begin, ensure you have:

- **Python 3.13+** installed
- **MySQL database** access with VGNC data
- **Google Cloud account** with:
  - A GCS bucket created
  - Service account key or Application Default Credentials configured

## 1. Install the Application

**Option A: Quick setup with the setup script (recommended)**

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

**Option B: Manual setup**

```bash
# Install dependencies (recommended: uv)
uv sync

# Or with pip
pip install -e .

# Install GNU parallel manually (optional, for parallel batch generation)
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

After installation, you have three ways to run the CLI:

```bash
# Option 1: Direct command (recommended)
vgnc-download-file-generator --species 9913 --chromosome X --formats tsv,json

# Option 2: Shorter alias
vgnc-generator --species 9913 --chromosome X --formats tsv,json

# Option 3: Python module (if entry points not in PATH)
uv run python -m vgnc_download_file_generator --species 9913 --chromosome X --formats tsv,json
```

### Generate Files for a Single Species

```bash
# Generate TSV and JSON files for cow (taxon_id: 9913), chromosome X
vgnc-download-file-generator --species 9913 --chromosome X --formats tsv,json
```

### Generate All Species Files

```bash
# Generate files for all species (with taxon_id column)
vgnc-download-file-generator --species All --formats tsv,json
```

### Generate Ensembl Mapping

```bash
# Generate VGNC to Ensembl gene ID mapping
vgnc-download-file-generator --species All --file-type vgnc_ensembl
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

## Common Use Cases

### Dry Run - Preview What Will Be Generated

```bash
# See what files would be created (no database/GCS needed)
vgnc-download-file-generator --species 9913 --chromosome X --dry-run
```

### Generate Chromosome-Specific Files

```bash
# Cow chromosome 1
vgnc-download-file-generator --species 9913 --chromosome 1 --formats tsv,json

# Zebrafish chromosome 5
vgnc-download-file-generator --species 7955 --chromosome 5 --formats tsv,json
```

### Generate Locus Type Files

```bash
# Protein-coding genes for cow
vgnc-download-file-generator --species 9913 --locus-type "gene with protein product" --formats tsv,json
```

### Generate Withdrawn Entries

```bash
# All withdrawn entries
vgnc-download-file-generator --species All --file-type vgnc_withdrawn --formats tsv
```

## Batch Generation (Parallel Script)

For generating multiple files efficiently, use the parallel batch script included with the project.

### Understanding What Gets Generated

The parallel script generates ALL files by default:

**Default behavior (no arguments):**
- "All" species TSV and JSON files (all species combined)
- Ensembl mapping file (unless `--skip-ensembl`)
- Withdrawn entries file (unless `--skip-withdrawn`)
- **Per-species chromosome files** for all species (auto-discovered from database)
- **Per-species locus type files** for all species (protein-coding, pseudogene)

**With `--species`:**
- Same as above, but only for the specified species

**With `--chromosomes`:**
- Restricts chromosome files to the specified chromosomes only

### Install GNU Parallel

The parallel script requires GNU parallel:

```bash
# macOS
brew install parallel

# Ubuntu/Debian
sudo apt-get install parallel

# CentOS/RHEL
sudo yum install parallel
```

### Generate Multiple Files in Parallel

```bash
# Generate ALL files for all species (auto-discovers from database)
./generate_all_parallel.sh

# Generate files for specific species only
./generate_all_parallel.sh --species "9913,9606,9598"

# Control job count manually
./generate_all_parallel.sh --jobs 4

# Restrict to specific chromosomes (auto-discovers from DB if not specified)
./generate_all_parallel.sh --chromosomes "1,2,X,Y"

# Preview what would be generated
./generate_all_parallel.sh --dry-run
```

### Parallel Script Features

- **Auto-detection**: Automatically detects CPU cores and calculates optimal job count (cores - 2)
- **Format splitting**: Creates separate jobs for TSV and JSON for better parallelization
- **Retries**: 3 automatic retries on transient failures
- **Progress tracking**: Real-time progress bar
- **Job logging**: Creates timestamped job log files for tracking
- **Continue on error**: Optional mode to continue processing after failures

### Parallel Script Options

| Option          | Description                              | Default                     |
| --------------- | ---------------------------------------- | --------------------------- |
| `--species`     | Comma-separated species taxon IDs        | Auto-discover from database |
| `--chromosomes` | Comma-separated chromosome list          | Auto-discover from database |
| `--formats`     | Output formats                           | `tsv,json`                  |
| `--jobs`        | Number of parallel jobs                  | Auto-detect (CPU cores - 2) |
| `--timeout`     | Job timeout in seconds                   | `3600` (1 hour)            |
| `--continue`    | Continue after retries exhausted         | Stop on failure            |
| `--skip-withdrawn` | Skip withdrawn entries generation   | Generate withdrawn          |
| `--skip-ensembl`   | Skip Ensembl mapping generation      | Generate Ensembl            |
| `--dry-run`     | Show what would be generated             | Execute jobs                |

### Recommended Settings

For your target environments:

| Environment       | CPUs  | Suggested Jobs | Command                          |
| ----------------- | ----- | -------------- | -------------------------------- |
| MacBook M4 Pro    | ~12   | 10             | `./generate_all_parallel.sh --species "9913,9606"` |
| GCP 8 vCPU        | 8     | 6              | `./generate_all_parallel.sh --species "9913,9606" --jobs 6` |

## Command Line Options

| Option          | Description                  | Example                                        |
| --------------- | ---------------------------- | ---------------------------------------------- |
| `--species`     | Species taxon ID or "All"    | `--species 9913`                               |
| `--chromosome`  | Chromosome identifier        | `--chromosome X`                               |
| `--locus-type`  | Locus type filter            | `--locus-type "gene with protein product"`       |
| `--locus-group` | Locus group filter           | `--locus-group "protein-coding gene"`            |
| `--file-type`   | File generator type          | `--file-type vgnc_ensembl`                     |
| `--formats`     | Output formats (comma-separated) | `--formats tsv,json`                        |
| `--compress`    | Enable gzip compression      | `--compress`                                   |

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
