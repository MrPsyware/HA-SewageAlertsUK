# Contributing

Use GitHub issues for bugs and feature requests, and pull requests for changes.
Include the Home Assistant and integration versions when reporting a problem.
Do not include your home coordinates, full postcode, access tokens or unredacted
Home Assistant diagnostics in a public issue.

## Local checks

Use Python 3.14, matching the supported Home Assistant release.

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check custom_components tests
.venv/bin/ruff format --check custom_components tests
.venv/bin/python -m pytest -q
```

Live API tests are opt-in: `python -m pytest tests/test_live.py --run-live -qs`.
The normal suite does not contact public services.

Preserve conservative handling of unknown monitoring data. Changes to river
matching should cover downstream exclusion, tributaries, ambiguity and distance
along the network, not just proximity.

## Releases

1. Update the integration manifest version and CHANGELOG.md.
2. Wait for tests, Hassfest and HACS validation on `main` to pass.
3. Publish a GitHub release tagged `vX.Y.Z`, matching the manifest version.

HACS installs the integration directory directly from the release tag. No ZIP
asset is required. The release workflow verifies that the tag and manifest match.
The project is a HACS custom repository; default-store inclusion is a separate
submission and is not implied by a release.
