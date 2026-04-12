"""Run the development server.

Usage:
    uv run dev
"""

import uvicorn


def main() -> None:
    uvicorn.run("app.main:app", host="127.0.0.1", port=8007)


if __name__ == "__main__":
    main()
