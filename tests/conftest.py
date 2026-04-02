"""Shared fixtures for garmin-auth tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


@pytest.fixture
def tmp_token_dir(tmp_path: Path) -> Path:
    """Empty temp directory for token storage."""
    d = tmp_path / "tokens"
    d.mkdir()
    return d


@pytest.fixture
def fresh_oauth1() -> dict:
    """Valid OAuth1 token."""
    return {
        "oauth_token": "test-oauth1-token",
        "oauth_token_secret": "test-oauth1-secret",
        "domain": "garmin.com",
    }


@pytest.fixture
def fresh_oauth2() -> dict:
    """Valid OAuth2 token with 24h remaining."""
    return {
        "access_token": "test-access-token",
        "token_type": "Bearer",
        "expires_in": 86400,
        "expires_at": int(time.time()) + 86400,
        "refresh_token": "test-refresh-token",
        "refresh_token_expires_in": 7776000,
        "refresh_token_expires_at": int(time.time()) + 7776000,
    }


@pytest.fixture
def expired_oauth2() -> dict:
    """Expired OAuth2 token."""
    return {
        "access_token": "expired-token",
        "token_type": "Bearer",
        "expires_in": 86400,
        "expires_at": int(time.time()) - 3600,  # expired 1h ago
        "refresh_token": "test-refresh-token",
    }


@pytest.fixture
def fresh_tokens(fresh_oauth1: dict, fresh_oauth2: dict) -> dict:
    """Complete token set with fresh OAuth2."""
    return {
        "oauth1_token.json": fresh_oauth1,
        "oauth2_token.json": fresh_oauth2,
    }


@pytest.fixture
def expired_tokens(fresh_oauth1: dict, expired_oauth2: dict) -> dict:
    """Complete token set with expired OAuth2."""
    return {
        "oauth1_token.json": fresh_oauth1,
        "oauth2_token.json": expired_oauth2,
    }


@pytest.fixture
def token_dir_with_fresh_tokens(tmp_token_dir: Path, fresh_tokens: dict) -> Path:
    """Temp directory pre-populated with fresh tokens."""
    for filename, data in fresh_tokens.items():
        (tmp_token_dir / filename).write_text(json.dumps(data))
    return tmp_token_dir


@pytest.fixture
def token_dir_with_expired_tokens(tmp_token_dir: Path, expired_tokens: dict) -> Path:
    """Temp directory pre-populated with expired tokens."""
    for filename, data in expired_tokens.items():
        (tmp_token_dir / filename).write_text(json.dumps(data))
    return tmp_token_dir
