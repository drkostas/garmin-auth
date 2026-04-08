# Releasing garmin-auth

This package publishes to PyPI via GitHub Actions using OIDC trusted publishing — no API tokens are stored in the repo.

## Release process

1. Make sure `main` is green (CI passing across the 3.10 / 3.11 / 3.12 matrix).
2. Bump the version in `pyproject.toml`. Follow [SemVer](https://semver.org):
   - patch (`0.2.1` → `0.2.2`) for bug fixes
   - minor (`0.2.2` → `0.3.0`) for backwards-compatible features
   - major (`0.3.0` → `1.0.0`) for breaking changes
3. Add a `## [X.Y.Z]` section to `CHANGELOG.md` describing what changed.
4. Commit, push to `main` (via PR — `main` is protected).
5. Tag the merge commit: `git tag vX.Y.Z && git push origin vX.Y.Z`.
6. The `publish.yml` workflow fires on the tag push, builds the wheel + sdist, and uploads to PyPI via OIDC.
7. Verify the release at https://pypi.org/project/garmin-auth/.

## CI matrix

`ci.yml` runs on every PR and push to main:
- `pytest tests/` against Python 3.10, 3.11, 3.12
- `ruff check .` for linting

## Trusted publishing setup

The PyPI account has `garmin-auth` configured as a trusted publisher pinned to:
- Owner: `drkostas`
- Repository: `garmin-auth`
- Workflow: `publish.yml`
- Environment: `pypi`

No password or token is stored anywhere. The PyPI token is minted on demand from the GitHub OIDC identity.
