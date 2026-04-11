"""Service singletons wired up from environment configuration.

Routers should consume services via the ``Annotated`` dependency aliases
(``OccupancyServiceDep``, ``PresenceServiceDep``, …) exported from this
module.  FastAPI resolves them through ``Depends``, which enables clean
test-time overrides via ``app.dependency_overrides``.

``env.validate()`` is called here to ensure all required variables are
present before any service is constructed.
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

env.validate()

_logger = logging.getLogger("uvicorn.error")

# ---------------------------------------------------------------------------
# Occupancy
# ---------------------------------------------------------------------------

occupancy_service = OccupancyService()
occupancy_service.start_polling(env.OCCUPANCY_POLLING_INTERVAL_SECONDS)

# ---------------------------------------------------------------------------
# Internal (router device tracking)
# ---------------------------------------------------------------------------

internal_service = InternalService()
internal_service.start_polling(
    env.ROUTER_IP,
    env.ROUTER_USERNAME,
    env.ROUTER_PASSWORD,
    env.INTERNAL_POLLING_INTERVAL_SECONDS,
    env.INTERNAL_POLLING_DELAY_SECONDS,
)

# ---------------------------------------------------------------------------
# Messaging & notifications
# ---------------------------------------------------------------------------

message_service = MessageService()

notification_service = NotificationService()
notification_service.start_cleanup_job()

# ---------------------------------------------------------------------------
# Weather (optional)
# ---------------------------------------------------------------------------

weather_service: WeatherService | None = None
if env.OPENWEATHERMAP_API_KEY and env.WEATHER_LAT is not None and env.WEATHER_LON is not None:
    weather_service = WeatherService(env.OPENWEATHERMAP_API_KEY, env.WEATHER_LAT, env.WEATHER_LON)
else:
    _logger.warning("OpenWeatherMap not configured; weather-aware messages disabled")

# ---------------------------------------------------------------------------
# Push notifications (optional)
# ---------------------------------------------------------------------------

push_subscription_service: PushSubscriptionService | None = None
if env.VAPID_PRIVATE_KEY and env.VAPID_PUBLIC_KEY and env.VAPID_CLAIM_SUBJECT:
    push_subscription_service = PushSubscriptionService(
        env.VAPID_PRIVATE_KEY, env.VAPID_PUBLIC_KEY, env.VAPID_CLAIM_SUBJECT
    )
else:
    _logger.warning("VAPID keys not configured; push notifications disabled")

# ---------------------------------------------------------------------------
# Presence detection
# ---------------------------------------------------------------------------

presence_service = PresenceLevelService(weather_service, message_service, push_subscription_service, occupancy_service)
presence_service.start_polling(
    env.ROUTER_IP,
    env.ROUTER_USERNAME,
    env.ROUTER_PASSWORD,
    env.PRESENCE_POLLING_INTERVAL_SECONDS,
    env.PRESENCE_POLLING_DELAY_SECONDS,
)

# ---------------------------------------------------------------------------
# Dependency providers (use these in routers via Annotated[T, Depends(...)])
# ---------------------------------------------------------------------------


def get_occupancy_service() -> OccupancyService:
    return occupancy_service


def get_internal_service() -> InternalService:
    return internal_service


def get_message_service() -> MessageService:
    return message_service


def get_notification_service() -> NotificationService:
    return notification_service


def get_weather_service() -> WeatherService | None:
    return weather_service


def get_presence_service() -> PresenceLevelService:
    return presence_service


def get_push_subscription_service() -> PushSubscriptionService:
    """Raise 503 when VAPID keys are not configured."""
    if push_subscription_service is None:
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    return push_subscription_service


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
