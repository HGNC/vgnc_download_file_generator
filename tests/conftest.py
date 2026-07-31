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


@pytest.fixture
def paginating_db():
    """Return a factory ``(all_ids, batch_size) -> MagicMock DatabaseConnection``.

    The fake cursor dispatches on the *compiled* SQL text: the
    ``DISTINCT gf.genefam_id ... LIMIT`` page query advances a sequential
    slice of ``all_ids`` (``batch_size`` per page); the gene-data query
    (recognised by ``gf.assigned_symbol``) returns rows for the current page;
    the xrefs/aliases/dates sub-queries return empty. A new mock connection is
    handed out per ``get_connection()`` call (recorded on ``db._conns``) so the
    per-batch connection lifecycle can be asserted. Executed SQL strings are
    recorded on ``db._cursor.executed``.

    Use it to drive a generator's ``stream_rows()`` without a real DB while
    still exercising the keyset pagination, the no-streaming-cursor invariant,
    and the per-batch connection checkout/release.
    """

    def _factory(all_ids: list[int], batch_size: int):
        class FakeCursor:
            def __init__(self) -> None:
                self.page_calls = 0
                self.last_page: list[int] = []
                self._rows: list[tuple] = []
                self.description: list = []
                self.executed: list[str] = []

            def execute(self, sql: str, _params: object = None) -> None:
                self.executed.append(sql or "")
                sql = sql or ""
                if "gf.assigned_symbol" in sql:
                    self.description = [("genefam_id",), ("assigned_id",)]
                    self._rows = [(i, f"VGNC:{i}") for i in self.last_page]
                elif "SELECT DISTINCT gf.genefam_id" in sql and "LIMIT" in sql:
                    start = self.page_calls * batch_size
                    self.last_page = list(all_ids[start:start + batch_size])
                    self.page_calls += 1
                    self.description = [("genefam_id",)]
                    self._rows = [(i,) for i in self.last_page]
                else:
                    self.description = [("genefam_id",)]
                    self._rows = []

            def fetchall(self) -> list[tuple]:
                return list(self._rows)

            def __iter__(self):
                return iter(self._rows)

            def close(self) -> None:
                pass

        db = MagicMock(spec=DatabaseConnection)
        shared_cursor = FakeCursor()
        conns: list = []

        def make_conn() -> object:
            conn = MagicMock()
            conn.cursor.return_value = shared_cursor
            conns.append(conn)
            return conn

        db.get_connection.side_effect = make_conn
        # The legacy server-side-cursor path must NOT be used by any generator.
        db.get_streaming_cursor.side_effect = AssertionError(
            "get_streaming_cursor must not be used by stream_rows"
        )
        db._conns = conns  # type: ignore[attr-defined]
        db._cursor = shared_cursor  # type: ignore[attr-defined]
        return db

    return _factory
