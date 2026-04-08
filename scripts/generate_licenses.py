#!/usr/bin/env python3
"""Generate third-party license metadata for the OpenAPI schema.

Reads direct production dependencies from pyproject.toml and uses
pip-licenses to resolve their SPDX identifiers and project URLs.

Usage:
    uv run generate-licenses          # writes app/licenses.json
"""

import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_ROOT / "app" / "licenses.json"
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"

# Matches 'packagename>=1.0' or 'package[extra]>=1.0' etc. inside a TOML list.
_DEP_RE = re.compile(r'"([a-zA-Z0-9_-]+)(?:\[.*?\])?[><=!~]')


def _read_packages() -> list[str]:
    """Extract direct dependency names from pyproject.toml [project].dependencies."""
    text = PYPROJECT_PATH.read_text()
    in_deps = False
    packages: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("dependencies"):
            in_deps = True
            continue
        if in_deps:
            if stripped == "]":
                break
            match = _DEP_RE.search(stripped)
            if match:
                packages.append(match.group(1))
    return packages


def main() -> None:
    packages = _read_packages()
    if not packages:
        print("No dependencies found in pyproject.toml")
        sys.exit(1)

    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "uv",
            "run",
            "pip-licenses",
            "--format=json",
            "--with-urls",
            "--no-version",
            "--packages",
            *packages,
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    raw: list[dict[str, str]] = json.loads(result.stdout)

    licenses = [
        {"name": entry["Name"], "license": entry["License"], "url": entry.get("URL", "")}
        for entry in sorted(raw, key=lambda e: e["Name"].lower())
    ]

    OUTPUT_PATH.write_text(json.dumps(licenses, indent=2) + "\n")
    print(f"Wrote {len(licenses)} license entries to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
