"""Tests for token storage backends (garminconnect 0.3.0 DI token payload)."""

from __future__ import annotations

import json
from pathlib import Path

from garmin_auth.storage import FileTokenStore


class TestFileTokenStore:
    """FileTokenStore tests — single ``garmin_tokens.json`` file format."""

    def test_load_empty_dir(self, tmp_token_dir: Path) -> None:
        store = FileTokenStore(tmp_token_dir)
        assert store.load() is None

    def test_load_nonexistent_dir(self, tmp_path: Path) -> None:
        store = FileTokenStore(tmp_path / "does-not-exist")
        assert store.load() is None

    def test_save_creates_dir_and_file(self, tmp_path: Path, fresh_token_payload: dict) -> None:
        target = tmp_path / "new" / "nested" / "dir"
        store = FileTokenStore(target)
        store.save(fresh_token_payload)
        assert target.exists()
        assert (target / "garmin_tokens.json").exists()

    def test_save_load_roundtrip_dict(
        self, tmp_token_dir: Path, fresh_token_payload: dict
    ) -> None:
        store = FileTokenStore(tmp_token_dir)
        store.save(fresh_token_payload)
        loaded = store.load()
        assert loaded is not None
        assert json.loads(loaded) == fresh_token_payload

    def test_save_load_roundtrip_string(
        self, tmp_token_dir: Path, fresh_token_payload: dict
    ) -> None:
        blob = json.dumps(fresh_token_payload)
        store = FileTokenStore(tmp_token_dir)
        store.save(blob)
        loaded = store.load()
        assert loaded is not None
        assert json.loads(loaded) == fresh_token_payload

    def test_load_rejects_payload_without_di_token(self, tmp_token_dir: Path) -> None:
        (tmp_token_dir / "garmin_tokens.json").write_text(
            json.dumps({"some_other_field": "value"})
        )
        store = FileTokenStore(tmp_token_dir)
        assert store.load() is None

    def test_load_rejects_corrupt_json(self, tmp_token_dir: Path) -> None:
        (tmp_token_dir / "garmin_tokens.json").write_text("{corrupt")
        store = FileTokenStore(tmp_token_dir)
        assert store.load() is None

    def test_delete_removes_file(
        self, tmp_token_dir: Path, fresh_token_payload: dict
    ) -> None:
        store = FileTokenStore(tmp_token_dir)
        store.save(fresh_token_payload)
        assert store.load() is not None
        store.delete()
        assert store.load() is None

    def test_delete_missing_file_is_noop(self, tmp_token_dir: Path) -> None:
        store = FileTokenStore(tmp_token_dir)
        store.delete()  # should not raise

    def test_legacy_oauth_files_ignored(self, legacy_oauth_tokens_file: Path) -> None:
        """Legacy 0.2.x oauth1/oauth2 files must not be picked up by 0.3.0 store."""
        store = FileTokenStore(legacy_oauth_tokens_file)
        assert store.load() is None

    def test_get_dir(self, tmp_token_dir: Path) -> None:
        store = FileTokenStore(tmp_token_dir)
        assert store.get_dir() == tmp_token_dir

    def test_get_garth_dir_deprecation_alias(self, tmp_token_dir: Path) -> None:
        import warnings

        store = FileTokenStore(tmp_token_dir)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = store.get_garth_dir()
        assert result == tmp_token_dir
        assert any(issubclass(x.category, DeprecationWarning) for x in w)
        assert any("get_dir" in str(x.message) for x in w)

    def test_tilde_expansion(self) -> None:
        store = FileTokenStore("~/test-garmin")
        assert "~" not in str(store.path)
        assert store.path.is_absolute()

    def test_overwrite_existing(self, tmp_token_dir: Path) -> None:
        store = FileTokenStore(tmp_token_dir)
        store.save({"di_token": "v1", "di_refresh_token": "r1", "di_client_id": "c"})
        store.save({"di_token": "v2", "di_refresh_token": "r2", "di_client_id": "c"})
        loaded = store.load()
        assert loaded is not None
        assert json.loads(loaded)["di_token"] == "v2"


class TestDBTokenStore:
    """DBTokenStore — failure-path smoke tests without a real DB."""

    def test_init_does_not_connect(self) -> None:
        from garmin_auth.storage import DBTokenStore

        store = DBTokenStore("postgresql://fake:fake@localhost/fake")
        assert store.database_url == "postgresql://fake:fake@localhost/fake"

    def test_load_returns_none_on_connection_failure(self) -> None:
        from garmin_auth.storage import DBTokenStore

        store = DBTokenStore("postgresql://fake:fake@localhost:5432/fake")
        assert store.load() is None

    def test_save_does_not_crash_on_connection_failure(
        self, fresh_token_payload: dict
    ) -> None:
        from garmin_auth.storage import DBTokenStore

        store = DBTokenStore("postgresql://fake:fake@localhost:5432/fake")
        store.save(fresh_token_payload)  # should log warning, not raise

    def test_delete_does_not_crash_on_connection_failure(self) -> None:
        from garmin_auth.storage import DBTokenStore

        store = DBTokenStore("postgresql://fake:fake@localhost:5432/fake")
        store.delete()  # should log warning, not raise
