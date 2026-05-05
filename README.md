# VGNC Download File Generator

Python tool for generating VGNC download files (TSV and JSON) and uploading
them to Google Cloud Storage. Runs as a Cloud Run Job, orchestrated by
Airflow.

## Features

- Multiple file generators: VGNC Public, Ensembl mapping, Withdrawn entries
- Per-species chromosome, locus type, and locus group files
- "Un" chromosome handling for scaffolds, contigs, and unlocated genes
- Dual output formats: TSV and JSON
- Streaming architecture with server-side cursors for memory efficiency
- Direct streaming uploads to GCS
- Empty file detection to prevent blank uploads
- Retry logic with exponential backoff

## Requirements

- Python 3.13+
- MySQL database connection
- Google Cloud project with GCS bucket
- GCP credentials (ADC)

## Environment variables

All configuration is provided via environment variables injected by Cloud Run:

| Variable | Description | Default |
|---|---|---|
| `DB_HOST` | MySQL hostname | — |
| `DB_PORT` | MySQL port | `3306` |
| `DB_NAME` | Database name | — |
| `DB_USER` | MySQL user | — |
| `DB_PASSWORD` | MySQL password (from Secret Manager) | — |
| `GCS_BUCKET` | GCS bucket name | — |
| `GCS_PROJECT_ID` | GCP project ID | — |
| `GCS_PREFIX` | Path prefix for GCS objects | `vgnc/` |
| `VGNC_SPECIES` | Species taxon IDs (comma-separated) | `9913` |
| `VGNC_FORMATS` | Output formats | `tsv,json` |

## Local development

```bash
uv sync
uv run pytest
```

## Usage

### CLI

```bash
# Generate files for a specific species
uv run python -m vgnc_download_file_generator --species 9913 --chromosome X --formats tsv,json

# Generate all species files
uv run python -m vgnc_download_file_generator --species All --formats tsv,json

# Dry run
uv run python -m vgnc_download_file_generator --species 9913 --chromosome X --dry-run
```

### Docker (Cloud Run)

The container entrypoint runs `generate_all.sh` with species and format from
environment variables:

```bash
docker build -t vgnc-download-files .
docker run --rm \
  -e DB_HOST=... -e DB_PASSWORD=... -e GCS_BUCKET=... \
  vgnc-download-files
```

## Project structure

```text
src/vgnc_download_file_generator/
├── __main__.py            # CLI entry point
├── config.py              # Pydantic configuration (env vars)
├── generator.py           # Base file generator class
├── database/
│   ├── connection.py      # MySQL connection
│   ├── queries.py         # SQL query utilities
│   └── queries_split.py   # Split query architecture
├── generators/
│   ├── vgnc_public.py     # VGNC public files
│   ├── vgnc_ensembl.py    # Ensembl mapping files
│   └── vgnc_withdrawn.py  # Withdrawn entries files
├── models/
│   ├── file_spec.py       # File specification models
│   └── species.py         # Species information model
├── utils/
│   └── streaming.py       # Streaming utilities
└── writers/
    └── gcs_writer.py      # GCS streaming writer with retry logic
```

## GCS output structure

```text
{GCS_PREFIX}/
├── json/
│   └── {species}/
│       ├── {species}_vgnc_gene_set_chr_{chromosome}.json
│       ├── locus_types/
│       └── locus_groups/
├── tsv/
│   └── {species}/
│       ├── {species}_vgnc_gene_set_chr_{chromosome}.txt
│       ├── locus_types/
│       └── locus_groups/
├── ensembl/
│   └── VGNC_to_Ensembl_mapping.txt
└── withdrawn/
    └── {species}/
        └── {species}_withdrawn.txt
```

## Error handling

- 3 retries with exponential backoff (1s, 2s, 4s)
- Transient errors: `ServiceUnavailable`, `DeadlineExceeded`
- Structured logging with retry attempt details

## License

MIT — see [LICENSE](LICENSE).
