# garmin-auth

[![CI](https://github.com/drkostas/garmin-auth/actions/workflows/ci.yml/badge.svg)](https://github.com/drkostas/garmin-auth/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/garmin-auth)](https://pypi.org/project/garmin-auth/)
[![Python](https://img.shields.io/pypi/pyversions/garmin-auth)](https://pypi.org/project/garmin-auth/)

Self-healing Garmin Connect authentication for Python, with 2FA/MFA support.

Wraps `garminconnect>=0.3.0` with token persistence, retry-aware rate limiting, and a CLI so you don't have to re-plumb auth for every project.

## Why?

The upstream [`garminconnect`](https://pypi.org/project/garminconnect/) library handles the login flow but leaves token persistence, 2FA resume, and rate limit recovery to the caller. This package wraps it with:

- **2FA/MFA support** — pass a `prompt_mfa` callback for blocking CLIs, or use `return_on_mfa=True` + `resume_login(code)` for async/web flows
- **Token persistence** — survives ephemeral CI runners via file (`~/.garminconnect/garmin_tokens.json`) or PostgreSQL storage
- **Rate limit handling** — retry with backoff on 429
- **Zero-config CLI** — interactive prompts, saved email, friendly output

## Install

```bash
pip install garmin-auth
```

## Quick Start

### CLI

```bash
# First time — prompts for email and password interactively
garmin-auth login

# Check token status
garmin-auth status

# Refresh tokens (for cron jobs / CI)
garmin-auth refresh

# Pass credentials via flags
garmin-auth login --email you@example.com --password yourpassword

# Or via environment variables
export GARMIN_EMAIL=you@example.com
export GARMIN_PASSWORD=yourpassword
garmin-auth login
```

After first login, your email is saved to `~/.garmin-auth/config.json` so you only need to enter your password on subsequent logins.

### Python API (no MFA)

```python
from garmin_auth import GarminAuth

# Reads GARMIN_EMAIL/GARMIN_PASSWORD from env, or uses saved tokens
auth = GarminAuth()
client = auth.login()  # Returns an authenticated garminconnect.Garmin client

activities = client.get_activities(0, 10)
```

### Python API (MFA, blocking CLI)

```python
# prompt_mfa is called by garminconnect when a second factor is needed.
auth = GarminAuth(
    email="user@example.com",
    password="...",
    prompt_mfa=lambda: input("Garmin MFA code: "),
)
client = auth.login()  # blocks on the prompt when MFA is required
```

### Python API (MFA, async/web flow)

```python
auth = GarminAuth(
    email="user@example.com",
    password="...",
    return_on_mfa=True,
)
result = auth.login()
if result == "needs_mfa":
    code = wait_for_user_to_enter_code()   # your web handler
    client = auth.resume_login(code)
else:
    client = result
```

### Token maintenance

```python
auth = GarminAuth()
info = auth.status()         # {"status": "stored", "has_di_token": True, ...}
auth.refresh()               # force a DI token refresh via cached credentials
```

## How It Works

1. **Cached tokens** — on each `login()`, the saved `garmin_tokens.json` is
   handed to `garminconnect.Garmin.login(tokenstore=...)`, which proactively
   refreshes the DI OAuth token when it's near expiry.
2. **Fresh credentials** — if no tokens exist (or they're rejected), garmin-auth
   hands off to `garminconnect`, which runs its own 4-strategy fallback
   (portal+curl_cffi → portal+requests → mobile+curl_cffi → mobile+requests).
3. **MFA** — when Garmin returns `MFA_REQUIRED`, you either handle it inline via
   `prompt_mfa` or catch `"needs_mfa"` and call `resume_login(code)`.

Tokens stay fresh automatically; even a fully expired session recovers without
manual intervention (assuming the credentials are still valid).

## Token Storage

Tokens are saved as `garmin_tokens.json` inside `~/.garminconnect/` by default
(single-file DI OAuth payload — not compatible with the old oauth1/oauth2 split
used by garmin-auth 0.2.x or by `garth`).

```bash
# Custom token directory
garmin-auth --token-dir /path/to/tokens login
```

```python
# Custom directory in Python
auth = GarminAuth(token_dir="/path/to/tokens")
```

For PostgreSQL storage (CI/CD or multi-machine setups):

```python
from garmin_auth import GarminAuth
from garmin_auth.storage import DBTokenStore

auth = GarminAuth(store=DBTokenStore("postgresql://user:pass@host/db"))
```

## Docker

```bash
# Build
docker build -t garmin-auth .

# Login (interactive)
docker run -it -v garmin-tokens:/root/.garminconnect garmin-auth login

# Check status
docker run -v garmin-tokens:/root/.garminconnect garmin-auth status

# Refresh (for cron)
docker run -e GARMIN_EMAIL=... -e GARMIN_PASSWORD=... \
  -v garmin-tokens:/root/.garminconnect garmin-auth refresh
```

## Development

```bash
git clone https://github.com/drkostas/garmin-auth.git
cd garmin-auth
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

## Limitations

- **Garmin rate limits** — Garmin aggressively rate-limits auth attempts (429). The package handles retries with backoff, but excessive calls in a short period may require waiting 1-24 hours
- **First-run upgrade from 0.2.x** — the token format changed; users upgrading from garmin-auth 0.2.x must log in again once (cached tokens from the old format are rejected cleanly)

## License

MIT
