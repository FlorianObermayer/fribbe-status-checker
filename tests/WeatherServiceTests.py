import threading
import time
from datetime import datetime, timedelta

import pytest

import app.env as env
from app.services.WeatherService import (
    Temperature,
    Weather,
    WeatherService,
    WeatherState,
    _weather_from_owm,  # pyright: ignore[reportPrivateUsage]
)


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
):
    weather = _weather_from_owm(weather_id, temp)
    assert weather.state == expected_state
    assert weather.temperature == expected_temp


def test_get_condition_uses_positive_cache(monkeypatch: pytest.MonkeyPatch):
    service = WeatherService()
    expected = Weather(temperature=Temperature.MILD, state=WeatherState.CLOUDY)
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


def test_get_condition_negative_cache_prevents_api_hammering(monkeypatch: pytest.MonkeyPatch):
    service = WeatherService()
    monkeypatch.setattr(env, "WEATHER_CACHE_TTL_SECONDS", 300)
    calls = 0

    def fake_fetch() -> None:
        nonlocal calls
        calls += 1
        return None

    monkeypatch.setattr(service, "_fetch", fake_fetch)

    first = service.get_condition()
    second = service.get_condition()

    assert first is None
    assert second is None
    assert calls == 1


def test_get_condition_refetches_after_ttl_expired(monkeypatch: pytest.MonkeyPatch):
    service = WeatherService()
    monkeypatch.setattr(env, "WEATHER_CACHE_TTL_SECONDS", 30)

    first_weather = Weather(temperature=Temperature.COLD, state=WeatherState.CLEAR)
    second_weather = Weather(temperature=Temperature.HOT, state=WeatherState.THUNDERSTORM)
    responses = [first_weather, second_weather]
    calls = 0

    def fake_fetch() -> Weather:
        nonlocal calls
        calls += 1
        return responses.pop(0)

    monkeypatch.setattr(service, "_fetch", fake_fetch)

    first = service.get_condition()
    service._cache_timestamp = datetime.now() - timedelta(seconds=31)  # pyright: ignore[reportPrivateUsage]
    second = service.get_condition()

    assert first == first_weather
    assert second == second_weather
    assert calls == 2


def test_invalidate_cache_forces_refetch(monkeypatch: pytest.MonkeyPatch):
    service = WeatherService()
    calls = 0

    def fake_fetch() -> Weather:
        nonlocal calls
        calls += 1
        return Weather(temperature=Temperature.WARM, state=WeatherState.CLEAR)

    monkeypatch.setattr(service, "_fetch", fake_fetch)

    service.get_condition()
    service.invalidate_cache()
    service.get_condition()

    assert calls == 2


def test_get_condition_deduplicates_concurrent_refresh(monkeypatch: pytest.MonkeyPatch):
    service = WeatherService()
    monkeypatch.setattr(env, "WEATHER_CACHE_TTL_SECONDS", 300)

    expected = Weather(temperature=Temperature.WARM, state=WeatherState.CLEAR)
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


def test_fetch_returns_none_on_http_error(monkeypatch: pytest.MonkeyPatch):
    service = WeatherService()
    monkeypatch.setattr(env, "OPENWEATHERMAP_API_KEY", "key")
    monkeypatch.setattr(env, "WEATHER_LAT", 10.0)
    monkeypatch.setattr(env, "WEATHER_LON", 20.0)

    import urllib.error
    import urllib.request

    def fake_urlopen(*_args, **_kwargs):  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]
        raise urllib.error.HTTPError("https://example.com", 500, "boom", hdrs=None, fp=None)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)  # pyright: ignore[reportUnknownArgumentType]

    assert service._fetch() is None  # pyright: ignore[reportPrivateUsage]


def test_fetch_returns_none_on_generic_error(monkeypatch: pytest.MonkeyPatch):
    service = WeatherService()
    monkeypatch.setattr(env, "OPENWEATHERMAP_API_KEY", "key")
    monkeypatch.setattr(env, "WEATHER_LAT", 10.0)
    monkeypatch.setattr(env, "WEATHER_LON", 20.0)

    import urllib.request

    def fake_urlopen(*_args, **_kwargs):  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]
        raise TimeoutError("network timeout")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)  # pyright: ignore[reportUnknownArgumentType]

    assert service._fetch() is None  # pyright: ignore[reportPrivateUsage]
