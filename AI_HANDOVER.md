# AI Handover — garmin-auth

Hey, welcome to the garmin-auth project. Here's what you need to know.

## What is this?

A Python package that handles Garmin Connect OAuth authentication. Garmin's auth is notoriously complex — it uses a multi-step SSO flow involving OAuth1 tokens, OAuth2 tokens, CSRF tokens, session cookies, and consumer credentials fetched from an S3 bucket. This package wraps all of that into a simple interface.

## Why does it exist?

We built this because:
1. The `garminconnect` PyPI package handles basic auth but fails silently when tokens expire on CI/CD (GitHub Actions)
2. Garmin aggressively rate-limits (429) auth attempts from shared IPs
3. We needed self-healing auth: if tokens die, automatically do a full SSO re-login without human intervention
4. Multiple downstream packages (hevy2garmin, banister, etc.) all need Garmin auth — this is the shared dependency

## How it works

Three auth strategies, tried in order:
1. **Cached token**: If OAuth2 token has >1h remaining, use it directly (fastest)
2. **Token exchange**: Use OAuth1 to get a fresh OAuth2 (no credentials needed)
3. **Full SSO login**: Email/password → SSO flow → fresh OAuth1 + OAuth2 (last resort)

Token storage is pluggable:
- `FileTokenStore`: Saves to `~/.garminconnect/` (garth-compatible JSON files)
- `DBTokenStore`: Saves to PostgreSQL `platform_credentials` table

## Key files

- `src/garmin_auth/auth.py` — Main `GarminAuth` class with cascading login strategy
- `src/garmin_auth/sso.py` — Full SSO login implementation (the 7-step flow)
- `src/garmin_auth/storage.py` — Token storage backends (file, DB)
- `src/garmin_auth/cli.py` — CLI commands (login, status, refresh)

## Usage

```python
from garmin_auth import GarminAuth

# Simple (reads GARMIN_EMAIL/GARMIN_PASSWORD from env)
auth = GarminAuth()
client = auth.login()  # Returns garminconnect.Garmin client

# With DB storage
from garmin_auth import DBTokenStore
auth = GarminAuth(store=DBTokenStore("postgresql://..."))
client = auth.login()

# Just refresh tokens (for cron jobs)
result = auth.refresh()  # {"status": "refreshed", "expires_at": "...", ...}

# Check status
info = auth.status()  # {"status": "valid", "hours_remaining": 23.5, ...}
```

## CLI

```bash
garmin-auth login                    # Interactive login, saves tokens
garmin-auth status                   # Check token validity
garmin-auth refresh                  # Refresh if needed (for cron)
garmin-auth --database-url=... refresh  # Refresh with DB storage
```

## The SSO flow (for context)

This is what `sso.py` implements:
1. GET sso.garmin.com/sso/embed → set session cookies
2. GET sso.garmin.com/sso/signin → extract CSRF token from HTML
3. POST sso.garmin.com/sso/signin with email/password/CSRF → get ticket in response
4. GET thegarth.s3.amazonaws.com/oauth_consumer.json → get consumer key/secret
5. GET connectapi.garmin.com/oauth-service/oauth/preauthorized?ticket=... → OAuth1 token
6. POST connectapi.garmin.com/oauth-service/oauth/exchange/user/2.0 → OAuth2 token

Steps 5-6 require OAuth1 HMAC-SHA1 signing. The consumer credentials come from Garmin's S3 bucket (same ones the garth library uses).

## Parent project

This was extracted from the Soma fitness tracking platform (github.com/drkostas/soma). Soma uses garmin-auth for its sync pipeline and will import it via PyPI.
