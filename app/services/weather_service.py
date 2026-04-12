"""Fetches current weather from the OpenWeatherMap current-weather API.

Usage:
    service = WeatherService()
    weather = service.get_condition()   # Weather | None

Results are cached for env.WEATHER_CACHE_TTL_SECONDS to avoid hammering the API.
Returns None when no API key / coordinates are configured or the request fails.
"""

import json
import logging
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum

from app import env

logger = logging.getLogger("uvicorn.error")

CURRENT_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


class Temperature(Enum):
    """Temperature category, derived from Celsius values."""

    HOT = "hot"  # >= 28 °C
    WARM = "warm"  # 22-27 °C
    MILD = "mild"  # 11-21 °C
    COLD = "cold"  # < 11 °C


class WeatherState(Enum):
    """Weather state, derived from OWM."""

    CLEAR = "clear"
    CLOUDY = "cloudy"
    MILD_RAIN = "mild_rain"  # drizzle, light rain
    HEAVY_RAIN = "heavy_rain"
    THUNDERSTORM = "thunderstorm"
    SNOW = "snow"


@dataclass
class Weather:
    """Represents the current weather condition."""

    temperature: Temperature
    state: WeatherState
    at_time: datetime


# OWM weather ID group (hundreds digit) → WeatherState.
_OWM_GROUP_STATE: dict[int, WeatherState] = {
    2: WeatherState.THUNDERSTORM,  # 2xx thunderstorm
    3: WeatherState.MILD_RAIN,  # 3xx drizzle
    6: WeatherState.SNOW,  # 6xx snow
    7: WeatherState.CLOUDY,  # 7xx atmosphere (fog/mist/haze/…)
}

# Temperature thresholds: (min_celsius, Temperature) — checked highest-first.
_TEMP_THRESHOLDS: list[tuple[float, Temperature]] = [
    (28.0, Temperature.HOT),
    (22.0, Temperature.WARM),
    (11.0, Temperature.MILD),
]

_OWM_GROUP_RAIN = 5  # 5xx rain
_OWM_ID_CLEAR = 800  # clear sky
_OWM_ID_HEAVY_RAIN_MIN = 502  # 502+ are heavy/extreme rain
_OWM_ID_FREEZING_RAIN = 511  # freezing rain → treated as heavy


def _weather_from_owm(weather_id: int, temp_celsius: float, at_time: datetime) -> Weather:
    """Map an OWM weather ID + temperature to a Weather."""
    group = weather_id // 100

    if group == _OWM_GROUP_RAIN:
        # 500 light rain, 501 moderate, 502+ heavy/extreme; 511 freezing rain → heavy
        state = (
            WeatherState.HEAVY_RAIN
            if (weather_id >= _OWM_ID_HEAVY_RAIN_MIN or weather_id == _OWM_ID_FREEZING_RAIN)
            else WeatherState.MILD_RAIN
        )
    elif weather_id == _OWM_ID_CLEAR:
        state = WeatherState.CLEAR
    else:
        # 8xx clouds (801-804) fall back to CLOUDY via the default
        state = _OWM_GROUP_STATE.get(group, WeatherState.CLOUDY)

    temperature = next(
        (t for threshold, t in _TEMP_THRESHOLDS if temp_celsius >= threshold),
        Temperature.COLD,
    )

    return Weather(temperature=temperature, state=state, at_time=at_time)


def _parse_owm_response(data: dict[str, object]) -> Weather:
    """Extract weather fields from a parsed OWM current-weather JSON response."""
    weather_id = int(data["weather"][0]["id"])  # type: ignore[index]
    temp = float(data["main"]["temp"])  # type: ignore[index]
    dt = int(data["dt"])  # type: ignore[index]
    tz_offset = int(data["timezone"])  # type: ignore[index]
    at_time = datetime.fromtimestamp(dt, tz=timezone(timedelta(seconds=tz_offset)))
    return _weather_from_owm(weather_id, temp, at_time)


class WeatherService:
    """Fetches current weather from OWM, with caching and in-flight request coalescing."""

    def __init__(self, api_key: str, lat: float, lon: float) -> None:
        self._api_key = api_key
        self._lat = lat
        self._lon = lon
        self._fetch_condition = threading.Condition()
        self._fetch_in_progress = False
        self._cached_weather: Weather | None = None
        self._cache_timestamp: datetime | None = None

    def _is_cache_valid(self) -> bool:
        if self._cache_timestamp is None:
            return False
        age = (datetime.now(UTC) - self._cache_timestamp).total_seconds()
        return age < env.WEATHER_CACHE_TTL_SECONDS

    def _fetch(self) -> Weather | None:
        url = f"{CURRENT_WEATHER_URL}?lat={self._lat}&lon={self._lon}&appid={self._api_key}&units=metric"
        try:
            with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310
                data: dict[str, object] = json.loads(response.read().decode())
            weather = _parse_owm_response(data)
            logger.info("WeatherService: fetched via OWM current-weather: %s", weather)
            return weather
        except urllib.error.HTTPError as e:
            logger.warning("WeatherService: OWM HTTP error %d: %s", e.code, e.reason)
        except Exception as e:  # noqa: BLE001
            logger.warning("WeatherService: fetch failed: %s", e)
        return None

    def get_condition(self) -> Weather | None:
        """Return the current weather, using the cache when fresh."""
        with self._fetch_condition:
            if self._is_cache_valid():
                return self._cached_weather

            while self._fetch_in_progress:
                self._fetch_condition.wait()
                if self._is_cache_valid():
                    return self._cached_weather

            self._fetch_in_progress = True

        try:
            weather = self._fetch()
        except Exception:
            with self._fetch_condition:
                self._fetch_in_progress = False
                self._fetch_condition.notify_all()
            raise

        with self._fetch_condition:
            self._cached_weather = weather
            self._cache_timestamp = datetime.now(UTC)
            self._fetch_in_progress = False
            self._fetch_condition.notify_all()
            return weather

    def invalidate_cache(self) -> None:
        """Clear cached weather state without cancelling an in-flight fetch."""
        with self._fetch_condition:
            self._cache_timestamp = None
            self._cached_weather = None
            self._fetch_condition.notify_all()
