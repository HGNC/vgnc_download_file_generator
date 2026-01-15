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

```bash
# Clone the repository
git clone <repository-url>
cd vgnc_download_file_generator

# Install dependencies (recommended: uv)
uv sync

# Or with pip
pip install -e .
```

## 2. Configure Environment

Create a `.env` file in the project root:

```bash
# Database Configuration
APP_DATABASE__DBHOST=localhost
APP_DATABASE__DBUSER=your_username
APP_DATABASE__DBPASS=your_password
APP_DATABASE__DBPORT=3306
APP_DATABASE__DBNAME=vgnc

# Google Cloud Storage
APP_GCS__BUCKET_NAME=your-gcs-bucket
APP_GCS__PROJECT_ID=your-project-id

# Optional: Runtime Configuration
APP_RUNTIME__CHUNK_SIZE=5000
APP_RUNTIME__MAX_WORKERS=4
```

### Alternative: Use GCP Secret Manager

If using Secret Manager for database credentials:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

The application will automatically fetch credentials from the secret named `vgnc-db-credentials`.

## 3. Run Your First Generation

### Generate Files for a Single Species

```bash
# Generate TSV and JSON files for cow (taxon_id: 9913), chromosome X
uv run python -m vgnc_download_file_generator \
  --species 9913 \
  --chromosome X \
  --formats tsv json
```

### Generate All Species Files

```bash
# Generate files for all species (with taxon_id column)
uv run python -m vgnc_download_file_generator \
  --species All \
  --formats tsv json
```

### Generate Ensembl Mapping

```bash
# Generate VGNC to Ensembl gene ID mapping
uv run python -m vgnc_download_file_generator \
  --species All \
  --file-type vgnc_ensembl
```

## 4. Verify Output

Check your GCS bucket:

```bash
# List files in the bucket
gsutil ls gs://your-gcs-bucket/json/

# Download a sample file
gsutil cp gs://your-gcs-bucket/json/cow/cow_vgnc_gene_set_chr_X.json ./
```

## Common Use Cases

### Generate Chromosome-Specific Files

```bash
# Cow chromosome 1
uv run python -m vgnc_download_file_generator \
  --species 9913 \
  --chromosome 1 \
  --formats tsv json

# Zebrafish chromosome 5
uv run python -m vgnc_download_file_generator \
  --species 7955 \
  --chromosome 5 \
  --formats tsv json
```

### Generate Locus Type Files

```bash
# Protein-coding genes for cow
uv run python -m vgnc_download_file_generator \
  --species cow \
  --locus-type gene_with_protein_product \
  --formats tsv json
```

### Generate Withdrawn Entries

```bash
# All withdrawn entries
uv run python -m vgnc_download_file_generator \
  --species All \
  --file-type vgnc_withdrawn \
  --formats tsv
```

## Command Line Options

| Option | Description | Example |
|--------|-------------|---------|
| `--species` | Species taxon ID or "All" | `--species 9913` |
| `--chromosome` | Chromosome identifier | `--chromosome X` |
| `--locus-type` | Locus type filter | `--locus-type gene_with_protein_product` |
| `--locus-group` | Locus group filter | `--locus-group protein-coding_gene` |
| `--file-type` | File generator type | `--file-type vgnc_ensembl` |
| `--formats` | Output formats | `--formats tsv json` |
| `--compress` | Enable gzip compression | `--compress` |

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
