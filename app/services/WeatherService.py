"""Fetches current weather from the OpenWeatherMap current-weather API.

Usage:
    service = WeatherService()
    weather = service.get_condition()   # Weather | None

Results are cached for CACHE_TTL_SECONDS to avoid hammering the API.
Returns None when no API key / coordinates are configured or the request fails.
"""

import json
import logging
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import app.env as env

logger = logging.getLogger("uvicorn.error")

CURRENT_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


class Temperature(Enum):
    HOT = "hot"  # >= 28 °C
    WARM = "warm"  # 22-27 °C
    MILD = "mild"  # 11-21 °C
    COLD = "cold"  # < 11 °C


class WeatherState(Enum):
    CLEAR = "clear"
    CLOUDY = "cloudy"
    MILD_RAIN = "mild_rain"  # drizzle, light rain
    HEAVY_RAIN = "heavy_rain"
    THUNDERSTORM = "thunderstorm"
    SNOW = "snow"


@dataclass
class Weather:
    temperature: Temperature
    state: WeatherState


def _weather_from_owm(weather_id: int, temp_celsius: float) -> Weather:
    """Map an OWM weather ID + temperature to a Weather."""
    group = weather_id // 100

    if group == 2:
        state = WeatherState.THUNDERSTORM
    elif group == 3:
        state = WeatherState.MILD_RAIN
    elif group == 5:
        # 500 light rain, 501 moderate, 502+ heavy/extreme
        state = WeatherState.HEAVY_RAIN if (weather_id >= 502 or weather_id == 511) else WeatherState.MILD_RAIN
    elif group == 6:
        state = WeatherState.SNOW
    elif weather_id == 800:
        state = WeatherState.CLEAR
    else:
        # 7xx atmosphere (fog/mist/haze), 801-804 clouds
        state = WeatherState.CLOUDY

    if temp_celsius >= 28:
        temperature = Temperature.HOT
    elif temp_celsius >= 22:
        temperature = Temperature.WARM
    elif temp_celsius >= 11:
        temperature = Temperature.MILD
    else:
        temperature = Temperature.COLD

    return Weather(temperature=temperature, state=state)


class WeatherService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cached_weather: Weather | None = None
        self._cache_timestamp: datetime | None = None
        self._cache_populated = False

    def _is_cache_valid(self) -> bool:
        if self._cache_timestamp is None or not self._cache_populated:
            return False
        age = (datetime.now() - self._cache_timestamp).total_seconds()
        return age < env.WEATHER_CACHE_TTL_SECONDS

    def _fetch(self) -> Weather | None:
        api_key = env.OPENWEATHERMAP_API_KEY
        lat = env.WEATHER_LAT
        lon = env.WEATHER_LON

        if not api_key or lat is None or lon is None:
            return None

        current_weather_url = f"{CURRENT_WEATHER_URL}?lat={lat}&lon={lon}&appid={api_key}&units=metric"
        try:
            with urllib.request.urlopen(current_weather_url, timeout=10) as response:  # noqa: S310
                data: dict[str, object] = json.loads(response.read().decode())
            weather_id = int(data["weather"][0]["id"])  # type: ignore[index]
            temp = float(data["main"]["temp"])  # type: ignore[index]
            weather = _weather_from_owm(weather_id, temp)
            logger.info(
                f"WeatherService: fetched via OWM current-weather temp={weather.temperature.value}, "
                f"state={weather.state.value} (id={weather_id}, temp={temp:.1f}°C)"
            )
            return weather
        except urllib.error.HTTPError as e:
            logger.warning(f"WeatherService: OWM HTTP {e.code}: {e.reason}")
        except Exception as e:
            logger.warning(f"WeatherService: fetch failed: {e}")
        return None

    def get_condition(self) -> Weather | None:
        """Return the current weather, using the cache when fresh."""
        with self._lock:
            if self._is_cache_valid():
                return self._cached_weather
            weather = self._fetch()
            self._cached_weather = weather
            self._cache_timestamp = datetime.now()
            self._cache_populated = True
            return weather

    def invalidate_cache(self) -> None:
        with self._lock:
            self._cache_timestamp = None
            self._cached_weather = None
            self._cache_populated = False
