# fribbe-status-checker

A FastAPI-based status checker for [Fribbe Beach](https://fribbebeach.de), running at [status.fribbe-beach.de](https://status.fribbe-beach.de). It combines real-time presence detection with occupancy data scraped from the Fribbe Beach website to give a live status overview.

## Features

- **Presence detection** — Polls router connection data to count connected devices and report a presence level (`empty` / `few` / `many`)
- **Occupancy parsing** — Scrapes the Fribbe Beach weekly plan and event calendar to determine booking status for any given date
- **Notifications** — Create and manage Markdown-formatted notifications with optional validity windows
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

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
