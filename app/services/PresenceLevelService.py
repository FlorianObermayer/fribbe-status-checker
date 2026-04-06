from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import date, datetime
from typing import TYPE_CHECKING, Protocol
from zoneinfo import ZoneInfo

from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection
from readerwriterlock import rwlock

from app.services.MacAddressHelper import should_ignore_device
from app.services.occupancy.Model import OccupancyType
from app.services.occupancy.OccupancyService import OccupancyService
from app.services.PresenceLevel import PresenceLevel
from app.services.PresenceThresholds import PresenceThresholds
from app.services.VirtualDay import get_virtual_date

if TYPE_CHECKING:
    from app.services.MessageService import MessageService
    from app.services.WeatherService import WeatherService


class PushSender(Protocol):
    def send_to_all_sync(self, title: str, body: str) -> None: ...


logger = logging.getLogger("uvicorn.error")


class PresenceLevelService:
    def __init__(
        self,
        weather_service: WeatherService | None,
        message_service: MessageService,
        push_sender: PushSender | None,
        occupancy_service: OccupancyService,
    ) -> None:

        self._message_service: MessageService = message_service
        self._weather_service: WeatherService | None = weather_service
        self._push_sender: PushSender | None = push_sender
        self._occupancy_service: OccupancyService = occupancy_service

        self._last_updated: datetime | None = None
        self._interval_thread = None
        self._stop_event = threading.Event()
        self._last_error: Exception | None = None
        self._presence_level: PresenceLevel = PresenceLevel.EMPTY

        self._rwlock = rwlock.RWLockFair()
        self._thresholds = PresenceThresholds()

        self._push_initialized: bool = False
        self._last_push_virtual_date: date | None = None

    def get_level(self):
        with self._rwlock.gen_rlock():
            return self._presence_level

    def get_last_updated(self):
        with self._rwlock.gen_rlock():
            return self._last_updated

    def get_last_error(self):
        with self._rwlock.gen_rlock():
            return self._last_error

    async def _run_presence_detection(self, router_ip: str, username: str, password: str):
        try:
            logger.info("Refresh Presence Level...")
            with Connection(f"http://{router_ip}", username, password, login_on_demand=True, timeout=10) as connection:
                client = Client(connection)
                active_member_devices_ct = len(
                    [
                        device
                        for device in client.wlan.host_list()["Hosts"]["Host"]
                        if not should_ignore_device(device["MacAddress"])
                    ]
                )
                logger.debug(f"active member devices: {active_member_devices_ct}", exc_info=True)
                new_level = self._thresholds.get_presence_level(active_member_devices_ct)
                with self._rwlock.gen_wlock():
                    prev_level = self._presence_level
                    self._presence_level = new_level
                    self._last_updated = datetime.now(tz=ZoneInfo("Europe/Berlin"))
                    self._last_error = None
            logger.info(f"Refresh Presence Level... DONE ({self._presence_level})")
            try:
                self._try_send_first_active_push(prev_level, new_level)
            except Exception as e:
                logger.error(f"Error sending first active push: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error during presence detection: {e}", exc_info=True)
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
        self._push_sender.send_to_all_sync(title, body)
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

    def _presence_detection_loop(self, interval: int, router_ip: str, username: str, password: str):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while not self._stop_event.is_set():
            loop.run_until_complete(self._run_presence_detection(router_ip, username, password))
            time.sleep(interval)

    def start_polling(
        self,
        router_ip: str | None,
        username: str | None,
        password: str | None,
        interval: int = 60,
        delay_to_first_poll: int = 0,
    ):
        if not router_ip or not username or not password:
            logger.warning("Router credentials not set — presence polling will not start")
            return
        if self._interval_thread is None or not self._interval_thread.is_alive():
            self._stop_event.clear()

            def delayed_start():
                time.sleep(delay_to_first_poll)
                self._presence_detection_loop(interval, router_ip, username, password)

            self._interval_thread = threading.Thread(
                target=delayed_start,
                daemon=True,
            )
            self._interval_thread.start()

    def stop_polling(self):
        if self._interval_thread and self._interval_thread.is_alive():
            self._stop_event.set()
            self._interval_thread.join()
            self._interval_thread = None
