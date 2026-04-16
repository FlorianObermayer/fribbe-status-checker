import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta, timezone
from typing import Never

import pytest

from app.config import cfg
from app.services.weather_service import (
    Temperature,
    Weather,
    WeatherService,
    WeatherState,
    _parse_owm_response,  # pyright: ignore[reportPrivateUsage]
    _weather_from_owm,  # pyright: ignore[reportPrivateUsage]
)


def test_parse_owm_response_extracts_fields() -> None:
    data: dict[str, object] = {
        "weather": [{"id": 800}],
        "main": {"temp": 22.5},
        "dt": 1776010220,
        "timezone": 7200,
    }
    weather = _parse_owm_response(data)
    assert weather.state == WeatherState.CLEAR
    assert weather.temperature == Temperature.WARM
    expected_at_time = datetime.fromtimestamp(1776010220, tz=timezone(timedelta(seconds=7200)))
    assert weather.at_time == expected_at_time


@pytest.mark.parametrize(
    ("weather_id", "temp", "expected_state", "expected_temp"),
    [
        (200, 28.0, WeatherState.THUNDERSTORM, Temperature.HOT),
        (300, 22.0, WeatherState.MILD_RAIN, Temperature.WARM),
        (500, 21.9, WeatherState.MILD_RAIN, Temperature.MILD),
        (501, 11.0, WeatherState.MILD_RAIN, Temperature.MILD),
        (502, 10.9, WeatherState.HEAVY_RAIN, Temperature.COLD),
        (511, 27.9, WeatherState.HEAVY_RAIN, Temperature.WARM),
        (600, -2.0, WeatherState.SNOW, Temperature.COLD),
        (800, 35.0, WeatherState.CLEAR, Temperature.HOT),
        (741, 15.0, WeatherState.CLOUDY, Temperature.MILD),
        (804, 23.5, WeatherState.CLOUDY, Temperature.WARM),
    ],
)
def test_weather_from_owm_mappings(
    weather_id: int,
    temp: float,
    expected_state: WeatherState,
    expected_temp: Temperature,
) -> None:
    weather = _weather_from_owm(weather_id, temp, datetime(2026, 1, 1, tzinfo=UTC))
    assert weather.state == expected_state
    assert weather.temperature == expected_temp


def test_get_condition_uses_positive_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    service = WeatherService("OPENWEATHERMAP_API_KEY", 10.0, 20.0)
    expected = Weather(
        temperature=Temperature.MILD,
        state=WeatherState.CLOUDY,
        at_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    calls = 0

    def fake_fetch() -> Weather:
        nonlocal calls
        calls += 1
        return expected

    monkeypatch.setattr(service, "_fetch", fake_fetch)

    first = service.get_condition()
    second = service.get_condition()

    assert first == expected
    assert second == expected
    assert calls == 1


def test_get_condition_negative_cache_prevents_api_hammering(monkeypatch: pytest.MonkeyPatch) -> None:
    service = WeatherService("OPENWEATHERMAP_API_KEY", 10.0, 20.0)
    monkeypatch.setattr(cfg, "WEATHER_CACHE_TTL_SECONDS", 300)
    calls = 0

    def fake_fetch() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(service, "_fetch", fake_fetch)

    first = service.get_condition()
    second = service.get_condition()

    assert first is None
    assert second is None
    assert calls == 1


def test_get_condition_refetches_after_ttl_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    service = WeatherService("OPENWEATHERMAP_API_KEY", 10.0, 20.0)
    monkeypatch.setattr(cfg, "WEATHER_CACHE_TTL_SECONDS", 30)

    first_weather = Weather(
        temperature=Temperature.COLD,
        state=WeatherState.CLEAR,
        at_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    second_weather = Weather(
        temperature=Temperature.HOT,
        state=WeatherState.THUNDERSTORM,
        at_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    responses = [first_weather, second_weather]
    calls = 0

    def fake_fetch() -> Weather:
        nonlocal calls
        calls += 1
        return responses.pop(0)

    monkeypatch.setattr(service, "_fetch", fake_fetch)

    first = service.get_condition()
    service._cache_timestamp = datetime.now(UTC) - timedelta(seconds=31)
    second = service.get_condition()

    assert first == first_weather
    assert second == second_weather
    assert calls == 2


def test_invalidate_cache_forces_refetch(monkeypatch: pytest.MonkeyPatch) -> None:
    service = WeatherService("OPENWEATHERMAP_API_KEY", 10.0, 20.0)
    calls = 0

    def fake_fetch() -> Weather:
        nonlocal calls
        calls += 1
        return Weather(temperature=Temperature.WARM, state=WeatherState.CLEAR, at_time=datetime(2026, 1, 1, tzinfo=UTC))

    monkeypatch.setattr(service, "_fetch", fake_fetch)

    service.get_condition()
    service.invalidate_cache()
    service.get_condition()

    assert calls == 2


def test_get_condition_deduplicates_concurrent_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    service = WeatherService("OPENWEATHERMAP_API_KEY", 10.0, 20.0)
    monkeypatch.setattr(cfg, "WEATHER_CACHE_TTL_SECONDS", 300)

    expected = Weather(temperature=Temperature.WARM, state=WeatherState.CLEAR, at_time=datetime(2026, 1, 1, tzinfo=UTC))
    calls = 0
    call_lock = threading.Lock()

    def fake_fetch() -> Weather:
        nonlocal calls
        with call_lock:
            calls += 1
        # Keep the fetch in flight long enough for other threads to queue.
        time.sleep(0.05)
        return expected

    monkeypatch.setattr(service, "_fetch", fake_fetch)

    start_barrier = threading.Barrier(5)
    results: list[Weather | None] = [None, None, None, None, None]

    def worker(index: int) -> None:
        start_barrier.wait()
        results[index] = service.get_condition()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls == 1
    assert results == [expected, expected, expected, expected, expected]


def test_fetch_returns_none_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    service = WeatherService("OPENWEATHERMAP_API_KEY", 10.0, 20.0)

    def fake_urlopen(*_args, **_kwargs) -> Never:  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]  # noqa: ANN002, ANN003
        msg = "https://example.com"
        raise urllib.error.HTTPError(msg, 500, "boom", hdrs=None, fp=None)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)  # pyright: ignore[reportUnknownArgumentType]

    assert service._fetch() is None  # pyright: ignore[reportPrivateUsage]


def test_fetch_returns_none_on_generic_error(monkeypatch: pytest.MonkeyPatch) -> None:
    service = WeatherService("OPENWEATHERMAP_API_KEY", 10.0, 20.0)

    def fake_urlopen(*_args, **_kwargs) -> Never:  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]  # noqa: ANN002, ANN003
        msg = "network timeout"
        raise TimeoutError(msg)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)  # pyright: ignore[reportUnknownArgumentType]

    assert service._fetch() is None
