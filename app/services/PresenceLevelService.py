import asyncio
from datetime import datetime
from enum import Enum
import threading
from zoneinfo import ZoneInfo
from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection
import time
import logging
from readerwriterlock import rwlock

from app.services.MacAddressHelper import should_ignore_device

logger = logging.getLogger("uvicorn.error")


class PresenceLevel(str, Enum):
    EMPTY = "empty"
    FEW = "few"
    MANY = "many"


class PresenceThresholds:
    EMPTY = range(0, 2)  # 0-1 devices
    FEW = range(2, 8)  # 2-7 devices
    MANY = range(8, 100)  # 8+ devices

    THRESHOLDS: dict[PresenceLevel, int] = {
        PresenceLevel.EMPTY: EMPTY[0],
        PresenceLevel.FEW: FEW[0],
        PresenceLevel.MANY: MANY[0],
    }

    @staticmethod
    def get_presence_level(devices_ct: int) -> PresenceLevel:
        match devices_ct:
            case ct if ct in PresenceThresholds.EMPTY:
                return PresenceLevel.EMPTY
            case ct if ct in PresenceThresholds.FEW:
                return PresenceLevel.FEW
            case _:
                return PresenceLevel.MANY


class PresenceLevelService:
    def __init__(self):
        self._last_updated: datetime | None = None
        self._interval_thread = None
        self._stop_event = threading.Event()
        self._last_error: Exception | None = None
        self._presence_level: PresenceLevel = PresenceLevel.EMPTY

        self._rwlock = rwlock.RWLockFair()

    def get_level(self):
        with self._rwlock.gen_rlock():
            return self._presence_level

    def get_last_updated(self):
        with self._rwlock.gen_rlock():
            return self._last_updated

    def get_last_error(self):
        with self._rwlock.gen_rlock():
            return self._last_error

    async def _run_presence_detection(
        self, router_ip: str, username: str, password: str
    ):
        try:
            logger.info(f"Refresh Presence Level...")
            with Connection(
                f"http://{router_ip}", username, password, login_on_demand=True
            ) as connection:
                client = Client(connection)
                active_member_devices_ct = len(
                    [
                        device
                        for device in client.wlan.host_list()["Hosts"]["Host"]
                        if not should_ignore_device(device["MacAddress"])
                    ]
                )
                logger.debug(
                    f"active member devices: {active_member_devices_ct}", exc_info=True
                )
                with self._rwlock.gen_wlock():
                    self._presence_level = PresenceThresholds.get_presence_level(
                        active_member_devices_ct
                    )
                    self._last_updated = datetime.now(tz=ZoneInfo("Europe/Berlin"))
                    self._last_error = None
            logger.info(f"Refresh Presence Level... DONE ({self._presence_level})")
        except Exception as e:
            logger.error(f"Error during presence detection: {e}", exc_info=True)
            with self._rwlock.gen_wlock():
                self._presence_level = PresenceLevel.EMPTY
                self._last_error = e

    def _presence_detection_loop(
        self, interval: int, router_ip: str, username: str, password: str
    ):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while not self._stop_event.is_set():
            loop.run_until_complete(
                self._run_presence_detection(router_ip, username, password)
            )
            time.sleep(interval)

    def start_polling(
        self,
        router_ip: str,
        username: str,
        password: str,
        interval: int = 60,
        delay_to_first_poll: int = 0,
    ):
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
