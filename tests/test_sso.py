"""Tests for SSO login flow — all HTTP mocked."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from garmin_auth.sso import exchange_oauth1, full_login


def _mock_session_responses(
    embed_html: str = "<html></html>",
    signin_html: str = '<input name="_csrf" value="test-csrf-123" />',
    login_html: str = 'embed?ticket=ST-12345-test',
    login_status: int = 200,
    consumer_json: dict | None = None,
    preauth_text: str = "oauth_token=new-token&oauth_token_secret=new-secret",
    preauth_ok: bool = True,
    exchange_json: dict | None = None,
    exchange_ok: bool = True,
):
    """Helper to create a mock requests.Session with predefined responses."""
    if consumer_json is None:
        consumer_json = {"consumer_key": "test-ck", "consumer_secret": "test-cs"}
    if exchange_json is None:
        exchange_json = {"access_token": "new-at", "expires_in": 86400, "refresh_token_expires_in": 7776000}

    responses = []

    # Step 1: embed GET
    r1 = MagicMock()
    r1.text = embed_html
    responses.append(r1)

    # Step 2: signin GET
    r2 = MagicMock()
    r2.text = signin_html
    responses.append(r2)

    # Step 3: signin POST
    r3 = MagicMock()
    r3.text = login_html
    r3.status_code = login_status
    responses.append(r3)

    # Step 5: consumer GET
    r4 = MagicMock()
    r4.json.return_value = consumer_json
    r4.ok = True
    r4.raise_for_status.return_value = None
    responses.append(r4)

    # Step 6: preauth GET
    r5 = MagicMock()
    r5.text = preauth_text
    r5.ok = preauth_ok
    r5.status_code = 200 if preauth_ok else 401
    responses.append(r5)

    return responses, exchange_json


class TestFullLogin:
    """Full SSO login flow tests."""

    def test_successful_login(self) -> None:
        responses, exchange_json = _mock_session_responses()

        with patch("garmin_auth.sso.requests.Session") as MockSession:
            session = MagicMock()
            session.headers = {}
            session.get.side_effect = [responses[0], responses[1], responses[3], responses[4]]
            session.post.side_effect = [responses[2]]
            MockSession.return_value = session

            with patch("garmin_auth.sso.exchange_oauth1") as mock_exchange:
                mock_exchange.return_value = {
                    "access_token": "new-at",
                    "expires_at": int(time.time()) + 86400,
                }

                result = full_login("test@test.com", "password123")

                assert "oauth1_token.json" in result
                assert "oauth2_token.json" in result
                assert result["oauth1_token.json"]["oauth_token"] == "new-token"
                assert result["oauth1_token.json"]["oauth_token_secret"] == "new-secret"

    def test_invalid_credentials(self) -> None:
        responses, _ = _mock_session_responses(
            login_html='<html><title>Sign In</title>Your sign in was incorrect</html>',
        )

        with patch("garmin_auth.sso.requests.Session") as MockSession:
            session = MagicMock()
            session.headers = {}
            session.get.side_effect = [responses[0], responses[1]]
            session.post.side_effect = [responses[2]]
            MockSession.return_value = session

            with pytest.raises(RuntimeError, match="Invalid email or password"):
                full_login("bad@test.com", "wrongpass")

    def test_account_locked(self) -> None:
        responses, _ = _mock_session_responses(
            login_html='<html>Your account has been locked</html>',
        )

        with patch("garmin_auth.sso.requests.Session") as MockSession:
            session = MagicMock()
            session.headers = {}
            session.get.side_effect = [responses[0], responses[1]]
            session.post.side_effect = [responses[2]]
            MockSession.return_value = session

            with pytest.raises(RuntimeError, match="locked"):
                full_login("locked@test.com", "pass")

    def test_mfa_required(self) -> None:
        responses, _ = _mock_session_responses(
            login_html='<html>MFA verification required</html>',
        )

        with patch("garmin_auth.sso.requests.Session") as MockSession:
            session = MagicMock()
            session.headers = {}
            session.get.side_effect = [responses[0], responses[1]]
            session.post.side_effect = [responses[2]]
            MockSession.return_value = session

            with pytest.raises(RuntimeError, match="MFA required"):
                full_login("mfa@test.com", "pass")

    def test_rate_limited_429_json(self) -> None:
        responses, _ = _mock_session_responses(
            login_html='{"error":{"status-code":"429","message":"{}"}}',
            login_status=429,
        )

        with patch("garmin_auth.sso.requests.Session") as MockSession:
            session = MagicMock()
            session.headers = {}
            session.get.side_effect = [responses[0], responses[1]]
            session.post.side_effect = [responses[2]]
            MockSession.return_value = session

            with pytest.raises(RuntimeError, match="rate limited"):
                full_login("test@test.com", "pass")

    def test_rate_limited_429_status(self) -> None:
        r_login = MagicMock()
        r_login.text = "Too many requests"
        r_login.status_code = 429

        responses, _ = _mock_session_responses()

        with patch("garmin_auth.sso.requests.Session") as MockSession:
            session = MagicMock()
            session.headers = {}
            session.get.side_effect = [responses[0], responses[1]]
            session.post.side_effect = [r_login]
            MockSession.return_value = session

            with pytest.raises(RuntimeError, match="rate limited"):
                full_login("test@test.com", "pass")

    def test_csrf_not_found(self) -> None:
        responses, _ = _mock_session_responses(
            signin_html='<html>No csrf here</html>',
        )

        with patch("garmin_auth.sso.requests.Session") as MockSession:
            session = MagicMock()
            session.headers = {}
            session.get.side_effect = [responses[0], responses[1]]
            MockSession.return_value = session

            with pytest.raises(RuntimeError, match="CSRF token"):
                full_login("test@test.com", "pass")

    def test_csrf_with_special_chars(self) -> None:
        responses, _ = _mock_session_responses(
            signin_html='<input name="_csrf" value="abc&quot;def<>123" />',
        )

        with patch("garmin_auth.sso.requests.Session") as MockSession:
            session = MagicMock()
            session.headers = {}
            session.get.side_effect = [responses[0], responses[1], responses[3], responses[4]]
            session.post.side_effect = [responses[2]]
            MockSession.return_value = session

            with patch("garmin_auth.sso.exchange_oauth1") as mock_exchange:
                mock_exchange.return_value = {"access_token": "t", "expires_at": int(time.time()) + 86400}
                result = full_login("test@test.com", "pass")
                assert result["oauth1_token.json"]["oauth_token"] == "new-token"

    def test_preauth_failure(self) -> None:
        responses, _ = _mock_session_responses(preauth_ok=False, preauth_text="Unauthorized")

        with patch("garmin_auth.sso.requests.Session") as MockSession:
            session = MagicMock()
            session.headers = {}
            session.get.side_effect = [responses[0], responses[1], responses[3], responses[4]]
            session.post.side_effect = [responses[2]]
            MockSession.return_value = session

            with pytest.raises(RuntimeError, match="OAuth1 token exchange failed"):
                full_login("test@test.com", "pass")

    def test_empty_oauth1_in_preauth(self) -> None:
        responses, _ = _mock_session_responses(preauth_text="oauth_token=&oauth_token_secret=")

        with patch("garmin_auth.sso.requests.Session") as MockSession:
            session = MagicMock()
            session.headers = {}
            session.get.side_effect = [responses[0], responses[1], responses[3], responses[4]]
            session.post.side_effect = [responses[2]]
            MockSession.return_value = session

            with pytest.raises(RuntimeError, match="No OAuth1 token"):
                full_login("test@test.com", "pass")

    def test_unknown_error_page(self) -> None:
        responses, _ = _mock_session_responses(
            login_html='<html><title>Error</title><div>Something went wrong</div></html>',
        )

        with patch("garmin_auth.sso.requests.Session") as MockSession:
            session = MagicMock()
            session.headers = {}
            session.get.side_effect = [responses[0], responses[1]]
            session.post.side_effect = [responses[2]]
            MockSession.return_value = session

            with pytest.raises(RuntimeError, match="SSO login failed"):
                full_login("test@test.com", "pass")


class TestExchangeOAuth1:
    """OAuth1 → OAuth2 exchange tests."""

    def test_successful_exchange(self) -> None:
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "access_token": "new-at",
            "expires_in": 86400,
            "refresh_token_expires_in": 7776000,
        }

        with patch("garmin_auth.sso.requests.post", return_value=mock_resp):
            result = exchange_oauth1(
                {"oauth_token": "tok", "oauth_token_secret": "sec", "domain": "garmin.com"}
            )
            assert result["access_token"] == "new-at"
            assert result["expires_at"] > int(time.time())
            assert result["refresh_token_expires_at"] > int(time.time())

    def test_exchange_failure(self) -> None:
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"

        with patch("garmin_auth.sso.requests.post", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="exchange failed.*401"):
                exchange_oauth1(
                    {"oauth_token": "tok", "oauth_token_secret": "sec"}
                )
