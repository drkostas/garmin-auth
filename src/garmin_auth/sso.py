"""Garmin SSO login flow — email/password → OAuth1 + OAuth2 tokens.

Implements the same flow as garth (Python) and our Vercel TypeScript endpoint:
1. Initialize SSO session (cookies)
2. Get CSRF token from signin page
3. Submit credentials
4. Extract ticket from success page
5. Fetch OAuth consumer credentials from S3
6. Exchange ticket for OAuth1 token
7. Exchange OAuth1 for OAuth2 token
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import time
from base64 import b64encode
from urllib.parse import parse_qs, quote

import requests

logger = logging.getLogger("garmin_auth")

DOMAIN: str = "garmin.com"
SSO_BASE: str = f"https://sso.{DOMAIN}/sso"
API_BASE: str = f"https://connectapi.{DOMAIN}"
USER_AGENT: str = "GCM-iOS-5.7.2.1"
CONSUMER_URL: str = "https://thegarth.s3.amazonaws.com/oauth_consumer.json"


def _oauth1_sign(
    method: str,
    url: str,
    params: dict[str, str],
    consumer_secret: str,
    token_secret: str,
) -> str:
    """Generate HMAC-SHA1 OAuth1 signature."""
    signing_key = f"{quote(consumer_secret, safe='')}&{quote(token_secret, safe='')}"
    sorted_params = "&".join(
        f"{quote(k, safe='')}={quote(v, safe='')}"
        for k, v in sorted(params.items())
    )
    base_string = f"{method.upper()}&{quote(url, safe='')}&{quote(sorted_params, safe='')}"
    sig = hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    return b64encode(sig).decode()


def _build_oauth1_header(
    method: str,
    url: str,
    consumer_key: str,
    consumer_secret: str,
    oauth_token: str = "",
    token_secret: str = "",
) -> str:
    """Build OAuth1 Authorization header."""
    nonce: str = secrets.token_hex(16)
    timestamp: str = str(int(time.time()))

    oauth_params: dict[str, str] = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": nonce,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp,
        "oauth_version": "1.0",
    }
    if oauth_token:
        oauth_params["oauth_token"] = oauth_token

    # Include query params in signature base
    base_url: str = url.split("?")[0]
    all_params: dict[str, str] = dict(oauth_params)
    if "?" in url:
        for part in url.split("?", 1)[1].split("&"):
            k, _, v = part.partition("=")
            all_params[k] = v

    signature: str = _oauth1_sign(method, base_url, all_params, consumer_secret, token_secret)
    oauth_params["oauth_signature"] = signature

    header_parts: str = ", ".join(
        f'{quote(k, safe="")}="{quote(v, safe="")}"'
        for k, v in oauth_params.items()
    )
    return f"OAuth {header_parts}"


def full_login(email: str, password: str) -> dict[str, dict]:
    """Perform full SSO login flow.

    Returns:
        {
            "oauth1_token.json": {"oauth_token": ..., "oauth_token_secret": ..., "domain": ...},
            "oauth2_token.json": {"access_token": ..., "expires_at": ..., ...},
        }

    Raises:
        RuntimeError: On login failure (bad credentials, MFA required, rate limited, etc.)
    """
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    embed_params: dict[str, str] = {
        "id": "gauth-widget",
        "embedWidget": "true",
        "gauthHost": SSO_BASE,
    }
    signin_params: dict[str, str] = {
        **embed_params,
        "service": f"{SSO_BASE}/embed",
        "source": f"{SSO_BASE}/embed",
        "redirectAfterAccountLoginUrl": f"{SSO_BASE}/embed",
        "redirectAfterAccountCreationUrl": f"{SSO_BASE}/embed",
    }

    # Step 1: Initialize SSO session
    logger.debug("SSO step 1: initializing session")
    session.get(f"{SSO_BASE}/embed", params=embed_params)

    # Step 2: Get CSRF token
    logger.debug("SSO step 2: fetching CSRF token")
    resp: requests.Response = session.get(f"{SSO_BASE}/signin", params=signin_params)
    csrf_match = re.search(r'name="_csrf"\s+value="(.+?)"', resp.text)
    if not csrf_match:
        raise RuntimeError("Could not extract CSRF token from Garmin SSO signin page")
    csrf: str = csrf_match.group(1)

    # Step 3: Submit credentials
    logger.debug("SSO step 3: submitting credentials")
    resp = session.post(
        f"{SSO_BASE}/signin",
        params=signin_params,
        data={"username": email, "password": password, "embed": "true", "_csrf": csrf},
    )

    # Check for MFA
    if "MFA" in resp.text and "ticket=" not in resp.text:
        raise RuntimeError(
            "MFA required — garmin-auth does not support MFA. "
            "Disable it in Garmin account settings."
        )

    # Step 4: Extract ticket
    ticket_match = re.search(r'embed\?ticket=([^"&]+)', resp.text)
    if not ticket_match:
        if "locked" in resp.text.lower():
            raise RuntimeError("Garmin account locked")
        if "incorrect" in resp.text.lower():
            raise RuntimeError("Invalid email or password")
        error_match = re.search(r'data-error="([^"]+)"', resp.text)
        error_msg: str = error_match.group(1) if error_match else "unknown error"
        raise RuntimeError(f"SSO login failed: {error_msg}")
    ticket: str = ticket_match.group(1)
    logger.debug("SSO step 4: ticket extracted")

    # Step 5: Fetch OAuth consumer credentials
    logger.debug("SSO step 5: fetching consumer credentials")
    consumer_resp: requests.Response = session.get(CONSUMER_URL)
    consumer_resp.raise_for_status()
    consumer: dict = consumer_resp.json()
    consumer_key: str = consumer["consumer_key"]
    consumer_secret: str = consumer["consumer_secret"]

    # Step 6: Exchange ticket for OAuth1 token
    logger.debug("SSO step 6: exchanging ticket for OAuth1")
    preauth_url: str = (
        f"{API_BASE}/oauth-service/oauth/preauthorized"
        f"?ticket={quote(ticket)}"
        f"&login-url={quote(f'{SSO_BASE}/embed')}"
        f"&accepts-mfa-tokens=true"
    )
    preauth_header: str = _build_oauth1_header("GET", preauth_url, consumer_key, consumer_secret)
    preauth_resp: requests.Response = session.get(
        preauth_url,
        headers={
            "Authorization": preauth_header,
            "User-Agent": "com.garmin.android.apps.connectmobile",
        },
    )
    if not preauth_resp.ok:
        raise RuntimeError(
            f"OAuth1 token exchange failed ({preauth_resp.status_code}): "
            f"{preauth_resp.text[:200]}"
        )

    preauth_data: dict[str, list[str]] = parse_qs(preauth_resp.text)
    oauth1: dict[str, str] = {
        "oauth_token": preauth_data.get("oauth_token", [""])[0],
        "oauth_token_secret": preauth_data.get("oauth_token_secret", [""])[0],
        "domain": DOMAIN,
    }
    if not oauth1["oauth_token"]:
        raise RuntimeError("No OAuth1 token in preauth response")

    # Step 7: Exchange OAuth1 → OAuth2
    logger.debug("SSO step 7: exchanging OAuth1 for OAuth2")
    oauth2: dict = exchange_oauth1(oauth1, consumer_key, consumer_secret)

    logger.info("Full SSO login completed successfully")
    return {"oauth1_token.json": oauth1, "oauth2_token.json": oauth2}


def exchange_oauth1(
    oauth1: dict[str, str],
    consumer_key: str = "",
    consumer_secret: str = "",
) -> dict:
    """Exchange OAuth1 token for a new OAuth2 token.

    Args:
        oauth1: Dict with oauth_token, oauth_token_secret, and optionally domain.
        consumer_key: OAuth consumer key (empty string for refresh of existing tokens).
        consumer_secret: OAuth consumer secret (empty string for refresh of existing tokens).

    Returns:
        OAuth2 token dict with access_token, expires_at, etc.

    Raises:
        RuntimeError: If exchange fails.
    """
    domain: str = oauth1.get("domain", DOMAIN)
    exchange_url: str = f"https://connectapi.{domain}/oauth-service/oauth/exchange/user/2.0"

    auth_header: str = _build_oauth1_header(
        "POST", exchange_url,
        consumer_key, consumer_secret,
        oauth1["oauth_token"], oauth1["oauth_token_secret"],
    )

    resp: requests.Response = requests.post(
        exchange_url,
        headers={
            "Authorization": auth_header,
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
        data="",
    )

    if not resp.ok:
        raise RuntimeError(
            f"OAuth1→OAuth2 exchange failed ({resp.status_code}): {resp.text[:200]}"
        )

    oauth2: dict = resp.json()
    now: int = int(time.time())
    oauth2["expires_at"] = now + oauth2.get("expires_in", 86400)
    oauth2["refresh_token_expires_at"] = now + oauth2.get("refresh_token_expires_in", 7776000)
    return oauth2
