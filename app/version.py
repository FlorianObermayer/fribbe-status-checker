import hashlib
import subprocess
from pathlib import Path


def get_content_hash_version() -> str:
    """Hash the content of CSS/JS static assets as a cache-busting version string."""
    h = hashlib.sha256()
    static_dir = Path(__file__).parent / "static"
    for pattern in ("css/*.css", "js/*.js"):
        for f in sorted(static_dir.glob(pattern)):
            h.update(f.read_bytes())
    return h.hexdigest()[:8]


def get_git_commit_version() -> str:
    """Return the current git commit hash as a version string, or "dev" if not available."""
    try:
        result = subprocess.run(
            ["/usr/bin/git", "rev-parse", "--short", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:  # noqa: BLE001
        return "dev"
