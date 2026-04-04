#!/usr/bin/env python3
"""Format, lint, and type-check the project.

Usage:
    uv run lint          # auto-fix formatting and lint issues
    uv run lint --check  # fail on violations without modifying files (for CI)
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)


def run(args: list[str], env: dict[str, str] | None = None) -> None:
    label = " ".join(args)
    print(f"==> {label}")
    result = subprocess.run(args, cwd=PROJECT_ROOT, env=env)  # noqa: S603
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    check = "--check" in sys.argv[1:]
    run(["ruff", "format", "--check", "."] if check else ["ruff", "format", "."])
    run(["ruff", "check", "."] if check else ["ruff", "check", ".", "--fix"])
    run(["pyright"], env={**os.environ, "NODE_OPTIONS": ""})
    print("==> Done")


if __name__ == "__main__":
    main()
