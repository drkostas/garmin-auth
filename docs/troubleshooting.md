# Troubleshooting

## Tokens look fine but every API call returns 401

The token's `expires_at` may be missing or stale. Earlier versions of garmin-auth (pre-0.2.1) had a bug where the Cloudflare Worker exchange path returned tokens without an `expires_at` field, so the self-healing refresh logic never triggered and stale tokens kept being reused until Garmin rejected them.

**Fixed in 0.2.1.** If you're on an older version, upgrade:

```bash
pip install --upgrade garmin-auth
```

If you're on 0.2.1+ and still seeing this, check that your stored token has an `expires_at` field:

```python
from garmin_auth.storage import DBTokenStore
store = DBTokenStore(database_url=...)
print(store.get("your@email.com"))
```

If `expires_at` is missing, force a re-login by clearing the stored token:

```python
store.set("your@email.com", {})  # or DELETE the row directly
```

## "Sign in to Garmin Connect" loop on Vercel / cloud

Garmin's SSO endpoints block requests from common cloud IP ranges. Use the Cloudflare Worker exchange flow — see `docs/storage.md` for the cloud setup pattern.

## Rate limited (429)

`garmin-auth` retries with backoff up to 3 times. If you keep hitting 429, you're probably making too many requests in a tight loop. Throttle your caller, or use the built-in `RateLimiter`:

```python
from garmin_auth import RateLimiter
limiter = RateLimiter(delay=1.0, max_retries=3, base_wait=30)
result = limiter.call(client.get_activities, 0, 10)
```
