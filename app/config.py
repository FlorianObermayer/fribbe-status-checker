"""Central environment variable configuration.

All configuration — both app constants and environment-sourced variables — is
declared as fields of the ``Config`` dataclass.  Each variable appears exactly
once, with its type, default, and (where applicable) loading logic co-located.

Import the module-level singleton directly::

    from app.config import cfg

    cfg.APP_URL  # env variable
    cfg.MIN_TOKEN_LENGTH  # constant
    cfg.features.is_push_enabled()  # derived feature flag

``reload()`` mutates ``cfg`` in-place from ``os.environ`` and validates it.
Call it explicitly (e.g. at FastAPI startup or in tests after
``monkeypatch.setenv``) to reload env vars.  Pass ``validate=False`` to
skip required-var checks when only a value refresh is needed.
"""

import logging
import os
import sys
from dataclasses import MISSING, dataclass, field
from dataclasses import fields as dataclass_fields
from typing import ClassVar
from zoneinfo import ZoneInfo

from app.version import get_content_hash_version


@dataclass
class Config:
    """All application configuration in one place.

    Instance field metadata keys:
    * ``"required": True``  — must be non-empty; checked during configuration validation.
    * ``"sensitive": True`` — value is masked in startup logs.
    """

    # ── Constants ────────────────────────────────────────────────────────────

    # Minimum token length for all generated and configured tokens.
    MIN_TOKEN_LENGTH: ClassVar[int] = 48
    # Minimum key prefix length for all API keys.
    MIN_KEY_PREFIX_LENGTH: ClassVar[int] = 5
    # Session cookie max age in seconds (7 days).
    SESSION_MAX_AGE_SECONDS: ClassVar[int] = 60 * 60 * 24 * 7
    SESSION_CLEANUP_INTERVAL_SECONDS: ClassVar[int] = 60 * 60  # 1 hour
    POLLING_STOP_TIMEOUT_SECONDS: ClassVar[int] = 10
    TOAST_DISPLAY_SECONDS: ClassVar[int] = 3
    CONTENT_HASH_VERSION: ClassVar[str] = get_content_hash_version()
    DEFAULT_API_KEY_VALIDITY_DAYS: ClassVar[int] = 90
    # Validation constraints for API key comment field.
    API_KEY_COMMENT_MIN_LENGTH: ClassVar[int] = 3
    API_KEY_COMMENT_MAX_LENGTH: ClassVar[int] = 200

    # ── Required ─────────────────────────────────────────────────────────────

    # Public-facing URL of the app, used for redirects and push callbacks.
    APP_URL: str = field(
        default_factory=lambda: os.environ.get("APP_URL") or "",
        metadata={"required": True},
    )
    # Secret key for signing session cookies.
    SESSION_SECRET_KEY: str = field(
        default_factory=lambda: os.environ.get("SESSION_SECRET_KEY") or "",
        metadata={"required": True, "sensitive": True},
    )
    # Directory where the app stores persistent data (notifications, occupancy history, …).
    LOCAL_DATA_PATH: str = field(
        default_factory=lambda: os.environ.get("LOCAL_DATA_PATH") or "",
        metadata={"required": True},
    )
    # Path to the JSON file that stores API keys.
    API_KEYS_PATH: str = field(
        default_factory=lambda: os.environ.get("API_KEYS_PATH") or "",
        metadata={"required": True},
    )

    # ── Auth ─────────────────────────────────────────────────────────────────

    # Master credential accepted on all protected endpoints (ADMIN role).
    ADMIN_TOKEN: str | None = field(
        default_factory=lambda: os.environ.get("ADMIN_TOKEN") or None,
        metadata={"sensitive": True},
    )
    # Show a "Login" button on the home page for unauthenticated users.
    SHOW_AUTH_BUTTON: bool = field(
        default_factory=lambda: os.environ.get("SHOW_AUTH_BUTTON", "false").lower() == "true",
    )
    # Redirect all HTTP requests to HTTPS.
    HTTPS_ONLY: bool = field(
        default_factory=lambda: (os.environ.get("HTTPS_ONLY") or "false").lower() == "true",
    )

    # ── Presence detection (WLAN) ─────────────────────────────────────────────
    # All three router variables must be set together to enable presence detection.

    ROUTER_IP: str | None = field(
        default_factory=lambda: os.environ.get("ROUTER_IP") or None,
    )
    ROUTER_USERNAME: str | None = field(
        default_factory=lambda: os.environ.get("ROUTER_USERNAME") or None,
        metadata={"sensitive": True},
    )
    ROUTER_PASSWORD: str | None = field(
        default_factory=lambda: os.environ.get("ROUTER_PASSWORD") or None,
        metadata={"sensitive": True},
    )
    # How often to poll the router, in seconds.
    PRESENCE_POLLING_INTERVAL_SECONDS: int = field(
        default_factory=lambda: int(os.environ.get("PRESENCE_POLLING_INTERVAL_SECONDS") or 60),
    )
    # Delay before the first presence poll, in seconds.
    PRESENCE_POLLING_DELAY_SECONDS: int = field(
        default_factory=lambda: int(os.environ.get("PRESENCE_POLLING_DELAY_SECONDS") or 0),
    )
    # How often to refresh internal device counts, in seconds.
    INTERNAL_POLLING_INTERVAL_SECONDS: int = field(
        default_factory=lambda: int(os.environ.get("INTERNAL_POLLING_INTERVAL_SECONDS") or 60),
    )
    # Delay before the first internal poll, in seconds.
    INTERNAL_POLLING_DELAY_SECONDS: int = field(
        default_factory=lambda: int(os.environ.get("INTERNAL_POLLING_DELAY_SECONDS") or 30),
    )

    # ── Occupancy scraping ────────────────────────────────────────────────────

    # How often to scrape the booking system for court availability, in seconds.
    OCCUPANCY_POLLING_INTERVAL_SECONDS: int = field(
        default_factory=lambda: int(os.environ.get("OCCUPANCY_POLLING_INTERVAL_SECONDS") or 360),
    )

    # ── Build ─────────────────────────────────────────────────────────────────

    # Build-time version tag injected by CI
    BUILD_VERSION: str = field(
        default_factory=lambda: os.environ.get("BUILD_VERSION") or "dev",
    )

    # ── Web Push / VAPID ─────────────────────────────────────────────────────
    # All three must be set together to enable push notifications.
    # Generate keys with: uv run generate-vapid-keys

    VAPID_PRIVATE_KEY: str | None = field(
        default_factory=lambda: os.environ.get("VAPID_PRIVATE_KEY") or None,
        metadata={"sensitive": True},
    )
    VAPID_PUBLIC_KEY: str | None = field(
        default_factory=lambda: os.environ.get("VAPID_PUBLIC_KEY") or None,
        metadata={"sensitive": True},
    )
    # Contact URI included in the VAPID claim (e.g. mailto:you@example.com).
    VAPID_CLAIM_SUBJECT: str | None = field(
        default_factory=lambda: os.environ.get("VAPID_CLAIM_SUBJECT") or None,
    )

    # ── Weather (OpenWeatherMap) ──────────────────────────────────────────────
    # All three must be set together to enable weather-aware push messages.

    OPENWEATHERMAP_API_KEY: str | None = field(
        default_factory=lambda: os.environ.get("OPENWEATHERMAP_API_KEY") or None,
        metadata={"sensitive": True},
    )
    # Latitude and longitude of the venue.
    WEATHER_LAT: float | None = field(
        default_factory=lambda: float(v) if (v := os.environ.get("WEATHER_LAT")) else None,
    )
    WEATHER_LON: float | None = field(
        default_factory=lambda: float(v) if (v := os.environ.get("WEATHER_LON")) else None,
    )
    # How long to cache weather data, in seconds.
    WEATHER_CACHE_TTL_SECONDS: int = field(
        default_factory=lambda: int(os.environ.get("WEATHER_CACHE_TTL_SECONDS") or 1800),
    )

    # ── Miscellaneous ─────────────────────────────────────────────────────────

    # Additional domain appended to all Content-Security-Policy source lists
    # (e.g. "https://*.example.com"). When unset, only 'self' is used.
    CSP_DOMAIN: str | None = field(
        default_factory=lambda: os.environ.get("CSP_DOMAIN") or None,
    )
    # IANA timezone name for all local datetime calculations (e.g. "Europe/Berlin").
    TZ: str = field(
        default_factory=lambda: os.environ.get("TZ") or "Europe/Berlin",
    )
    # Operator identity shown on the /legal page.
    OPERATOR_NAME: str = field(
        default_factory=lambda: os.environ.get("OPERATOR_NAME") or "",
    )
    OPERATOR_EMAIL: str = field(
        default_factory=lambda: os.environ.get("OPERATOR_EMAIL") or "",
    )
    # Log level for app.* loggers (DEBUG / INFO / WARNING / ERROR / CRITICAL).
    LOG_LEVEL: str = field(
        default_factory=lambda: os.environ.get("LOG_LEVEL") or "INFO",
    )

    # Derived feature flags — not env-sourced, set in __post_init__.
    features: "Features" = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Validate the initial configuration after loading from environment variables."""
        self.features = Features(self)
        self._REQUIRED: frozenset[str] = frozenset(
            f.name for f in dataclass_fields(Config) if f.metadata.get("required")
        )
        self._SENSITIVE: frozenset[str] = frozenset(
            f.name for f in dataclass_fields(Config) if f.metadata.get("sensitive")
        )
        self._validate()
        self._configure_logging()
        self._log(reloaded=False)

    # Derived metadata sets — no manual lists to maintain.

    # ---------------------------------------------------------------------------
    # Loading and validation
    # ---------------------------------------------------------------------------

    def _validate(self) -> None:
        """Raise RuntimeError if the current cfg state is invalid.

        Checks required fields, token lengths, and timezone validity against the
        already-loaded ``cfg`` instance.
        """
        _missing = [v for v in self._REQUIRED if not getattr(self, v, None)]
        if _missing:
            msg = f"Missing required environment variable(s): {', '.join(_missing)}"
            raise RuntimeError(msg)
        if len(self.SESSION_SECRET_KEY) < self.MIN_TOKEN_LENGTH:
            msg = f"SESSION_SECRET_KEY must be at least {self.MIN_TOKEN_LENGTH} characters long"
            raise RuntimeError(msg)
        if self.ADMIN_TOKEN is not None and len(self.ADMIN_TOKEN) < self.MIN_TOKEN_LENGTH:
            msg = f"ADMIN_TOKEN must be at least {self.MIN_TOKEN_LENGTH} characters long"
            raise RuntimeError(msg)
        try:
            _ = ZoneInfo(self.TZ)
        except Exception as e:
            msg = f"Invalid timezone in TZ: {self.TZ} ({e})"
            raise RuntimeError(msg) from e
        _valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.LOG_LEVEL.upper() not in _valid_levels:
            msg = f"Invalid LOG_LEVEL: {self.LOG_LEVEL!r}. Must be one of {', '.join(sorted(_valid_levels))}"
            raise RuntimeError(msg)

    def reload(self) -> None:
        """Mutate ``cfg`` in-place from ``os.environ``.

        Reloads environment-backed values and validates the resulting configuration.
        """
        for f in dataclass_fields(self):
            if f.init and f.default_factory is not MISSING:  # skip non-env fields such as `features`
                setattr(self, f.name, f.default_factory())
        self._validate()
        self._configure_logging()
        self._log(reloaded=True)

    def _configure_logging(self) -> None:
        """Configure the ``app`` logger hierarchy level and attach a stdout handler if needed."""
        level = self.LOG_LEVEL.upper()
        app_logger = logging.getLogger("app")
        app_logger.setLevel(level)
        # Prevent double-logging: uvicorn installs a root handler, so without this
        # every app.* record would be emitted once by our handler and again by uvicorn's.
        app_logger.propagate = False
        if not app_logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(levelname)-8s %(name)s  %(message)s"))
            app_logger.addHandler(handler)
        # Cap noisy third-party loggers so they don't flood output at LOG_LEVEL=DEBUG,
        # while still honoring stricter app log levels like ERROR/CRITICAL.
        noisy_level = max(app_logger.level, logging.WARNING)
        # urllib3 is used by huawei-lte-api; dateparser is verbose during locale loading.
        for noisy in ("urllib3", "dateparser"):
            logging.getLogger(noisy).setLevel(noisy_level)

    def _log(self, *, reloaded: bool) -> None:
        """Log all loaded env vars, masking sensitive ones, then derived feature flags."""
        logger = logging.getLogger(__name__)
        title = "Reloaded" if reloaded else "Loaded"
        logger.info("┌─ %s environment variables %s", title, "─" * (52 - len(title)))

        for f in dataclass_fields(self):
            if not f.init:  # skip non-env fields (e.g. features)
                continue
            value = getattr(self, f.name)
            if f.name in self._SENSITIVE and value is not None and isinstance(value, str):
                display = "••••••" if value else "(empty)"
            else:
                display = str(value) if value is not None else "(unset)"
            logger.info("│  %-40s %s", f.name, display)

        logger.info("├─ Feature flags %s", "─" * 63)

        for name, enabled in self.features.all().items():
            state = "✓  on " if enabled else "✗  off"
            logger.info("│  %s  %s", state, name)

        logger.info("└%s", "─" * 79)


class Features:
    """Derived on/off feature flags computed live from a ``Config`` instance.

    Access via ``cfg.features.is_presence_enabled()`` etc.  The instance holds
    a reference to the parent ``Config``, so changes made by ``reload()`` or
    monkeypatching individual ``cfg`` fields are reflected immediately.
    """

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg

    def is_presence_enabled(self) -> bool:
        """Router credentials are fully configured → WLAN presence detection active."""
        return bool(self._cfg.ROUTER_IP and self._cfg.ROUTER_USERNAME and self._cfg.ROUTER_PASSWORD)

    def is_push_enabled(self) -> bool:
        """Full VAPID key triple is configured → Web Push notifications active."""
        return bool(self._cfg.VAPID_PRIVATE_KEY and self._cfg.VAPID_PUBLIC_KEY and self._cfg.VAPID_CLAIM_SUBJECT)

    def is_weather_enabled(self) -> bool:
        """OpenWeatherMap key and coordinates are configured → weather-aware messages active."""
        return bool(
            self._cfg.OPENWEATHERMAP_API_KEY and self._cfg.WEATHER_LAT is not None and self._cfg.WEATHER_LON is not None
        )

    def is_legal_page_enabled(self) -> bool:
        """OPERATOR_NAME and OPERATOR_EMAIL are configured → /legal page active."""
        return bool(self._cfg.OPERATOR_NAME and self._cfg.OPERATOR_EMAIL)

    def is_login_button_enabled(self) -> bool:
        """SHOW_AUTH_BUTTON is true → Login button shown in the UI."""
        return self._cfg.SHOW_AUTH_BUTTON

    def all(self) -> dict[str, bool]:
        """Return all feature flags as a name → value mapping."""
        return {
            name: getattr(self, name)()
            for name in sorted(vars(type(self)))
            if name != "all" and not name.startswith("__") and callable(getattr(self, name))
        }


# Module-level singleton
cfg: Config = Config()
