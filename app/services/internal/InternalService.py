import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection
from readerwriterlock import rwlock

import app.env as env
from app.services.internal.Model import Warden, Wardens
from app.services.MacAddressHelper import should_ignore_device
from app.services.PersistentCollections import PersistentPathProvider, persistent
from app.services.VirtualDay import crossed_virtual_day

logger = logging.getLogger("uvicorn.error")


@dataclass
class InternalPersistentData(PersistentPathProvider):
    first_device_on_site = persistent(datetime, "first_device_on_site", None)

    last_device_on_site = persistent(datetime, "last_device_on_site", None)

    active_devices_ct = persistent(int, "active_devices_ct", 0)

    wardens_on_site = persistent(list[Warden], "wardens_on_site", [])

    def get_path(self) -> str:
        return str(Path(env.LOCAL_DATA_PATH) / "internal")


class InternalService:
    def __init__(self):
        self._last_service_started: datetime = datetime.now(tz=ZoneInfo("Europe/Berlin"))

        self._internal_data = InternalPersistentData()
        self._last_updated: datetime | None = None
        self._interval_thread = None
        self._stop_event = threading.Event()
        self._last_error: Exception | None = None

        self._rwlock = rwlock.RWLockFair()

    def get_last_service_started(self):
        return self._last_service_started

    def get_last_updated(self):
        with self._rwlock.gen_rlock():
            return self._last_updated

    def get_last_error(self):
        with self._rwlock.gen_rlock():
            return self._last_error

    def get_active_devices_ct(self):
        with self._rwlock.gen_rlock():
            return self._internal_data.active_devices_ct

    def get_wardens_on_site(self):
        with self._rwlock.gen_rlock():
            return self._internal_data.wardens_on_site

    def get_first_device_on_site(self):
        with self._rwlock.gen_rlock():
            return self._internal_data.first_device_on_site

    def get_last_device_on_site(self):
        with self._rwlock.gen_rlock():
            return self._internal_data.last_device_on_site

    def _update_device_statistics(self, old_active_devices_ct: int, new_active_devices_ct: int):
        """Updates the first and last device timestamps based on device count changes.

        The day resets at 5 AM, meaning:
        - At 5 AM, both first and last device timestamps are reset to None
        - First device: Set when we see devices > 0 for the first time after reset
        - Last device: Set when the last devices leave (count goes from > 0 to 0)
        """
        now = datetime.now(tz=ZoneInfo("Europe/Berlin"))

        # Reset timestamps at 5am if we crossed the virtual day boundary
        if crossed_virtual_day(self._last_updated, now):
            self._internal_data.first_device_on_site = None
            self._internal_data.last_device_on_site = None

        # Set first device timestamp when we see the first activity after reset
        if self._internal_data.first_device_on_site is None and new_active_devices_ct > 0:
            self._internal_data.first_device_on_site = now

        # Set last device timestamp when everyone leaves
        if old_active_devices_ct > 0 and new_active_devices_ct == 0:
            self._internal_data.last_device_on_site = now

    async def _run_internal_query(self, router_ip: str, username: str, password: str):
        try:
            logger.info("Refresh Internal...")
            with Connection(f"http://{router_ip}", username, password, login_on_demand=True) as connection:
                client = Client(connection)
                active_member_devices = [
                    device
                    for device in client.wlan.host_list()["Hosts"]["Host"]
                    if not should_ignore_device(device["MacAddress"])
                ]

                active_member_devices_ct = len(active_member_devices)

                with self._rwlock.gen_wlock():
                    wardens = [
                        Wardens.first_or_none(device["MacAddress"], device["ActualName"])
                        for device in active_member_devices
                    ]
                    # Filter out None and deduplicate by warden name
                    seen_names: set[str] = set()
                    wardens_on_site: list[Warden] = []
                    for warden in wardens:
                        if warden and warden.name not in seen_names:
                            wardens_on_site.append(warden)
                            seen_names.add(warden.name)

                    self._internal_data.wardens_on_site = wardens_on_site
                    self._update_device_statistics(self._internal_data.active_devices_ct, active_member_devices_ct)
                    self._internal_data.active_devices_ct = active_member_devices_ct
                    self._last_updated = datetime.now(tz=ZoneInfo("Europe/Berlin"))
                    self._last_error = None
            logger.info("Refresh Internal... DONE)")
        except Exception as e:
            logger.error(f"Error during Internal refresh: {e}", exc_info=True)
            with self._rwlock.gen_wlock():
                self._last_error = e

    def _internal_query_loop(self, interval: int, router_ip: str, username: str, password: str):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while not self._stop_event.is_set():
            loop.run_until_complete(self._run_internal_query(router_ip, username, password))
            time.sleep(interval)

    def start_polling(
        self,
        router_ip: str | None,
        username: str | None,
        password: str | None,
        interval: int = 60,
        delay_to_first_poll: int = 30,
    ):
        if not router_ip or not username or not password:
            logger.warning("Router credentials not set — internal polling will not start")
            return
        if self._interval_thread is None or not self._interval_thread.is_alive():
            self._stop_event.clear()

            def delayed_start():
                time.sleep(delay_to_first_poll)
                self._internal_query_loop(interval, router_ip, username, password)

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
