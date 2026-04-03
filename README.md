# fribbe-status-checker

A FastAPI-based status checker for [Fribbe Beach](https://fribbebeach.de), running at [status.fribbe-beach.de](https://status.fribbe-beach.de). It combines real-time presence detection with occupancy data scraped from the Fribbe Beach website to give a live status overview.

## Features

- **Presence detection** — Polls router connection data to count connected devices and report a presence level (`empty` / `few` / `many`)
- **Occupancy parsing** — Scrapes the Fribbe Beach weekly plan and event calendar to determine booking status for any given date
- **Notifications** — Create and manage Markdown-formatted notifications with optional validity windows
- **REST API** — JSON API with API key + session-cookie hybrid authentication
- **Web UI** — Static HTML/CSS/JS frontend served directly by the app



## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
