import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection
from readerwriterlock import rwlock

from app import env
from app.services.internal.model import Warden
from app.services.internal.warden_store import WardenStore
from app.services.mac_address_helper import should_ignore_device
from app.services.persistent_collections import PersistentPathProvider, persistent
from app.services.polling_service import PollingService
from app.services.virtual_day import crossed_virtual_day

logger = logging.getLogger("uvicorn.error")


@dataclass
class InternalPersistentData(PersistentPathProvider):
    """Persistent storage for internal device-tracking state."""

    first_device_on_site = persistent(datetime, "first_device_on_site", None)

    last_device_on_site = persistent(datetime, "last_device_on_site", None)

    active_devices_ct = persistent(int, "active_devices_ct", 0)

    wardens_on_site = persistent(list[Warden], "wardens_on_site", [])

    def get_path(self) -> str:
        """Return the base path for internal persistent data."""
        return str(Path(env.LOCAL_DATA_PATH) / "internal")


class InternalService(PollingService):
    """Poll the router for connected devices and track warden presence."""

    def __init__(self) -> None:
        super().__init__()
        self._last_service_started: datetime = datetime.now(tz=ZoneInfo("Europe/Berlin"))

        self._internal_data = InternalPersistentData()
        self._last_updated: datetime | None = None
        self._last_error: Exception | None = None

        self._rwlock = rwlock.RWLockFair()

        self._router_ip: str = ""
        self._username: str = ""
        self._password: str = ""

    def get_last_service_started(self) -> datetime:
        """Return the timestamp when the service was created."""
        return self._last_service_started

    def get_last_updated(self) -> datetime | None:
        """Return the timestamp of the last successful poll."""
        with self._rwlock.gen_rlock():
            return self._last_updated

    def get_last_error(self) -> Exception | None:
        """Return the last polling error, if any."""
        with self._rwlock.gen_rlock():
            return self._last_error

    def get_active_devices_ct(self) -> int:
        """Return the number of active non-infrastructure devices."""
        with self._rwlock.gen_rlock():
            return self._internal_data.active_devices_ct

    def get_wardens_on_site(self) -> list[Warden]:
        """Return the list of wardens currently on site."""
        with self._rwlock.gen_rlock():
            return self._internal_data.wardens_on_site

    def get_first_device_on_site(self) -> datetime | None:
        """Return the timestamp when the first device appeared today."""
        with self._rwlock.gen_rlock():
            return self._internal_data.first_device_on_site

    def get_last_device_on_site(self) -> datetime | None:
        """Return the timestamp when the last device left today."""
        with self._rwlock.gen_rlock():
            return self._internal_data.last_device_on_site

    async def _run_poll(self) -> None:
        await self._run_internal_query(self._router_ip, self._username, self._password)

    def _update_device_statistics(self, old_active_devices_ct: int, new_active_devices_ct: int) -> None:
        """Update the first and last device timestamps based on device count changes.

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

    async def _run_internal_query(self, router_ip: str, username: str, password: str) -> None:
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
                        WardenStore.get_instance().first_or_none(device["MacAddress"], device["ActualName"])
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
            logger.exception("Error during Internal refresh")
            with self._rwlock.gen_wlock():
                self._last_error = e

    def start_polling(  # type: ignore[override]
        self,
        router_ip: str | None,
        username: str | None,
        password: str | None,
        interval: int = 60,
        delay_to_first_poll: int = 30,
    ) -> None:
        """Begin periodic router polling with the given credentials."""
        if not router_ip or not username or not password:
            logger.warning("Router credentials not set - internal polling will not start")
            return
        self._router_ip = router_ip
        self._username = username
        self._password = password
        super().start_polling(interval, delay=delay_to_first_poll)
