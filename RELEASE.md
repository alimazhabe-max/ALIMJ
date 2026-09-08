# ALIMJ V26 — AI Service Decomposition Release

## Release
- Version: `26.0.0`
- Channel: `production`
- Base: V11 regression-tested build

## Deployment checklist
1. Copy `.env.example` to `.env` or configure the same variables in the hosting platform.
2. Set `BOT_TOKEN` and `ADMIN_IDS`.
3. Set a strong random `METRICS_TOKEN` if `/metrics` is exposed.
4. Put `DB_PATH` and `BACKUP_DIR` on persistent storage when the hosting platform supports it.
5. Run `python -m unittest discover -s tests -v` before deployment.
6. Start with `python -m bot.main`.
7. Verify `/health`, Telegram polling, database writes, and the admin diagnostics command.

## Important compatibility note
Existing providers, handlers, tools, market/weather fallbacks, backup/restore flows, and feature data are preserved. `jokes_data.json` is intentionally unchanged.

## V15 — Intelligent Automation
- Added opt-in `/automation on|off` daily personal digest.
- Digest is capped to one message per user per local day and includes upcoming reminders plus lightweight usage/preferences.
- Automation is disabled by default for existing and new users.

## V19 — RAG & Hybrid Intelligence
- Added `bot/services/retrieval.py` as a bounded hybrid retrieval layer.
- Normal AI prompts retrieve only relevant local user memory + project knowledge; no implicit web request is made.
- Added `hybrid_retrieve` AI tool for explicit local retrieval and optional web retrieval.
- Web retrieval is opt-in at tool level, reducing surprise network traffic and keeping current-data retrieval deliberate.
- Retrieval context is capped to protect prompt size and token budget.
- `jokes_data.json` remains excluded from the knowledge index and unchanged.

## V22 — Agent Memory & Modularization
- Added privacy-conscious aggregate agent/tool learning: success/failure counters and a short last error only.
- Agent execution can prefer a bounded fallback after repeated low reliability; the learning layer never blocks a request.
- Added `/agent memory` to inspect aggregate agent/tool reliability.
- Split large implementation modules: AI media/voice/image helpers, market technical analysis, crypto analysis, and Istikhara data are now separated into focused modules.
- No existing feature or provider was removed.
- `jokes_data.json` remains untouched and excluded from all new indexes/learning data.

## V26 — AI Service Decomposition
- Extracted the heavy Telegram media/voice handlers from `messages.py` into `bot/handlers/media_handlers.py`.
- Kept `media_ai_handler` and `voice_ai_handler` compatibility facades in `messages.py`, preserving existing handler registration/import surfaces.
- Deferred the facade helper imports inside the extracted handlers to avoid circular imports while preserving existing helper behavior.
- Added decomposition, AST, release, and jokes-integrity regression tests.
- No feature/provider was removed; `jokes_data.json` remains byte-for-byte unchanged.


### V26 — AI Service Decomposition

- Extracted shared AI configuration/state/routing/key-pool logic into `bot/services/ai_runtime.py`.
- Extracted provider HTTP and provider-specific implementations into `bot/services/ai_providers.py`.
- Kept `bot/services/ai_service.py` as the public compatibility facade for existing imports.
- Existing provider selection, circuit breaker, key rotation, memory, media, streaming and tool integrations remain available.
- No changes to `bot/features/fun/jokes_data.json`.

## V27 — Finance Core Decomposition
- Extracted pricing/conversion/crypto-list operations into `bot/features/market/finance_core.py`.
- Kept `bot/features/market/finance.py` as the compatibility facade for legacy imports.
- Preserved the existing market API and providers/fallbacks.
- Added decomposition and immutability regression tests.
