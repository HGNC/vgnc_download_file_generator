"""Configuration models for VGNC Download File Generator.

This module defines Pydantic models for configuration validation with support
for loading from environment variables and CLI arguments.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Load .env file explicitly for better reliability
# Search from current directory up to project root
def _load_env_file() -> None:
    """Load .env file from current directory or parent directories.

    This function searches for .env file starting from the current working
    directory and moving up the directory tree. This ensures the .env file
    is found regardless of where the CLI is invoked from.
    """
    current_path = Path.cwd()

    # Search up to 5 directory levels
    for _ in range(5):
        env_file = current_path / ".env"
        if env_file.exists():
            logger.debug(f"Loading .env from {env_file}")
            load_dotenv(env_file, override=True)
            return

        parent = current_path.parent
        if parent == current_path:  # Reached root
            break
        current_path = parent

    logger.debug("No .env file found in current or parent directories")


# Load .env file when module is imported
_load_env_file()


class DatabaseConfig(BaseModel):
    """Database connection configuration.

    Attributes:
        dbhost: Database host address
        dbuser: Database username
        dbpasswd: Database password
        dbport: Database port (accepts int or str, coerced to int)
        dbname: Database name
    """

    dbhost: str = Field(description="Database host address")
    dbuser: str = Field(description="Database username")
    dbpasswd: str = Field(description="Database password")
    dbport: int | str = Field(description="Database port")
    dbname: str = Field(description="Database name")

    @field_validator("dbport", mode="before")
    @classmethod
    def coerce_port_to_int(cls, value: int | str) -> int:
        """Coerce port value to int.

        Args:
            value: Port value as int or str

        Returns:
            Port value as int

        Raises:
            ValueError: If value cannot be converted to int
        """
        if isinstance(value, str):
            return int(value)
        return value


class GCSConfig(BaseModel):
    """Google Cloud Storage configuration.

    Attributes:
        bucket_name: GCS bucket name for file uploads
        project_id: GCP project ID
    """

    bucket_name: str = Field(description="GCS bucket name for file uploads")
    project_id: str = Field(description="GCP project ID")


class RuntimeConfig(BaseModel):
    """Runtime parameters for file generation.

    Attributes:
        chunk_size: Number of records to process per chunk
        max_workers: Maximum number of parallel workers
    """

    chunk_size: int = Field(description="Number of records to process per chunk")
    max_workers: int = Field(description="Maximum number of parallel workers")


class AppConfig(BaseModel):
    """Top-level application configuration.

    Attributes:
        database: Database connection configuration
        gcs: Google Cloud Storage configuration
        runtime: Runtime parameters
    """

    database: DatabaseConfig = Field(description="Database connection configuration")
    gcs: GCSConfig = Field(description="Google Cloud Storage configuration")
    runtime: RuntimeConfig = Field(description="Runtime parameters")


class Settings(BaseSettings):
    """Settings loaded from environment variables.

    Environment variables should use the APP_ prefix:
    - APP_DATABASE_DBHOST, APP_DATABASE_DBUSER, etc.
    - APP_GCS_BUCKET_NAME, APP_GCS_PROJECT_ID
    - APP_RUNTIME_CHUNK_SIZE, APP_RUNTIME_MAX_WORKERS

    Database credentials can be provided either via environment variables
    or via GCP Secret Manager (as a fallback).
    """

    # Database settings (optional - will use Secret Manager if not provided)
    database_dbhost: str | None = None
    database_dbuser: str | None = None
    database_dbpasswd: str | None = None
    database_dbport: int | str | None = None
    database_dbname: str | None = None

    # GCS settings
    gcs_bucket_name: str
    gcs_project_id: str

    # Runtime settings
    runtime_chunk_size: int = 5000
    runtime_max_workers: int = 4

    @field_validator("database_dbport", mode="before")
    @classmethod
    def coerce_port_to_int(cls, value: int | str) -> int:
        """Coerce port value to int.

        Args:
            value: Port value as int or str

        Returns:
            Port value as int

        Raises:
            ValueError: If value cannot be converted to int
        """
        if isinstance(value, str):
            return int(value)
        return value

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def to_app_config(self) -> AppConfig:
        """Convert Settings to AppConfig.

        Returns:
            AppConfig instance with the same values
        """
        return AppConfig(
            database=DatabaseConfig(
                dbhost=self.database_dbhost,
                dbuser=self.database_dbuser,
                dbpasswd=self.database_dbpasswd,
                dbport=self.database_dbport,
                dbname=self.database_dbname,
            ),
            gcs=GCSConfig(
                bucket_name=self.gcs_bucket_name,
                project_id=self.gcs_project_id,
            ),
            runtime=RuntimeConfig(
                chunk_size=self.runtime_chunk_size,
                max_workers=self.runtime_max_workers,
            ),
        )


def get_settings() -> AppConfig:
    """Load settings from environment variables and return as AppConfig.

    Database credentials are loaded from environment variables if available.
    If not, falls back to GCP Secret Manager (if configured).

    Returns:
        AppConfig instance loaded from environment variables or Secret Manager

    Raises:
        ValidationError: If required environment variables are missing or invalid
        ValueError: If Secret Manager is configured but credentials are invalid
    """
    settings = Settings()  # type: ignore[call-arg]

    # Check if database credentials are missing from environment
    db_from_env = all([
        settings.database_dbhost,
        settings.database_dbuser,
        settings.database_dbpasswd,
        settings.database_dbport,
        settings.database_dbname,
    ])

    if not db_from_env:
        # Try to load from Secret Manager
        secret_name = os.environ.get("GOOGLE_SECRET_MANAGER_SECRET_NAME")
        if secret_name:
            logger.info("Database credentials not in environment, loading from Secret Manager...")
            try:
                from vgnc_download_file_generator.utils.secret_manager import get_db_credentials

                # Use gcs_project_id from settings for Secret Manager
                db_config = get_db_credentials(
                    secret_name=secret_name,
                    project_id=settings.gcs_project_id,
                )

                # Override settings with Secret Manager values
                settings.database_dbhost = db_config.dbhost
                settings.database_dbuser = db_config.dbuser
                settings.database_dbpasswd = db_config.dbpasswd
                settings.database_dbport = db_config.dbport
                settings.database_dbname = db_config.dbname

                logger.info("Successfully loaded database credentials from Secret Manager")
            except Exception as e:
                logger.error("Failed to load credentials from Secret Manager: %s", e)
                raise ValueError(
                    f"Database credentials not found in environment variables and "
                    f"Secret Manager fallback failed: {e}"
                ) from e
        else:
            # No credentials available anywhere
            msg = "Database credentials not found in environment variables and GOOGLE_SECRET_MANAGER_SECRET_NAME not set"
            logger.error(msg)
            raise ValueError(msg)

    return settings.to_app_config()
