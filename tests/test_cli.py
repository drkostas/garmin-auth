"""Tests for CLI commands."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def run_cli(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run garmin-auth CLI and capture output."""
    return subprocess.run(
        [sys.executable, "-m", "garmin_auth.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


class TestCLINoArgs:
    """No command → help."""

    def test_no_args_shows_help(self) -> None:
        result = run_cli()
        assert result.returncode == 0
        assert "garmin-auth" in result.stdout
        assert "login" in result.stdout
        assert "status" in result.stdout
        assert "refresh" in result.stdout


class TestCLIStatus:
    """garmin-auth status."""

    def test_status_with_fresh_tokens(self, token_dir_with_fresh_tokens: Path) -> None:
        result = run_cli("--token-dir", str(token_dir_with_fresh_tokens), "status")
        assert result.returncode == 0
        assert "✓" in result.stdout
        assert "valid" in result.stdout.lower()

    def test_status_with_expired_tokens(self, token_dir_with_expired_tokens: Path) -> None:
        result = run_cli("--token-dir", str(token_dir_with_expired_tokens), "status")
        assert result.returncode == 1
        assert "✗" in result.stdout
        assert "expired" in result.stdout.lower()

    def test_status_no_tokens(self, tmp_token_dir: Path) -> None:
        result = run_cli("--token-dir", str(tmp_token_dir), "status")
        assert result.returncode == 1
        assert "✗" in result.stdout
        assert "garmin-auth login" in result.stdout

    def test_status_verbose(self, token_dir_with_fresh_tokens: Path) -> None:
        result = run_cli("--token-dir", str(token_dir_with_fresh_tokens), "-v", "status")
        assert result.returncode == 0
        assert "oauth1_present" in result.stdout  # JSON output in verbose mode


class TestCLIRefresh:
    """garmin-auth refresh."""

    def test_refresh_skips_fresh(self, token_dir_with_fresh_tokens: Path) -> None:
        result = run_cli("--token-dir", str(token_dir_with_fresh_tokens), "refresh")
        assert result.returncode == 0
        assert "✓" in result.stdout
        assert "still valid" in result.stdout.lower()

    def test_quiet_flag(self, token_dir_with_fresh_tokens: Path) -> None:
        result = run_cli("--token-dir", str(token_dir_with_fresh_tokens), "-q", "refresh")
        assert result.returncode == 0
        # Should still show result but no logging
        assert "✓" in result.stdout


class TestCLIConfig:
    """Config persistence."""

    def test_config_dir_created(self, token_dir_with_fresh_tokens: Path, tmp_path: Path) -> None:
        config_dir = tmp_path / ".garmin-auth"
        with patch("garmin_auth.cli.CONFIG_DIR", config_dir), \
             patch("garmin_auth.cli.CONFIG_FILE", config_dir / "config.json"), \
             patch("garmin_auth.auth.Garmin") as MockGarmin:
            mock_client = MagicMock()
            mock_client.display_name = "test"
            MockGarmin.return_value = mock_client

            from garmin_auth.cli import cmd_login, _save_config
            _save_config({"email": "test@test.com"})
            assert config_dir.exists()
            assert (config_dir / "config.json").exists()

    def test_corrupt_config_ignored(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".garmin-auth"
        config_dir.mkdir()
        (config_dir / "config.json").write_text("{corrupt json")

        with patch("garmin_auth.cli.CONFIG_DIR", config_dir), \
             patch("garmin_auth.cli.CONFIG_FILE", config_dir / "config.json"):
            from garmin_auth.cli import _load_config
            result = _load_config()
            assert result == {}

    def test_config_roundtrip(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".garmin-auth"
        config_file = config_dir / "config.json"

        with patch("garmin_auth.cli.CONFIG_DIR", config_dir), \
             patch("garmin_auth.cli.CONFIG_FILE", config_file):
            from garmin_auth.cli import _load_config, _save_config
            _save_config({"email": "saved@test.com"})
            loaded = _load_config()
            assert loaded["email"] == "saved@test.com"
