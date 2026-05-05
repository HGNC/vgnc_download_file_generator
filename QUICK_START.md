# Quick Start Guide

Get up and running with the VGNC Download File Generator locally.

## Prerequisites

- Python 3.13+
- MySQL database with VGNC data
- GCS bucket and GCP credentials (ADC)

## Install

```bash
git clone <repository-url>
cd vgnc_download_file_generator
uv sync
```

## Configure

Set environment variables:

```bash
export DB_HOST=localhost
export DB_USER=username
export DB_PASSWORD=password
export DB_PORT=3306
export DB_NAME=vgnc_public_2025_01_01
export GCS_BUCKET=your-bucket
export GCS_PROJECT_ID=your-project-id
```

Secrets are injected as environment variables by Cloud Run at runtime.
Locally, export them in your shell or use `direnv`.

## Generate files

```bash
# Single species, single chromosome
uv run python -m vgnc_download_file_generator --species 9913 --chromosome X --formats tsv,json

# All species
uv run python -m vgnc_download_file_generator --species All --formats tsv,json

# Ensembl mapping only
uv run python -m vgnc_download_file_generator --species All --file-type vgnc_ensembl

# Dry run (no uploads)
uv run python -m vgnc_download_file_generator --species 9913 --dry-run
```

## Verify output

```bash
gsutil ls gs://${GCS_BUCKET}/vgnc/json/cattle/
gsutil ls gs://${GCS_BUCKET}/vgnc/tsv/cattle/
```

## Run tests

```bash
uv run pytest
```
