# garmin-auth

Self-healing Garmin Connect OAuth authentication for Python.

Handles the complex Garmin SSO flow (OAuth1 → OAuth2), automatic token refresh, and rate limit recovery — so you don't have to.

## Install

```bash
pip install garmin-auth
```

For PostgreSQL token storage:
```bash
pip install garmin-auth[db]
```

## Quick Start

```python
from garmin_auth import GarminAuth

auth = GarminAuth(email="you@example.com", password="yourpassword")
client = auth.login()  # Returns an authenticated garminconnect.Garmin client

# Use the client
activities = client.get_activities(0, 10)
```

Or use environment variables:
```bash
export GARMIN_EMAIL=you@example.com
export GARMIN_PASSWORD=yourpassword
```

```python
auth = GarminAuth()
client = auth.login()
```

## CLI

```bash
# Login and save tokens
garmin-auth login --email you@example.com --password yourpassword

# Check token status
garmin-auth status

# Refresh tokens (for cron jobs / CI)
garmin-auth refresh
```

## Token Storage

**File-based (default):** Tokens saved to `~/.garminconnect/` as JSON files.

```python
auth = GarminAuth(token_dir="~/.garminconnect")
```

**PostgreSQL:** For CI/CD or multi-machine setups.

```python
from garmin_auth import GarminAuth, DBTokenStore

auth = GarminAuth(store=DBTokenStore("postgresql://user:pass@host/db"))
```

## How It Works

Three strategies, tried in order:

1. **Cached token** — If OAuth2 has >1h remaining, use it (instant)
2. **Token exchange** — Use OAuth1 to get fresh OAuth2 (no password needed)
3. **Full SSO login** — Email/password through Garmin's SSO flow (last resort)

This means tokens stay fresh automatically, and even if they fully expire, the package recovers without manual intervention.

## Docker

```bash
docker build -t garmin-auth .
docker run -e GARMIN_EMAIL=... -e GARMIN_PASSWORD=... garmin-auth refresh
```

## License

MIT
