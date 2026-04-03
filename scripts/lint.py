#!/usr/bin/env python3
"""Format, lint, and type-check the project.

Usage:
    uv run lint
"""

import os
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(args: list[str], env: dict[str, str] | None = None) -> None:
    label = " ".join(args)
    print(f"==> {label}")
    result = subprocess.run(args, cwd=PROJECT_ROOT, env=env)  # noqa: S603
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    run(["ruff", "format", "."])
    run(["ruff", "check", ".", "--fix"])
    run(["pyright"], env={**os.environ, "NODE_OPTIONS": ""})
    print("==> Done")


if __name__ == "__main__":
    main()
