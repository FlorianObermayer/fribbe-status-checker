"""Central environment variable configuration.

All environment variables consumed by the app are declared here.
Required variables are validated at application startup via validate().
Optional variables fall back to their stated defaults.
"""

import logging
import os
from zoneinfo import ZoneInfo

from app.version import get_content_hash_version

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------

# Minimum token length for all generated and configured tokens.
MIN_TOKEN_LENGTH: int = 48

# Minimum key prefix length for all API keys.
MIN_KEY_PREFIX_LENGTH: int = 5

# Session cookie max age in seconds (7 days).
SESSION_MAX_AGE_SECONDS: int = 60 * 60 * 24 * 7
SESSION_CLEANUP_INTERVAL_SECONDS: int = 60 * 60  # 1 hour

POLLING_STOP_TIMEOUT_SECONDS: int = 10

TOAST_DISPLAY_SECONDS: int = 3

CONTENT_HASH_VERSION: str = get_content_hash_version()

DEFAULT_API_KEY_VALIDITY_DAYS: int = 90

# Validation constraints for API key comment field.
COMMENT_MIN_LENGTH: int = 3
COMMENT_MAX_LENGTH: int = 200


# ---------------------------------------------------------------------------
# Required
# ---------------------------------------------------------------------------

APP_URL: str = ""

SESSION_SECRET_KEY: str = ""
LOCAL_DATA_PATH: str = ""
API_KEYS_PATH: str = ""

_REQUIRED: list[str] = [
    "APP_URL",
    "SESSION_SECRET_KEY",
    "LOCAL_DATA_PATH",
    "API_KEYS_PATH",
]

_SENSITIVE: list[str] = [
    "SESSION_SECRET_KEY",
    "ROUTER_USERNAME",
    "ROUTER_PASSWORD",
    "ADMIN_TOKEN",
    "VAPID_PRIVATE_KEY",
    "VAPID_PUBLIC_KEY",
    "OPENWEATHERMAP_API_KEY",
]


# ---------------------------------------------------------------------------
# Optional (with defaults)
# ---------------------------------------------------------------------------

ROUTER_IP: str | None = None
ROUTER_USERNAME: str | None = None
ROUTER_PASSWORD: str | None = None

PRESENCE_POLLING_INTERVAL_SECONDS: int = 60
PRESENCE_POLLING_DELAY_SECONDS: int = 0

INTERNAL_POLLING_INTERVAL_SECONDS: int = 60
INTERNAL_POLLING_DELAY_SECONDS: int = 30

OCCUPANCY_POLLING_INTERVAL_SECONDS: int = 360

HTTPS_ONLY: bool = False

SHOW_AUTH_BUTTON: bool = False

# When set, accepted as a master credential on all protected endpoints.
# Also disables the empty-store bypass, so setup mode never opens the API to the world.
ADMIN_TOKEN: str | None = None

# Build-time version tag injected by CI; falls back to "dev" locally.
BUILD_VERSION: str = "dev"

# All three must be set together to enable Web Push; individually optional.
VAPID_PRIVATE_KEY: str | None = None
VAPID_PUBLIC_KEY: str | None = None
VAPID_CLAIM_SUBJECT: str | None = None

# OpenWeatherMap integration — all three must be set to enable weather-aware push messages.
OPENWEATHERMAP_API_KEY: str | None = None
WEATHER_LAT: float | None = None
WEATHER_LON: float | None = None
WEATHER_CACHE_TTL_SECONDS: int = 1800  # 30 minutes

# Optional domain added to all Content-Security-Policy source lists (e.g. "https://*.example.com").
# When unset only 'self' is used.
CSP_DOMAIN: str | None = None

# IANA timezone name used for all local datetime calculations (e.g. "Europe/Berlin").
TZ: str = "Europe/Berlin"

# Operator identity shown on the Impressum / Datenschutz page.
OPERATOR_NAME: str = ""
OPERATOR_EMAIL: str = ""

# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------


def is_presence_enabled() -> bool:
    """Return True when router credentials are fully configured.

    Enables WLAN presence detection and named warden tracking.
    """
    return bool(ROUTER_IP and ROUTER_USERNAME and ROUTER_PASSWORD)


def is_push_enabled() -> bool:
    """Return True when the full VAPID key triple is configured.

    Enables Web Push notifications.
    """
    return bool(VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY and VAPID_CLAIM_SUBJECT)


def is_weather_enabled() -> bool:
    """Return True when OpenWeatherMap API key and coordinates are configured.

    Enables weather-aware status messages.
    """
    return bool(OPENWEATHERMAP_API_KEY and WEATHER_LAT is not None and WEATHER_LON is not None)


def is_legal_page_enabled() -> bool:
    """Return True when OPERATOR_NAME and OPERATOR_EMAIL are configured.

    Enables the /legal page with operator contact info and feature disclosures.
    """
    return bool(OPERATOR_NAME and OPERATOR_EMAIL)


def is_login_button_enabled() -> bool:
    """Return True when SHOW_AUTH_BUTTON is configured.

    Enables the "Login" button in the UI.
    """
    return bool(SHOW_AUTH_BUTTON)


# ---------------------------------------------------------------------------
# Env loading and validation
# ---------------------------------------------------------------------------


def load() -> None:
    """Load (or reload) all env var values into the module-level globals.

    Called once at import time and again by validate() so that env vars set
    after the initial import (e.g. in tests) are reflected in the constants.
    Uses globals() dict access to avoid Pyright's reportConstantRedefinition
    rule, which treats uppercase module-level names as Final by convention.
    """
    g = globals()
    g["APP_URL"] = os.environ.get("APP_URL") or ""
    g["SESSION_SECRET_KEY"] = os.environ.get("SESSION_SECRET_KEY", "")
    g["LOCAL_DATA_PATH"] = os.environ.get("LOCAL_DATA_PATH", "")
    g["API_KEYS_PATH"] = os.environ.get("API_KEYS_PATH", "")

    g["ROUTER_IP"] = os.environ.get("ROUTER_IP") or None
    g["ROUTER_USERNAME"] = os.environ.get("ROUTER_USERNAME") or None
    g["ROUTER_PASSWORD"] = os.environ.get("ROUTER_PASSWORD") or None

    g["PRESENCE_POLLING_INTERVAL_SECONDS"] = int(os.environ.get("PRESENCE_POLLING_INTERVAL_SECONDS") or 60)
    g["PRESENCE_POLLING_DELAY_SECONDS"] = int(os.environ.get("PRESENCE_POLLING_DELAY_SECONDS") or 0)

    g["INTERNAL_POLLING_INTERVAL_SECONDS"] = int(os.environ.get("INTERNAL_POLLING_INTERVAL_SECONDS") or 60)
    g["INTERNAL_POLLING_DELAY_SECONDS"] = int(os.environ.get("INTERNAL_POLLING_DELAY_SECONDS") or 30)

    g["OCCUPANCY_POLLING_INTERVAL_SECONDS"] = int(os.environ.get("OCCUPANCY_POLLING_INTERVAL_SECONDS") or 360)

    g["HTTPS_ONLY"] = (os.environ.get("HTTPS_ONLY") or "false").lower() == "true"

    g["SHOW_AUTH_BUTTON"] = os.environ.get("SHOW_AUTH_BUTTON", "false").lower() == "true"

    g["ADMIN_TOKEN"] = os.environ.get("ADMIN_TOKEN") or None

    g["BUILD_VERSION"] = os.environ.get("BUILD_VERSION") or "dev"

    g["VAPID_PRIVATE_KEY"] = os.environ.get("VAPID_PRIVATE_KEY") or None
    g["VAPID_PUBLIC_KEY"] = os.environ.get("VAPID_PUBLIC_KEY") or None
    g["VAPID_CLAIM_SUBJECT"] = os.environ.get("VAPID_CLAIM_SUBJECT") or None

    g["OPENWEATHERMAP_API_KEY"] = os.environ.get("OPENWEATHERMAP_API_KEY") or None
    _lat = os.environ.get("WEATHER_LAT")
    _lon = os.environ.get("WEATHER_LON")
    g["WEATHER_LAT"] = float(_lat) if _lat else None
    g["WEATHER_LON"] = float(_lon) if _lon else None

    g["WEATHER_CACHE_TTL_SECONDS"] = int(os.environ.get("WEATHER_CACHE_TTL_SECONDS") or 1800)  # 30 minutes
    g["CSP_DOMAIN"] = os.environ.get("CSP_DOMAIN") or None

    g["TZ"] = os.environ.get("TZ") or "UTC"

    g["OPERATOR_NAME"] = os.environ.get("OPERATOR_NAME") or ""
    g["OPERATOR_EMAIL"] = os.environ.get("OPERATOR_EMAIL") or ""
    _log()


def _log() -> None:
    """Log all loaded env vars, masking sensitive ones, then derived feature flags."""
    logger = logging.getLogger("uvicorn.error")

    logger.info("Loaded environment variables:")

    for var in [v for v in globals() if v.isupper() and not v.startswith("_")]:
        value = globals().get(var)
        if var in _SENSITIVE and value is not None and isinstance(value, str):
            masked = "******" if value else ""
            logger.info("%s=%s", var, masked)
        else:
            logger.info("%s=%s", var, value)

    logger.info("Feature flags:")
    g = globals()
    for name, fn in sorted(
        (k, v) for k, v in g.items() if k.startswith("is_") and k.endswith("_enabled") and callable(v)
    ):
        logger.info("%s -> %s", name, fn())


def validate() -> None:
    """Raise RuntimeError if any required environment variable is missing."""
    load()
    _missing = [v for v in _REQUIRED if not os.environ.get(v)]
    if _missing:
        msg = f"Missing required environment variable(s): {', '.join(_missing)}"
        raise RuntimeError(msg)
    if len(SESSION_SECRET_KEY) < MIN_TOKEN_LENGTH:
        msg = f"SESSION_SECRET_KEY must be at least {MIN_TOKEN_LENGTH} characters long"
        raise RuntimeError(msg)
    if ADMIN_TOKEN is not None and len(ADMIN_TOKEN) < MIN_TOKEN_LENGTH:
        msg = f"ADMIN_TOKEN must be at least {MIN_TOKEN_LENGTH} characters long"
        raise RuntimeError(msg)

    try:
        _ = ZoneInfo(TZ)
    except Exception as e:
        msg = f"Invalid timezone in TZ: {TZ} ({e})"
        raise RuntimeError(msg) from e


# Populate from os.environ at import time.
load()
