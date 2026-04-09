"""Type definitions for garmin-auth tokens and responses (garminconnect 0.3.0)."""

from __future__ import annotations

from typing import TypedDict


class DITokenPayload(TypedDict, total=False):
    """Serialized payload produced by ``garminconnect.Client.dumps()``."""

    di_token: str
    di_refresh_token: str
    di_client_id: str


class StatusResult(TypedDict, total=False):
    status: str  # "no_tokens" | "stored"
    store_type: str
    has_di_token: bool
    message: str


class RefreshResult(TypedDict, total=False):
    status: str  # "refreshed"
    display_name: str | None
