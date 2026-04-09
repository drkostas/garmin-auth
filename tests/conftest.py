"""Shared fixtures for garmin-auth tests (garminconnect 0.3.0 token format)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def tmp_token_dir(tmp_path: Path) -> Path:
    """Empty temp directory for token storage."""
    d = tmp_path / "tokens"
    d.mkdir()
    return d


@pytest.fixture
def fresh_token_payload() -> dict:
    """A valid DI OAuth token payload (garminconnect 0.3.0 shape)."""
    return {
        "di_token": "test-di-access-token",
        "di_refresh_token": "test-di-refresh-token",
        "di_client_id": "GARMIN_CONNECT_MOBILE_ANDROID_DI_2025Q2",
    }


@pytest.fixture
def token_dir_with_fresh_tokens(tmp_token_dir: Path, fresh_token_payload: dict) -> Path:
    """Temp directory pre-populated with a fresh garmin_tokens.json file."""
    (tmp_token_dir / "garmin_tokens.json").write_text(json.dumps(fresh_token_payload))
    return tmp_token_dir


@pytest.fixture
def legacy_oauth_tokens_file(tmp_token_dir: Path) -> Path:
    """Temp directory pre-populated with legacy 0.2.x oauth1/oauth2 files.

    These should be treated as stale and ignored by the 0.3.0 store.
    """
    (tmp_token_dir / "oauth1_token.json").write_text(
        json.dumps({"oauth_token": "legacy", "oauth_token_secret": "legacy"})
    )
    (tmp_token_dir / "oauth2_token.json").write_text(
        json.dumps({"access_token": "legacy", "expires_at": 9999999999})
    )
    return tmp_token_dir
