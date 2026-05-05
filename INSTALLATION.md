# Installation Guide

## System requirements

| Software | Version |
|---|---|
| Python | 3.13+ |
| MySQL | 5.7+ (8.0+ recommended) |
| uv | Latest |

## Install

```bash
git clone <repository-url>
cd vgnc_download_file_generator
uv sync
```

## Docker

```bash
docker build -t vgnc-download-files .
docker run --rm \
  -e DB_HOST=... \
  -e DB_USER=... \
  -e DB_PASSWORD=... \
  -e DB_PORT=3306 \
  -e DB_NAME=vgnc_public_2025_01_01 \
  -e GCS_BUCKET=your-bucket \
  -e GCS_PROJECT_ID=your-project-id \
  vgnc-download-files
```

The Docker image uses `python:3.13-slim` and installs `uv` for dependency
management. The entrypoint runs `generate_all.sh` which generates files for
the species specified in `VGNC_SPECIES` (default: `9913`) and formats in
`VGNC_FORMATS` (default: `tsv,json`).

## Configuration

All configuration is via environment variables. No `.env` files or Secret
Manager client library — Cloud Run mounts secrets as environment variables
at runtime and uses Application Default Credentials for GCS access.

| Variable | Description | Default |
|---|---|---|
| `DB_HOST` | MySQL hostname | — |
| `DB_PORT` | MySQL port | `3306` |
| `DB_NAME` | Database name | — |
| `DB_USER` | MySQL user | — |
| `DB_PASSWORD` | MySQL password | — |
| `GCS_BUCKET` | GCS bucket name | — |
| `GCS_PROJECT_ID` | GCP project ID | — |
| `GCS_PREFIX` | Path prefix for GCS objects | `vgnc/` |
| `VGNC_SPECIES` | Comma-separated species taxon IDs | `9913` |
| `VGNC_FORMATS` | Output formats | `tsv,json` |

## Development

```bash
# Run tests
uv run pytest

# Type checking
uv run mypy src/

# Linting
uv run ruff check src/
```

## Troubleshooting

### Database connection

```bash
mysql -h $DB_HOST -u $DB_USER -p -P $DB_PORT $DB_NAME
```

### GCS authentication

Cloud Run uses ADC automatically. Locally:

```bash
gcloud auth application-default login
```
