"""Tests for token storage backends."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from garmin_auth.storage import FileTokenStore


class TestFileTokenStore:
    """FileTokenStore tests."""

    def test_load_empty_dir(self, tmp_token_dir: Path) -> None:
        store = FileTokenStore(tmp_token_dir)
        assert store.load() is None

    def test_load_nonexistent_dir(self, tmp_path: Path) -> None:
        store = FileTokenStore(tmp_path / "does-not-exist")
        assert store.load() is None

    def test_save_creates_dir(self, tmp_path: Path) -> None:
        target = tmp_path / "new" / "nested" / "dir"
        store = FileTokenStore(target)
        store.save({"oauth1_token.json": {"token": "abc"}})
        assert target.exists()
        assert (target / "oauth1_token.json").exists()

    def test_save_load_roundtrip(self, tmp_token_dir: Path, fresh_tokens: dict) -> None:
        store = FileTokenStore(tmp_token_dir)
        store.save(fresh_tokens)
        loaded = store.load()
        assert loaded is not None
        assert loaded["oauth1_token.json"]["oauth_token"] == fresh_tokens["oauth1_token.json"]["oauth_token"]
        assert loaded["oauth2_token.json"]["access_token"] == fresh_tokens["oauth2_token.json"]["access_token"]

    def test_save_load_preserves_exact_data(self, tmp_token_dir: Path) -> None:
        original = {
            "oauth1_token.json": {"oauth_token": "tok", "oauth_token_secret": "sec", "domain": "garmin.com"},
            "oauth2_token.json": {"access_token": "at", "expires_at": 1234567890, "refresh_token": "rt"},
        }
        store = FileTokenStore(tmp_token_dir)
        store.save(original)
        loaded = store.load()
        assert loaded == original

    def test_skips_non_json_files(self, tmp_token_dir: Path, fresh_tokens: dict) -> None:
        store = FileTokenStore(tmp_token_dir)
        store.save(fresh_tokens)
        # Add a non-json file
        (tmp_token_dir / "notes.txt").write_text("not json")
        (tmp_token_dir / "backup.bak").write_text("{invalid")
        loaded = store.load()
        assert loaded is not None
        assert "notes.txt" not in loaded
        assert "backup.bak" not in loaded

    def test_handles_corrupt_json(self, tmp_token_dir: Path) -> None:
        (tmp_token_dir / "oauth1_token.json").write_text("{corrupt")
        (tmp_token_dir / "oauth2_token.json").write_text('{"valid": true}')
        store = FileTokenStore(tmp_token_dir)
        loaded = store.load()
        # Should load the valid file and skip the corrupt one
        assert loaded is not None
        assert "oauth2_token.json" in loaded
        assert "oauth1_token.json" not in loaded

    def test_get_garth_dir(self, tmp_token_dir: Path) -> None:
        store = FileTokenStore(tmp_token_dir)
        assert store.get_garth_dir() == tmp_token_dir

    def test_tilde_expansion(self) -> None:
        store = FileTokenStore("~/test-garmin")
        assert "~" not in str(store.path)
        assert store.path.is_absolute()

    def test_overwrite_existing(self, tmp_token_dir: Path) -> None:
        store = FileTokenStore(tmp_token_dir)
        store.save({"oauth1_token.json": {"v": 1}})
        store.save({"oauth1_token.json": {"v": 2}})
        loaded = store.load()
        assert loaded["oauth1_token.json"]["v"] == 2


class TestDBTokenStore:
    """DBTokenStore tests — connection failure handling (no real DB)."""

    def test_import_error_without_psycopg2(self) -> None:
        from garmin_auth.storage import DBTokenStore
        store = DBTokenStore("postgresql://fake:fake@localhost/fake")
        # Should not crash on init, only on connect
        assert store.database_url == "postgresql://fake:fake@localhost/fake"

    def test_load_returns_none_on_connection_failure(self) -> None:
        from garmin_auth.storage import DBTokenStore
        store = DBTokenStore("postgresql://fake:fake@localhost:5432/fake")
        result = store.load()
        assert result is None

    def test_save_does_not_crash_on_connection_failure(self) -> None:
        from garmin_auth.storage import DBTokenStore
        store = DBTokenStore("postgresql://fake:fake@localhost:5432/fake")
        # Should log warning but not raise
        store.save({"oauth1_token.json": {"token": "test"}})
