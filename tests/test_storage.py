"""Tests for token storage backends (garminconnect 0.3.0 DI token payload)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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

    # These three previously asserted the opposite: that a store which could not reach the
    # database returned None or reported a success anyway. That is what made a broken database
    # look like an expired credential, and a lost token look like a saved one. An unreachable
    # store must say so.

    def test_load_raises_on_connection_failure(self) -> None:
        from garmin_auth.storage import DBTokenStore

        store = DBTokenStore("postgresql://fake:fake@localhost:5432/fake")
        with pytest.raises(Exception):
            store.load()

    def test_save_raises_on_connection_failure(self, fresh_token_payload: dict) -> None:
        from garmin_auth.storage import DBTokenStore

        store = DBTokenStore("postgresql://fake:fake@localhost:5432/fake")
        with pytest.raises(Exception):
            store.save(fresh_token_payload)

    def test_delete_raises_on_connection_failure(self) -> None:
        from garmin_auth.storage import DBTokenStore

        store = DBTokenStore("postgresql://fake:fake@localhost:5432/fake")
        with pytest.raises(Exception):
            store.delete()

    def test_save_upsert_restores_status_auth_type_and_connected_at(self) -> None:
        """The update half must rewrite the flags, not only the payload.

        Setting them in the INSERT branch alone left every login after the first with whatever
        the row already held, so a status parked at the schema default of 'disconnected' stayed
        there while the tokens underneath it were healthy.
        """
        from garmin_auth.storage import DBTokenStore

        captured: list[str] = []

        class FakeCursor:
            def execute(self, sql: str, params: object = None) -> None:
                captured.append(" ".join(sql.split()))

            def __enter__(self) -> "FakeCursor":
                return self

            def __exit__(self, *a: object) -> None:
                return None

        class FakeConn:
            def cursor(self) -> FakeCursor:
                return FakeCursor()

            def commit(self) -> None:
                return None

            def __enter__(self) -> "FakeConn":
                return self

            def __exit__(self, *a: object) -> None:
                return None

        store = DBTokenStore("postgresql://fake:fake@localhost:5432/fake")
        store._connect = lambda: FakeConn()  # type: ignore[method-assign]
        store.save({"di_token": "t", "di_refresh_token": "r", "di_client_id": "c"})

        sql = captured[0]
        assert "ON CONFLICT (platform) DO UPDATE" in sql
        assert "credentials = EXCLUDED.credentials" in sql
        assert "status = EXCLUDED.status" in sql
        assert "auth_type = EXCLUDED.auth_type" in sql
        assert "connected_at = EXCLUDED.connected_at" in sql
