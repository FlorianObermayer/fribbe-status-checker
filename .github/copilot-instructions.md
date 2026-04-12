# fribbe-status-checker

FastAPI beach volleyball status app: presence detection (router polling), occupancy scraping, push notifications, Jinja2-templated web frontend.

## Build & Test

```sh
uv run dev             # run app locally (http://localhost:8007)
uv run pytest          # run tests (reads .env.test automatically)
uv run lint            # backend and frontend lint
uv run lint --fix      # backend and frontend lint + auto-fix
```

Env files: create `.env.dev` and `.env.test` from `.env.template`. Required: `SESSION_SECRET_KEY`, `LOCAL_DATA_PATH`, `API_KEYS_PATH`.

Test patterns: `*Test.py`, `*Tests.py`, `*_test.py`, `*_tests.py`.
Integration tests (`tests/integration/`) are `@pytest.mark.skip` — do not remove the skip marker.

## UI Validation

For larger frontend changes, validate against `http://localhost:8007`.

- Use VS Code Simple Browser or Copilot browser tools for quick visual/content checks.
- Keep localhost access read-only for verification; do not rely on live/manual checks as the only test signal.

## File Structure

```text
.github/
  copilot-instructions.md  # Instructions for Copilot
  workflows/
    ci-cd.yml              # CI/CD pipeline (lint, test, build, deploy)
    codeql.yml             # CodeQL security analysis
  dependabot.yml           # Dependabot config for dependency updates
app/
  main.py                  # FastAPI app, routing, service wiring, lifespan handler
  dependencies.py          # Service singletons & DI; startup()/shutdown() c  env.py                   # ALL env vars declared here; validate() called at startup
  api/                     # Auth (HybridAuth, EphemeralAPIKeyStore), request/response schemas
  services/                # Domain services (presence, occupancy, push, messages, weather)
    internal/              # Internal device-count tracking (WardenStore)
    occupancy/             # Web scraping for booking status
  templates/               # Jinja2 HTML templates (index, auth, notification-create)
  static/                  # Served CSS/JS/images frontend assets
scripts/                   # uv entry points (dev, lint, watch, generate-vapid-keys, …)
tests/                     # Unit tests; test-data/ holds fixture files
README.md                  # Project overview, setup, conventions, instructions
```

## Architecture

- **Lifecycle**: `app.dependencies.startup()` / `shutdown()` are called from the FastAPI lifespan in `main.py`. Service singletons and background pollers are created/stopped there - never at import time. This keeps module imports side-effect free so tests can import routers without spawning threads.
- `PresenceLevelService` polls router → `PresenceLevel` (empty/few/many) → on first daily EMPTY→active transition fires push notification via `PushSubscriptionService`
- `MessageService` provides German-language text; uses `Weather` from `WeatherService` (OWM, 30-min cache)
- `HybridAuth` checks an opaque server-side session referenced by the session cookie first, then `api_key` header; one-time bootstrap bypass when key store is empty

## Conventions

- **Env vars**: Declared as typed globals in `app/env.py`; `load()` populates from `os.environ`. Never read `os.environ` outside `env.py`. `.env.template` is the canonical var list.
- **Auth**: The browser cookie must store only an opaque `auth_session_id`. Raw API keys and `ADMIN_TOKEN` values are never stored in the cookie. Admin sessions are bound to the current `ADMIN_TOKEN` fingerprint server-side, so rotating `ADMIN_TOKEN` invalidates existing admin sessions. Unsafe requests authenticated by cookie also require the per-session `X-CSRF-Token` header; header-based `api_key` auth does not.
- **Token length**: `env.MIN_TOKEN_LENGTH = 48` is character count (not bytes). Use with `Field(min_length=...)`. For generation: `secrets.token_urlsafe(env.MIN_TOKEN_LENGTH)` (byte param, yields ≥48 chars).
- **Threading**: `EphemeralAPIKeyStore` has module-level `_write_lock`. Use `append(key, require_empty=True)` (not `save()`); returns `False` on failure.
- **Weather types**: `WeatherService.get_condition()` → `Weather | None` with `temperature: Temperature` (HOT/WARM/MILD/COLD) and `state: WeatherState` (CLEAR/CLOUDY/MILD_RAIN/HEAVY_RAIN/THUNDERSTORM/SNOW). In `MessageService`, precipitation states take priority over temperature messages.
- **Type checking**: PyRight strict. All public functions need return-type annotations. Avoid `# type: ignore`.
- **Linting**: Line length 120. Ruff rules: `ALL`. Tests rules differ. See `pyproject.toml` for details.
- **Markdown linting**: `markdownlint-cli2` enforced in CI (warnings as errors). Config in `.markdownlint-cli2.yaml`. Run locally with `npx markdownlint-cli2`.
- **Licenses**: After adding or removing any dependency in `pyproject.toml`, run `uv run generate-licenses` and commit the updated `app/licenses.json`. The CI lint job fails if this file is out of date.

## Copilot Instructions

- Always write tests for new features and bug fixes; update existing tests if the change affects their behavior.
- Update `README.md` on every UI feature update.
- Update `.github/copilot-instructions.md` if needed.
