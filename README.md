# garmin-auth

[![CI](https://github.com/drkostas/garmin-auth/actions/workflows/ci.yml/badge.svg)](https://github.com/drkostas/garmin-auth/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/garmin-auth)](https://pypi.org/project/garmin-auth/)
[![Python](https://img.shields.io/pypi/pyversions/garmin-auth)](https://pypi.org/project/garmin-auth/)

Self-healing Garmin Connect OAuth authentication for Python.

Handles the complex Garmin SSO flow (OAuth1 → OAuth2), automatic token refresh, and rate limit recovery — so you don't have to.

## Why?

The [`garminconnect`](https://pypi.org/project/garminconnect/) library handles basic auth but breaks in CI/CD — tokens expire between runs, shared IPs get rate-limited (429), and there's no automatic recovery. This package wraps it with:

- **Self-healing login** — three cascading strategies (cached token → OAuth1 exchange → full SSO re-login)
- **Token persistence** — survives CI ephemeral runners via file or DB storage
- **Rate limit handling** — retry with backoff on 429, never hammers Garmin's servers
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

### Python API

```python
from garmin_auth import GarminAuth

# Reads GARMIN_EMAIL/GARMIN_PASSWORD from env, or uses saved tokens
auth = GarminAuth()
client = auth.login()  # Returns an authenticated garminconnect.Garmin client

# Use the client
activities = client.get_activities(0, 10)
```

```python
# Rate-limited API calls (retry with backoff on 429)
from garmin_auth import GarminAuth, RateLimiter

auth = GarminAuth()
client = auth.login()
limiter = RateLimiter(delay=1.0, max_retries=3)

activities = limiter.call(client.get_activities, 0, 10)
heart_rates = limiter.call(client.get_heart_rates, "2026-01-01")
```

```python
# Token maintenance (no client needed)
auth = GarminAuth()
result = auth.refresh()   # {"status": "refreshed", "hours_valid": "23.5", ...}
info = auth.status()      # {"status": "valid", "hours_remaining": 23.5, ...}
```

## How It Works

Three strategies, tried in order:

1. **Cached token** — If OAuth2 has >1h remaining, use it (instant)
2. **Token exchange** — Use OAuth1 to get fresh OAuth2 (no password needed)
3. **Full SSO login** — Email/password through Garmin's SSO flow (last resort)

Tokens stay fresh automatically. Even if they fully expire, the package recovers without manual intervention.

## Token Storage

Tokens are saved to `~/.garminconnect/` by default (garth-compatible JSON files).

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

- **MFA not supported** — If your Garmin account has MFA enabled, disable it or use an app password
- **Garmin rate limits** — Garmin aggressively rate-limits auth attempts (429). The package handles retries with backoff, but excessive calls in a short period may require waiting 1-24 hours

## License

MIT
