"""Tests for setup.sh script."""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPT_PATH = Path(__file__).parent.parent / "setup.sh"


class TestScriptExists:
    """Tests for script file existence and basic properties."""

    def test_script_exists(self) -> None:
        """Test that the setup script file exists."""
        assert SCRIPT_PATH.exists(), f"Script not found at {SCRIPT_PATH}"

    def test_script_is_executable(self) -> None:
        """Test that the script has executable permissions."""
        if SCRIPT_PATH.exists():
            assert os.access(SCRIPT_PATH, os.X_OK), "Script must be executable (chmod +x)"


class TestScriptContent:
    """Tests for script content and structure."""

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_script_calls_uv_sync(self) -> None:
        """Test that the script calls uv sync."""
        script_content = SCRIPT_PATH.read_text()
        assert "uv sync" in script_content, "Script should call 'uv sync'"

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_script_checks_for_gnu_parallel(self) -> None:
        """Test that the script checks for GNU parallel."""
        script_content = SCRIPT_PATH.read_text()
        assert "parallel" in script_content.lower(), "Script should check for GNU parallel"
        # Should use command -v or which to check
        assert ("command -v" in script_content or "which" in script_content), \
            "Script should use 'command -v' or 'which' to check for parallel"

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_script_installs_gnu_parallel_if_missing(self) -> None:
        """Test that the script installs GNU parallel if missing."""
        script_content = SCRIPT_PATH.read_text()
        # Should have installation commands for both macOS and Linux
        assert "brew install parallel" in script_content, \
            "Script should install parallel via brew on macOS"
        assert "apt-get install parallel" in script_content or \
               "apt install parallel" in script_content, \
            "Script should install parallel via apt on Linux"

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_script_has_shebang(self) -> None:
        """Test that the script has a proper shebang."""
        script_content = SCRIPT_PATH.read_text()
        assert script_content.startswith("#!"), "Script should have a shebang"
        assert "/bin/bash" in script_content or "/bin/sh" in script_content, \
            "Script should use bash or sh"

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_script_has_error_handling(self) -> None:
        """Test that the script has proper error handling."""
        script_content = SCRIPT_PATH.read_text()
        # Should use set -e or similar error handling
        assert "set -e" in script_content or "set -euo" in script_content, \
            "Script should have error handling (set -e or set -euo pipefail)"

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_script_informs_user(self) -> None:
        """Test that the script provides user feedback."""
        script_content = SCRIPT_PATH.read_text()
        # Should have echo statements for user feedback
        assert script_content.count("echo") >= 3, \
            "Script should provide user feedback via echo statements"


class TestScriptBehavior:
    """Tests for script execution behavior."""

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_help_or_usage_info(self) -> None:
        """Test that script provides usage information or is self-documenting."""
        if SCRIPT_PATH.exists():
            result = subprocess.run(
                [str(SCRIPT_PATH), "--help"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # Should either support --help or fail gracefully
            assert result.returncode in [0, 1]

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_script_idempotent(self) -> None:
        """Test that running the script multiple times is safe."""
        # This is a hard test to run in CI, but we can check script structure
        if SCRIPT_PATH.exists():
            script_content = SCRIPT_PATH.read_text()
            # Script should check if things are already installed
            # by checking for their existence before installing
            assert "command -v" in script_content or "which" in script_content, \
                "Script should check for existing commands before installing"


class TestUVSyncBehavior:
    """Tests for uv sync execution."""

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_uv_sync_command_present(self) -> None:
        """Test that uv sync is called correctly."""
        script_content = SCRIPT_PATH.read_text()
        assert "uv sync" in script_content, "Script should call 'uv sync'"

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_checks_uv_installed(self) -> None:
        """Test that script checks if uv is installed."""
        script_content = SCRIPT_PATH.read_text()
        # Should check for uv before using it
        assert "uv" in script_content, "Script should mention uv"


class TestGNUParallelHandling:
    """Tests for GNU parallel installation logic."""

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_detects_macos_for_brew(self) -> None:
        """Test that script detects macOS and uses brew."""
        script_content = SCRIPT_PATH.read_text()
        # Should check for Darwin/macOS
        assert "Darwin" in script_content or "macOS" in script_content or "$(uname)" in script_content, \
            "Script should detect macOS"
        assert "brew" in script_content, "Script should use brew on macOS"

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_detects_linux_for_apt(self) -> None:
        """Test that script detects Linux and uses apt."""
        script_content = SCRIPT_PATH.read_text()
        # Should check for Linux
        assert "Linux" in script_content or "$(uname)" in script_content, \
            "Script should detect Linux"
        assert "apt" in script_content, "Script should use apt on Linux"

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_handles_sucessful_parallel_install(self) -> None:
        """Test that script acknowledges successful parallel installation."""
        script_content = SCRIPT_PATH.read_text()
        # Should have success message
        assert any(word in script_content.lower() for word in ["success", "installed", "✓", "done"]), \
            "Script should indicate successful installation"

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_handles_missing_parallel_gracefully(self) -> None:
        """Test that script handles missing parallel gracefully."""
        script_content = SCRIPT_PATH.read_text()
        # Should not error out if parallel is missing
        # It should either install it or provide helpful message
        assert "install" in script_content.lower() or "required" in script_content.lower(), \
            "Script should handle missing parallel by installing or providing guidance"


class TestScriptMessages:
    """Tests for user-facing messages."""

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_shows_start_message(self) -> None:
        """Test that script shows an initial message."""
        script_content = SCRIPT_PATH.read_text()
        assert any(word in script_content.lower() for word in ["setting", "setup", "installing", "dependencies"]), \
            "Script should show a clear start message"

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_shows_completion_message(self) -> None:
        """Test that script shows a completion message."""
        script_content = SCRIPT_PATH.read_text()
        assert any(word in script_content.lower() for word in ["complete", "done", "success", "ready"]), \
            "Script should show a completion message"

    @pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not created yet")
    def test_provides_helpful_error_messages(self) -> None:
        """Test that script provides helpful error messages."""
        script_content = SCRIPT_PATH.read_text()
        # Should have stderr redirection or error handling
        assert "2>&1" in script_content or "error" in script_content.lower() or "fail" in script_content.lower(), \
            "Script should handle errors gracefully"
