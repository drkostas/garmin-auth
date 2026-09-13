# Changelog

All notable changes to garmin-auth are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [npm 0.7.0] — one Garmin SSO Worker for the ecosystem (#47)

- `garmin-auth/sso-worker`: the client for the Cloudflare Worker that performs the Garmin DI login, MFA continuation and token exchange from an IP Garmin accepts; the Worker source lives in `worker/` and is the only copy (hevy2garmin's copies were deleted).

## [npm 0.6.0] — the Garmin parsers move in (#46)

- The activity, sleep and daily-summary parsers that soma's sync pipeline used to carry are exported from the package, so every consumer reads Garmin's raw JSON the same way.

## [npm 0.7.1] — the client can DELETE

- `GarminClient.delete(path)`: a DELETE against a connectapi path, with the same one-time DI token refresh on 401 as `post` and `put`. soma uses it to take a dropped training plan's pushed workouts off the Garmin calendar (soma#926).

## [Python 0.4.1] — the PyPI package is deprecated, end date 2026-10-31

### Deprecated
- The Python package exists for hevy2garmin's Python side, which is being retired (hevy2garmin 0.11.0 announces it). No releases after **2026-10-31**; after that date it is marked deprecated on PyPI and `src/`, `tests/` and the Python CI/publish steps are removed from this repository. The npm package `garmin-auth` is the product: the same auth engine, token store and now the Garmin payload parsers.

## [Python 0.4.0 / npm 0.5.0] — the token store stops lying

`DBTokenStore` reported success it had not achieved and absence it had not verified. Three
downstream failures came out of that, and all of them looked like something else:

- A Garmin login on the npm side could not persist at all, and still answered "connected".
  `DBTokenStore` opens its own client through `pg`, which was declared as an **optional** peer
  dependency, and npm does not install optional peers. So `require("pg")` threw, `save()` caught
  it and returned normally, and nothing was ever written. Every fresh install of a consumer that
  did not happen to depend on `pg` itself was affected. The Python half had the same hole through
  the `psycopg2` extra.
- A row written by anything other than the very first login kept a `status` of `'disconnected'`
  forever, because the upsert set the flags only in its INSERT branch. Consumers that trusted the
  column showed a working connection as disconnected.
- A database that could not be reached was reported as "there are no tokens", which reads as an
  expired credential. That points every investigation at the one thing that is not wrong.

### Changed (breaking within 0.x)
- `DBTokenStore.save()`, `.load()` and `.delete()` now raise when the database cannot be reached
  or the statement fails. `load()` returns `None` only when the row is genuinely absent, empty, of
  the legacy 0.2.x oauth1/oauth2 shape, or holds credentials that will not parse.
- `GarminAuth`'s token persistence no longer swallows failures, and it now runs outside the block
  that catches authentication errors, so a storage fault can never be reported as `needs_mfa`.
- The upsert restores `status`, `auth_type` and `connected_at` alongside the payload, so a
  re-login repairs a stale row instead of leaving its flags behind.
- npm: `pg` moved from an optional peer dependency to a regular dependency. Installing
  `garmin-auth` now installs a working `DBTokenStore`. Consumers that already declare `pg` need no
  change.

### Migration
Callers that relied on these methods never throwing must handle errors. The shape that was
previously silent, and is now loud, is a broken database or a missing driver, both of which need
fixing rather than ignoring. Code that wants a token store to survive a rejection without
destroying a shared credential should override `delete()`.

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
