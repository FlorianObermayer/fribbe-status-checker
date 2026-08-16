"""Run the same dependency/security checks locally that CI runs in the `uv-audit` job.

Covers:
    - uv.lock consistency check
    - uv audit vulnerability scan (Python dependencies, via OSV)

Usage:
    uv run security-check

"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)

def _run(args: list[str], summary: str) -> bool:
    print(f"\n>>> {summary}", flush=True)
    result = subprocess.run(args, cwd=PROJECT_ROOT, check=False)
    return result.returncode == 0


def main() -> None:
    results: dict[str, bool] = {}

    results["uv lock --check"] = _run(["uv", "lock", "--check"], "uv lock --check")
    results["uv audit"] = _run(
        ["uv", "audit", "--frozen", "--preview-features", "audit-command"],
        "uv audit (Python dependency vulnerabilities)",
    )

    print("\n=== Summary ===")
    failed = False
    for name, passed in results.items():
        print(f"  [{'OK' if passed else 'FAILED'}] {name}")
        failed = failed or not passed

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
