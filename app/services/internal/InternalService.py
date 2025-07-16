import asyncio
from datetime import datetime, timedelta
from os import path
import os
import threading
from typing import List
from zoneinfo import ZoneInfo
from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection
import time
import logging
from readerwriterlock import rwlock

from app.services.MacAddressHelper import should_ignore_device
from app.services.PersistentCollections import PersistentDict
from app.services.internal.Model import Warden, Wardens

logger = logging.getLogger("uvicorn.error")


class InternalService:

    _first_device_on_site_key = "first_device_on_site"
    _last_device_on_site_key = "last_device_on_site"

    def __init__(self):
        self._last_service_started: datetime = datetime.now(
            tz=ZoneInfo("Europe/Berlin")
        )
        self._last_updated : datetime | None =  None
        self._interval_thread = None
        self._stop_event = threading.Event()
        self._last_error: Exception | None = None
        self._active_devices_ct: int = 0
        self._wardens_on_site: List[Warden] = []

        self._persistent_device_timestamps: PersistentDict[datetime | None] = (
            PersistentDict(
                path.join(
                    os.environ["LOCAL_DATA_PATH"], "persistent_device_timestamps.json"
                ),
                value_type=datetime,
            )
        )

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
            return self._active_devices_ct

    def get_wardens_on_site(self):
        with self._rwlock.gen_rlock():
            return self._wardens_on_site

    def get_first_device_on_site(self):
        with self._rwlock.gen_rlock():
            return self._persistent_device_timestamps[
                InternalService._first_device_on_site_key
            ]

    def get_last_device_on_site(self):
        with self._rwlock.gen_rlock():
            return self._persistent_device_timestamps[
                InternalService._last_device_on_site_key
            ]

    def _update_device_statistics(self, new_active_devices_ct: int):
        now = datetime.now(tz=ZoneInfo("Europe/Berlin"))

        # reset at 5am
        reset_hour = 5
        if self._last_updated:
            last_virtual_day = (self._last_updated - timedelta(hours=reset_hour)).date()
            now_virtual_day = (now - timedelta(hours=reset_hour)).date()
            if last_virtual_day < now_virtual_day:
                self._persistent_device_timestamps[
                    InternalService._first_device_on_site_key
                ] = None
                self._persistent_device_timestamps[
                    InternalService._last_device_on_site_key
                ] = None

        if self._persistent_device_timestamps[
            InternalService._first_device_on_site_key
        ] is None and (new_active_devices_ct > 0 or self._active_devices_ct > 9):
            self._persistent_device_timestamps[
                InternalService._first_device_on_site_key
            ] = now

        if (
            self._active_devices_ct == 0
            and new_active_devices_ct > 0
            and self._persistent_device_timestamps[
                InternalService._first_device_on_site_key
            ]
            is None
        ):
            self._persistent_device_timestamps[
                InternalService._first_device_on_site_key
            ] = now

        if self._active_devices_ct > 0 and new_active_devices_ct == 0:
            self._persistent_device_timestamps[
                InternalService._last_device_on_site_key
            ] = now

    async def _run_internal_query(self, router_ip: str, username: str, password: str):
        try:
            logger.info(f"Refresh Internal...")
            with Connection(
                f"http://{router_ip}", username, password, login_on_demand=True
            ) as connection:
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
                    self._wardens_on_site = []
                    for warden in wardens:
                        if warden and warden.name not in seen_names:
                            self._wardens_on_site.append(warden)
                            seen_names.add(warden.name)
                    self._active_devices_ct = active_member_devices_ct
                    self._update_device_statistics(active_member_devices_ct)
                    self._last_updated = datetime.now(tz=ZoneInfo("Europe/Berlin"))
                    self._last_error = None
            logger.info(f"Refresh Internal... DONE)")
        except Exception as e:
            logger.error(f"Error during Internal refresh: {e}", exc_info=True)
            with self._rwlock.gen_wlock():
                self._last_error = e

    def _internal_query_loop(
        self, interval: int, router_ip: str, username: str, password: str
    ):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while not self._stop_event.is_set():
            loop.run_until_complete(
                self._run_internal_query(router_ip, username, password)
            )
            time.sleep(interval)

    def start_polling(
        self,
        router_ip: str,
        username: str,
        password: str,
        interval: int = 60,
        delay_to_first_poll: int = 30,
    ):
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
