# Fixture repositories (dev-only)

Deterministic, offline sources for tests and the local demo. They are **not** real repositories:
a fixture is registered as `https://fixtures.local/local/<name>` (only when `AQS_DEV_FIXTURE_REPOS=true`),
each sub-directory of `refs/` is a "branch", and the pinned "commit SHA" is a hash over the tree.
Nothing here is fetched from the network. Values such as `AKIAIOSFODNN7EXAMPLE` are AWS's published
documentation examples, planted so the secret scanner has something to find; they are not credentials.

| Fixture | Ref | What the checks find |
|---|---|---|
| `sample-python-app` | `main` | 2 failing tests (rounding bug), 1 syntax error in `scripts/legacy_report.py`, 1 example key in `config/settings_example.py` |
| `sample-python-app` | `fix-rounding` | all tests pass, syntax clean, no secrets |
