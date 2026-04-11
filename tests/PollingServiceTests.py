"""Tests for PollingService base class."""

import threading
import time

from app.services.PollingService import PollingService


class _CountingService(PollingService):
    """Minimal concrete subclass that counts poll invocations."""

    def __init__(self) -> None:
        super().__init__()
        self.poll_count = 0
        self._poll_event = threading.Event()

    async def _run_poll(self) -> None:
        self.poll_count += 1
        self._poll_event.set()

    def wait_for_poll(self, timeout: float = 2.0) -> bool:
        result = self._poll_event.wait(timeout=timeout)
        self._poll_event.clear()
        return result


class _FailingService(PollingService):
    """Service whose _run_poll raises an exception."""

    def __init__(self) -> None:
        super().__init__()
        self.poll_count = 0
        self._poll_event = threading.Event()

    async def _run_poll(self) -> None:
        self.poll_count += 1
        self._poll_event.set()
        raise RuntimeError("poll failed")

    def wait_for_poll(self, timeout: float = 2.0) -> bool:
        result = self._poll_event.wait(timeout=timeout)
        self._poll_event.clear()
        return result


def test_start_and_stop():
    svc = _CountingService()
    svc.start_polling(interval=60)
    assert svc.is_polling
    svc.wait_for_poll()
    assert svc.poll_count >= 1
    svc.stop_polling()
    assert not svc.is_polling


def test_stop_without_start_is_noop():
    svc = _CountingService()
    svc.stop_polling()
    assert not svc.is_polling


def test_multiple_start_calls_ignored():
    svc = _CountingService()
    svc.start_polling(interval=60)
    svc.wait_for_poll()
    first_count = svc.poll_count
    svc.start_polling(interval=60)
    assert svc.is_polling
    assert svc.poll_count == first_count
    svc.stop_polling()


def test_poll_runs_multiple_times():
    svc = _CountingService()
    svc.start_polling(interval=0)
    svc.wait_for_poll()
    svc.wait_for_poll()
    assert svc.poll_count >= 2
    svc.stop_polling()


def test_delay_defers_first_poll():
    svc = _CountingService()
    svc.start_polling(interval=60, delay=5)
    # Immediately after start, poll should not have run yet
    assert svc.poll_count == 0
    svc.stop_polling()
    # After stop during delay, poll should still not have run
    assert svc.poll_count == 0


def test_exception_in_poll_does_not_kill_loop():
    svc = _FailingService()
    svc.start_polling(interval=0)
    svc.wait_for_poll()
    svc.wait_for_poll()
    assert svc.poll_count >= 2
    svc.stop_polling()


def test_stop_event_interrupts_sleep():
    svc = _CountingService()
    svc.start_polling(interval=9999)
    svc.wait_for_poll()
    start = time.monotonic()
    svc.stop_polling()
    elapsed = time.monotonic() - start
    # stop_polling should return quickly, not wait 9999 seconds
    assert elapsed < 2.0
