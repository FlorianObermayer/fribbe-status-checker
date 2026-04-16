"""Service singletons wired up from environment configuration.

Routers should consume services via the ``Annotated`` dependency aliases
(``OccupancyServiceDep``, ``PresenceServiceDep``, …) exported from this
module.  FastAPI resolves them through ``Depends``, which enables clean
test-time overrides via ``app.dependency_overrides``.

All service construction and background-polling is deferred to
``startup()`` / ``shutdown()``, called from the FastAPI lifespan handler
in ``app.main``.  This keeps importing the module side-effect free so
that tests can import routers without spawning real background threads.
"""

import logging
from typing import Annotated, cast

from fastapi import Depends, HTTPException

from app.config import cfg
from app.services.internal.internal_service import InternalService
from app.services.message_service import MessageService
from app.services.notification_service import NotificationService
from app.services.occupancy.occupancy_service import OccupancyService
from app.services.presence_level_service import PresenceLevelService
from app.services.push_subscription_service import PushSubscriptionService
from app.services.weather_service import WeatherService

_logger = logging.getLogger("uvicorn.error")

# ---------------------------------------------------------------------------
# Service singletons — populated by startup(), accessed via getters below.
# ---------------------------------------------------------------------------


class _Services:
    """Mutable container for service singletons."""

    occupancy: OccupancyService | None = None
    internal: InternalService | None = None
    message: MessageService | None = None
    notification: NotificationService | None = None
    weather: WeatherService | None = None
    push_subscription: PushSubscriptionService | None = None
    presence: PresenceLevelService | None = None


_svc = _Services()


# ---------------------------------------------------------------------------
# Lifecycle — called from the FastAPI lifespan in app.main
# ---------------------------------------------------------------------------


def startup() -> None:
    """Create service singletons, start background pollers.

    Must be called exactly once during FastAPI lifespan startup.
    """
    # -- Occupancy -----------------------------------------------------------
    _svc.occupancy = OccupancyService()
    _svc.occupancy.start_polling(cfg.OCCUPANCY_POLLING_INTERVAL_SECONDS)

    # -- Internal (router device tracking) -----------------------------------
    _svc.internal = InternalService()
    if cfg.features.is_presence_enabled():
        _svc.internal.start_polling(
            cfg.ROUTER_IP,
            cfg.ROUTER_USERNAME,
            cfg.ROUTER_PASSWORD,
            cfg.INTERNAL_POLLING_INTERVAL_SECONDS,
            cfg.INTERNAL_POLLING_DELAY_SECONDS,
        )
    else:
        _logger.warning("Router credentials not configured; internal polling disabled")

    # -- Messaging & notifications -------------------------------------------
    _svc.message = MessageService()

    # -- Push notifications (optional) ---------------------------------------
    if cfg.features.is_push_enabled():
        _svc.push_subscription = PushSubscriptionService(
            cast("str", cfg.VAPID_PRIVATE_KEY),
            cast("str", cfg.VAPID_PUBLIC_KEY),
            cast("str", cfg.VAPID_CLAIM_SUBJECT),
        )
    else:
        _logger.warning("VAPID keys not configured; push notifications disabled")

    _svc.notification = NotificationService(push_sender=_svc.push_subscription)
    _svc.notification.start_cleanup_job()

    # -- Weather (optional) --------------------------------------------------
    if cfg.features.is_weather_enabled():
        _svc.weather = WeatherService(
            cast("str", cfg.OPENWEATHERMAP_API_KEY),
            cast("float", cfg.WEATHER_LAT),
            cast("float", cfg.WEATHER_LON),
        )
    else:
        _logger.warning("OpenWeatherMap not configured; weather-aware messages disabled")

    # -- Presence detection --------------------------------------------------
    _svc.presence = PresenceLevelService(
        _svc.weather,
        _svc.message,
        _svc.push_subscription,
        _svc.occupancy,
    )
    if cfg.features.is_presence_enabled():
        _svc.presence.start_polling(
            cfg.ROUTER_IP,
            cfg.ROUTER_USERNAME,
            cfg.ROUTER_PASSWORD,
            cfg.PRESENCE_POLLING_INTERVAL_SECONDS,
            cfg.PRESENCE_POLLING_DELAY_SECONDS,
        )
    else:
        _logger.warning("Router credentials not configured; presence polling disabled")


def shutdown() -> None:
    """Stop all background pollers for a graceful shutdown."""
    if _svc.occupancy:
        _svc.occupancy.stop_polling()
    if _svc.internal:
        _svc.internal.stop_polling()
    if _svc.notification:
        _svc.notification.stop_polling()
    if _svc.presence:
        _svc.presence.stop_polling()


# ---------------------------------------------------------------------------
# Dependency providers (use these in routers via Annotated[T, Depends(...)])
# ---------------------------------------------------------------------------


def get_occupancy_service() -> OccupancyService:
    """Return the OccupancyService singleton."""
    if _svc.occupancy is None:
        msg = "Services not initialized - call startup() first"
        raise RuntimeError(msg)
    return _svc.occupancy


def get_internal_service() -> InternalService:
    """Return the InternalService singleton."""
    if _svc.internal is None:
        msg = "Services not initialized - call startup() first"
        raise RuntimeError(msg)
    return _svc.internal


def get_message_service() -> MessageService:
    """Return the MessageService singleton."""
    if _svc.message is None:
        msg = "Services not initialized - call startup() first"
        raise RuntimeError(msg)
    return _svc.message


def get_notification_service() -> NotificationService:
    """Return the NotificationService singleton."""
    if _svc.notification is None:
        msg = "Services not initialized - call startup() first"
        raise RuntimeError(msg)
    return _svc.notification


def get_weather_service() -> WeatherService | None:
    """Return the WeatherService singleton, or None if not configured."""
    return _svc.weather


def get_presence_service() -> PresenceLevelService:
    """Return the PresenceLevelService singleton."""
    if _svc.presence is None:
        msg = "Services not initialized - call startup() first"
        raise RuntimeError(msg)
    return _svc.presence


def get_push_subscription_service() -> PushSubscriptionService:
    """Raise 503 when VAPID keys are not configured."""
    if _svc.push_subscription is None:
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    return _svc.push_subscription


# ---------------------------------------------------------------------------
# Annotated type aliases — import these in routers for concise signatures
# ---------------------------------------------------------------------------

OccupancyServiceDep = Annotated[OccupancyService, Depends(get_occupancy_service)]
InternalServiceDep = Annotated[InternalService, Depends(get_internal_service)]
MessageServiceDep = Annotated[MessageService, Depends(get_message_service)]
NotificationServiceDep = Annotated[NotificationService, Depends(get_notification_service)]
WeatherServiceDep = Annotated[WeatherService | None, Depends(get_weather_service)]
PresenceServiceDep = Annotated[PresenceLevelService, Depends(get_presence_service)]
PushSubscriptionServiceDep = Annotated[PushSubscriptionService, Depends(get_push_subscription_service)]
