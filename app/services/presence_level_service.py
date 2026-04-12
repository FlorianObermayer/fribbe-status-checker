from __future__ import annotations

import logging
from datetime import date, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection
from readerwriterlock import rwlock

from app.services.mac_address_helper import should_ignore_device
from app.services.occupancy.model import OccupancyType
from app.services.polling_service import PollingService
from app.services.presence_level import PresenceLevel
from app.services.presence_thresholds import PresenceThresholds
from app.services.virtual_day import get_virtual_date

if TYPE_CHECKING:
    from app.services.message_service import MessageService
    from app.services.occupancy.occupancy_service import OccupancyService
    from app.services.push_sender import PushSender
    from app.services.weather_service import WeatherService

logger = logging.getLogger("uvicorn.error")


class PresenceLevelService(PollingService):
    """Poll the router for device counts and derive the current presence level."""

    def __init__(
        self,
        weather_service: WeatherService | None,
        message_service: MessageService,
        push_sender: PushSender | None,
        occupancy_service: OccupancyService,
    ) -> None:
        super().__init__()

        self._message_service: MessageService = message_service
        self._weather_service: WeatherService | None = weather_service
        self._push_sender: PushSender | None = push_sender
        self._occupancy_service: OccupancyService = occupancy_service

        self._last_updated: datetime | None = None
        self._last_error: Exception | None = None
        self._presence_level: PresenceLevel = PresenceLevel.EMPTY

        self._rwlock = rwlock.RWLockFair()
        self._thresholds = PresenceThresholds()

        self._push_initialized: bool = False
        self._last_push_virtual_date: date | None = None

        self._router_ip: str = ""
        self._username: str = ""
        self._password: str = ""

    def get_level(self) -> PresenceLevel:
        """Return the current presence level."""
        with self._rwlock.gen_rlock():
            return self._presence_level

    def get_last_updated(self) -> datetime | None:
        """Return the timestamp of the last successful poll."""
        with self._rwlock.gen_rlock():
            return self._last_updated

    def get_last_error(self) -> Exception | None:
        """Return the last polling error, if any."""
        with self._rwlock.gen_rlock():
            return self._last_error

    async def _run_poll(self) -> None:
        await self._run_presence_detection(self._router_ip, self._username, self._password)

    async def _run_presence_detection(self, router_ip: str, username: str, password: str) -> None:
        try:
            logger.info("Refresh Presence Level...")
            with Connection(f"http://{router_ip}", username, password, login_on_demand=True, timeout=10) as connection:
                client = Client(connection)
                active_member_devices_ct = len(
                    [
                        device
                        for device in client.wlan.host_list()["Hosts"]["Host"]
                        if not should_ignore_device(device["MacAddress"])
                    ],
                )
                logger.debug("active member devices: %s", active_member_devices_ct)
                new_level = self._thresholds.get_presence_level(active_member_devices_ct)
                with self._rwlock.gen_wlock():
                    prev_level = self._presence_level
                    self._presence_level = new_level
                    self._last_updated = datetime.now(tz=ZoneInfo("Europe/Berlin"))
                    self._last_error = None
            logger.info("Refresh Presence Level... DONE (%s)", self._presence_level)
            try:
                self._try_send_first_active_push(prev_level, new_level)
            except Exception:
                logger.exception("Error sending first active push")
        except Exception as e:
            logger.exception("Error during presence detection")
            with self._rwlock.gen_wlock():
                self._presence_level = PresenceLevel.EMPTY
                self._last_error = e

    def _try_send_first_active_push(self, prev_level: PresenceLevel, new_level: PresenceLevel) -> bool:
        """Fire a push notification the first time per day the level goes from empty to non-empty."""
        if not self._push_sender:
            return False
        if not self._push_initialized:
            # Skip the very first poll to avoid false alarms on service restart
            self._push_initialized = True
            return False

        if new_level == PresenceLevel.EMPTY:
            return False

        if prev_level != PresenceLevel.EMPTY:
            return False

        now = datetime.now(tz=ZoneInfo("Europe/Berlin"))

        virtual_today = get_virtual_date(now)

        if self._last_push_virtual_date == virtual_today:
            return False

        self._last_push_virtual_date = virtual_today
        title, body = self._build_push_message(new_level)
        logger.info("First non-empty presence today — sending push notifications")
        self._push_sender.send_to_topic_sync("presence", title, body)
        return True

    def _build_push_message(self, level: PresenceLevel) -> tuple[str, str]:
        """Return (title, body) for the push notification."""
        weather = self._weather_service.get_condition() if self._weather_service is not None else None
        daily = self._occupancy_service.get_occupancy()
        occupancy_type = daily.occupancy_type if hasattr(daily, "occupancy_type") else OccupancyType.NONE
        occupancy_time_str = next(
            (event.time_str for event in daily.events if event.occupancy_type == OccupancyType.FULLY),
            None,
        )
        msg = self._message_service.get_push_message(level, occupancy_type, occupancy_time_str, weather=weather)
        return msg.title, msg.message

    def start_polling(  # type: ignore[override]
        self,
        router_ip: str | None,
        username: str | None,
        password: str | None,
        interval: int = 60,
        delay_to_first_poll: int = 0,
    ) -> None:
        """Begin periodic presence polling with the given credentials."""
        if not router_ip or not username or not password:
            logger.warning("Router credentials not set - presence polling will not start")
            return
        self._router_ip = router_ip
        self._username = username
        self._password = password
        super().start_polling(interval, delay=delay_to_first_poll)
