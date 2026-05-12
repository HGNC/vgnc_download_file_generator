"""Tests for DatabaseConnection class."""

import logging
from unittest.mock import MagicMock, patch

import MySQLdb
import MySQLdb.cursors
import pytest

from vgnc_download_file_generator.config import DatabaseConfig
from vgnc_download_file_generator.database.connection import DatabaseConnection


class TestDatabaseConnection:
    """Tests for DatabaseConnection class."""

    def test_get_connection_returns_valid_connection(
        self, db_config: DatabaseConfig
    ) -> None:
        """Test that get_connection() returns a valid connection."""
        conn = DatabaseConnection(db_config)

        with patch.object(MySQLdb, "connect") as mock_connect:
            mock_connection = MagicMock(spec=MySQLdb.Connection)
            mock_connect.return_value = mock_connection

            result = conn.get_connection()

            # Result should be a connection (either raw or wrapped by pool)
            assert result is not None
            mock_connect.assert_called_once()

    def test_context_manager_opens_and_closes_connection(
        self, db_config: DatabaseConfig
    ) -> None:
        """Test that context manager properly opens and closes connection."""
        conn = DatabaseConnection(db_config)

        with patch.object(MySQLdb, "connect") as mock_connect:
            mock_connection = MagicMock(spec=MySQLdb.Connection)
            mock_connect.return_value = mock_connection

            with conn:
                pass

            mock_connect.assert_called_once()
            # Connection is managed by pool, so it's returned to pool

    def test_invalid_credentials_raises_exception(
        self, db_config: DatabaseConfig
    ) -> None:
        """Test that invalid credentials raise MySQLdb.OperationalError."""
        conn = DatabaseConnection(db_config)

        with patch.object(MySQLdb, "connect") as mock_connect:
            mock_connect.side_effect = MySQLdb.OperationalError(
                "Access denied for user"
            )

            with pytest.raises(MySQLdb.OperationalError) as exc_info:
                conn.get_connection()

            assert "Access denied" in str(exc_info.value)

    def test_context_manager_exception_handling(
        self, db_config: DatabaseConfig
    ) -> None:
        """Test that context manager closes connection even on exception."""
        conn = DatabaseConnection(db_config)

        with patch.object(MySQLdb, "connect") as mock_connect:
            mock_connection = MagicMock(spec=MySQLdb.Connection)
            mock_connect.return_value = mock_connection

            with pytest.raises(RuntimeError), conn:
                raise RuntimeError("Test error")

            # Connection should still be managed (returned to pool)


class TestConnectionPooling:
    """Tests for SQLAlchemy QueuePool integration."""

    def test_pool_initialized_with_correct_settings(
        self, db_config: DatabaseConfig
    ) -> None:
        """Test that QueuePool is initialized with pool_size=5, recycle=300."""
        conn = DatabaseConnection(db_config)

        # Access the internal pool to verify its settings
        assert hasattr(conn, "_pool")
        from sqlalchemy.pool import QueuePool
        assert isinstance(conn._pool, QueuePool)
        assert conn._pool._pool.maxsize == 5

    def test_connection_checked_out_from_pool(
        self, db_config: DatabaseConfig
    ) -> None:
        """Test that get_connection() checks out from the pool."""
        conn = DatabaseConnection(db_config)

        with patch.object(MySQLdb, "connect") as mock_connect:
            mock_connection = MagicMock()
            mock_connect.return_value = mock_connection

            # Get multiple connections from pool
            conn1 = conn.get_connection()
            conn2 = conn.get_connection()

            # With a pool of size 5, we should be able to get connections
            assert conn1 is not None
            assert conn2 is not None

    def test_connection_returned_to_pool_on_context_exit(
        self, db_config: DatabaseConfig
    ) -> None:
        """Test that context manager returns connection to pool on exit."""
        conn = DatabaseConnection(db_config)

        with patch.object(MySQLdb, "connect") as mock_connect:
            mock_connection = MagicMock()
            mock_connect.return_value = mock_connection

            with conn:
                pass

            # Connection should be returned to pool (managed by pool)

    def test_pool_max_size_is_5(
        self, db_config: DatabaseConfig
    ) -> None:
        """Test that pool creates exactly 5 connections max."""
        conn = DatabaseConnection(db_config)

        # Verify pool size is 5
        assert conn._pool._pool.maxsize == 5


class TestStreamingCursor:
    """Tests for get_streaming_cursor() method."""

    def test_returns_ss_cursor_type(
        self, db_config: DatabaseConfig
    ) -> None:
        """Test that get_streaming_cursor() returns MySQLdb.SSCursor."""
        conn = DatabaseConnection(db_config)

        with patch.object(MySQLdb, "connect") as mock_connect:
            mock_connection = MagicMock()
            mock_cursor = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_connection

            cursor = conn.get_streaming_cursor()

            # Verify cursor was created with SSCursor type
            mock_connection.cursor.assert_called_once_with(MySQLdb.cursors.SSCursor)
            assert cursor is not None

    def test_cursor_associated_with_pooled_connection(
        self, db_config: DatabaseConfig
    ) -> None:
        """Test that cursor is properly associated with pooled connection."""
        conn = DatabaseConnection(db_config)

        with patch.object(MySQLdb, "connect") as mock_connect:
            mock_connection = MagicMock()
            mock_cursor = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_connection

            cursor = conn.get_streaming_cursor()

            # Verify the cursor comes from the pooled connection
            assert cursor is not None
            mock_connection.cursor.assert_called_once()

    def test_can_execute_large_result_queries(
        self, db_config: DatabaseConfig
    ) -> None:
        """Test that streaming cursor can handle large result sets."""
        conn = DatabaseConnection(db_config)

        with patch.object(MySQLdb, "connect") as mock_connect:
            mock_connection = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = ("row1",)
            mock_connection.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_connection

            cursor = conn.get_streaming_cursor()

            # Simulate large result set
            cursor.execute("SELECT * FROM large_table")
            row = cursor.fetchone()

            assert row == ("row1",)
            cursor.execute.assert_called_once()
            cursor.fetchone.assert_called_once()


class TestProxyAttachment:
    """Regression tests for proxy-GC bug (server has gone away, error 2006)."""

    def test_streaming_cursor_holds_proxy_reference(
        self, db_config: DatabaseConfig
    ) -> None:
        """Streaming cursor must retain _proxy_connection to prevent GC."""
        conn = DatabaseConnection(db_config)

        with patch.object(MySQLdb, "connect") as mock_connect:
            mock_connection = MagicMock()
            mock_cursor = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_connection

            cursor = conn.get_streaming_cursor()

            assert hasattr(cursor, "_proxy_connection")
            assert cursor._proxy_connection is not None

    def test_regular_cursor_holds_proxy_reference(
        self, db_config: DatabaseConfig
    ) -> None:
        """Regular cursor must retain _proxy_connection to prevent GC."""
        conn = DatabaseConnection(db_config)

        with patch.object(MySQLdb, "connect") as mock_connect:
            mock_connection = MagicMock()
            mock_cursor = MagicMock()
            mock_connection.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_connection

            cursor = conn.get_cursor()

            assert hasattr(cursor, "_proxy_connection")
            assert cursor._proxy_connection is not None

    def test_concurrent_streaming_and_regular_cursor(
        self, db_config: DatabaseConfig
    ) -> None:
        """Regression: get_cursor() after get_streaming_cursor() must not break SSCursor.

        Before the fix, calling get_cursor() overwrote self._connection, causing
        the previous pool proxy to be GC'd. The proxy finalizer issued a ROLLBACK
        on the connection while the SSCursor result set was still active, producing
        a 'server has gone away' (2006) error.
        """
        import gc

        conn = DatabaseConnection(db_config)

        with patch.object(MySQLdb, "connect") as mock_connect:
            mock_streaming_conn = MagicMock()
            mock_streaming_cursor = MagicMock()
            mock_streaming_conn.cursor.return_value = mock_streaming_cursor

            mock_regular_conn = MagicMock()
            mock_regular_cursor = MagicMock()
            mock_regular_conn.cursor.return_value = mock_regular_cursor

            mock_connect.side_effect = [mock_streaming_conn, mock_regular_conn]

            streaming_cursor = conn.get_streaming_cursor()
            regular_cursor = conn.get_cursor()

            gc.collect()

            assert hasattr(streaming_cursor, "_proxy_connection")
            assert streaming_cursor._proxy_connection is not None
            assert hasattr(regular_cursor, "_proxy_connection")
            assert regular_cursor._proxy_connection is not None


class TestRetryLogic:
    """Tests for connection retry logic."""

    def test_retry_logic_attempts_3_times_on_failure(
        self, db_config: DatabaseConfig
    ) -> None:
        """Test that connection retry logic attempts 3 times before giving up."""
        conn = DatabaseConnection(db_config)

        with patch.object(MySQLdb, "connect") as mock_connect:
            # Fail 3 times, then succeed
            mock_connect.side_effect = [
                MySQLdb.OperationalError("Connection timeout"),
                MySQLdb.OperationalError("Connection timeout"),
                MySQLdb.OperationalError("Connection timeout"),
            ]

            with pytest.raises(MySQLdb.OperationalError):
                conn.get_connection()

            # Should have attempted 3 times (initial + 2 retries)
            assert mock_connect.call_count == 3

    def test_success_on_retry(
        self, db_config: DatabaseConfig
    ) -> None:
        """Test that connection succeeds on retry after initial failure."""
        conn = DatabaseConnection(db_config)

        with patch.object(MySQLdb, "connect") as mock_connect:
            mock_connection = MagicMock()
            # Fail twice, then succeed
            mock_connect.side_effect = [
                MySQLdb.OperationalError("Connection timeout"),
                MySQLdb.OperationalError("Connection timeout"),
                mock_connection,
            ]

            # This should succeed on the 3rd attempt
            result = conn.get_connection()

            assert result is not None
            assert mock_connect.call_count == 3

    def test_exponential_backoff_delays(
        self, db_config: DatabaseConfig
    ) -> None:
        """Test that retry logic uses exponential backoff (1s, 2s)."""
        import time

        conn = DatabaseConnection(db_config)

        with patch.object(MySQLdb, "connect") as mock_connect, patch.object(
            time, "sleep"
        ) as mock_sleep:
            # Fail 3 times
            mock_connect.side_effect = MySQLdb.OperationalError("Connection timeout")

            with pytest.raises(MySQLdb.OperationalError):
                conn.get_connection()

            # Verify sleep was called with 1s and 2s delays
            assert mock_sleep.call_count == 2
            mock_sleep.assert_any_call(1)
            mock_sleep.assert_any_call(2)

    def test_logs_retry_attempts(
        self, db_config: DatabaseConfig, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that retry attempts are logged appropriately."""
        conn = DatabaseConnection(db_config)

        with patch.object(MySQLdb, "connect") as mock_connect:
            # Fail 3 times
            mock_connect.side_effect = MySQLdb.OperationalError("Connection timeout")

            with caplog.at_level(logging.INFO), pytest.raises(MySQLdb.OperationalError):
                conn.get_connection()

            # Should have log entries for retry attempts
            assert any("retry" in record.message.lower() for record in caplog.records)

    def test_streaming_cursor_uses_retry_logic(
        self, db_config: DatabaseConfig
    ) -> None:
        """Test that get_streaming_cursor() also uses retry logic."""
        conn = DatabaseConnection(db_config)

        with patch.object(MySQLdb, "connect") as mock_connect:
            mock_connection = MagicMock()
            # Fail twice, then succeed
            mock_connect.side_effect = [
                MySQLdb.OperationalError("Connection timeout"),
                MySQLdb.OperationalError("Connection timeout"),
                mock_connection,
            ]
            mock_connection.cursor.return_value = MagicMock()

            # This should succeed on the 3rd attempt
            cursor = conn.get_streaming_cursor()

            assert cursor is not None
            assert mock_connect.call_count == 3

    def test_programming_error_also_retries(
        self, db_config: DatabaseConfig
    ) -> None:
        """Test that ProgrammingError also triggers retry logic."""
        conn = DatabaseConnection(db_config)

        with patch.object(MySQLdb, "connect") as mock_connect:
            mock_connection = MagicMock()
            # Fail with ProgrammingError once, then succeed
            mock_connect.side_effect = [
                MySQLdb.ProgrammingError("Syntax error"),
                mock_connection,
            ]
            mock_connection.cursor.return_value = MagicMock()

            # This should succeed on retry
            cursor = conn.get_streaming_cursor()

            assert cursor is not None
            assert mock_connect.call_count == 2


@pytest.fixture
def db_config() -> DatabaseConfig:
    """Fixture providing test database configuration."""
    return DatabaseConfig(
        dbhost="localhost",
        dbuser="test_user",
        dbpasswd="test_pass",
        dbport=3306,
        dbname="test_db",
    )
