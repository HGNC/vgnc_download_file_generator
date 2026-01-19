# VGNC Download File Generator

A Python tool for generating VGNC (Vertebrate Gene Nomenclature Consortium) download files and uploading them to Google Cloud Storage.

[![Tests](https://img.shields.io/badge/tests-216%20passing-brightgreen)](tests/)
[![Coverage](https://img.shields.io/badge/coverage-94%25-brightgreen)](#test-coverage)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

## Quick Links

- **[Quick Start Guide](QUICK_START.md)** - Get up and running in 5 minutes
- **[Installation Guide](INSTALLATION.md)** - Detailed setup instructions
- **Features** - See what's included below

## Features

- **Multiple File Generators**: Support for VGNC Public, Ensembl mapping, and Withdrawn entries
- **Dual Output Formats**: TSV (tab-separated values) and JSON
- **Streaming Architecture**: Memory-efficient processing for large datasets
- **GCS Integration**: Direct streaming uploads to Google Cloud Storage
- **Retry Logic**: Exponential backoff for transient failures
- **Compression**: Optional gzip compression for large files
- **Database Integration**: MySQL with SQLAlchemy ORM and server-side cursors

## Requirements

- Python 3.13+
- MySQL database connection
- Google Cloud project with GCS bucket
- GCP credentials (ADC or service account)

## Installation

For detailed installation instructions, see the [Installation Guide](INSTALLATION.md).

**Quick install:**

```bash
# Clone and install with uv (recommended)
git clone <repository-url>
cd vgnc_download_file_generator
uv sync

# Or with pip
pip install -e .
```

**Requirements:**
- Python 3.13+
- MySQL database with VGNC data
- Google Cloud account with GCS bucket

## Configuration

Configuration is managed via environment variables or `.env` file:

```bash
# Database
APP_DATABASE__DBHOST=localhost
APP_DATABASE__DBUSER=username
APP_DATABASE__DBPASS=password
APP_DATABASE__DBPORT=3306
APP_DATABASE__DBNAME=vgnc

# GCS
APP_GCS__BUCKET_NAME=your-bucket
APP_GCS__PROJECT_ID=your-project-id

# Runtime (optional)
APP_RUNTIME__CHUNK_SIZE=5000
APP_RUNTIME__MAX_WORKERS=4
```

Alternatively, use GCP Secret Manager to retrieve database credentials:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

## Usage

For more usage examples and common use cases, see the [Quick Start Guide](QUICK_START.md).

### Command Line

After installation, two CLI commands are available:

```bash
# Use the shorter command (recommended)
vgnc-download-file-generator --species 9913 --chromosome X --formats tsv,json

# Or use the shorter alias
vgnc-generator --species 9913 --chromosome X --formats tsv,json

# Or use python module syntax
uv run python -m vgnc_download_file_generator --species 9913 --chromosome X --formats tsv,json
```

**Examples:**

```bash
# Generate files for a specific species (cow = 9913)
vgnc-download-file-generator --species 9913 --chromosome X --formats tsv,json

# Generate all species files
vgnc-download-file-generator --species All --formats tsv,json

# Generate Ensembl mapping
vgnc-download-file-generator --species All --file-type vgnc_ensembl

# Generate locus type files
vgnc-download-file-generator --species 9913 --locus-type "gene with protein product" --formats tsv

# Dry run to see what would be generated
vgnc-download-file-generator --species 9913 --chromosome X --dry-run
```

### Python API

```python
from vgnc_download_file_generator import (
    AppConfig,
    DatabaseConnection,
    GCSStreamWriter,
    SpeciesInfo,
    VgncPublic,
)

# Load configuration
config = AppConfig()

# Initialize database and GCS writer
db = DatabaseConnection(config.database)
gcs = GCSStreamWriter(config.gcs.bucket_name, config.gcs.project_id)

# Create species info
species = SpeciesInfo(taxon_id=9593, display_name="cow", is_live="Y")

# Generate files
generator = VgncPublic(db, species, chromosome="X")

# Stream to GCS (TSV)
with gcs.open_write_stream(generator.generate_filename("txt"), "text/tab-separated-values") as f:
    for line in generator.generate_tsv_rows():
        f.write(line)

# Or upload compressed file
generator.generate_tsv_file("/tmp/output.txt")
gcs.upload_from_file("/tmp/output.txt", "cow_chrX.txt", compress=True)
```

## Project Structure

```
src/vgnc_download_file_generator/
├── config.py              # Pydantic configuration models
├── generator.py           # Base file generator class
├── database/
│   ├── connection.py      # MySQL connection with pooling
│   ├── queries.py         # SQL query builders
│   └── schema.py          # SQLAlchemy ORM models
├── generators/
│   ├── vgnc_public.py     # VGNC public files
│   ├── vgnc_ensembl.py    # Ensembl mapping files
│   └── vgnc_withdrawn.py  # Withdrawn entries files
├── models/
│   ├── file_spec.py       # File specification models
│   └── species.py         # Species information model
├── utils/
│   ├── secret_manager.py  # GCP Secret Manager integration
│   └── streaming.py       # Streaming utilities
└── writers/
    └── gcs_writer.py      # GCS streaming writer with retry logic
```

## Development

### Running Tests

The project has three types of tests:

1. **Unit Tests**: Fast tests with mocked dependencies (216 tests)
2. **Integration Tests**: Tests against real database and GCS (28 tests)
3. **E2E Tests**: Full CLI workflow tests (16 tests)

```bash
# Run unit tests only (default - fast, no external dependencies)
uv run pytest -m "not integration and not e2e"

# Run integration tests (requires real database and GCS)
uv run pytest --integration

# Run E2E tests (requires full environment)
uv run pytest --e2e

# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/vgnc_download_file_generator --cov-report=html

# Run specific test file
uv run pytest tests/test_gcs_writer.py -v
```

**Note**: Integration and E2E tests require:
- `GOOGLE_APPLICATION_CREDENTIALS` pointing to a service account key
- Database credentials via environment variables or GCP Secret Manager
- Access to the test GCS bucket

### Code Quality

```bash
# Type checking
uv run mypy src/

# Linting
uv run ruff check src/

# Format code
uv run ruff format src/
```

### Test Coverage

Current coverage: **94%** (260 total tests: 216 unit + 28 integration + 16 E2E)

## File Formats

### VGNC Public Files
- **TSV**: Tab-separated values with standard headers
- **JSON**: Array of objects with lowercase_underscore keys
- **Special cases**:
  - `All` species: Adds `taxon_id` and `primary_db_id` columns
  - Cattle/Bos taurus (taxon 9913): Adds `bgd_id` column

### Ensembl Mapping
- Single file mapping VGNC IDs to Ensembl gene IDs
- Filter: Status = 'Approved'
- Location: `ensembl/VGNC_to_Ensembl_mapping.txt`

### Withdrawn Entries
- Filter: Status IN ['Entry Withdrawn', 'Symbol Withdrawn']
- Includes `MERGED_INTO_REPORT(S)` field

## GCS Output Structure

```
bucket/
├── json/
│   ├── {species}/
│   │   ├── {species}_vgnc_gene_set_chr_{chromosome}.json
│   │   └── locus_types/
│   │       └── {species}_{locus_type}_All.json
├── tsv/
│   ├── {species}/
│   │   ├── {species}_vgnc_gene_set_chr_{chromosome}.txt
│   │   └── locus_types/
│   │       └── {species}_{locus_type}_All.txt
├── ensembl/
│   └── VGNC_to_Ensembl_mapping.txt
└── withdrawn/
    └── {species}/
        └── {species}_withdrawn.txt
```

## Error Handling

- **Retry Logic**: 3 retries with exponential backoff (1s, 2s, 4s)
- **Transient Errors**: `ServiceUnavailable`, `DeadlineExceeded`
- **Logging**: Structured logging with retry attempt details

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
