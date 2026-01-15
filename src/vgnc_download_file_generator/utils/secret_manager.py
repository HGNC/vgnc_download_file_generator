"""GCP Secret Manager integration for retrieving database credentials.

This module provides utilities to retrieve MySQL database credentials from
GCP Secret Manager using the google-cloud-secret-manager library.
"""

import json
import logging
import os

from google.api_core import exceptions as gcp_exceptions
from google.cloud import secretmanager

from vgnc_download_file_generator.config import DatabaseConfig

logger = logging.getLogger(__name__)


class SecretManagerError(Exception):
    """Custom exception for Secret Manager errors.

    This exception wraps GCP API exceptions to provide a consistent
    error interface for Secret Manager operations.
    """

    def __init__(self, message: str, secret_name: str, original_exception: Exception | None = None) -> None:
        """Initialize SecretManagerError.

        Args:
            message: Error message
            secret_name: Name of the secret that caused the error
            original_exception: The original exception that caused this error
        """
        self.secret_name = secret_name
        self.original_exception = original_exception
        super().__init__(f"{message} (secret: {secret_name})")


def get_db_credentials(
    secret_name: str,
    project_id: str | None = None,
    client: secretmanager.SecretManagerServiceClient | None = None,
) -> DatabaseConfig:
    """Retrieve MySQL database credentials from GCP Secret Manager.

    Args:
        secret_name: Name of the secret in Secret Manager
        project_id: GCP project ID. If None, will attempt to discover from
            environment variable GOOGLE_CLOUD_PROJECT or from ADC.
        client: Optional SecretManagerServiceClient instance for testing.
            If None, a new client will be created.

    Returns:
        DatabaseConfig instance with credentials from the secret

    Raises:
        SecretManagerError: If GCP Secret Manager API returns an error
        ValueError: If secret data is invalid JSON or missing required fields
    """
    # Auto-discover project_id if not provided
    if project_id is None:
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        if not project_id:
            msg = "project_id must be provided or set in GOOGLE_CLOUD_PROJECT environment variable"
            raise ValueError(msg)

    # Create client if not provided (useful for testing)
    if client is None:
        client = secretmanager.SecretManagerServiceClient()

    # Build the secret resource name
    secret_path = f"projects/{project_id}/secrets/{secret_name}/versions/latest"

    # Access the secret version with error handling
    try:
        response = client.access_secret_version(name=secret_path)
    except gcp_exceptions.NotFound as e:
        logger.error("Secret not found: %s in project %s", secret_name, project_id, exc_info=True)
        raise SecretManagerError("Secret not found", secret_name, e) from e
    except gcp_exceptions.Forbidden as e:
        logger.error("Permission denied accessing secret: %s", secret_name, exc_info=True)
        raise SecretManagerError("Permission denied", secret_name, e) from e
    except gcp_exceptions.InvalidArgument as e:
        logger.error("Invalid argument for secret: %s", secret_name, exc_info=True)
        raise SecretManagerError("Invalid argument", secret_name, e) from e
    except gcp_exceptions.GoogleAPIError as e:
        logger.error("GCP API error accessing secret: %s", secret_name, exc_info=True)
        raise SecretManagerError("GCP API error", secret_name, e) from e

    # Decode the secret payload
    secret_data = response.payload.data.decode("UTF-8")

    # Parse JSON with error handling and logging
    try:
        credentials = json.loads(secret_data)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in secret %s: %s", secret_name, e, exc_info=True)
        msg = f"Invalid JSON in secret {secret_name}"
        raise ValueError(msg) from e

    # Validate and map to DatabaseConfig
    try:
        config = DatabaseConfig(
            dbhost=str(credentials["dbhost"]),
            dbuser=str(credentials["dbuser"]),
            dbpasswd=str(credentials["dbpasswd"]),
            dbport=credentials["dbport"],
            dbname=str(credentials["dbname"]),
        )
        logger.info("Successfully retrieved secret %s from project %s", secret_name, project_id)
        return config
    except KeyError as e:
        logger.error("Missing required field in secret %s: %s", secret_name, e, exc_info=True)
        msg = f"Missing required field in secret {secret_name}: {e!s}"
        raise ValueError(msg) from e
