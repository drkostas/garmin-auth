"""Type definitions for garmin-auth tokens and responses."""

from __future__ import annotations

from typing import TypedDict


class OAuth1Token(TypedDict, total=False):
    oauth_token: str
    oauth_token_secret: str
    domain: str
    mfa_token: str
    mfa_expiration_timestamp: str


class OAuth2Token(TypedDict, total=False):
    access_token: str
    token_type: str
    expires_in: int
    expires_at: int
    refresh_token: str
    refresh_token_expires_in: int
    refresh_token_expires_at: int
    scope: str
    jti: str


class TokenDict(TypedDict, total=False):
    """Token storage format — keys match garth's file-based convention."""
    oauth1_token_json: OAuth1Token  # stored as "oauth1_token.json"
    oauth2_token_json: OAuth2Token  # stored as "oauth2_token.json"


class StatusResult(TypedDict):
    status: str  # "valid" | "expired" | "no_tokens"
    oauth1_present: bool
    oauth2_expires_at: str | None
    hours_remaining: float
    store_type: str


class RefreshResult(TypedDict, total=False):
    status: str  # "refreshed" | "skipped"
    method: str  # "oauth1_exchange" | "full_login"
    message: str
    expires_at: str
    hours_valid: str
