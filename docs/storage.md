# Token storage backends

garmin-auth ships with two `TokenStore` implementations. Pick the one that matches your deployment.

## FileTokenStore (default)

Persists tokens as files under `~/.garminconnect`. Best for local installs and Docker volumes.

```python
from garmin_auth import GarminAuth

auth = GarminAuth(email="...", password="...")
client = auth.login()  # uses FileTokenStore implicitly
```

## DBTokenStore (cloud deployments)

Stores OAuth1 + OAuth2 tokens as a single JSONB row in Postgres. Best for serverless / read-only filesystems like Vercel where files don't survive between requests.

```python
from garmin_auth import GarminAuth
from garmin_auth.storage import DBTokenStore

store = DBTokenStore(database_url=os.environ["DATABASE_URL"])
auth = GarminAuth(email="...", password="...", store=store, token_dir="/tmp/.garminconnect")
client = auth.login()
```

### Notes
- The `tokens` table is created automatically on first use (`_ensure_tables()`).
- On read-only filesystems, `garth` (the underlying Garmin client) still requires a writable `token_dir`. Set it to `/tmp/.garminconnect` on Vercel — `garmin-auth` writes to the DB and `garth` keeps its working files in `/tmp`.
- Schema:
  ```sql
  CREATE TABLE garmin_auth_tokens (
      user_email TEXT PRIMARY KEY,
      tokens JSONB NOT NULL,
      updated_at TIMESTAMPTZ DEFAULT NOW()
  );
  ```

## Custom backends

Implement the `TokenStore` protocol for any other backend (Redis, S3, secrets manager, …).

```python
from garmin_auth.storage import TokenStore

class MyStore(TokenStore):
    def get(self, user: str) -> dict | None: ...
    def set(self, user: str, tokens: dict) -> None: ...
```
