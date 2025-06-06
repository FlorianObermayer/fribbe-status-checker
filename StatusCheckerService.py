#!/usr/bin/env python3
import asyncio
from enum import Enum
import threading
from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection
import time
import logging

logger = logging.getLogger('uvicorn.error')

class Status(str,Enum):
    NoOne = 'NoOne'
    AFew = 'AFew'
    Many = 'Many'
    
class StatusCheckerService:
    def __init__(self):
        self._status = Status.NoOne
        self._interval_thread = None
        self._stop_event = threading.Event()

    def get_status(self):
        return self._status

    async def _run_status_check(self, router_ip:str, username:str, password:str):
        try:
            logger.info(f"Refresh Status...")
            with Connection(f"http://{username}:{password}@{router_ip}") as connection:
                client = Client(connection)
                active_devices_ct = len(client.wlan.host_list())
                logger.debug(f"active devices: {active_devices_ct}", exc_info=True)
                if active_devices_ct == 0:
                    self._status = Status.NoOne
                elif active_devices_ct <= 2:
                    self._status = Status.AFew
                else:
                    self._status = Status.Many
            logger.info(f"Refresh Status... DONE")
        except Exception as e:
            logger.error(f"Error during status check: {e}", exc_info=True)
            self._status = Status.NoOne

    def _status_check_loop(self, interval: int, router_ip: str, username:str, password:str):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while not self._stop_event.is_set():
            loop.run_until_complete(
                self._run_status_check(router_ip, username, password)
            )
            time.sleep(interval)

    def start_status_check(self, router_ip:str, username:str, password:str, interval:int=30):
        if self._interval_thread is None or not self._interval_thread.is_alive():
            self._stop_event.clear()
            self._interval_thread = threading.Thread(
                target=self._status_check_loop,
                args=(interval, router_ip, username, password),
                daemon=True,
            )
            self._interval_thread.start()

    def stop_status_check(self):
        if self._interval_thread and self._interval_thread.is_alive():
            self._stop_event.set()
            self._interval_thread.join()
            self._interval_thread = None
