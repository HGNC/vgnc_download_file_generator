# VGNC Download File Generator

Python tool for generating VGNC download files (TSV and JSON) and uploading
them to Google Cloud Storage. Runs as a Cloud Run Job, orchestrated by
Airflow.

## Features

- Multiple file generators: VGNC Public, Ensembl mapping, Withdrawn entries
- Per-species all-genes, locus type, and locus group files
- Dual output formats: TSV and JSON
- Streaming architecture with server-side cursors for memory efficiency
- Direct streaming uploads to GCS
- Empty file detection to prevent blank uploads
- Retry logic with exponential backoff
- Runtime ID-format validation (pydantic): aborts on malformed or swapped
  cross-reference IDs (e.g. NCBI/Ensembl) before any data is written to GCS
- Partial-file cleanup: deletes incomplete GCS objects when a generation fails

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
| `VGNC_MODE` | Operating mode (`all`, `all-species`, or `species`) | `species` |
| `VGNC_SPECIES` | Species taxon ID (used only when `VGNC_MODE=species`) | `9913` |
| `VGNC_FORMATS` | Output formats | `tsv,json` |
| `VGNC_VALIDATION_MODE` | ID-format validation: `strict` (abort on bad IDs) or `warn` (log only) | `strict` |
| `VGNC_VALIDATION_GRACE` | Max tolerated ID violations per field before aborting (strict mode) | `50` |

## Local development

```bash
uv sync
uv run pytest
```

## Usage

### CLI

```bash
# Generate files for a specific species
uv run python -m vgnc_download_file_generator --species 9913 --formats tsv,json

# Generate all species files
uv run python -m vgnc_download_file_generator --species All --formats tsv,json

# Dry run
uv run python -m vgnc_download_file_generator --species 9913 --dry-run
```

### Docker (Cloud Run)

The container entrypoint (`entrypoint.sh`) dispatches on `VGNC_MODE`:

> Chromosome-split publication policy: the automated entrypoint no longer
> schedules chromosome-split files. Publication includes species-level
> all-genes and locus-filtered files only.

- **`all` mode** — generates cross-species combined files (public, Ensembl,
  withdrawn) and cross-species per-locus-type and per-locus-group files.
- **`all-species` mode** — generates all cross-species files (same as `all`),
  then discovers all species from the database and generates per-species
  files. Used by the `scripts/run_all_species.sh` helper.
- **`species` mode** — generates per-species all-genes, per-locus-type,
  and per-locus-group files (no chromosome-split files) using GNU parallel
  for concurrent CLI invocations.

The image is based on `python:3.13-slim` with `default-mysql-client`,
`default-libmysqlclient-dev`, `build-essential`, `pkg-config`, and
`parallel` (GNU parallel for concurrent file generation).
The Dockerfile copies `pyproject.toml`, `uv.lock`, and `README.md` before
running `uv sync --frozen --no-dev` for reproducible production builds. It
also copies `db_query_helper.py` and `entrypoint.sh`:

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
├── validation.py          # Runtime ID-format validation (pydantic)
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
│   ├── all/
│   │   ├── all_vgnc_gene_set_All.json
│   │   ├── all_vgnc_withdrawn.json
│   │   ├── locus_types/
│   │   │   └── all_{locus_type}_All.json
│   │   └── locus_groups/
│   │       └── all_{locus_group}_All.json
│   └── {species}/
│       ├── {species}_vgnc_gene_set_All.json
│       ├── locus_types/
│       │   └── {species}_{locus_type}_All.json
│       └── locus_groups/
│           └── {species}_{locus_group}_All.json
├── tsv/
│   ├── all/
│   │   ├── all_vgnc_gene_set_All.tsv
│   │   ├── all_vgnc_withdrawn.tsv
│   │   ├── locus_types/
│   │   │   └── all_{locus_type}_All.tsv
│   │   └── locus_groups/
│   │       └── all_{locus_group}_All.tsv
│   └── {species}/
│       ├── {species}_vgnc_gene_set_All.tsv
│       ├── locus_types/
│       │   └── {species}_{locus_type}_All.tsv
│       └── locus_groups/
│           └── {species}_{locus_group}_All.tsv
└── ensembl/
    └── VGNC_to_Ensembl_mapping.txt
```

## Error handling

- 3 retries with exponential backoff (1s, 2s, 4s)
- Transient errors: `ServiceUnavailable`, `DeadlineExceeded`
- Structured logging with retry attempt details
- Runtime ID-format validation aborts the run on a systematic violation
  (e.g. a swapped cross-reference column) before data reaches GCS; see
  `VGNC_VALIDATION_MODE` / `VGNC_VALIDATION_GRACE`
- Failed writes delete any partial GCS object so incomplete files don't linger

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

### macOS mysqlclient fix

If `mysqlclient` fails to find `libmysqlclient` on macOS:

```bash
python scripts/fix_mysqlclient.py
```

## License

MIT — see [LICENSE](LICENSE).
