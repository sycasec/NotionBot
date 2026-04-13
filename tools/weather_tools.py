import logging

import requests
from langchain_core.tools import tool

log = logging.getLogger(__name__)

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


@tool
def get_weather(city: str) -> str:
    """Get current weather conditions for a city.
    city: city name, e.g. 'Manila', 'Tokyo', 'New York'
    Returns temperature, humidity, wind speed, and conditions.
    """
    try:
        geo = requests.get(
            _GEOCODE_URL,
            params={"name": city, "count": 1, "language": "en"},
            timeout=10,
        )
        geo.raise_for_status()
        results = geo.json().get("results")
        if not results:
            return f"Could not find a location named '{city}'."

        loc = results[0]
        lat, lon = loc["latitude"], loc["longitude"]
        name = loc.get("name", city)
        country = loc.get("country", "")

        weather = requests.get(
            _WEATHER_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
            },
            timeout=10,
        )
        weather.raise_for_status()
        current = weather.json().get("current", {})

        temp = current.get("temperature_2m", "?")
        humidity = current.get("relative_humidity_2m", "?")
        wind = current.get("wind_speed_10m", "?")
        code = current.get("weather_code", -1)
        condition = _weather_code_to_text(code)

        return (
            f"Weather in {name}, {country}:\n"
            f"Condition: {condition}\n"
            f"Temperature: {temp}°C\n"
            f"Humidity: {humidity}%\n"
            f"Wind: {wind} km/h"
        )
    except requests.exceptions.RequestException as e:
        log.warning("Weather API error for %s: %s", city, e)
        return f"Error fetching weather for '{city}': {e}"


def _weather_code_to_text(code: int) -> str:
    """Convert WMO weather code to human-readable text."""
    codes = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snowfall",
        73: "Moderate snowfall",
        75: "Heavy snowfall",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }
    return codes.get(code, f"Unknown (code {code})")
