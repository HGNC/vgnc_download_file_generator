"""Database connection manager for MySQL.

This module provides a connection manager for MySQL databases using mysqlclient
(MySQLdb) with connection pooling and server-side cursor support.
"""

import logging
import time
from collections.abc import Callable
from typing import Any

import MySQLdb
from sqlalchemy.pool import PoolProxiedConnection, QueuePool

from vgnc_download_file_generator.config import DatabaseConfig

logger = logging.getLogger(__name__)


def _retry_on_mysql_error(
    max_attempts: int = 3,
    delays: tuple[int, ...] = (1, 2),
) -> Callable[[Callable[[], Any]], Any]:
    """Decorator to retry MySQL connection on specific errors with exponential backoff.

    Args:
        max_attempts: Maximum number of connection attempts (default: 3)
        delays: Tuple of delay seconds between retries (default: 1s, 2s)

    Returns:
        Decorator function
    """

    def decorator(func: Callable[[], Any]) -> Callable[[], Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: MySQLdb.OperationalError | MySQLdb.ProgrammingError | None = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except (MySQLdb.OperationalError, MySQLdb.ProgrammingError) as e:
                    last_exception = e

                    if attempt < max_attempts - 1:
                        delay = delays[attempt] if attempt < len(delays) else delays[-1]
                        logger.warning(
                            "Connection attempt %d/%d failed: %s. Retrying in %d second(s)...",
                            attempt + 1,
                            max_attempts,
                            e,
                            delay,
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            "All %d connection attempts failed. Last error: %s",
                            max_attempts,
                            e,
                            exc_info=True,
                        )

            if last_exception:
                raise last_exception
            return None

        return wrapper

    return decorator


class DatabaseConnection:
    """MySQL database connection manager.

    This class manages MySQL connections using mysqlclient (MySQLdb)
    with support for connection pooling and server-side cursors.

    Attributes:
        config: Database configuration containing connection parameters
        _pool: SQLAlchemy QueuePool for connection management
    """

    def __init__(self, config: DatabaseConfig) -> None:
        """Initialize DatabaseConnection with database configuration.

        Args:
            config: DatabaseConfig instance with connection parameters
        """
        self.config = config
        self._connection: PoolProxiedConnection | None = None
        self._pool: QueuePool = self._create_pool()

    def _create_connection(self) -> MySQLdb.Connection:
        """Create a new MySQL database connection.

        Returns:
            MySQLdb.Connection instance

        Raises:
            MySQLdb.OperationalError: If connection fails
        """
        return MySQLdb.connect(
            host=self.config.dbhost,
            user=self.config.dbuser,
            passwd=self.config.dbpasswd,
            db=self.config.dbname,
            port=self.config.dbport,
        )

    def _create_pool(self) -> QueuePool:
        """Create and initialize SQLAlchemy QueuePool.

        Returns:
            QueuePool configured with pool_size=5, recycle=300
        """
        pool = QueuePool(
            self._create_connection,  # type: ignore[arg-type]
            pool_size=5,
            max_overflow=0,
            recycle=300,
            reset_on_return=True,
        )
        logger.info(
            "Initialized connection pool with pool_size=5, recycle=300, reset_on_return=True"
        )
        return pool

    def get_connection(self) -> PoolProxiedConnection:
        """Get a MySQL database connection from the pool with retry logic.

        Returns:
            PoolProxiedConnection that wraps MySQLdb.Connection

        Raises:
            MySQLdb.OperationalError: If all connection attempts fail
            MySQLdb.ProgrammingError: If all connection attempts fail
        """
        def _do_connect() -> PoolProxiedConnection:
            logger.info(
                "Checking out connection from pool to database %s at %s:%s",
                self.config.dbname,
                self.config.dbhost,
                self.config.dbport,
            )
            conn = self._pool.connect()
            self._connection = conn
            logger.info("Successfully checked out connection from pool")
            return conn

        result = _retry_on_mysql_error()(_do_connect)()
        return result  # type: ignore[no-any-return]

    def get_streaming_cursor(self) -> Any:
        """Get a server-side cursor for memory-efficient large result set streaming.

        Returns:
            MySQLdb.SSCursor instance for streaming large result sets

        Raises:
            MySQLdb.OperationalError: If connection fails
        """
        conn = self.get_connection()
        cursor = conn.cursor(MySQLdb.cursors.SSCursor)
        logger.info("Created server-side cursor for streaming")
        return cursor

    def __enter__(self) -> "DatabaseConnection":
        """Enter context manager and establish connection.

        Returns:
            Self for use in with statement
        """
        self.get_connection()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        """Exit context manager and return connection to pool.

        Args:
            exc_type: Exception type if an exception was raised
            exc_val: Exception value if an exception was raised
            exc_tb: Exception traceback if an exception was raised
        """
        if self._connection is not None:
            try:
                self._connection.close()
                logger.info("MySQL connection returned to pool")
            except MySQLdb.Error as e:
                logger.error("Error closing MySQL connection: %s", e, exc_info=True)
            finally:
                self._connection = None
