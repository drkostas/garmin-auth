"""Main GarminAuth class — self-healing authentication with cascading fallbacks.

Auth strategy (in order):
1. Load tokens from store → if OAuth2 has >1h remaining, use it
2. Load tokens → OAuth1→OAuth2 exchange (fast refresh)
3. Full SSO login with email/password → fresh OAuth1 + OAuth2
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)
from garth.exc import GarthHTTPError

from garmin_auth.sso import exchange_oauth1, full_login
from garmin_auth.storage import FileTokenStore, TokenStore

logger = logging.getLogger("garmin_auth")

# Delay between API calls to avoid rate limiting
API_CALL_DELAY = 1.0


class GarminAuth:
    """Self-healing Garmin Connect authentication.

    Usage:
        auth = GarminAuth(email="user@example.com", password="pass")
        client = auth.login()  # Returns authenticated Garmin client

        # Or with custom token storage:
        from garmin_auth import FileTokenStore, DBTokenStore
        auth = GarminAuth(
            email="user@example.com",
            password="pass",
            store=DBTokenStore("postgresql://..."),
        )
    """

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        store: Optional[TokenStore] = None,
        token_dir: str | Path = "~/.garminconnect",
    ):
        self.email = email or os.environ.get("GARMIN_EMAIL", "")
        self.password = password or os.environ.get("GARMIN_PASSWORD", "")
        self.store = store or FileTokenStore(token_dir)
        self._client: Optional[Garmin] = None

        # If using FileTokenStore, ensure garth can find the tokens
        if isinstance(self.store, FileTokenStore):
            self._garth_dir = self.store.get_garth_dir()
        else:
            # DB store needs a temp file dir for garth compatibility
            self._garth_dir = Path(token_dir).expanduser()

    @property
    def client(self) -> Garmin:
        """Get the authenticated Garmin client, logging in if needed."""
        if self._client is None:
            self._client = self.login()
        return self._client

    def login(self) -> Garmin:
        """Authenticate with Garmin Connect using cascading fallback strategy.

        Returns:
            Authenticated Garmin client ready for API calls.

        Raises:
            RuntimeError: If all auth strategies fail.
        """
        # Load tokens from store → write to filesystem for garth
        tokens = self.store.load()
        if tokens:
            self._write_tokens_to_disk(tokens)

        # Strategy 1: Use cached OAuth2 if still fresh (>1h remaining)
        client = self._try_cached_token()
        if client:
            return client

        # Strategy 2: Token exchange (OAuth1 → new OAuth2)
        client = self._try_token_exchange()
        if client:
            return client

        # Strategy 3: Full SSO login with credentials
        client = self._try_full_login()
        if client:
            return client

        raise RuntimeError(
            "All Garmin auth strategies failed. Check credentials and rate limits."
        )

    def refresh(self) -> dict:
        """Refresh tokens without returning a client. Useful for token maintenance.

        Returns:
            Dict with status info: {"status": "refreshed"|"skipped", ...}
        """
        tokens = self.store.load()

        # Check if refresh is needed
        if tokens:
            oauth2 = tokens.get("oauth2_token.json", {})
            if isinstance(oauth2, str):
                oauth2 = json.loads(oauth2)
            expires_at = oauth2.get("expires_at", 0)
            hours_remaining = (expires_at - time.time()) / 3600
            if hours_remaining > 2:
                return {
                    "status": "skipped",
                    "message": f"Token still valid ({hours_remaining:.1f}h remaining)",
                    "expires_at": datetime.fromtimestamp(expires_at).isoformat(),
                }

        # Try OAuth1 exchange first
        if tokens:
            oauth1 = tokens.get("oauth1_token.json", {})
            if isinstance(oauth1, str):
                oauth1 = json.loads(oauth1)
            if oauth1.get("oauth_token"):
                try:
                    new_oauth2 = exchange_oauth1(oauth1)
                    tokens["oauth2_token.json"] = new_oauth2
                    self.store.save(tokens)
                    return {
                        "status": "refreshed",
                        "method": "oauth1_exchange",
                        "expires_at": datetime.fromtimestamp(new_oauth2["expires_at"]).isoformat(),
                        "hours_valid": f"{(new_oauth2['expires_at'] - time.time()) / 3600:.1f}",
                    }
                except Exception as e:
                    logger.warning("OAuth1 exchange failed: %s", e)

        # Fall back to full login
        if not self.email or not self.password:
            raise RuntimeError(
                "Token refresh failed and no credentials available. "
                "Set GARMIN_EMAIL and GARMIN_PASSWORD environment variables."
            )

        new_tokens = full_login(self.email, self.password)
        self.store.save(new_tokens)
        oauth2 = new_tokens["oauth2_token.json"]
        return {
            "status": "refreshed",
            "method": "full_login",
            "expires_at": datetime.fromtimestamp(oauth2["expires_at"]).isoformat(),
            "hours_valid": f"{(oauth2['expires_at'] - time.time()) / 3600:.1f}",
        }

    def status(self) -> dict:
        """Check current token status without modifying anything."""
        tokens = self.store.load()
        if not tokens:
            return {"status": "no_tokens", "message": "No tokens found in store"}

        oauth1 = tokens.get("oauth1_token.json", {})
        oauth2 = tokens.get("oauth2_token.json", {})
        if isinstance(oauth1, str):
            oauth1 = json.loads(oauth1)
        if isinstance(oauth2, str):
            oauth2 = json.loads(oauth2)

        expires_at = oauth2.get("expires_at", 0)
        hours_remaining = (expires_at - time.time()) / 3600

        return {
            "status": "valid" if hours_remaining > 0 else "expired",
            "oauth1_present": bool(oauth1.get("oauth_token")),
            "oauth2_expires_at": datetime.fromtimestamp(expires_at).isoformat() if expires_at else None,
            "hours_remaining": round(hours_remaining, 1),
            "store_type": type(self.store).__name__,
        }

    # ── Private helpers ──────────────────────────────────────────────────────

    def _write_tokens_to_disk(self, tokens: dict) -> None:
        """Write tokens to filesystem so garth/garminconnect can load them."""
        self._garth_dir.mkdir(parents=True, exist_ok=True)
        for filename, data in tokens.items():
            if isinstance(data, str):
                data = json.loads(data)
            # Ensure garth-required timestamp fields exist
            if filename == "oauth2_token.json" and isinstance(data, dict):
                now = int(time.time())
                if "expires_at" not in data and "expires_in" in data:
                    data["expires_at"] = now + data["expires_in"]
                if "refresh_token_expires_at" not in data and "refresh_token_expires_in" in data:
                    data["refresh_token_expires_at"] = now + data["refresh_token_expires_in"]
            content = json.dumps(data) if isinstance(data, dict) else str(data)
            (self._garth_dir / filename).write_text(content)

    def _save_tokens(self, client: Garmin) -> None:
        """Dump garth tokens to disk and save to store."""
        self._garth_dir.mkdir(parents=True, exist_ok=True)
        client.garth.dump(str(self._garth_dir))
        # Read back from disk and save to store
        tokens = {}
        for f in self._garth_dir.iterdir():
            if f.is_file() and f.suffix == ".json":
                try:
                    tokens[f.name] = json.loads(f.read_text())
                except (json.JSONDecodeError, OSError):
                    pass
        if tokens:
            self.store.save(tokens)

    def _try_cached_token(self) -> Optional[Garmin]:
        """Strategy 1: Use cached OAuth2 if >1h remaining."""
        try:
            oauth2_path = self._garth_dir / "oauth2_token.json"
            if not oauth2_path.exists():
                return None
            oauth2 = json.loads(oauth2_path.read_text())
            expires_at = oauth2.get("expires_at", 0)
            remaining = (datetime.fromtimestamp(expires_at) - datetime.now()).total_seconds() / 3600
            if remaining <= 1:
                logger.info("OAuth2 expiring soon (%.1fh)", remaining)
                return None

            client = Garmin()
            client.login(str(self._garth_dir))
            logger.info("Using cached token (%.1fh remaining)", remaining)
            self._save_tokens(client)
            return client
        except Exception as e:
            logger.debug("Cached token failed: %s", e)
            return None

    def _try_token_exchange(self) -> Optional[Garmin]:
        """Strategy 2: Exchange OAuth1 → new OAuth2."""
        try:
            client = Garmin()
            client.login(str(self._garth_dir))
            logger.info("Token exchange successful")
            self._save_tokens(client)
            return client
        except GarminConnectTooManyRequestsError:
            logger.warning("Rate limited (429) on token exchange")
            return None
        except (FileNotFoundError, GarthHTTPError, GarminConnectAuthenticationError) as e:
            logger.debug("Token exchange failed: %s", e)
            return None

    def _try_full_login(self) -> Optional[Garmin]:
        """Strategy 3: Full SSO login with email/password."""
        if not self.email or not self.password:
            logger.warning("No credentials for full login")
            return None

        try:
            tokens = full_login(self.email, self.password)
            self.store.save(tokens)
            self._write_tokens_to_disk(tokens)

            client = Garmin()
            client.login(str(self._garth_dir))
            logger.info("Full SSO login successful (display_name=%s)", client.display_name)
            self._save_tokens(client)
            return client
        except GarminConnectTooManyRequestsError:
            logger.warning("Rate limited (429) on full login")
            return None
        except Exception as e:
            logger.error("Full login failed: %s", e)
            return None
