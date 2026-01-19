"""Tests for GCP Secret Manager integration."""

import json
import logging
from unittest.mock import MagicMock

import pytest
from google.api_core import exceptions as gcp_exceptions
from google.cloud.secretmanager_v1 import AccessSecretVersionResponse, SecretPayload

from vgnc_download_file_generator.config import DatabaseConfig
from vgnc_download_file_generator.utils.secret_manager import (
    SecretManagerError,
    get_db_credentials,
)


class TestGetDbCredentials:
    """Tests for get_db_credentials function."""

    def test_successful_secret_retrieval_and_parsing(
        self, mock_secret_client: MagicMock
    ) -> None:
        """Test successful secret retrieval and parsing with mocked client."""
        secret_data = {
            "dbhost": "test-host",
            "dbuser": "test-user",
            "dbpasswd": "test-pass",
            "dbport": 3306,
            "dbname": "test-db",
        }
        secret_payload = SecretPayload(data=json.dumps(secret_data).encode())

        response = AccessSecretVersionResponse(payload=secret_payload)
        mock_secret_client.access_secret_version.return_value = response

        result = get_db_credentials(
            secret_name="test-secret",
            project_id="test-project",
            client=mock_secret_client,
        )

        assert isinstance(result, DatabaseConfig)
        assert result.dbhost == "test-host"
        assert result.dbuser == "test-user"
        assert result.dbpasswd == "test-pass"
        assert result.dbport == 3306
        assert result.dbname == "test-db"
        mock_secret_client.access_secret_version.assert_called_once_with(
            name="projects/test-project/secrets/test-secret/versions/latest",
            timeout=30,
        )

    def test_project_id_auto_discovery_from_env(
        self, monkeypatch: pytest.MonkeyPatch, mock_secret_client: MagicMock
    ) -> None:
        """Test project_id auto-discovery from environment variable."""
        secret_data = {
            "dbhost": "env-host",
            "dbuser": "env-user",
            "dbpasswd": "env-pass",
            "dbport": 3307,
            "dbname": "env-db",
        }
        secret_payload = SecretPayload(data=json.dumps(secret_data).encode())

        response = AccessSecretVersionResponse(payload=secret_payload)
        mock_secret_client.access_secret_version.return_value = response

        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "env-project")

        result = get_db_credentials(
            secret_name="test-secret",
            client=mock_secret_client,
        )

        assert result.dbhost == "env-host"
        mock_secret_client.access_secret_version.assert_called_once_with(
            name="projects/env-project/secrets/test-secret/versions/latest",
            timeout=30,
        )

    def test_returns_correct_database_config_object(
        self, mock_secret_client: MagicMock
    ) -> None:
        """Test that a valid DatabaseConfig object is returned."""
        secret_data = {
            "dbhost": "config-host",
            "dbuser": "config-user",
            "dbpasswd": "config-pass",
            "dbport": "3306",
            "dbname": "config-db",
        }
        secret_payload = SecretPayload(data=json.dumps(secret_data).encode())

        response = AccessSecretVersionResponse(payload=secret_payload)
        mock_secret_client.access_secret_version.return_value = response

        result = get_db_credentials(
            secret_name="config-secret",
            project_id="config-project",
            client=mock_secret_client,
        )

        assert isinstance(result, DatabaseConfig)
        assert result.dbport == 3306  # Coerced to int
        assert isinstance(result.dbport, int)


class TestErrorHandling:
    """Tests for error handling in get_db_credentials function."""

    def test_secret_not_found_raises_custom_error(
        self, mock_secret_client: MagicMock,
    ) -> None:
        """Test that NotFound exception raises SecretManagerError."""
        mock_secret_client.access_secret_version.side_effect = (
            gcp_exceptions.NotFound("Secret not found")
        )

        with pytest.raises(SecretManagerError) as exc_info:
            get_db_credentials(
                secret_name="missing-secret",
                project_id="test-project",
                client=mock_secret_client,
            )

        assert "Secret not found" in str(exc_info.value)
        assert "missing-secret" in str(exc_info.value)

    def test_permission_denied_raises_custom_error(
        self, mock_secret_client: MagicMock,
    ) -> None:
        """Test that Forbidden exception raises SecretManagerError."""
        mock_secret_client.access_secret_version.side_effect = (
            gcp_exceptions.Forbidden("Permission denied")
        )

        with pytest.raises(SecretManagerError) as exc_info:
            get_db_credentials(
                secret_name="restricted-secret",
                project_id="test-project",
                client=mock_secret_client,
            )

        assert "Permission denied" in str(exc_info.value)
        assert "restricted-secret" in str(exc_info.value)

    def test_invalid_argument_raises_custom_error(
        self, mock_secret_client: MagicMock,
    ) -> None:
        """Test that InvalidArgument exception raises SecretManagerError."""
        mock_secret_client.access_secret_version.side_effect = (
            gcp_exceptions.InvalidArgument("Invalid argument")
        )

        with pytest.raises(SecretManagerError) as exc_info:
            get_db_credentials(
                secret_name="invalid-secret",
                project_id="test-project",
                client=mock_secret_client,
            )

        assert "Invalid argument" in str(exc_info.value)

    def test_invalid_json_raises_value_error_with_log(
        self, mock_secret_client: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that invalid JSON raises ValueError with appropriate log."""
        secret_payload = SecretPayload(data=b"not valid json")
        response = AccessSecretVersionResponse(payload=secret_payload)
        mock_secret_client.access_secret_version.return_value = response

        with caplog.at_level(logging.ERROR), pytest.raises(ValueError) as exc_info:
            get_db_credentials(
                secret_name="bad-json-secret",
                project_id="test-project",
                client=mock_secret_client,
            )

        assert "Invalid JSON" in str(exc_info.value)
        assert any(
            "Invalid JSON in secret" in record.message
            for record in caplog.records
        )

    def test_logs_info_on_successful_retrieval(
        self, mock_secret_client: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that successful secret retrieval logs info message."""
        secret_data = {
            "dbhost": "log-host",
            "dbuser": "log-user",
            "dbpasswd": "log-pass",
            "dbport": 3306,
            "dbname": "log-db",
        }
        secret_payload = SecretPayload(data=json.dumps(secret_data).encode())
        response = AccessSecretVersionResponse(payload=secret_payload)
        mock_secret_client.access_secret_version.return_value = response

        with caplog.at_level(logging.INFO):
            get_db_credentials(
                secret_name="log-test-secret",
                project_id="test-project",
                client=mock_secret_client,
            )

        assert any(
            "Successfully retrieved secret" in record.message
            for record in caplog.records
        )


@pytest.fixture
def mock_secret_client() -> MagicMock:
    """Fixture that provides a mocked SecretManagerServiceClient."""
    from google.cloud import secretmanager

    mock_client = MagicMock(spec=secretmanager.SecretManagerServiceClient)
    return mock_client
