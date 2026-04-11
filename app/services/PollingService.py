import asyncio
import logging
import threading
from abc import ABC, abstractmethod

logger = logging.getLogger("uvicorn.error")


class PollingService(ABC):
    """Base class for services that run an async task on a fixed interval in a background thread."""

    def __init__(self) -> None:
        self._interval_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @abstractmethod
    async def _run_poll(self) -> None:
        """Execute one polling iteration. Subclasses must implement this."""

    @property
    def is_polling(self) -> bool:
        return self._interval_thread is not None and self._interval_thread.is_alive()

    def _poll_loop(self, interval: int) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while not self._stop_event.is_set():
            try:
                loop.run_until_complete(self._run_poll())
            except Exception:
                logger.exception("Error in polling iteration")
            self._stop_event.wait(timeout=interval)

    def start_polling(self, interval: int, delay: int = 0) -> None:
        if self._interval_thread is not None and self._interval_thread.is_alive():
            return
        self._stop_event.clear()

        def _start() -> None:
            if delay > 0:
                self._stop_event.wait(timeout=delay)
                if self._stop_event.is_set():
                    return
            self._poll_loop(interval)

        self._interval_thread = threading.Thread(target=_start, daemon=True)
        self._interval_thread.start()

    def stop_polling(self) -> None:
        if self._interval_thread and self._interval_thread.is_alive():
            self._stop_event.set()
            self._interval_thread.join()
            self._interval_thread = None
