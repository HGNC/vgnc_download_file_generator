# Installation Guide

Detailed installation instructions for the VGNC Download File Generator.

## Table of Contents

- [System Requirements](#system-requirements)
- [Installation Methods](#installation-methods)
- [Database Setup](#database-setup)
- [Google Cloud Setup](#google-cloud-setup)
- [Configuration](#configuration)
- [Verification](#verification)
- [Development Setup](#development-setup)
- [Troubleshooting](#troubleshooting)

## System Requirements

### Required Software

| Software | Minimum Version | Recommended |
|----------|-----------------|-------------|
| Python | 3.13 | 3.13+ |
| MySQL | 5.7+ | 8.0+ |
| uv (optional) | Latest | Latest |

### Operating Systems

- Linux (Ubuntu 20.04+, Debian 11+)
- macOS (11+)
- Windows (WSL2 recommended)

### Hardware Requirements

- **Minimum**: 2 CPU cores, 4GB RAM
- **Recommended**: 4 CPU cores, 8GB RAM
- **Disk**: 500MB for installation + space for temporary files

## Installation Methods

### Method 1: Using uv (Recommended)

`uv` is a fast Python package installer and resolver.

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone <repository-url>
cd vgnc_download_file_generator

# Install dependencies
uv sync

# Activate the virtual environment
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows
```

### Method 2: Using pip

```bash
# Clone the repository
git clone <repository-url>
cd vgnc_download_file_generator

# Create virtual environment
python3.13 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows

# Install in editable mode
pip install -e .

# Install development dependencies
pip install -e ".[dev]"
```

### Method 3: Using Docker

```bash
# Build the image
docker build -t vgnc-generator .

# Run with environment file
docker run --env-file .env vgnc-generator
```

## Database Setup

### 1. MySQL Database

Ensure you have a MySQL database with VGNC data:

```sql
-- Create database (if not exists)
CREATE DATABASE IF NOT EXISTS vgnc;

-- Grant permissions
GRANT SELECT, EXECUTE ON vgnc.* TO 'username'@'host';
FLUSH PRIVILEGES;
```

### 2. Verify Tables

```sql
-- Check required tables exist
SHOW TABLES;

-- Expected output should include:
-- species, genefam, gene_status, locus_type, locus_group,
-- chromosome, gene_location
```

### 3. Test Connection

```bash
mysql -h localhost -u username -p vgnc -e "SELECT COUNT(*) FROM species;"
```

## Google Cloud Setup

### 1. Create GCS Bucket

```bash
# Create bucket
gsutil mb -p your-project-id gs://your-bucket-name

# Set permissions (optional)
gsutil iam ch serviceAccount:your-service-account@project.iam.gserviceaccount.com:roles/storage.objectAdmin \
  gs://your-bucket-name
```

### 2. Authentication

#### Option A: Service Account Key

```bash
# Download service account key from GCP Console
# Set environment variable
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"

# Add to .bashrc or .zshrc for persistence
echo 'export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"' >> ~/.bashrc
```

#### Option B: Application Default Credentials (ADC)

```bash
# Install gcloud CLI
curl https://sdk.cloud.google.com | bash

# Authenticate
gcloud auth application-default login
```

### 3. Verify GCS Access

```bash
# List bucket contents
gsutil ls gs://your-bucket-name

# Test upload
echo "test" > test.txt
gsutil cp test.txt gs://your-bucket-name/test.txt
gsutil rm gs://your-bucket-name/test.txt
```

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# ============================================
# Database Configuration
# ============================================
APP_DATABASE__DBHOST=localhost
APP_DATABASE__DBUSER=your_username
APP_DATABASE__DBPASS=your_password
APP_DATABASE__DBPORT=3306
APP_DATABASE__DBNAME=vgnc

# ============================================
# Google Cloud Storage
# ============================================
APP_GCS__BUCKET_NAME=your-gcs-bucket
APP_GCS__PROJECT_ID=your-project-id

# ============================================
# Runtime Configuration (Optional)
# ============================================
# Chunk size for database streaming (default: 5000)
APP_RUNTIME__CHUNK_SIZE=5000

# Maximum parallel workers (default: 4)
APP_RUNTIME__MAX_WORKERS=4
```

### Using GCP Secret Manager (Optional)

Instead of storing database credentials in `.env`, use Secret Manager:

```bash
# Create secret
gcloud secrets create vgnc-db-credentials \
  --data-file=db_credentials.json

# Grant access to service account
gcloud secrets add-iam-policy-binding vgnc-db-credentials \
  --member="serviceAccount:your-service-account@project.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

Format of `db_credentials.json`:

```json
{
  "dbhost": "localhost",
  "dbuser": "username",
  "dbpasswd": "password",
  "dbport": 3306,
  "dbname": "vgnc"
}
```

## Verification

### 1. Verify Installation

```bash
# Check Python version
python --version
# Expected: Python 3.13.x

# Check package installation
pip show vgnc-download-file-generator

# Run tests
uv run pytest -v
# Expected: All tests pass
```

### 2. Verify Configuration

```bash
# Test database connection
python -c "
from vgnc_download_file_generator import DatabaseConnection, AppConfig
config = AppConfig()
db = DatabaseConnection(config.database)
conn = db.get_connection()
print('Database connection successful!')
conn.close()
"

# Test GCS connection
python -c "
from vgnc_download_file_generator import GCSStreamWriter, AppConfig
config = AppConfig()
writer = GCSStreamWriter(config.gcs.bucket_name, config.gcs.project_id)
print('GCS connection successful!')
print(f'Bucket: {writer.bucket_name}')
"
```

### 3. Test Run

```bash
# Generate a small test file
uv run python -m vgnc_download_file_generator \
  --species 9913 \
  --chromosome X \
  --formats tsv

# Verify output in GCS
gsutil ls gs://your-bucket-name/json/cow/
```

## Development Setup

For contributing to the project:

```bash
# Clone repository
git clone <repository-url>
cd vgnc_download_file_generator

# Install with development dependencies
uv sync --all-extras

# Install pre-commit hooks (optional)
uv run pre-commit install

# Run type checking
uv run mypy src/

# Run linting
uv run ruff check src/

# Run tests with coverage
uv run pytest --cov=src/vgnc_download_file_generator --cov-report=html
```

### Development Tools

- **mypy**: Static type checker
- **ruff**: Fast Python linter and formatter
- **pytest**: Testing framework
- **pytest-cov**: Coverage plugin

## Troubleshooting

### Python Version Issues

```bash
# Check Python version
python --version

# Install Python 3.13+ using pyenv
brew install pyenv  # macOS
# or
sudo apt install pyenv  # Ubuntu

pyenv install 3.13
pyenv global 3.13
```

### MySQL Client Installation

```bash
# macOS
brew install mysql-client

# Ubuntu/Debian
sudo apt install libmysqlclient-dev

# Then install mysqlclient
pip install mysqlclient
```

### Import Errors

```bash
# Reinstall all dependencies
uv sync --reinstall

# Clear Python cache
find . -type d -name __pycache__ -exec rm -rf {} +
```

### GCS Authentication Issues

```bash
# Verify ADC is configured
gcloud auth application-default print-access-token

# Re-authenticate if needed
gcloud auth application-default login

# Verify service account key
echo $GOOGLE_APPLICATION_CREDENTIALS
ls -la $GOOGLE_APPLICATION_CREDENTIALS
```

### Database Connection Issues

```bash
# Test MySQL connection
mysql -h localhost -u username -p -P 3306 vgnc

# Check firewall rules
sudo ufw status  # Ubuntu

# Check MySQL is running
sudo systemctl status mysql  # Linux
brew services list  # macOS
```

### Permission Errors

```bash
# Make scripts executable
chmod +x scripts/*.sh

# Fix directory permissions
chmod -R 755 src/
```

## Next Steps

- Follow the [Quick Start Guide](QUICK_START.md) for your first generation
- Read the [README.md](README.md) for full documentation
- Review test files for usage examples

## Additional Resources

- [Python Packaging Guide](https://packaging.python.org/)
- [GCS Python Documentation](https://cloud.google.com/python/docs/reference/storage/latest)
- [MySQL Python Connector](https://dev.mysql.com/doc/connector-python/en/)
- [uv Documentation](https://github.com/astral-sh/uv)
