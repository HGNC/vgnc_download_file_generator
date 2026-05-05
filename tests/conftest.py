"""Pytest configuration and fixtures for test suite."""

import os
from unittest.mock import MagicMock

import pytest
from google.cloud import storage

from vgnc_download_file_generator.config import AppConfig, DatabaseConfig, GCSConfig
from vgnc_download_file_generator.database.connection import DatabaseConnection


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command line options to pytest."""
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests (requires real database and GCS)",
    )
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="Run end-to-end tests (requires full environment setup)",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests (no external dependencies)")
    config.addinivalue_line("markers", "integration: Integration tests (database, GCS)")
    config.addinivalue_line("markers", "e2e: End-to-end tests (full workflow)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Modify test collection to skip integration/e2e tests by default."""
    run_integration = config.getoption("--integration")
    run_e2e = config.getoption("--e2e")

    skip_integration = pytest.mark.skip(reason="Integration tests require --integration flag")
    skip_e2e = pytest.mark.skip(reason="E2E tests require --e2e flag")

    for item in items:
        if "integration" in item.keywords and not run_integration:
            item.add_marker(skip_integration)

        if "e2e" in item.keywords and not run_e2e:
            item.add_marker(skip_e2e)


@pytest.fixture
def mock_config() -> AppConfig:
    """Provide a mock AppConfig for unit tests."""
    return AppConfig(
        database=DatabaseConfig(
            dbhost="localhost",
            dbuser="test_user",
            dbpasswd="test_pass",
            dbport=3306,
            dbname="test_db",
        ),
        gcs=GCSConfig(
            bucket_name="test-bucket",
            project_id="test-project",
        ),
    )


@pytest.fixture
def mock_db() -> DatabaseConnection:
    """Provide a mock DatabaseConnection for unit tests."""
    mock_conn = MagicMock(spec=DatabaseConnection)
    return mock_conn


@pytest.fixture(scope="session")
def real_config() -> AppConfig:
    """Load real configuration from environment for integration tests."""
    return AppConfig(
        database=DatabaseConfig(
            dbhost=os.environ.get("DB_HOST", ""),
            dbuser=os.environ.get("DB_USER", ""),
            dbpasswd=os.environ.get("DB_PASSWORD", ""),
            dbport=int(os.environ.get("DB_PORT", "3306")),
            dbname=os.environ.get("DB_NAME", ""),
        ),
        gcs=GCSConfig(
            bucket_name=os.environ.get("GCS_BUCKET", ""),
            project_id=os.environ.get("GCS_PROJECT_ID", ""),
            path_prefix=os.environ.get("GCS_PREFIX", "vgnc/"),
        ),
    )


@pytest.fixture(scope="session")
def real_database(real_config: AppConfig) -> DatabaseConnection:
    """Provide a real database connection for integration tests."""
    db = DatabaseConnection(real_config.database)

    try:
        conn = db.get_connection()
        conn.close()
    except Exception as e:
        pytest.skip(f"Failed to connect to database: {e}")

    return db


@pytest.fixture(scope="session")
def real_gcs_client(real_config: AppConfig) -> storage.Client:
    """Provide a real GCS client for integration tests."""
    try:
        client = storage.Client(project=real_config.gcs.project_id)

        bucket = client.bucket(real_config.gcs.bucket_name)
        if not bucket.exists():
            pytest.skip(f"GCS bucket {real_config.gcs.bucket_name} does not exist")

        return client
    except Exception as e:
        pytest.skip(f"Failed to connect to GCS: {e}")


@pytest.fixture(scope="session")
def test_gcs_bucket(real_gcs_client: storage.Client, real_config: AppConfig) -> storage.Bucket:
    """Provide the test GCS bucket for integration tests."""
    bucket = real_gcs_client.bucket(real_config.gcs.bucket_name)
    return bucket
