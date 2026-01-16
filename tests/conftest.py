"""Pytest configuration and fixtures for test suite."""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv
from google.cloud import storage

from vgnc_download_file_generator.config import AppConfig, DatabaseConfig, GCSConfig, RuntimeConfig
from vgnc_download_file_generator.database.connection import DatabaseConnection
from vgnc_download_file_generator.utils.secret_manager import get_db_credentials

# Load environment variables from .env file
# This is required for integration and e2e tests
load_dotenv()


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
        # Skip integration tests unless --integration flag is set
        if "integration" in item.keywords and not run_integration:
            item.add_marker(skip_integration)

        # Skip e2e tests unless --e2e flag is set
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
        runtime=RuntimeConfig(
            chunk_size=100,
            max_workers=2,
        ),
    )


@pytest.fixture
def mock_db() -> DatabaseConnection:
    """Provide a mock DatabaseConnection for unit tests."""
    mock_conn = MagicMock(spec=DatabaseConnection)
    return mock_conn


# ============================================================================
# INTEGRATION TEST FIXTURES (require real services)
# ============================================================================

@pytest.fixture(scope="session")
def real_config() -> AppConfig:
    """Load real configuration from environment for integration tests.

    This fixture requires:
    - GOOGLE_APPLICATION_CREDENTIALS pointing to service account key
    - GOOGLE_SECRET_MANAGER_SECRET_NAME set to access database credentials
    - APP_GCS_BUCKET_NAME and APP_GCS_PROJECT_ID configured
    """
    from pydantic import ValidationError

    # Load from environment variables
    try:
        config = AppConfig()
    except ValidationError as e:
        # If database config is missing, try loading from Secret Manager
        if "database" in str(e):
            # Create partial config with defaults
            try:
                config = AppConfig(
                    database=DatabaseConfig(
                        dbhost="placeholder",
                        dbuser="placeholder",
                        dbpasswd="placeholder",
                        dbport=3306,
                        dbname="placeholder",
                    ),
                    gcs=GCSConfig(
                        bucket_name=os.environ.get("APP_GCS_BUCKET_NAME", ""),
                        project_id=os.environ.get("APP_GCS_PROJECT_ID", ""),
                    ),
                    runtime=RuntimeConfig(
                        chunk_size=int(os.environ.get("APP_RUNTIME_CHUNK_SIZE", 5000)),
                        max_workers=int(os.environ.get("APP_RUNTIME_MAX_WORKERS", 4)),
                    ),
                )
            except ValidationError:
                pytest.skip(f"Cannot create config: {e}")
        else:
            pytest.skip(f"Cannot create config: {e}")

    # Validate required configuration
    if not config.gcs.bucket_name:
        pytest.skip("APP_GCS_BUCKET_NAME not set")

    if not config.gcs.project_id:
        pytest.skip("APP_GCS_PROJECT_ID not set")

    # Try to load database credentials from Secret Manager
    secret_name = os.environ.get("GOOGLE_SECRET_MANAGER_SECRET_NAME")
    if not secret_name:
        pytest.skip("GOOGLE_SECRET_MANAGER_SECRET_NAME not set")

    try:
        # Fetch database credentials from Secret Manager
        db_config = get_db_credentials(secret_name, project_id=config.gcs.project_id)
        config.database = db_config
    except Exception as e:
        pytest.skip(f"Failed to load database credentials from Secret Manager: {e}")

    return config


@pytest.fixture(scope="session")
def real_database(real_config: AppConfig) -> DatabaseConnection:
    """Provide a real database connection for integration tests.

    This fixture connects to the actual test database.
    Tests using this fixture will be marked as integration tests.
    """
    db = DatabaseConnection(real_config.database)

    # Verify connection works
    try:
        conn = db.get_connection()
        conn.close()
    except Exception as e:
        pytest.skip(f"Failed to connect to database: {e}")

    return db


@pytest.fixture(scope="session")
def real_gcs_client(real_config: AppConfig) -> storage.Client:
    """Provide a real GCS client for integration tests.

    This fixture connects to the actual test GCS bucket.
    Tests using this fixture will be marked as integration tests.
    """
    try:
        client = storage.Client(project=real_config.gcs.project_id)

        # Verify bucket exists and is accessible
        bucket = client.bucket(real_config.gcs.bucket_name)
        if not bucket.exists():
            pytest.skip(f"GCS bucket {real_config.gcs.bucket_name} does not exist")

        return client
    except Exception as e:
        pytest.skip(f"Failed to connect to GCS: {e}")


@pytest.fixture(scope="session")
def test_gcs_bucket(real_gcs_client: storage.Client, real_config: AppConfig) -> storage.Bucket:
    """Provide the test GCS bucket for integration tests.

    This bucket is used to test actual file uploads and downloads.
    All test files should be prefixed with 'test/' for easy cleanup.
    """
    bucket = real_gcs_client.bucket(real_config.gcs.bucket_name)
    return bucket


@pytest.fixture(scope="session")
def gcs_config_only() -> AppConfig:
    """Provide minimal config with only GCS settings (no database).

    This fixture is for GCS tests that don't need database access.
    """
    try:
        config = AppConfig(
            database=DatabaseConfig(
                dbhost="placeholder",
                dbuser="placeholder",
                dbpasswd="placeholder",
                dbport=3306,
                dbname="placeholder",
            ),
            gcs=GCSConfig(
                bucket_name=os.environ.get("APP_GCS_BUCKET_NAME", ""),
                project_id=os.environ.get("APP_GCS_PROJECT_ID", ""),
            ),
            runtime=RuntimeConfig(
                chunk_size=int(os.environ.get("APP_RUNTIME_CHUNK_SIZE", 5000)),
                max_workers=int(os.environ.get("APP_RUNTIME_MAX_WORKERS", 4)),
            ),
        )
    except Exception as e:
        pytest.skip(f"Cannot create GCS config: {e}")

    if not config.gcs.bucket_name:
        pytest.skip("APP_GCS_BUCKET_NAME not set")

    if not config.gcs.project_id:
        pytest.skip("APP_GCS_PROJECT_ID not set")

    return config


@pytest.fixture(scope="session")
def gcs_client_only(gcs_config_only: AppConfig) -> storage.Client:
    """Provide a GCS client without requiring database credentials.

    This fixture is for GCS tests that don't need database access.
    """
    try:
        client = storage.Client(project=gcs_config_only.gcs.project_id)

        # Verify bucket exists and is accessible
        bucket = client.bucket(gcs_config_only.gcs.bucket_name)
        if not bucket.exists():
            pytest.skip(f"GCS bucket {gcs_config_only.gcs.bucket_name} does not exist")

        return client
    except Exception as e:
        pytest.skip(f"Failed to connect to GCS: {e}")


@pytest.fixture(scope="session")
def test_gcs_bucket_only(gcs_client_only: storage.Client, gcs_config_only: AppConfig) -> storage.Bucket:
    """Provide the test GCS bucket for GCS-only tests.

    This bucket is used to test actual file uploads and downloads.
    All test files should be prefixed with 'test/' for easy cleanup.
    This fixture doesn't require database credentials.
    """
    bucket = gcs_client_only.bucket(gcs_config_only.gcs.bucket_name)
    return bucket


@pytest.fixture(autouse=True)
def cleanup_test_files() -> None:
    """Automatically clean up test files from GCS after each test.

    This fixture looks for any files/blobs prefixed with 'test/' in the
    test GCS bucket and deletes them after the test runs.
    """
    yield

    # Cleanup happens after test
    try:
        from vgnc_download_file_generator.config import AppConfig
        config = AppConfig()

        if not config.gcs.bucket_name or not config.gcs.project_id:
            return

        client = storage.Client(project=config.gcs.project_id)
        bucket = client.bucket(config.gcs.bucket_name)

        # List and delete test files
        for blob in bucket.list_blobs(prefix="test/"):
            blob.delete()
    except Exception:
        # Don't fail tests if cleanup fails
        pass
