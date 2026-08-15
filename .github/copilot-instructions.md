# fribbe-status-checker

FastAPI beach volleyball status app: presence detection (router polling), occupancy scraping, push notifications, Jinja2-templated web frontend.

## Commands

```sh
uv run dev             # run app locally (http://localhost:8007)
uv run test            # run all tests (--cov for coverage)
uv run lint --fix      # ruff format + ruff check --fix + frontend lint
```

Env files: create `.env.dev` and `.env.test` from `.env.template`. Required: `SESSION_SECRET_KEY`, `LOCAL_DATA_PATH`, `API_KEYS_PATH`.

## File Structure

```text
app/
  main.py          # FastAPI app, routing, service wiring, lifespan handler
  dependencies.py  # Service singletons & DI; startup()/shutdown() called at startup/shutdown
  config.py        # ALL env vars declared here
  api/             # Auth (HybridAuth, EphemeralAPIKeyStore), request/response schemas
  services/        # Domain services (presence, occupancy, push, messages, weather)
    internal/      # Internal device-count tracking (WardenStore)
    occupancy/     # Web scraping for booking status
  templates/       # Jinja2 HTML templates
  static/          # CSS/JS/images
scripts/           # uv entry points (dev, lint, watch, generate-vapid-keys, …)
tests/             # Unit tests; test-data/ holds fixture files
```

## Architecture

- **Lifecycle**: `startup()` / `shutdown()` in `app/dependencies.py` are called from the FastAPI lifespan. Service singletons and background pollers are created/stopped there — never at import time (keeps imports side-effect free for tests).
- `PresenceLevelService` polls router → `PresenceLevel` (empty/few/many) → on first daily EMPTY→active transition fires push via `PushSubscriptionService`.
- `MessageService` provides German-language text; uses `Weather` from `WeatherService` (OWM, 30-min cache).
- `HybridAuth` checks session cookie first, then `api_key` header. `PageAuth` works the same way for HTML routes.
- **Access roles**: `READER < NOTIFICATION_OPERATOR < ADMIN` (`app/api/access_role.py`). `ADMIN_TOKEN` always maps to `ADMIN`. Missing `role` in stored API keys falls back to `READER`.

## Conventions

- **Env vars**: Declare in `app/config.py` only — never read `os.environ` elsewhere. `.env.template` is the canonical var list. Tests use `monkeypatch.setattr(cfg, ...)` or `monkeypatch.setenv(...)` + `cfg.reload()`.
- **Token length**: `cfg.MIN_TOKEN_LENGTH = 48` chars. Generation: `secrets.token_urlsafe(cfg.MIN_TOKEN_LENGTH)`.
- **Threading**: `EphemeralAPIKeyStore` uses a module-level `_write_lock`. Use `append(key)` (not `save()`); returns `False` on failure.
- **Weather types**: `WeatherService.get_condition()` → `Weather | None`; `temperature`: HOT/WARM/MILD/COLD, `state`: CLEAR/CLOUDY/MILD_RAIN/HEAVY_RAIN/THUNDERSTORM/SNOW. Precipitation takes priority over temperature in `MessageService`.
- **Types**: PyRight strict. All public functions need return-type annotations. Avoid `# type: ignore`.
- **Linting**: Line length 120. Ruff `ALL` rules (tests differ — see `pyproject.toml`). CI enforces `ruff format` and `ruff check` as separate gates; run `uv run lint --fix` before every commit.
- **Markdown**: `markdownlint-cli2` in CI (warnings as errors). Config in `.markdownlint-cli2.yaml`. Run: `npx markdownlint-cli2`.
- **Licenses**: After changing `pyproject.toml` deps, run `uv run generate-licenses` and commit `app/licenses.json`.
- **Coverage**: Thresholds in `pyproject.toml` (`[tool.coverage.report] fail_under` global, `[tool.diff-cover] fail_under` per-PR diff).

## Workflow

- Write tests for every feature and bug fix; update existing tests when behavior changes. Test patterns: `*Test.py`, `*Tests.py`, `*_test.py`, `*_tests.py`. Integration tests (`tests/integration/`) are `@pytest.mark.skip` — do not remove the marker.
- Run `uv run lint --fix` before committing.
- Update `README.md` on UI feature changes.
- Update this file when conventions change.
- For larger frontend changes validate visually at `http://localhost:8007` (read-only; not a substitute for automated tests).
