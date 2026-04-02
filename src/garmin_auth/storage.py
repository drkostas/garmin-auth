"""Token storage backends — file-based (default) and PostgreSQL."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class TokenStore(ABC):
    """Abstract token storage interface."""

    @abstractmethod
    def load(self) -> Optional[dict]:
        """Load tokens. Returns dict with 'oauth1_token.json' and 'oauth2_token.json' keys, or None."""
        ...

    @abstractmethod
    def save(self, tokens: dict) -> None:
        """Save tokens dict with 'oauth1_token.json' and 'oauth2_token.json' keys."""
        ...


class FileTokenStore(TokenStore):
    """Store tokens as JSON files in a directory (garth-compatible format)."""

    def __init__(self, path: str | Path = "~/.garminconnect"):
        self.path = Path(path).expanduser()

    def load(self) -> Optional[dict]:
        if not self.path.exists():
            return None
        tokens = {}
        for f in self.path.iterdir():
            if f.is_file() and f.suffix == ".json":
                try:
                    tokens[f.name] = json.loads(f.read_text())
                except (json.JSONDecodeError, OSError):
                    pass
        return tokens if tokens else None

    def save(self, tokens: dict) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        for filename, data in tokens.items():
            content = json.dumps(data) if isinstance(data, dict) else str(data)
            (self.path / filename).write_text(content)

    def get_garth_dir(self) -> Path:
        """Return path for garth/garminconnect to load from."""
        return self.path


class DBTokenStore(TokenStore):
    """Store tokens in a PostgreSQL database (platform_credentials table).

    Requires the `db` extra: pip install garmin-auth[db]

    The table must have columns: platform (PK), auth_type, credentials (JSONB), status.
    """

    def __init__(self, database_url: str, platform: str = "garmin_tokens"):
        self.database_url = database_url
        self.platform = platform

    def _connect(self):
        try:
            import psycopg2
        except ImportError:
            raise ImportError(
                "psycopg2 is required for DB token storage. "
                "Install with: pip install garmin-auth[db]"
            )
        return psycopg2.connect(self.database_url)

    def load(self) -> Optional[dict]:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT credentials FROM platform_credentials WHERE platform = %s LIMIT 1",
                        (self.platform,),
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        creds = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                        # Normalize nested JSON strings
                        for key in ("oauth1_token.json", "oauth2_token.json"):
                            if key in creds and isinstance(creds[key], str):
                                creds[key] = json.loads(creds[key])
                        return creds
        except Exception as e:
            print(f"[garmin-auth] DB load failed: {e}")
        return None

    def save(self, tokens: dict) -> None:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO platform_credentials (platform, auth_type, credentials, status)
                        VALUES (%s, 'oauth', %s, 'active')
                        ON CONFLICT (platform) DO UPDATE SET credentials = EXCLUDED.credentials
                        """,
                        (self.platform, json.dumps(tokens)),
                    )
                conn.commit()
        except Exception as e:
            print(f"[garmin-auth] DB save failed: {e}")
