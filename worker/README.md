# Garmin SSO proxy (Cloudflare Worker)

Garmin blocks the login and token exchange from cloud provider IP ranges (Vercel, GitHub Actions, AWS). This Worker runs the whole credential flow, including two-factor, on Cloudflare's edge, which Garmin does not block, and hands the DI tokens back to the caller. It is the one deploy every consumer in the ecosystem points at (hevy2garmin's dashboards, macro-engine's setup page, soma).

## Endpoints

- `POST /login` `{ email, password }` → `{ status: "success", di_token, di_refresh_token, di_client_id }` | `{ status: "needs_mfa", session_id, mfa_method }` | `{ status: "needs_captcha" }` | `{ status: "invalid_credentials" }` | `{ status: "rate_limited", retry_after_seconds }` | `{ status: "error", message }`
- `POST /login-mfa` `{ session_id, mfa_code }` → the same shapes.
- `POST /exchange` → the OAuth ticket exchange used by the manual sign-in fallback.

A 429 from Garmin records a per-account cooldown in KV and later logins for that account short-circuit until it clears, so one bad password cannot lock an account out for longer.

## Deploy your own

```bash
cd worker
npx wrangler login
npx wrangler kv namespace create MFA_SESSIONS   # paste the id into wrangler.toml
npx wrangler deploy
```

The Worker URL is then `https://garmin-auth-sso.<your-subdomain>.workers.dev`. Point consumers at it (hevy2garmin's `GARMIN_LOGIN_WORKER_URL`, macro-engine's `NEXT_PUBLIC_GARMIN_SSO_URL`). Nothing is stored beyond the MFA session between the two login calls; the Worker never sees a database.

## Tests

```bash
node --test worker/index.test.mjs   # or: cd worker && npm test
```
