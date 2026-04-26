"""Run all test suites (pytest + vitest).

Usage:
    uv run test          # run all tests
    uv run test --cov    # run all tests with coverage
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    cov = "--cov" in sys.argv

    py_cmd = ["uv", "run", "pytest", "tests/", "--ignore=tests/js", "--junitxml=junit/test-results.xml"]
    if cov:
        py_cmd += ["--cov=app", "--cov-report=xml", "--cov-report=html"]

    js_cmd = ["npm", "run", "test:js"]
    if cov:
        js_cmd += ["--", "--coverage"]

    failed = False
    env = {**os.environ, "NODE_OPTIONS": ""}
    for cmd in [py_cmd, js_cmd]:
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, env=env, check=False)
        if result.returncode != 0:
            failed = True

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
