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
from typing import Annotated

from fastapi import Depends, HTTPException

import app.env as env
from app.services.internal.InternalService import InternalService
from app.services.MessageService import MessageService
from app.services.NotificationService import NotificationService
from app.services.occupancy.OccupancyService import OccupancyService
from app.services.PresenceLevelService import PresenceLevelService
from app.services.PushSubscriptionService import PushSubscriptionService
from app.services.WeatherService import WeatherService

_logger = logging.getLogger("uvicorn.error")

# ---------------------------------------------------------------------------
# Service singletons — populated by startup(), accessed via getters below.
# ---------------------------------------------------------------------------

_occupancy_service: OccupancyService | None = None
_internal_service: InternalService | None = None
_message_service: MessageService | None = None
_notification_service: NotificationService | None = None
_weather_service: WeatherService | None = None
_push_subscription_service: PushSubscriptionService | None = None
_presence_service: PresenceLevelService | None = None


# ---------------------------------------------------------------------------
# Lifecycle — called from the FastAPI lifespan in app.main
# ---------------------------------------------------------------------------


def startup() -> None:
    """Create service singletons, start background pollers.

    Must be called exactly once during FastAPI lifespan startup.
    """
    global _occupancy_service, _internal_service, _message_service
    global _notification_service, _weather_service, _push_subscription_service, _presence_service

    env.validate()

    # -- Occupancy -----------------------------------------------------------
    _occupancy_service = OccupancyService()
    _occupancy_service.start_polling(env.OCCUPANCY_POLLING_INTERVAL_SECONDS)

    # -- Internal (router device tracking) -----------------------------------
    _internal_service = InternalService()
    _internal_service.start_polling(
        env.ROUTER_IP,
        env.ROUTER_USERNAME,
        env.ROUTER_PASSWORD,
        env.INTERNAL_POLLING_INTERVAL_SECONDS,
        env.INTERNAL_POLLING_DELAY_SECONDS,
    )

    # -- Messaging & notifications -------------------------------------------
    _message_service = MessageService()

    _notification_service = NotificationService()
    _notification_service.start_cleanup_job()

    # -- Weather (optional) --------------------------------------------------
    if env.OPENWEATHERMAP_API_KEY and env.WEATHER_LAT is not None and env.WEATHER_LON is not None:
        _weather_service = WeatherService(env.OPENWEATHERMAP_API_KEY, env.WEATHER_LAT, env.WEATHER_LON)
    else:
        _logger.warning("OpenWeatherMap not configured; weather-aware messages disabled")

    # -- Push notifications (optional) ---------------------------------------
    if env.VAPID_PRIVATE_KEY and env.VAPID_PUBLIC_KEY and env.VAPID_CLAIM_SUBJECT:
        _push_subscription_service = PushSubscriptionService(
            env.VAPID_PRIVATE_KEY, env.VAPID_PUBLIC_KEY, env.VAPID_CLAIM_SUBJECT
        )
    else:
        _logger.warning("VAPID keys not configured; push notifications disabled")

    # -- Presence detection --------------------------------------------------
    _presence_service = PresenceLevelService(
        _weather_service, _message_service, _push_subscription_service, _occupancy_service
    )
    _presence_service.start_polling(
        env.ROUTER_IP,
        env.ROUTER_USERNAME,
        env.ROUTER_PASSWORD,
        env.PRESENCE_POLLING_INTERVAL_SECONDS,
        env.PRESENCE_POLLING_DELAY_SECONDS,
    )


def shutdown() -> None:
    """Stop all background pollers for a graceful shutdown."""
    if _occupancy_service:
        _occupancy_service.stop_polling()
    if _internal_service:
        _internal_service.stop_polling()
    if _notification_service:
        _notification_service.stop_polling()
    if _presence_service:
        _presence_service.stop_polling()


def reset_for_testing() -> None:
    """Reset all service singletons to ``None``.  **Test-only.**"""
    global _occupancy_service, _internal_service, _message_service
    global _notification_service, _weather_service, _push_subscription_service, _presence_service

    _occupancy_service = None
    _internal_service = None
    _message_service = None
    _notification_service = None
    _weather_service = None
    _push_subscription_service = None
    _presence_service = None


# ---------------------------------------------------------------------------
# Dependency providers (use these in routers via Annotated[T, Depends(...)])
# ---------------------------------------------------------------------------


def get_occupancy_service() -> OccupancyService:
    if _occupancy_service is None:
        raise RuntimeError("Services not initialized - call startup() first")
    return _occupancy_service


def get_internal_service() -> InternalService:
    if _internal_service is None:
        raise RuntimeError("Services not initialized - call startup() first")
    return _internal_service


def get_message_service() -> MessageService:
    if _message_service is None:
        raise RuntimeError("Services not initialized - call startup() first")
    return _message_service


def get_notification_service() -> NotificationService:
    if _notification_service is None:
        raise RuntimeError("Services not initialized - call startup() first")
    return _notification_service


def get_weather_service() -> WeatherService | None:
    return _weather_service


def get_presence_service() -> PresenceLevelService:
    if _presence_service is None:
        raise RuntimeError("Services not initialized - call startup() first")
    return _presence_service


def get_push_subscription_service() -> PushSubscriptionService:
    """Raise 503 when VAPID keys are not configured."""
    if _push_subscription_service is None:
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    return _push_subscription_service


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
