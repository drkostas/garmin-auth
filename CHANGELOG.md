# Changelog

All notable changes to garmin-auth are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
