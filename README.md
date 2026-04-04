# fribbe-status-checker

A FastAPI-based status checker for [Fribbe Beach](https://fribbebeach.de), running at [status.fribbe-beach.de](https://status.fribbe-beach.de). It combines real-time presence detection with occupancy data scraped from the Fribbe Beach website to give a live status overview.

## Features

- **Presence detection** — Polls router connection data to count connected devices and report a presence level (`empty` / `few` / `many`)
- **Occupancy parsing** — Scrapes the Fribbe Beach weekly plan and event calendar to determine booking status for any given date
- **Notifications** — Create and manage Markdown-formatted notifications with optional validity windows
- **Push notifications** — Browser Web Push alerts when someone first arrives at the Fribbe on a given day
- **REST API** — JSON API with API key + session-cookie hybrid authentication
- **Web UI** — Static HTML/CSS/JS frontend served directly by the app

## Development

### Prerequisites

- [uv](https://docs.astral.sh/uv/) — used for dependency management and running scripts

### Install dependencies

```sh
uv sync
```

### Local development setup

**Using a dev container** is recommended for local development, but you can also run the app directly on your machine. Either way, set up the required environment variables as described below.

The local app expects several environment variables, provided via a `.env.dev` file. Check the `.env.template` file for the minimal set for local development.

```sh
uv run dev
```

### Run with VSCode Debugger

Run `Python: Debug` run configuration in VSCode.

The API and UI are then available at <http://localhost:8007>.

### Run tests

```sh
uv run pytest
```

### Lint and format

```sh
uv run lint
```

## Admin authentication

### First API key (bootstrap / setup mode)

On a fresh install with no API keys configured, the `POST /api/internal/api_key` endpoint operates in **setup mode**: authentication is skipped, allowing anyone to create the very first key without credentials. Once at least one key exists the endpoint requires a valid key, so setup mode is automatically deactivated after bootstrap.

> **Production recommendation:** set `ADMIN_TOKEN` to a strong random secret (see below). This disables the open bootstrap bypass entirely, so the endpoint is never unauthenticated even if the key store is accidentally emptied.

To obtain the first key on a fresh install (no `ADMIN_TOKEN` set), send a request to the running app while the key store is empty:

```sh
curl -X POST http://localhost:8007/api/internal/api_key \
  -H "Content-Type: application/json" \
  -d '{"comment": "bootstrap key"}'
```

When `ADMIN_TOKEN` is set, pass it as the `api_key` header instead:

```sh
curl -X POST http://localhost:8007/api/internal/api_key \
  -H "api_key: $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"comment": "bootstrap key"}'
```

Store the returned key securely and use it for all subsequent authenticated requests. `ADMIN_TOKEN` is also accepted on all other protected endpoints and acts as a permanent recovery credential.

### `ADMIN_TOKEN` (master / recovery credential)

```sh
ADMIN_TOKEN=<strong-random-secret>  # recommended for production
```

- Accepted as a valid credential on **all** protected API endpoints.
- Disables the open empty-store bootstrap bypass — the create-key endpoint always requires auth when this is set.
- The home-page bootstrap warning banner is suppressed when `ADMIN_TOKEN` is configured (no open endpoint, no warning).
- Use `python -c "import secrets; print(secrets.token_urlsafe(48))"` to generate a suitable value.

### Sign-in button on the home page (`SHOW_ADMIN_AUTH`)

By default the home page (`/`) shows no sign-in affordance to keep the public-facing UI clean. Setting `SHOW_ADMIN_AUTH=true` makes a sign-in button appear in the bottom-right corner whenever the visitor is **not** authenticated. Clicking it leads to the `/auth` page.

```sh
SHOW_ADMIN_AUTH=true  # default: false
```

Authenticated users always see the full admin button group regardless of this setting.

## Enable Push notifications (Web Push / VAPID)

Push notifications require a VAPID key pair. Generate one with:

```sh
uv run generate-vapid-keys
```

Then add the three printed lines to your `.env`:

```sh
VAPID_PRIVATE_KEY=<generated>
VAPID_PUBLIC_KEY=<generated>
VAPID_CLAIM_SUBJECT=mailto:your@email.com  # or https://yourdomain.com
```

If the VAPID variables are absent or empty the feature is silently disabled and everything else continues to work normally.

To send a test notification to all current subscribers:

```sh
uv run test-push-notification # optional: add "My title" "My body text" as positional args
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
