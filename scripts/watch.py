"""Run the development server with auto-reload.

Usage:
    uv run watch
"""

import uvicorn


def main() -> None:
    uvicorn.run("app.main:app", host="127.0.0.1", port=8007, reload=True)


if __name__ == "__main__":
    main()
