"""Format, lint, and type-check the project.

Usage:
    uv run lint        # fail on violations without modifying files (for CI)
    uv run lint --fix  # auto-fix formatting and lint issues
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
JS_FILES = sorted(str(p) for p in Path(PROJECT_ROOT, "app/static/js").rglob("*.js"))
HTML_FILES = sorted(str(p) for p in Path(PROJECT_ROOT, "app/templates").rglob("*.html"))
CSS_FILES = sorted(str(p) for p in Path(PROJECT_ROOT, "app/static/css").rglob("*.css"))
NODE_BIN = Path(PROJECT_ROOT) / "node_modules" / ".bin"


def _run(args: list[str], summary: str, env: dict[str, str] | None = None) -> None:
    print(f"\n>>> {summary}", flush=True)  # noqa: T201
    result = subprocess.run(args, cwd=PROJECT_ROOT, env=env, check=False)  # noqa: S603
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    fix = "--fix" in sys.argv[1:]
    node_env = {**os.environ, "NODE_OPTIONS": ""}

    _run(["ruff", "format", "."] if fix else ["ruff", "format", "--check", "."], "ruff format")
    _run(["ruff", "check", ".", "--fix", "--unsafe-fixes"] if fix else ["ruff", "check", "."], "ruff check")
    _run(["pyright"], "pyright", env=node_env)
    for js_file in JS_FILES:
        _run(["node", "--check", js_file], f"node --check {Path(js_file).name}", env=node_env)
    _run([str(NODE_BIN / "htmlhint"), *HTML_FILES], "htmlhint", env=node_env)
    md_cmd = [str(NODE_BIN / "markdownlint-cli2")]
    if fix:
        md_cmd.append("--fix")
    _run(md_cmd, "markdownlint-cli2", env=node_env)
    css_cmd = [str(NODE_BIN / "stylelint"), *CSS_FILES]
    if fix:
        css_cmd.append("--fix")
    _run(css_cmd, "stylelint", env=node_env)


if __name__ == "__main__":
    main()
