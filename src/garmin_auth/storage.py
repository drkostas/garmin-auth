"""Token storage backends for garminconnect 0.3.0 single-file DI OAuth tokens.

Token payload shape (from ``garminconnect.Client.dumps()``)::

    {"di_token": "...", "di_refresh_token": "...", "di_client_id": "..."}

Stored as a JSON string both on disk (``garmin_tokens.json``) and in Postgres.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

logger = logging.getLogger("garmin_auth")

TOKEN_FILE_NAME = "garmin_tokens.json"


class TokenStore(ABC):
    """Abstract token storage interface.

    Implementations return the raw JSON string so it can be passed directly to
    ``garminconnect.Client.loads()``. They accept either a raw JSON string or a
    dict (which is serialised) when saving.
    """

    @abstractmethod
    def load(self) -> Optional[str]:
        """Load the serialized token JSON, or None if not present."""
        ...

    @abstractmethod
    def save(self, tokens: str | dict) -> None:
        """Save the token payload (JSON string or dict)."""
        ...

    @abstractmethod
    def delete(self) -> None:
        """Clear the saved tokens. Called when they are rejected as stale."""
        ...


def _normalize(tokens: str | dict) -> str:
    if isinstance(tokens, dict):
        return json.dumps(tokens)
    return tokens


class FileTokenStore(TokenStore):
    """Store the token payload as ``garmin_tokens.json`` inside a directory."""

    def __init__(self, path: str | Path = "~/.garminconnect"):
        self.path = Path(path).expanduser()

    @property
    def token_path(self) -> Path:
        return self.path / TOKEN_FILE_NAME

    def load(self) -> Optional[str]:
        target = self.token_path
        if not target.exists():
            return None
        try:
            content = target.read_text()
            # Validate it parses as JSON with the expected shape before returning
            data = json.loads(content)
            if not isinstance(data, dict) or "di_token" not in data:
                logger.debug("Token file at %s missing di_token, ignoring", target)
                return None
            return content
        except (json.JSONDecodeError, OSError) as e:
            logger.debug("Failed to read token file %s: %s", target, e)
            return None

    def save(self, tokens: str | dict) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(_normalize(tokens))

    def delete(self) -> None:
        target = self.token_path
        if target.exists():
            try:
                target.unlink()
            except OSError as e:
                logger.warning("Could not delete stale token file %s: %s", target, e)

    def get_dir(self) -> Path:
        """Return the directory path for garminconnect ``tokenstore`` argument."""
        return self.path

    def get_garth_dir(self) -> Path:
        """Deprecated alias for :meth:`get_dir`.

        Kept for one release so downstream code that still calls
        ``store.get_garth_dir()`` from the 0.2.x API degrades gracefully.
        ``garth`` itself is no longer used; the directory is still used to
        hand ``garmin_tokens.json`` to garminconnect 0.3.0.
        """
        import warnings

        warnings.warn(
            "FileTokenStore.get_garth_dir() is deprecated; use get_dir() instead. "
            "garth is no longer a dependency of garmin-auth.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.get_dir()


class DBTokenStore(TokenStore):
    """Store the token payload in PostgreSQL (``platform_credentials`` table).

    Requires the ``db`` extra: ``pip install garmin-auth[db]``.

    Schema: ``platform`` (PK), ``auth_type``, ``credentials`` (JSONB), ``status``.
    The serialized JSON payload is stored under key ``garmin_tokens`` inside the
    ``credentials`` JSONB column so existing tables keep working.
    """

    def __init__(self, database_url: str, platform: str = "garmin_tokens"):
        self.database_url = database_url
        self.platform = platform

    def _connect(self):
        try:
            import psycopg2
        except ImportError as exc:
            raise ImportError(
                "psycopg2 is required for DB token storage. "
                "Install with: pip install garmin-auth[db]"
            ) from exc
        return psycopg2.connect(self.database_url)

    def load(self) -> Optional[str]:
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT credentials FROM platform_credentials "
                    "WHERE platform = %s LIMIT 1",
                    (self.platform,),
                )
                row = cur.fetchone()
                if not row or not row[0]:
                    return None
                creds = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                # New format: payload stored under "garmin_tokens"
                if isinstance(creds, dict) and "garmin_tokens" in creds:
                    payload = creds["garmin_tokens"]
                    if isinstance(payload, dict):
                        if "di_token" not in payload:
                            return None
                        return json.dumps(payload)
                    return payload if isinstance(payload, str) else None
                # Legacy 0.2.x format had oauth1/oauth2 keys — treat as stale
                if isinstance(creds, dict) and (
                    "oauth1_token.json" in creds or "oauth2_token.json" in creds
                ):
                    logger.info(
                        "DB has legacy oauth1/oauth2 tokens (garmin-auth <0.3). "
                        "Rejecting and forcing re-auth."
                    )
                    return None
                return None
        except Exception as e:
            logger.warning("DB token load failed: %s", e)
            return None

    def save(self, tokens: str | dict) -> None:
        payload = (
            tokens if isinstance(tokens, dict) else json.loads(_normalize(tokens))
        )
        wrapped = json.dumps({"garmin_tokens": payload})
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO platform_credentials (platform, auth_type, credentials, status)
                    VALUES (%s, 'oauth', %s, 'active')
                    ON CONFLICT (platform) DO UPDATE SET credentials = EXCLUDED.credentials
                    """,
                    (self.platform, wrapped),
                )
                conn.commit()
        except Exception as e:
            logger.warning("DB token save failed: %s", e)

    def delete(self) -> None:
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM platform_credentials WHERE platform = %s",
                    (self.platform,),
                )
                conn.commit()
        except Exception as e:
            logger.warning("DB token delete failed: %s", e)
