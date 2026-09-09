# Rooze Ziba / ALIMJ

Telegram bot in Python with AI providers, market/weather tools, memory, RAG, agents, automation and SQLite persistence.

## Quick start

Requirements: Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m bot.main
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m bot.main
```

Set at least `BOT_TOKEN`. Add `ADMIN_IDS` and provider keys for the features you use.

## Testing

Run the regression suite before deployment:

```bash
python -m unittest discover -s tests -v
```

If pytest is installed, the same suite can be run with:

```bash
PYTHONPATH=. pytest -q
```

The test suite includes release/deployment contracts, modularization checks, runtime diagnostics and market-speed regressions. `jokes_data.json` is protected by an immutability check.

## Render deployment

The project is configured through `render.yaml`. Set secrets in Render Environment Variables rather than committing `.env`.

Important deployment variables:

- `BOT_TOKEN`
- `ADMIN_IDS`
- `DB_PATH` / persistent disk path when persistence is available
- `METRICS_TOKEN` if `/metrics` is exposed
- `RELEASE_VERSION=35.0.0`
- `STARTUP_CHECK=true`

The startup self-check runs before polling and validates important handler/keyboard contracts.

## Diagnostics

Admin command:

```text
/diagnostics
```

HTTP health endpoint:

```text
/health
```

The diagnostics output is intentionally bounded and must not contain API keys.

## Architecture

```text
bot/
├── handlers/       Telegram presentation and routing
├── services/       AI, retrieval, agents, workflows and tools
├── features/       domain features such as market/weather/fun
├── api/            external API adapters
├── plugins/        plugin lifecycle/registry
├── utils/          shared contracts, keyboards, text, events, HTTP and ops
└── database*.py    SQLite persistence and DB primitives
```

### `bot/utils/`

- `keyboard_factory.py` — canonical keyboard constructors; `helpers.py` remains a compatibility facade.
- `texts.py` — multilingual text registry and safe language-aware lookup.
- `events.py` — Persian/Hijri event data plus stable accessors.
- `http_client.py` — shared async HTTP pool, bounded GET cache, retry and 429 cooldown.
- `http_resilience.py` — compatibility facade for pooled HTTP/cache helpers.
- `observability.py` — bounded counters, latency samples and recent runtime errors.
- `task_manager.py` — tracked background task lifecycle.
- `motivation.py` — motivation message selection without modifying the message corpus.

## Environment variables

`.env.example` documents all known runtime variables grouped by function. Never commit real secrets.

## Database

SQLite uses WAL/transaction retries. Keep database files on persistent storage in production. Database restore validates SQLite integrity and required tables before replacement.

## Release discipline

- Update `bot/release.py` and `RELEASE.md` together.
- Run the complete regression suite.
- Run `python -m compileall -q bot`.
- Verify `jokes_data.json` SHA256 remains unchanged.
- Deploy only after startup self-check passes.

## Compatibility rule

Existing providers, fallbacks, handlers, tools and user-facing features are preserved. Refactors should keep public import/function contracts whenever practical. `bot/features/fun/jokes_data.json` is immutable and must not be edited, regenerated or indexed.
