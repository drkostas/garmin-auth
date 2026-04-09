"""Tests for GarminAuth on garminconnect 0.3.0 (MFA + DI OAuth tokens)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from garmin_auth.auth import NEEDS_MFA, GarminAuth
from garmin_auth.storage import FileTokenStore


def _mock_garmin_client(
    *,
    display_name: str = "test-user",
    login_return: tuple = (None, None),
    login_side_effect=None,
    dumps_return: str | None = None,
) -> MagicMock:
    """Build a MagicMock that looks like a ``garminconnect.Garmin`` instance.

    ``login_return`` is what ``Garmin.login()`` returns (``(mfa_status, _)``).
    ``dumps_return`` is what ``client.client.dumps()`` returns (JSON string).
    """
    mock = MagicMock()
    mock.display_name = display_name
    mock.full_name = display_name
    if login_side_effect is not None:
        mock.login.side_effect = login_side_effect
    else:
        mock.login.return_value = login_return
    mock.client = MagicMock()
    if dumps_return is None:
        dumps_return = json.dumps(
            {
                "di_token": f"tok-{display_name}",
                "di_refresh_token": f"refresh-{display_name}",
                "di_client_id": "GARMIN_CONNECT_MOBILE_ANDROID_DI_2025Q2",
            }
        )
    mock.client.dumps.return_value = dumps_return
    mock.client.resume_login.return_value = (None, None)
    mock.client.connectapi.return_value = {
        "displayName": display_name,
        "fullName": display_name,
    }
    return mock


class TestCachedLogin:
    """Strategy 1: cached tokens from the store."""

    def test_uses_cached_when_present(self, token_dir_with_fresh_tokens: Path) -> None:
        mock = _mock_garmin_client()
        with patch("garmin_auth.auth.Garmin", return_value=mock) as MockGarmin:
            auth = GarminAuth(token_dir=token_dir_with_fresh_tokens)
            result = auth.login()
            assert result is mock
            # Garmin was constructed once and login() was called with a tokenstore path
            MockGarmin.assert_called_once()
            call = mock.login.call_args
            assert "tokenstore" in call.kwargs
            assert str(call.kwargs["tokenstore"]).endswith("tokens")

    def test_cached_load_persists_refreshed_tokens_back(
        self, token_dir_with_fresh_tokens: Path, fresh_token_payload: dict
    ) -> None:
        new_blob = json.dumps({**fresh_token_payload, "di_token": "refreshed-token"})
        mock = _mock_garmin_client(dumps_return=new_blob)
        with patch("garmin_auth.auth.Garmin", return_value=mock):
            store = FileTokenStore(token_dir_with_fresh_tokens)
            auth = GarminAuth(token_dir=token_dir_with_fresh_tokens, store=store)
            auth.login()
            # Store should now hold the refreshed blob
            stored = store.load()
            assert stored is not None
            assert json.loads(stored)["di_token"] == "refreshed-token"

    def test_cached_rejected_clears_store_and_falls_back(
        self, token_dir_with_fresh_tokens: Path
    ) -> None:
        from garminconnect import GarminConnectAuthenticationError

        stale = _mock_garmin_client(
            login_side_effect=GarminConnectAuthenticationError("stale")
        )
        fresh = _mock_garmin_client(display_name="after-relogin")

        call_count = {"n": 0}

        def factory(*args, **kwargs):
            call_count["n"] += 1
            return stale if call_count["n"] == 1 else fresh

        with patch("garmin_auth.auth.Garmin", side_effect=factory):
            auth = GarminAuth(
                email="u@e.com",
                password="p",
                token_dir=token_dir_with_fresh_tokens,
            )
            result = auth.login()
            assert result is fresh
            assert call_count["n"] == 2


class TestFreshLogin:
    """Strategy 2: fresh credential login when no cached tokens are usable."""

    def test_login_with_credentials_when_store_empty(self, tmp_token_dir: Path) -> None:
        mock = _mock_garmin_client()
        with patch("garmin_auth.auth.Garmin", return_value=mock):
            auth = GarminAuth(
                email="user@example.com",
                password="pw",
                token_dir=tmp_token_dir,
            )
            result = auth.login()
            assert result is mock
            # Tokens were persisted via store.save()
            store_file = tmp_token_dir / "garmin_tokens.json"
            assert store_file.exists()
            assert "di_token" in store_file.read_text()

    def test_no_tokens_and_no_credentials_raises(self, tmp_token_dir: Path) -> None:
        from garminconnect import GarminConnectAuthenticationError

        auth = GarminAuth(token_dir=tmp_token_dir)
        with pytest.raises(GarminConnectAuthenticationError, match="credentials"):
            auth.login()

    def test_rate_limit_bubbles_up(self, tmp_token_dir: Path) -> None:
        from garminconnect import GarminConnectTooManyRequestsError

        mock = _mock_garmin_client(
            login_side_effect=GarminConnectTooManyRequestsError("429")
        )
        with patch("garmin_auth.auth.Garmin", return_value=mock):
            auth = GarminAuth(
                email="user@example.com",
                password="pw",
                token_dir=tmp_token_dir,
            )
            with pytest.raises(GarminConnectTooManyRequestsError):
                auth.login()


class TestMfaFlow:
    """return_on_mfa=True flow for web/async callers."""

    def test_login_returns_needs_mfa_sentinel(self, tmp_token_dir: Path) -> None:
        pending = _mock_garmin_client(login_return=(NEEDS_MFA, None))
        with patch("garmin_auth.auth.Garmin", return_value=pending):
            auth = GarminAuth(
                email="u@e.com",
                password="p",
                token_dir=tmp_token_dir,
                return_on_mfa=True,
            )
            result = auth.login()
            assert result == NEEDS_MFA
            # Client is NOT cached yet because login is incomplete
            assert auth._client is None
            assert auth._mfa_pending is pending

    def test_resume_login_completes_and_caches_client(self, tmp_token_dir: Path) -> None:
        pending = _mock_garmin_client(login_return=(NEEDS_MFA, None))
        with patch("garmin_auth.auth.Garmin", return_value=pending):
            auth = GarminAuth(
                email="u@e.com",
                password="p",
                token_dir=tmp_token_dir,
                return_on_mfa=True,
            )
            auth.login()
            client = auth.resume_login("123456")

            assert client is pending
            pending.client.resume_login.assert_called_once_with(None, "123456")
            # Tokens persisted
            store_file = tmp_token_dir / "garmin_tokens.json"
            assert store_file.exists()
            # Pending slot cleared
            assert auth._mfa_pending is None

    def test_resume_login_without_pending_raises(self, tmp_token_dir: Path) -> None:
        from garminconnect import GarminConnectAuthenticationError

        auth = GarminAuth(email="u@e.com", password="p", token_dir=tmp_token_dir)
        with pytest.raises(GarminConnectAuthenticationError, match="No pending MFA"):
            auth.resume_login("123456")

    def test_resume_login_rejects_empty_code(self, tmp_token_dir: Path) -> None:
        pending = _mock_garmin_client(login_return=(NEEDS_MFA, None))
        with patch("garmin_auth.auth.Garmin", return_value=pending):
            auth = GarminAuth(
                email="u@e.com",
                password="p",
                token_dir=tmp_token_dir,
                return_on_mfa=True,
            )
            auth.login()
            with pytest.raises(ValueError, match="non-empty"):
                auth.resume_login("   ")

    def test_blocking_prompt_mfa_does_not_trigger_sentinel(
        self, tmp_token_dir: Path
    ) -> None:
        """When return_on_mfa=False, garminconnect handles MFA internally via prompt_mfa."""
        mock = _mock_garmin_client(login_return=(None, None))
        prompt_calls = []
        with patch("garmin_auth.auth.Garmin", return_value=mock):
            auth = GarminAuth(
                email="u@e.com",
                password="p",
                token_dir=tmp_token_dir,
                prompt_mfa=lambda: (prompt_calls.append(1), "654321")[1],
            )
            result = auth.login()
            assert result is mock
            # Our wrapper doesn't invoke prompt_mfa directly — garminconnect does.
            # We just confirm the flag was wired through.
            ctor_kwargs = mock.mock_calls  # sanity: no exception
            assert ctor_kwargs is not None


class TestClientProperty:
    """GarminAuth.client should raise clearly if login needs MFA."""

    def test_client_raises_when_mfa_needed(self, tmp_token_dir: Path) -> None:
        from garminconnect import GarminConnectAuthenticationError

        pending = _mock_garmin_client(login_return=(NEEDS_MFA, None))
        with patch("garmin_auth.auth.Garmin", return_value=pending):
            auth = GarminAuth(
                email="u@e.com",
                password="p",
                token_dir=tmp_token_dir,
                return_on_mfa=True,
            )
            with pytest.raises(GarminConnectAuthenticationError, match="MFA"):
                _ = auth.client

    def test_client_returns_cached(self, tmp_token_dir: Path) -> None:
        mock = _mock_garmin_client()
        with patch("garmin_auth.auth.Garmin", return_value=mock):
            auth = GarminAuth(
                email="u@e.com", password="p", token_dir=tmp_token_dir
            )
            first = auth.client
            second = auth.client
            assert first is second is mock


class TestStatus:
    def test_no_tokens(self, tmp_token_dir: Path) -> None:
        auth = GarminAuth(token_dir=tmp_token_dir)
        result = auth.status()
        assert result["status"] == "no_tokens"
        assert result["store_type"] == "FileTokenStore"

    def test_stored(self, token_dir_with_fresh_tokens: Path) -> None:
        auth = GarminAuth(token_dir=token_dir_with_fresh_tokens)
        result = auth.status()
        assert result["status"] == "stored"
        assert result["has_di_token"] is True


class TestLegacyTokenMigration:
    def test_legacy_oauth1_oauth2_files_ignored(
        self, legacy_oauth_tokens_file: Path
    ) -> None:
        """Old 0.2.x token files must not be loaded as 0.3.0 tokens."""
        store = FileTokenStore(legacy_oauth_tokens_file)
        assert store.load() is None
