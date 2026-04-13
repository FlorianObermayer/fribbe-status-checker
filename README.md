# fribbe-status-checker

[![Build](https://github.com/FlorianObermayer/fribbe-status-checker/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/FlorianObermayer/fribbe-status-checker/actions/workflows/ci-cd.yml)
[![CodeQL](https://github.com/FlorianObermayer/fribbe-status-checker/actions/workflows/codeql.yml/badge.svg)](https://github.com/FlorianObermayer/fribbe-status-checker/actions/workflows/codeql.yml)
[![Coverity Scan Build Status](https://img.shields.io/coverity/scan/33029.svg)](https://scan.coverity.com/projects/florianobermayer-fribbe-status-checker)

A FastAPI-based status checker for [Fribbe Beach](https://fribbebeach.de), running at [status.fribbe-beach.de](https://status.fribbe-beach.de). It combines real-time presence detection with occupancy data scraped from the Fribbe Beach website to give a live status overview.

## Features

- **Presence detection** — Polls a Huawei LTE router to count connected Wi-Fi devices and derive a presence level (`empty` / `few` / `many`). Configurable thresholds via the API.
- **Occupancy parsing** — Scrapes the Fribbe Beach weekly plan and event calendar to determine booking status for any given date.
- **Wardens** — Named device watchers that track specific people by MAC address or device name, showing who is currently on-site.
- **Notifications** — Create and manage Markdown-formatted notifications with optional validity windows. Includes a dedicated builder UI at `/notification-create`.
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

A dev container configuration is also available. Alternatively, use the `Python: Debug` launch configuration in VS Code.

### Test, lint, format

```sh
uv run pytest          # run tests (reads .env.test automatically)
uv run lint --fix      # backend and frontend lint + auto-fix
```

## Configuration

All environment variables are declared in [`app/env.py`](app/env.py). See [`.env.template`](.env.template) for the full list with defaults.

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

### Bootstrap (first API key)

On a fresh install with an empty key store and no `ADMIN_TOKEN`, `POST /api/internal/api_key` is open to allow creating the first key:

```sh
curl -X POST http://localhost:8007/api/internal/api_key \
  -H "Content-Type: application/json" \
  -d '{"comment": "bootstrap key"}'
```

Once a key exists, the endpoint requires authentication. Setting `ADMIN_TOKEN` disables this bootstrap bypass entirely.

### `ADMIN_TOKEN`

A master credential accepted on all protected endpoints. Also suppresses the bootstrap warning banner on the home page. Generate a suitable value with:

```sh
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Deployment

A production-ready Docker setup is included:

```sh
docker compose up --build   # builds image, runs on port 8007
```

See [`Dockerfile`](Dockerfile) and [`docker-compose.yml`](docker-compose.yml) for details. The CI/CD pipeline ([`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml)) lints, tests, builds and pushes the Docker image on every push to `main`.
