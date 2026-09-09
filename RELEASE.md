# ALIMJ V35 — Core Utilities Reconstruction

## Release
- Version: `35.0.0`
- Channel: `production`
- Focus: `bot/utils` contracts, reproducible dependencies, documentation and regression hardening.

## V35 changes
- Added a small application exception hierarchy in `bot/utils/exceptions.py`.
- Hardened `bot/utils/http_client.py` with typed settings, defensive environment parsing, bounded host diagnostics and explicit timeout classification while preserving the existing response/fallback contract.
- Kept `http_resilience.py` as the compatibility facade over the shared HTTP client/cache.
- Added stable language APIs to `bot/utils/texts.py` without changing the existing text registry.
- Added stable Persian/Hijri event accessors to `bot/utils/events.py`.
- Made motivation selection accept an optional sequence while preserving the existing corpus and no-repeat behavior.
- Added pinned runtime dependencies in `requirements.txt`.
- Added `pyproject.toml` with Ruff and mypy baseline configuration.
- Added a complete `.env.example` covering known configuration groups.
- Added `README.md` with local installation, deployment, diagnostics, testing and architecture instructions.
- Added V35 utility-contract regression tests.

## Regression guarantees
- Existing features/providers/fallbacks are preserved.
- `bot/features/fun/jokes_data.json` is intentionally untouched and remains immutable.
- Release metadata and Render deployment pin are synchronized at `35.0.0`.

## Validation checklist
1. `python -m compileall -q bot`
2. `python -m unittest discover -s tests -v`
3. Verify the jokes-data SHA256 against the protected baseline.
4. Deploy with `STARTUP_CHECK=true` and `RELEASE_VERSION=35.0.0`.
