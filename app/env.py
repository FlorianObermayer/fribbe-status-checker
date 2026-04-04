"""Central environment variable configuration.

All environment variables consumed by the app are declared here.
Required variables are validated at application startup via validate().
Optional variables fall back to their stated defaults.
"""

import os

# ---------------------------------------------------------------------------
# Required
# ---------------------------------------------------------------------------

SESSION_SECRET_KEY: str = os.environ.get("SESSION_SECRET_KEY", "")
LOCAL_DATA_PATH: str = os.environ.get("LOCAL_DATA_PATH", "")
API_KEYS_PATH: str = os.environ.get("API_KEYS_PATH", "")

_REQUIRED: list[str] = [
    "SESSION_SECRET_KEY",
    "LOCAL_DATA_PATH",
    "API_KEYS_PATH",
]


def validate() -> None:
    """Raise RuntimeError if any required environment variable is missing."""
    _missing = [v for v in _REQUIRED if not os.environ.get(v)]
    if _missing:
        raise RuntimeError(f"Missing required environment variable(s): {', '.join(_missing)}")


# ---------------------------------------------------------------------------
# Optional (with defaults)
# ---------------------------------------------------------------------------

ROUTER_IP: str | None = os.environ.get("ROUTER_IP", "") or None
ROUTER_USERNAME: str | None = os.environ.get("ROUTER_USERNAME", "") or None
ROUTER_PASSWORD: str | None = os.environ.get("ROUTER_PASSWORD", "") or None

PRESENCE_POLLING_INTERVAL_SECONDS: int = int(os.environ.get("PRESENCE_POLLING_INTERVAL_SECONDS", "60"))
PRESENCE_POLLING_DELAY_SECONDS: int = int(os.environ.get("PRESENCE_POLLING_DELAY_SECONDS", "0"))

INTERNAL_POLLING_INTERVAL_SECONDS: int = int(os.environ.get("INTERNAL_POLLING_INTERVAL_SECONDS", "60"))
INTERNAL_POLLING_DELAY_SECONDS: int = int(os.environ.get("INTERNAL_POLLING_DELAY_SECONDS", "30"))

OCCUPANCY_POLLING_INTERVAL_SECONDS: int = int(os.environ.get("OCCUPANCY_POLLING_INTERVAL_SECONDS", "360"))

HTTPS_ONLY: bool = os.environ.get("HTTPS_ONLY", "false").lower() == "true"

# Build-time version tag injected by CI; falls back to "dev" locally.
BUILD_VERSION: str = os.environ.get("BUILD_VERSION", "dev")
