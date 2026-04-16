import asyncio
import logging
import threading
from abc import ABC, abstractmethod

from app.config import cfg

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
        """Return True if the polling thread is running."""
        return self._interval_thread is not None and self._interval_thread.is_alive()

    def _poll_loop(self, interval: int) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            while not self._stop_event.is_set():
                try:
                    loop.run_until_complete(self._run_poll())
                except Exception:
                    logger.exception("Error in polling iteration")
                self._stop_event.wait(timeout=interval)
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                logger.exception("Error shutting down polling event loop async generators")
            finally:
                asyncio.set_event_loop(None)
                loop.close()

    def start_polling(self, interval: int, delay: int = 0) -> None:
        """Start the background polling thread."""
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
        """Signal the polling thread to stop and wait for it to finish."""
        if self._interval_thread and self._interval_thread.is_alive():
            self._stop_event.set()
            self._interval_thread.join(timeout=cfg.POLLING_STOP_TIMEOUT_SECONDS)
            self._interval_thread = None
