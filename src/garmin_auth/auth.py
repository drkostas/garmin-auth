"""GarminAuth — self-healing wrapper around garminconnect 0.3.0 with MFA support.

Flow:
    1. ``GarminAuth(email, password, store=...)`` configures credentials + token store.
    2. ``auth.login()`` returns an authenticated ``garminconnect.Garmin`` client on
       success, or the string ``"needs_mfa"`` when Garmin requires a second factor.
    3. Callers that got ``"needs_mfa"`` call ``auth.resume_login(code)`` with the
       code the user entered. That returns the authenticated client.

Behind the scenes we prefer cached tokens, fall back to a fresh login, and when
the server demands MFA we defer the flow so the caller can prompt the user.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Callable, Literal, Optional, Union

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from garmin_auth.storage import FileTokenStore, TokenStore

logger = logging.getLogger("garmin_auth")

NEEDS_MFA: Literal["needs_mfa"] = "needs_mfa"
LoginResult = Union[Garmin, Literal["needs_mfa"]]


class GarminAuth:
    """Self-healing Garmin Connect authentication with 2FA support.

    Basic usage (no MFA, or blocking prompt)::

        auth = GarminAuth(email="...", password="...")
        client = auth.login()  # returns Garmin client

    MFA-aware usage (web flow, non-blocking)::

        auth = GarminAuth(email="...", password="...", return_on_mfa=True)
        result = auth.login()
        if result == "needs_mfa":
            code = ask_user_for_code()
            client = auth.resume_login(code)
        else:
            client = result
    """

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        store: Optional[TokenStore] = None,
        token_dir: Union[str, Path] = "~/.garminconnect",
        prompt_mfa: Optional[Callable[[], str]] = None,
        return_on_mfa: bool = False,
    ):
        self.email = email or os.environ.get("GARMIN_EMAIL", "")
        self.password = password or os.environ.get("GARMIN_PASSWORD", "")
        self.store: TokenStore = store or FileTokenStore(token_dir)
        self.prompt_mfa = prompt_mfa
        self.return_on_mfa = return_on_mfa
        self._client: Optional[Garmin] = None
        self._mfa_pending: Optional[Garmin] = None
        self._tokenstore_dir = self._resolve_tokenstore_dir(token_dir)

    @staticmethod
    def _resolve_tokenstore_dir(token_dir: Union[str, Path]) -> Path:
        """Pick a writable directory for garminconnect's dump/load to use.

        On read-only filesystems (e.g. Vercel) the caller should pass a ``/tmp``
        path. We still expand ``~`` here so callers can use the default.
        """
        return Path(token_dir).expanduser()

    @property
    def client(self) -> Garmin:
        """Return an authenticated client, triggering a login if needed.

        If the login needs MFA this raises rather than returning the sentinel,
        because callers of ``.client`` can't handle a string.
        """
        if self._client is None:
            result = self.login()
            if result == NEEDS_MFA:
                raise GarminConnectAuthenticationError(
                    "Garmin login needs MFA — call auth.login() directly and "
                    "handle the 'needs_mfa' return value."
                )
            self._client = result
        return self._client

    def login(self) -> LoginResult:
        """Attempt to authenticate, returning a client or the ``needs_mfa`` sentinel.

        Strategy:
            1. Load saved token from store → try ``Garmin.login(tokenstore=path)``.
               garminconnect handles proactive DI refresh internally.
            2. On failure (missing/expired/invalid tokens) fall back to
               credentials and call ``Garmin.login()`` again with tokenstore=None.
            3. If Garmin demands MFA and ``return_on_mfa`` is True, stash the
               pending client and return ``"needs_mfa"``.
        """
        # Strategy 1: cached tokens
        client = self._try_cached_login()
        if client is not None:
            self._client = client
            return client

        # Strategy 2: fresh credential login
        if not self.email or not self.password:
            raise GarminConnectAuthenticationError(
                "No cached tokens and no email/password credentials. "
                "Set GARMIN_EMAIL and GARMIN_PASSWORD or pass them to GarminAuth()."
            )

        pending = Garmin(
            email=self.email,
            password=self.password,
            prompt_mfa=self.prompt_mfa,
            return_on_mfa=self.return_on_mfa,
        )
        try:
            mfa_status, _ = pending.login()
        except GarminConnectAuthenticationError:
            raise
        except GarminConnectTooManyRequestsError:
            logger.warning("Garmin rate limited during login")
            raise
        except GarminConnectConnectionError as e:
            logger.error("Garmin connection error during login: %s", e)
            raise

        if mfa_status == NEEDS_MFA:
            logger.info("Garmin login requires MFA — awaiting resume_login")
            self._mfa_pending = pending
            return NEEDS_MFA

        # Clean login success — persist tokens and return the client
        self._persist_client_tokens(pending)
        self._client = pending
        return pending

    def resume_login(self, mfa_code: str) -> Garmin:
        """Complete a pending MFA login with the code the user supplied."""
        if self._mfa_pending is None:
            raise GarminConnectAuthenticationError(
                "No pending MFA login to resume. Call login() first."
            )
        if not mfa_code or not mfa_code.strip():
            raise ValueError("mfa_code must be a non-empty string")

        pending = self._mfa_pending
        pending.client.resume_login(None, mfa_code.strip())

        # Load profile so display_name/full_name are populated like a clean login.
        self._load_profile(pending)
        self._persist_client_tokens(pending)
        self._client = pending
        self._mfa_pending = None
        return pending

    def status(self) -> dict:
        """Inspect the token store without touching Garmin."""
        tokens = self.store.load()
        if not tokens:
            return {
                "status": "no_tokens",
                "message": "No tokens found in store",
                "store_type": type(self.store).__name__,
            }
        return {
            "status": "stored",
            "store_type": type(self.store).__name__,
            "has_di_token": '"di_token"' in tokens,
        }

    def refresh(self) -> dict:
        """Force a cached-token-based login to bounce and refresh the DI token.

        Returns a dict describing what happened. Raises on hard failure.
        """
        tokens = self.store.load()
        if not tokens:
            raise RuntimeError(
                "No tokens in store — cannot refresh. Call login() with creds first."
            )
        client = self._try_cached_login()
        if client is None:
            raise RuntimeError("Cached-token refresh failed")
        return {
            "status": "refreshed",
            "display_name": getattr(client, "display_name", None),
        }

    # ── Private helpers ──────────────────────────────────────────────────────

    def _try_cached_login(self) -> Optional[Garmin]:
        tokens = self.store.load()
        if not tokens:
            return None

        tokenstore_path = self._write_tokens_to_disk(tokens)
        try:
            client = Garmin(
                email=self.email or None,
                password=self.password or None,
                prompt_mfa=self.prompt_mfa,
                return_on_mfa=self.return_on_mfa,
            )
            # Passing a tokenstore path makes garminconnect load tokens and
            # proactively refresh the DI token if it's near expiry.
            mfa_status, _ = client.login(tokenstore=str(tokenstore_path))
            if mfa_status == NEEDS_MFA:
                # Cached tokens shouldn't ever trigger MFA — if they do the
                # tokens are stale/invalid. Clear them and fall through.
                logger.info("Cached login triggered MFA — clearing stale tokens")
                self.store.delete()
                return None
            # Persist any refreshed tokens back to the store
            self._persist_client_tokens(client)
            return client
        except GarminConnectAuthenticationError as e:
            logger.info("Cached token rejected (will re-login): %s", e)
            self.store.delete()
            return None
        except (GarminConnectConnectionError, GarminConnectTooManyRequestsError) as e:
            logger.warning("Cached login transient failure: %s", e)
            return None
        except Exception as e:
            logger.debug("Cached login unexpected error: %s", e)
            return None

    def _persist_client_tokens(self, client: Garmin) -> None:
        """Dump the client's tokens and save them to the store."""
        try:
            blob: str = client.client.dumps()
        except Exception as e:
            logger.warning("Could not serialize client tokens: %s", e)
            return
        try:
            self.store.save(blob)
        except Exception as e:
            logger.warning("Could not save tokens to store: %s", e)

    def _write_tokens_to_disk(self, tokens: str) -> Path:
        """Materialise token JSON as a file garminconnect can load."""
        target_dir = self._tokenstore_dir
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Read-only filesystem — fall back to a tempdir
            target_dir = Path(tempfile.gettempdir()) / ".garminconnect"
            target_dir.mkdir(parents=True, exist_ok=True)
            self._tokenstore_dir = target_dir
        token_file = target_dir / "garmin_tokens.json"
        token_file.write_text(tokens)
        return target_dir

    def _load_profile(self, client: Garmin) -> None:
        """After MFA completion, manually trigger profile load so display_name works."""
        try:
            prof = client.client.connectapi("/userprofile-service/socialProfile")
            if isinstance(prof, dict):
                client.display_name = prof.get("displayName")
                client.full_name = prof.get("fullName", "")
        except Exception as e:
            logger.debug("Post-MFA profile load failed (non-fatal): %s", e)
