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

logger = logging.getLogger('uvicorn.error')

class PresenceLevel(str,Enum):
    EMPTY = "empty"
    FEW = "few"
    MANY = "many"


class PresenceLevelService:
    def __init__(self):
        self._last_updated = datetime.now(tz=ZoneInfo("Europe/Berlin"))
        self._interval_thread = None
        self._stop_event = threading.Event()
        self._last_error: Exception | None = None
        self._presence_level: PresenceLevel = PresenceLevel.EMPTY

        self._devices_to_ignore = {
            "2C:CF:67:DD:46:23",  # raspberrypi
            "54:60:09:EE:19:28",  # chromecast-audio
        }
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

    async def _run_presence_detection(self, router_ip:str, username:str, password:str):
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
                        if device["MacAddress"] not in self._devices_to_ignore
                    ]
                )
                logger.debug(
                    f"active member devices: {active_member_devices_ct}", exc_info=True
                )
                with self._rwlock.gen_wlock():
                    if active_member_devices_ct == 0:
                        self._presence_level = PresenceLevel.EMPTY
                    elif active_member_devices_ct <= 5:
                        self._presence_level = PresenceLevel.FEW
                    else:
                        self._presence_level = PresenceLevel.MANY

                    self._last_updated = datetime.now(tz=ZoneInfo("Europe/Berlin"))
                    self._last_error = None
            logger.info(f"Refresh Presence Level... DONE ({self._presence_level})")
        except Exception as e:
            logger.error(f"Error during presence detection: {e}", exc_info=True)
            with self._rwlock.gen_wlock():
                self._presence_level = PresenceLevel.EMPTY
                self._last_error = e

    def _presence_detection_loop(self, interval: int, router_ip: str, username:str, password:str):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while not self._stop_event.is_set():
            loop.run_until_complete(
                self._run_presence_detection(router_ip, username, password)
            )
            time.sleep(interval)

    def start_polling(
        self, router_ip: str, username: str, password: str, interval: int = 30
    ):
        if self._interval_thread is None or not self._interval_thread.is_alive():
            self._stop_event.clear()
            self._interval_thread = threading.Thread(
                target=self._presence_detection_loop,
                args=(interval, router_ip, username, password),
                daemon=True,
            )
            self._interval_thread.start()

    def stop_polling(self):
        if self._interval_thread and self._interval_thread.is_alive():
            self._stop_event.set()
            self._interval_thread.join()
            self._interval_thread = None
