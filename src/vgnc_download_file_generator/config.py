"""Configuration for VGNC Download File Generator (GCP Cloud Run).

Reads all config from environment variables injected by Cloud Run.
No .env files, no Secret Manager client — secrets are mounted as env vars.
"""

import os

from pydantic import BaseModel, Field, field_validator


class DatabaseConfig(BaseModel):
    """Database connection configuration.

    Attributes:
        dbhost: Database host address
        dbuser: Database username
        dbpasswd: Database password
        dbport: Database port
        dbname: Database name
    """

    dbhost: str = Field(description="Database host address")
    dbuser: str = Field(description="Database username")
    dbpasswd: str = Field(description="Database password")
    dbport: int = Field(description="Database port")
    dbname: str = Field(description="Database name")

    @field_validator("dbport", mode="before")
    @classmethod
    def coerce_port_to_int(cls, value: int | str) -> int:
        if isinstance(value, str):
            return int(value)
        return value


class GCSConfig(BaseModel):
    """Google Cloud Storage configuration.

    Attributes:
        bucket_name: GCS bucket name for file uploads
        project_id: GCP project ID
        path_prefix: Path prefix for all GCS objects (e.g., "vgnc/")
    """

    bucket_name: str = Field(description="GCS bucket name for file uploads")
    project_id: str = Field(description="GCP project ID")
    path_prefix: str = Field(default="", description="Path prefix for all GCS objects")


class AppConfig(BaseModel):
    """Top-level application configuration.

    Attributes:
        database: Database connection configuration
        gcs: Google Cloud Storage configuration
    """

    database: DatabaseConfig
    gcs: GCSConfig


def get_settings() -> AppConfig:
    """Load configuration from environment variables.

    Returns:
        AppConfig instance loaded from environment variables

    Raises:
        ValueError: If required environment variables are missing
    """
    dbhost = os.environ.get("DB_HOST", "")
    dbuser = os.environ.get("DB_USER", "")
    dbpasswd = os.environ.get("DB_PASSWORD", "")
    dbport = os.environ.get("DB_PORT", "3306")
    dbname = os.environ.get("DB_NAME", "")

    bucket_name = os.environ.get("GCS_BUCKET", "")
    project_id = os.environ.get("GCS_PROJECT_ID", "")
    path_prefix = os.environ.get("GCS_PREFIX", "vgnc/")

    return AppConfig(
        database=DatabaseConfig(
            dbhost=dbhost,
            dbuser=dbuser,
            dbpasswd=dbpasswd,
            dbport=dbport,
            dbname=dbname,
        ),
        gcs=GCSConfig(
            bucket_name=bucket_name,
            project_id=project_id,
            path_prefix=path_prefix,
        ),
    )
