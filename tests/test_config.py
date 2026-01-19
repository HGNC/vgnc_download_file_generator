"""Tests for Pydantic configuration models."""

import pytest
from pydantic import ValidationError

from vgnc_download_file_generator.config import (
    AppConfig,
    DatabaseConfig,
    GCSConfig,
    RuntimeConfig,
    get_settings,
)


class TestDatabaseConfig:
    """Tests for DatabaseConfig model."""

    def test_valid_config_with_string_port(self) -> None:
        """Test valid config with string port that coerces to int."""
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
        assert config.dbport == 3306  # Should be coerced to int
        assert config.dbname == "test_db"

    def test_valid_config_with_int_port(self) -> None:
        """Test valid config with int port."""
        config = DatabaseConfig(
            dbhost="localhost",
            dbuser="test_user",
            dbpasswd="test_pass",
            dbport=3306,
            dbname="test_db",
        )
        assert config.dbport == 3306

    def test_missing_required_field_raises_error(self) -> None:
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DatabaseConfig(  # type: ignore[call-arg]
                dbhost="localhost",
                dbuser="test_user",
                dbpasswd="test_pass",
                # Missing dbport and dbname
            )
        errors = exc_info.value.errors()
        error_fields = {e["loc"][0] for e in errors}
        assert "dbport" in error_fields
        assert "dbname" in error_fields


class TestGCSConfig:
    """Tests for GCSConfig model."""

    def test_valid_config(self) -> None:
        """Test valid GCS config."""
        config = GCSConfig(
            bucket_name="test-bucket",
            project_id="test-project",
        )
        assert config.bucket_name == "test-bucket"
        assert config.project_id == "test-project"

    def test_missing_required_field_raises_error(self) -> None:
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            GCSConfig(bucket_name="test-bucket")  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        assert errors[0]["loc"][0] == "project_id"


class TestRuntimeConfig:
    """Tests for RuntimeConfig model."""

    def test_valid_config(self) -> None:
        """Test valid runtime config."""
        config = RuntimeConfig(
            chunk_size=1000,
            max_workers=4,
        )
        assert config.chunk_size == 1000
        assert config.max_workers == 4

    def test_invalid_type_for_int_fields_raises_error(self) -> None:
        """Test that invalid types for int fields raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            RuntimeConfig(
                chunk_size="not_a_number",  # type: ignore[arg-type]
                max_workers=4,
            )
        errors = exc_info.value.errors()
        assert errors[0]["loc"][0] == "chunk_size"


class TestAppConfig:
    """Tests for AppConfig model."""

    def test_valid_config_composes_all_subconfigs(self) -> None:
        """Test that AppConfig composes all sub-configs correctly."""
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
            runtime=RuntimeConfig(
                chunk_size=1000,
                max_workers=4,
            ),
        )
        assert config.database.dbhost == "localhost"
        assert config.gcs.bucket_name == "test-bucket"
        assert config.runtime.chunk_size == 1000

    def test_missing_subconfig_raises_error(self) -> None:
        """Test that missing sub-configs raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            AppConfig(  # type: ignore[call-arg]
                database=DatabaseConfig(
                    dbhost="localhost",
                    dbuser="test_user",
                    dbpasswd="test_pass",
                    dbport=3306,
                    dbname="test_db",
                ),
                # Missing gcs and runtime
            )
        errors = exc_info.value.errors()
        error_fields = {e["loc"][0] for e in errors}
        assert "gcs" in error_fields
        assert "runtime" in error_fields


class TestSettingsLoading:
    """Tests for settings loading from environment variables."""

    def test_full_valid_config_from_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test loading full valid config from environment variables."""
        # Set all required environment variables
        monkeypatch.setenv("APP_DATABASE_DBHOST", "test-host")
        monkeypatch.setenv("APP_DATABASE_DBUSER", "test-user")
        monkeypatch.setenv("APP_DATABASE_DBPASSWD", "test-pass")
        monkeypatch.setenv("APP_DATABASE_DBPORT", "3307")
        monkeypatch.setenv("APP_DATABASE_DBNAME", "test-db")
        monkeypatch.setenv("APP_GCS_BUCKET_NAME", "test-bucket")
        monkeypatch.setenv("APP_GCS_PROJECT_ID", "test-project")
        monkeypatch.setenv("APP_RUNTIME_CHUNK_SIZE", "5000")
        monkeypatch.setenv("APP_RUNTIME_MAX_WORKERS", "8")

        config = get_settings()

        assert config.database.dbhost == "test-host"
        assert config.database.dbuser == "test-user"
        assert config.database.dbpasswd == "test-pass"
        assert config.database.dbport == 3307  # Coerced to int
        assert config.database.dbname == "test-db"
        assert config.gcs.bucket_name == "test-bucket"
        assert config.gcs.project_id == "test-project"
        assert config.runtime.chunk_size == 5000
        assert config.runtime.max_workers == 8

    def test_missing_database_credentials_without_secret_manager_raises_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test ValueError raised when database credentials are missing and Secret Manager not configured."""
        # Set GCS and runtime, but missing database credentials
        monkeypatch.setenv("APP_GCS_BUCKET_NAME", "test-bucket")
        monkeypatch.setenv("APP_GCS_PROJECT_ID", "test-project")
        # Make sure Secret Manager is not configured
        monkeypatch.delenv("GOOGLE_SECRET_MANAGER_SECRET_NAME", raising=False)

        with pytest.raises(ValueError, match="Database credentials not found"):
            get_settings()

    def test_prefix_parsing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that prefix parsing works correctly."""
        monkeypatch.setenv("APP_DATABASE_DBHOST", "nested-host")
        monkeypatch.setenv("APP_DATABASE_DBUSER", "nested-user")
        monkeypatch.setenv("APP_DATABASE_DBPASSWD", "nested-pass")
        monkeypatch.setenv("APP_DATABASE_DBPORT", "3306")
        monkeypatch.setenv("APP_DATABASE_DBNAME", "nested-db")
        monkeypatch.setenv("APP_GCS_BUCKET_NAME", "nested-bucket")
        monkeypatch.setenv("APP_GCS_PROJECT_ID", "nested-project")
        monkeypatch.setenv("APP_RUNTIME_CHUNK_SIZE", "1000")
        monkeypatch.setenv("APP_RUNTIME_MAX_WORKERS", "4")

        config = get_settings()

        assert config.database.dbhost == "nested-host"
        assert config.gcs.bucket_name == "nested-bucket"
        assert config.runtime.chunk_size == 1000

    def test_port_string_to_int_conversion(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that port string from env is converted to int."""
        monkeypatch.setenv("APP_DATABASE_DBHOST", "localhost")
        monkeypatch.setenv("APP_DATABASE_DBUSER", "user")
        monkeypatch.setenv("APP_DATABASE_DBPASSWD", "pass")
        monkeypatch.setenv("APP_DATABASE_DBPORT", "9999")  # String
        monkeypatch.setenv("APP_DATABASE_DBNAME", "db")
        monkeypatch.setenv("APP_GCS_BUCKET_NAME", "bucket")
        monkeypatch.setenv("APP_GCS_PROJECT_ID", "project")
        monkeypatch.setenv("APP_RUNTIME_CHUNK_SIZE", "100")
        monkeypatch.setenv("APP_RUNTIME_MAX_WORKERS", "1")

        config = get_settings()

        assert config.database.dbport == 9999
        assert isinstance(config.database.dbport, int)

    def test_invalid_port_string_raises_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that invalid port string raises ValidationError."""
        monkeypatch.setenv("APP_DATABASE_DBHOST", "localhost")
        monkeypatch.setenv("APP_DATABASE_DBUSER", "user")
        monkeypatch.setenv("APP_DATABASE_DBPASSWD", "pass")
        monkeypatch.setenv("APP_DATABASE_DBPORT", "not-a-number")
        monkeypatch.setenv("APP_DATABASE_DBNAME", "db")
        monkeypatch.setenv("APP_GCS_BUCKET_NAME", "bucket")
        monkeypatch.setenv("APP_GCS_PROJECT_ID", "project")
        monkeypatch.setenv("APP_RUNTIME_CHUNK_SIZE", "100")
        monkeypatch.setenv("APP_RUNTIME_MAX_WORKERS", "1")

        with pytest.raises(ValidationError):
            get_settings()

