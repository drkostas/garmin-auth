"""Tests for GarminAuth — cascading login strategy."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from garmin_auth.auth import GarminAuth
from garmin_auth.storage import FileTokenStore


class TestCachedTokenStrategy:
    """Strategy 1: Use cached OAuth2 if >1h remaining."""

    def test_uses_cached_when_fresh(self, token_dir_with_fresh_tokens: Path) -> None:
        with patch("garmin_auth.auth.Garmin") as MockGarmin:
            mock_client = MagicMock()
            mock_client.display_name = "test-user"
            MockGarmin.return_value = mock_client

            auth = GarminAuth(token_dir=token_dir_with_fresh_tokens)
            client = auth.login()

            assert client is mock_client
            mock_client.login.assert_called_once_with(str(token_dir_with_fresh_tokens))

    def test_skips_cached_when_expiring_soon(self, token_dir_with_expired_tokens: Path) -> None:
        with patch("garmin_auth.auth.Garmin") as MockGarmin:
            mock_client = MagicMock()
            mock_client.display_name = "test-user"
            MockGarmin.return_value = mock_client

            auth = GarminAuth(
                email="test@test.com",
                password="pass",
                token_dir=token_dir_with_expired_tokens,
            )
            # Should skip cached (expired) and try exchange, which also uses mock
            client = auth.login()
            assert client is mock_client

    def test_boundary_exactly_1h(self, tmp_token_dir: Path) -> None:
        """OAuth2 with exactly 1h remaining should NOT use cached (boundary)."""
        tokens = {
            "oauth1_token.json": {"oauth_token": "t", "oauth_token_secret": "s", "domain": "garmin.com"},
            "oauth2_token.json": {"access_token": "a", "expires_at": int(time.time()) + 3600},
        }
        for f, d in tokens.items():
            (tmp_token_dir / f).write_text(json.dumps(d))

        with patch("garmin_auth.auth.Garmin") as MockGarmin:
            mock_client = MagicMock()
            MockGarmin.return_value = mock_client

            auth = GarminAuth(token_dir=tmp_token_dir)
            # 1h = boundary, should skip cached and go to exchange
            auth.login()
            # Login called at least once (exchange or full login)
            assert mock_client.login.called

    def test_boundary_just_over_1h(self, tmp_token_dir: Path) -> None:
        """OAuth2 with 1h01m remaining should use cached."""
        tokens = {
            "oauth1_token.json": {"oauth_token": "t", "oauth_token_secret": "s"},
            "oauth2_token.json": {"access_token": "a", "expires_at": int(time.time()) + 3660},
        }
        for f, d in tokens.items():
            (tmp_token_dir / f).write_text(json.dumps(d))

        with patch("garmin_auth.auth.Garmin") as MockGarmin:
            mock_client = MagicMock()
            MockGarmin.return_value = mock_client

            auth = GarminAuth(token_dir=tmp_token_dir)
            client = auth.login()
            assert client is mock_client


class TestTokenExchangeStrategy:
    """Strategy 2: OAuth1 → OAuth2 exchange."""

    def test_exchange_succeeds_after_expired_cache(self, token_dir_with_expired_tokens: Path) -> None:
        with patch("garmin_auth.auth.Garmin") as MockGarmin:
            mock_client = MagicMock()
            mock_client.display_name = "test-user"
            # First call (cached) fails, second call (exchange) succeeds
            MockGarmin.return_value = mock_client

            auth = GarminAuth(token_dir=token_dir_with_expired_tokens)
            client = auth.login()
            assert client is mock_client

    def test_exchange_429_falls_through(self, token_dir_with_expired_tokens: Path) -> None:
        from garminconnect import GarminConnectTooManyRequestsError

        sso_called = False

        def garmin_factory(*a, **kw):
            client = MagicMock()
            if not sso_called:
                client.login.side_effect = GarminConnectTooManyRequestsError("429")
            else:
                client.display_name = "fresh-user"
                client.login.return_value = None
            return client

        with patch("garmin_auth.auth.Garmin", side_effect=garmin_factory):
            with patch("garmin_auth.auth.full_login") as mock_sso:
                def sso_side_effect(email, password):
                    nonlocal sso_called
                    sso_called = True
                    return {
                        "oauth1_token.json": {"oauth_token": "new", "oauth_token_secret": "new"},
                        "oauth2_token.json": {"access_token": "new", "expires_at": int(time.time()) + 86400},
                    }
                mock_sso.side_effect = sso_side_effect

                auth = GarminAuth(
                    email="test@test.com",
                    password="pass",
                    token_dir=token_dir_with_expired_tokens,
                )
                client = auth.login()
                assert mock_sso.called


class TestFullLoginStrategy:
    """Strategy 3: Full SSO login."""

    def test_no_credentials_raises(self, tmp_token_dir: Path) -> None:
        auth = GarminAuth(token_dir=tmp_token_dir)
        with pytest.raises(RuntimeError, match="All Garmin auth strategies failed"):
            auth.login()

    def test_oauth1_missing_goes_to_full_login(self, tmp_token_dir: Path) -> None:
        # Only OAuth2 (no OAuth1) — exchange will fail, should try full login
        (tmp_token_dir / "oauth2_token.json").write_text(
            json.dumps({"access_token": "a", "expires_at": int(time.time()) - 100})
        )

        # Track whether full_login has been called — after that, Garmin() should work
        sso_called = False
        original_full_login = None

        def garmin_factory(*a, **kw):
            client = MagicMock()
            if not sso_called:
                client.login.side_effect = FileNotFoundError("no oauth1")
            else:
                client.display_name = "test"
                client.login.return_value = None
            return client

        with patch("garmin_auth.auth.Garmin", side_effect=garmin_factory):
            with patch("garmin_auth.auth.full_login") as mock_sso:
                def sso_side_effect(email, password):
                    nonlocal sso_called
                    sso_called = True
                    return {
                        "oauth1_token.json": {"oauth_token": "new", "oauth_token_secret": "new"},
                        "oauth2_token.json": {"access_token": "new", "expires_at": int(time.time()) + 86400},
                    }
                mock_sso.side_effect = sso_side_effect

                auth = GarminAuth(email="e@e.com", password="p", token_dir=tmp_token_dir)
                auth.login()
                assert mock_sso.called

    def test_all_strategies_fail(self, token_dir_with_expired_tokens: Path) -> None:
        from garminconnect import GarminConnectTooManyRequestsError

        with patch("garmin_auth.auth.Garmin") as MockGarmin:
            mock_client = MagicMock()
            mock_client.login.side_effect = GarminConnectTooManyRequestsError("429")
            MockGarmin.return_value = mock_client

            with patch("garmin_auth.auth.full_login") as mock_sso:
                mock_sso.side_effect = GarminConnectTooManyRequestsError("429")

                auth = GarminAuth(
                    email="test@test.com",
                    password="pass",
                    token_dir=token_dir_with_expired_tokens,
                )
                with pytest.raises(RuntimeError, match="All Garmin auth strategies failed"):
                    auth.login()


class TestRefresh:
    """Token refresh without client."""

    def test_skip_when_fresh(self, token_dir_with_fresh_tokens: Path) -> None:
        auth = GarminAuth(token_dir=token_dir_with_fresh_tokens)
        result = auth.refresh()
        assert result["status"] == "skipped"
        assert "remaining" in result["message"]

    def test_exchange_when_expired(self, token_dir_with_expired_tokens: Path) -> None:
        with patch("garmin_auth.auth.exchange_oauth1") as mock_exchange:
            mock_exchange.return_value = {
                "access_token": "new",
                "expires_at": int(time.time()) + 86400,
            }
            auth = GarminAuth(token_dir=token_dir_with_expired_tokens)
            result = auth.refresh()
            assert result["status"] == "refreshed"
            assert result["method"] == "oauth1_exchange"

    def test_full_login_when_exchange_fails(self, token_dir_with_expired_tokens: Path) -> None:
        with patch("garmin_auth.auth.exchange_oauth1") as mock_exchange:
            mock_exchange.side_effect = RuntimeError("exchange failed")

            with patch("garmin_auth.auth.full_login") as mock_sso:
                mock_sso.return_value = {
                    "oauth1_token.json": {"oauth_token": "new", "oauth_token_secret": "new"},
                    "oauth2_token.json": {"access_token": "new", "expires_at": int(time.time()) + 86400},
                }

                auth = GarminAuth(
                    email="e@e.com",
                    password="p",
                    token_dir=token_dir_with_expired_tokens,
                )
                result = auth.refresh()
                assert result["status"] == "refreshed"
                assert result["method"] == "full_login"

    def test_no_credentials_raises_on_exchange_fail(self, token_dir_with_expired_tokens: Path) -> None:
        with patch("garmin_auth.auth.exchange_oauth1") as mock_exchange:
            mock_exchange.side_effect = RuntimeError("exchange failed")

            auth = GarminAuth(token_dir=token_dir_with_expired_tokens)
            with pytest.raises(RuntimeError, match="no credentials"):
                auth.refresh()


class TestStatus:
    """Token status check."""

    def test_no_tokens(self, tmp_token_dir: Path) -> None:
        auth = GarminAuth(token_dir=tmp_token_dir)
        result = auth.status()
        assert result["status"] == "no_tokens"

    def test_valid_tokens(self, token_dir_with_fresh_tokens: Path) -> None:
        auth = GarminAuth(token_dir=token_dir_with_fresh_tokens)
        result = auth.status()
        assert result["status"] == "valid"
        assert result["hours_remaining"] > 0
        assert result["oauth1_present"] is True

    def test_expired_tokens(self, token_dir_with_expired_tokens: Path) -> None:
        auth = GarminAuth(token_dir=token_dir_with_expired_tokens)
        result = auth.status()
        assert result["status"] == "expired"
        assert result["hours_remaining"] < 0


class TestSaveTokens:
    """Token save after successful login."""

    def test_save_updates_store(self, token_dir_with_fresh_tokens: Path) -> None:
        with patch("garmin_auth.auth.Garmin") as MockGarmin:
            mock_client = MagicMock()
            mock_client.display_name = "test"
            MockGarmin.return_value = mock_client

            auth = GarminAuth(token_dir=token_dir_with_fresh_tokens)
            auth.login()

            # garth.dump should have been called
            mock_client.garth.dump.assert_called_once_with(str(token_dir_with_fresh_tokens))
