# Changelog

All notable changes to garmin-auth are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — Garmin 2FA support, native auth engine (breaking 0.x change)

This release rewrites the auth layer on top of `garminconnect>=0.3.0`, which
dropped the deprecated `garth` library in favour of a native portal+mobile JSON
login flow with Cloudflare TLS impersonation (`curl_cffi`). The main user-visible
change is that Garmin 2FA/MFA now works end-to-end. We're staying in the 0.x
series — the library is still young enough that we want to signal "early days,
breaking changes allowed between minor versions". Both the on-disk token format
and the `garmin_auth.sso` module are gone, so downstream code that inspects
either will need updates.

### Added
- `GarminAuth(prompt_mfa=..., return_on_mfa=...)` constructor kwargs mirroring
  the underlying `garminconnect.Garmin` API.
- `GarminAuth.resume_login(mfa_code)` for non-blocking web flows that receive a
  `"needs_mfa"` sentinel from `GarminAuth.login()` and later supply the code.
- `TokenStore.delete()` on the storage interface so stale tokens can be cleared
  cleanly when the server rejects them.
- `curl_cffi` and `ua_generator` as runtime dependencies (Cloudflare bypass +
  random browser fingerprinting, both transitively required by garminconnect).

### Changed
- Bumped `garminconnect` pin from `>=0.2.38,<0.3.0` to `>=0.3.0,<0.4.0`.
- `GarminAuth.login()` now returns either a `Garmin` client or the string
  `"needs_mfa"` when `return_on_mfa=True`. Without that flag the behaviour is
  unchanged (MFA is handled inline by the `prompt_mfa` callback, or raises).
- Token file format is now a single `garmin_tokens.json` with a DI OAuth payload
  (`di_token`, `di_refresh_token`, `di_client_id`). The legacy `oauth1_token.json`
  / `oauth2_token.json` pair is no longer produced.
- `DBTokenStore` wraps the new payload under a `garmin_tokens` key inside the
  `credentials` JSONB column; legacy rows are ignored on load.
- Cascading strategy simplified — garminconnect already has its own 4-way login
  fallback and proactive DI refresh, so `GarminAuth` only owns token caching and
  MFA plumbing.

### Removed
- `garmin_auth.sso` module (`full_login`, `exchange_oauth1`, `GarminSSOError`).
- `garth` dependency. Existing users with cached garth OAuth1 sessions will be
  forced through a fresh login the first time they upgrade.
- `GarminAuth.status()` no longer reports OAuth2 expiry or `hours_remaining` —
  the new DI token format doesn't expose that to callers. `status()` now reports
  presence/absence only.

### Migration notes
Upgrading to 0.3.0 invalidates all existing token files and DB rows. Users will
be prompted to log in again on first use. MFA users can now authenticate
directly without disabling MFA in their Garmin account settings.

### Credit
The 2FA investigation was sparked by u/CassiusBotdorf on Reddit (r/Hevy), whose
[`Zettt/liftosaur2garmin`](https://github.com/Zettt/liftosaur2garmin) fork of
`hevy2garmin` proved the portal+mobile flow works with MFA and encouraged us to
adopt it back. Thanks!

## [0.1.0] — Initial release

The first published version of garmin-auth, extracting the Garmin SSO + token
storage layer from soma into a standalone PyPI package.

### Added
- Full Garmin SSO login flow (OAuth1 → OAuth2 token exchange)
- Self-healing token refresh: three cascading strategies (cached token → OAuth1
  re-exchange → full SSO re-login)
- `FileTokenStore` for persisting tokens under `~/.garminconnect`
- Pluggable `TokenStore` interface for adding new backends
- Rate limit handling: retry with backoff on HTTP 429
- Zero-config CLI with interactive email prompt and saved-credentials flow
- Package layout with `pyproject.toml`, MIT license, `README.md`

[0.1.0]: https://github.com/drkostas/garmin-auth/releases/tag/v0.1.0
