# fribbe-status-checker

[![Build](https://github.com/FlorianObermayer/fribbe-status-checker/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/FlorianObermayer/fribbe-status-checker/actions/workflows/ci-cd.yml)
[![CodeQL](https://github.com/FlorianObermayer/fribbe-status-checker/actions/workflows/codeql.yml/badge.svg)](https://github.com/FlorianObermayer/fribbe-status-checker/actions/workflows/codeql.yml)
[![Coverity Scan Build Status](https://img.shields.io/coverity/scan/33029.svg)](https://scan.coverity.com/projects/florianobermayer-fribbe-status-checker)
[![Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/FlorianObermayer/b2ba5d0b8ce8a8826506ff50f4af68ee/raw/fribbe-coverage.json)](https://github.com/FlorianObermayer/fribbe-status-checker/actions/workflows/ci-cd.yml)

A FastAPI-based status checker for [Fribbe Beach](https://fribbebeach.de), running at [status.fribbe-beach.de](https://status.fribbe-beach.de). It combines real-time presence detection with occupancy data scraped from the Fribbe Beach website to give a live status overview.

## Features

- **Presence detection** — Polls a Huawei LTE router to count connected Wi-Fi devices and derive a presence level (`empty` / `few` / `many`). Configurable thresholds via the API.
- **Occupancy parsing** — Scrapes the Fribbe Beach weekly plan and event calendar to determine booking status for any given date.
- **Wardens** — Named device watchers that track specific people by MAC address or device name, showing who is currently on-site.
- **Notifications** — Create and manage Markdown-formatted notifications with optional validity windows. Includes a dedicated builder UI at `/notification-create`.
- **API key management** — Admin-only web page at `/api-keys` to create, list, and delete API keys without using the REST API or cURL. Accessible via the floating key button on the index page.
- **Push notifications** — Browser Web Push (VAPID) alerts when someone first arrives at the Fribbe on a given day or when a notification becomes active. Topic-based subscriptions (`presence`, `notifications`).
- **Weather-aware messages** — Optional OpenWeatherMap integration for temperature- and weather-state-aware status and push messages.
- **REST API** — JSON API with hybrid authentication (API key header or opaque server-side session cookie). Interactive docs at `/docs`.
- **Web UI** — Jinja2-templated HTML pages with CSS/JS frontend, service worker support, and **dark mode** (follows system preference, override via toggle). Static assets served directly by the app.
- **Impressum & Datenschutz** — To activate legal compliance, set both `OPERATOR_NAME` and `OPERATOR_EMAIL` environment variables. When configured, a GDPR-compliant legal page is served at `/legal` and a link appears in the UI footer.

## Development

### Dev container & VS Code

A [dev container](https://containers.dev/) configuration is included. To use it:

1. Install the [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension in VS Code.
2. Open the workspace folder and select **Dev Containers: Reopen in Container** from the command palette.

The container includes all necessary prerequisites pre-installed.

Alternatively, use the **Python: Debug** launch configuration to run locally without the container.

### Prerequisites

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) — dependency management and script runner

### Setup

```sh
uv sync                # install dependencies
cp .env.template .env.dev   # configure env vars (see .env.template for all options)
```

### Run locally

```sh
uv run dev             # start app at http://localhost:8007
```

### Test, lint, format

```sh
uv run test          # run tests (--cov for coverage)
uv run lint --fix      # backend and frontend lint + auto-fix
```

## Configuration

All environment variables are declared in [`app/config.py`](app/config.py). See [`.env.template`](.env.template) for the full list with defaults.

**Required:** `APP_URL`, `SESSION_SECRET_KEY`, `LOCAL_DATA_PATH`, `API_KEYS_PATH`.

Each optional feature is silently disabled when its variables are absent.

### Generate VAPID keys

```sh
uv run generate-vapid-keys   # prints VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_CLAIM_SUBJECT
```

### Test push notification

```sh
uv run test-push-notification          # default title/body
uv run test-push-notification "Title" "Body text"
```

## Authentication

The app uses **HybridAuth**: an API key passed via the `api_key` header or an opaque server-side session cookie. Browser sessions are protected by a per-session CSRF token (`X-CSRF-Token`).

### Access roles

Every authenticated subject carries an **AccessRole** (`READER < NOTIFICATION_OPERATOR < ADMIN`). Higher roles inherit all permissions of lower roles.

| Role | Permissions |
| --- | --- |
| `READER` | Read-only access to all protected endpoints. |
| `NOTIFICATION_OPERATOR` | Everything in READER, plus create / update / delete notifications. |
| `ADMIN` | Full access — API key management, warden CRUD, config changes, and all of the above. |

- `ADMIN_TOKEN` always maps to `ADMIN`.
- API keys carry a `role` field. New keys default to `READER`; specify `"role": 3` (or `"role": "admin"`) in `POST /api/internal/api_key` to set a higher role.
- Existing stored keys without a `role` field fallback to `READER` for backward compatibility.

### `ADMIN_TOKEN`

A master credential accepted on all protected endpoints. When neither `ADMIN_TOKEN` nor a valid admin API key is configured, a warning banner is shown on the home page. Generate a suitable value with:

```sh
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Deployment

### Docker image

Pre-built images are published to GitHub Container Registry on every push to `main`:

```sh
docker pull ghcr.io/florianobermayer/fribbe-status-checker:latest
```

Available image tags:

| Tag | Description |
| --- | --- |
| `latest` | Most recent build from `main`. |
| `<version>` (e.g. `0.5.0`) | Immutable tag, created once when the version in `pyproject.toml` is bumped. |
| `<version>-<run>` (e.g. `0.5.0-42`) | Unique per-build tag for traceability. |

### Releases

The CI/CD pipeline ([`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml)) automates releases:

- **Stable release** — Created automatically (with changelog) when the version in `pyproject.toml` is bumped and pushed to `main`.
- **Nightly pre-release** — Updated on every subsequent push to `main` under the same version. Tagged `nightly`.

The pipeline can also be triggered manually via `workflow_dispatch`.

See [`Dockerfile`](Dockerfile) and [`examples/docker-compose.yml`](examples/docker-compose.yml) for container and setup details.
