# Releasing garmin-auth

This package publishes to PyPI via GitHub Actions using OIDC trusted publishing — no API tokens are stored in the repo.

## Release process

1. Make sure `main` is green (CI runs the Python matrix on 3.10 and 3.12, the TypeScript package, an npm-consumer install, and the Worker's tests).
2. Bump the version in `pyproject.toml`. Follow [SemVer](https://semver.org):
   - patch (`0.2.1` → `0.2.2`) for bug fixes
   - minor (`0.2.2` → `0.3.0`) for backwards-compatible features
   - major (`0.3.0` → `1.0.0`) for breaking changes
3. Add a `## [X.Y.Z]` section to `CHANGELOG.md` describing what changed.
4. Commit, push to `main` (via PR — `main` is protected).
5. Do not tag by hand: `publish.yml` runs on every push to `main` and, when `pyproject.toml`'s version changed, builds, uploads to PyPI via OIDC and creates the `vX.Y.Z` tag itself.
6. The npm package (`typescript/`) has no workflow: publish it by hand from a fresh worktree with `npm publish --access public`; `prepack` builds `dist/`.
7. Verify the release at https://pypi.org/project/garmin-auth/.

## CI matrix

`ci.yml` runs on every PR and push to main:
- `pytest tests/` against Python 3.10 and 3.12, with the `db` extra installed so the connection-failure tests run for real
- `npm run build` and `npm test` in `typescript/`, an npm-consumer install, and `node --test` for `worker/`
- no linter runs in CI (ruff is not configured for this repository)

## Trusted publishing setup

The PyPI account has `garmin-auth` configured as a trusted publisher pinned to:
- Owner: `drkostas`
- Repository: `garmin-auth`
- Workflow: `publish.yml`
- Environment: `pypi`

No password or token is stored anywhere. The PyPI token is minted on demand from the GitHub OIDC identity.
