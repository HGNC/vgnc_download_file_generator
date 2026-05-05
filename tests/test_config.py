"""Tests for Pydantic configuration models."""

import pytest
from pydantic import ValidationError

from vgnc_download_file_generator.config import (
    AppConfig,
    DatabaseConfig,
    GCSConfig,
    get_settings,
)


class TestDatabaseConfig:
    """Tests for DatabaseConfig model."""

    def test_valid_config_with_string_port(self) -> None:
        config = DatabaseConfig(
            dbhost="localhost",
            dbuser="test_user",
            dbpasswd="test_pass",
            dbport="3306",
            dbname="test_db",
        )
        assert config.dbhost == "localhost"
        assert config.dbuser == "test_user"
        assert config.dbpasswd == "test_pass"
        assert config.dbport == 3306
        assert config.dbname == "test_db"

    def test_valid_config_with_int_port(self) -> None:
        config = DatabaseConfig(
            dbhost="localhost",
            dbuser="test_user",
            dbpasswd="test_pass",
            dbport=3306,
            dbname="test_db",
        )
        assert config.dbport == 3306

    def test_missing_required_field_raises_error(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            DatabaseConfig(  # type: ignore[call-arg]
                dbhost="localhost",
                dbuser="test_user",
                dbpasswd="test_pass",
            )
        errors = exc_info.value.errors()
        error_fields = {e["loc"][0] for e in errors}
        assert "dbport" in error_fields
        assert "dbname" in error_fields


class TestGCSConfig:
    """Tests for GCSConfig model."""

    def test_valid_config(self) -> None:
        config = GCSConfig(
            bucket_name="test-bucket",
            project_id="test-project",
        )
        assert config.bucket_name == "test-bucket"
        assert config.project_id == "test-project"

    def test_missing_required_field_raises_error(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            GCSConfig(bucket_name="test-bucket")  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        assert errors[0]["loc"][0] == "project_id"


class TestAppConfig:
    """Tests for AppConfig model."""

    def test_valid_config_composes_subconfigs(self) -> None:
        config = AppConfig(
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
        assert config.database.dbhost == "localhost"
        assert config.gcs.bucket_name == "test-bucket"


class TestSettingsLoading:
    """Tests for settings loading from environment variables."""

    def test_full_valid_config_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_HOST", "test-host")
        monkeypatch.setenv("DB_USER", "test-user")
        monkeypatch.setenv("DB_PASSWORD", "test-pass")
        monkeypatch.setenv("DB_PORT", "3307")
        monkeypatch.setenv("DB_NAME", "test-db")
        monkeypatch.setenv("GCS_BUCKET", "test-bucket")
        monkeypatch.setenv("GCS_PROJECT_ID", "test-project")

        config = get_settings()

        assert config.database.dbhost == "test-host"
        assert config.database.dbuser == "test-user"
        assert config.database.dbpasswd == "test-pass"
        assert config.database.dbport == 3307
        assert config.database.dbname == "test-db"
        assert config.gcs.bucket_name == "test-bucket"
        assert config.gcs.project_id == "test-project"

    def test_port_string_to_int_conversion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_HOST", "localhost")
        monkeypatch.setenv("DB_USER", "user")
        monkeypatch.setenv("DB_PASSWORD", "pass")
        monkeypatch.setenv("DB_PORT", "9999")
        monkeypatch.setenv("DB_NAME", "db")
        monkeypatch.setenv("GCS_BUCKET", "bucket")
        monkeypatch.setenv("GCS_PROJECT_ID", "project")

        config = get_settings()

        assert config.database.dbport == 9999
        assert isinstance(config.database.dbport, int)

    def test_invalid_port_string_raises_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_HOST", "localhost")
        monkeypatch.setenv("DB_USER", "user")
        monkeypatch.setenv("DB_PASSWORD", "pass")
        monkeypatch.setenv("DB_PORT", "not-a-number")
        monkeypatch.setenv("DB_NAME", "db")
        monkeypatch.setenv("GCS_BUCKET", "bucket")
        monkeypatch.setenv("GCS_PROJECT_ID", "project")

        with pytest.raises(ValidationError):
            get_settings()

    def test_defaults_for_port_and_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_HOST", "localhost")
        monkeypatch.setenv("DB_USER", "user")
        monkeypatch.setenv("DB_PASSWORD", "pass")
        monkeypatch.delenv("DB_PORT", raising=False)
        monkeypatch.setenv("DB_NAME", "db")
        monkeypatch.setenv("GCS_BUCKET", "bucket")
        monkeypatch.setenv("GCS_PROJECT_ID", "project")
        monkeypatch.delenv("GCS_PREFIX", raising=False)

        config = get_settings()

        assert config.database.dbport == 3306
        assert config.gcs.path_prefix == "vgnc/"
