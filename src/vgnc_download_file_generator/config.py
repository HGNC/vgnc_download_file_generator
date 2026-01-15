"""Configuration models for VGNC Download File Generator.

This module defines Pydantic models for configuration validation with support
for loading from environment variables and CLI arguments.
"""

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    """

    # Database settings
    database_dbhost: str
    database_dbuser: str
    database_dbpasswd: str
    database_dbport: int | str
    database_dbname: str

    # GCS settings
    gcs_bucket_name: str
    gcs_project_id: str

    # Runtime settings
    runtime_chunk_size: int
    runtime_max_workers: int

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

    Returns:
        AppConfig instance loaded from environment variables

    Raises:
        ValidationError: If required environment variables are missing or invalid
    """
    settings = Settings()  # type: ignore[call-arg]
    return settings.to_app_config()
