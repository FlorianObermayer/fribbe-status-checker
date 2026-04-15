import hashlib
from pathlib import Path


def get_content_hash_version() -> str:
    """Hash the content of CSS/JS static assets as a cache-busting version string."""
    h = hashlib.sha256()
    static_dir = Path(__file__).parent / "static"
    for pattern in ("css/*.css", "js/*.js"):
        for f in sorted(static_dir.glob(pattern)):
            h.update(f.read_bytes())
    return h.hexdigest()[:8]
