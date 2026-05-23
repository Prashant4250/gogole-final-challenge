from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import httpx

from app.models import StadiumWeatherResponse
from app.services.state_store import StateStore

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 1.8

# Known demo/local stadium IDs with stable coordinates and city labels.
STADIUM_LOCATIONS: dict[str, tuple[float, float, str]] = {
    "stadium-1": (40.8296, -73.9262, "Bronx, New York"),
    "wembley": (51.5560, -0.2796, "London"),
    "camp-nou": (41.3809, 2.1228, "Barcelona"),
    "old-trafford": (53.4631, -2.2913, "Manchester"),
}

WEATHER_CODE_LABELS = {
    0: "Clear sky",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Dense drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Rain showers",
    82: "Heavy showers",
    95: "Thunderstorm",
    96: "Thunderstorm hail",
    99: "Severe thunderstorm",
}


class WeatherService:
    def __init__(self, store: StateStore) -> None:
        self._store = store

    def current_weather(
        self,
        tenant_id: str,
        stadium_id: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> StadiumWeatherResponse:
        city_name = None
        if latitude is not None and longitude is not None:
            selected_latitude = float(latitude)
            selected_longitude = float(longitude)
            city_name = self._reverse_geocode_city(selected_latitude, selected_longitude) or "Your location"
        else:
            location = self._resolve_location(stadium_id)
            if not location:
                return self._fallback_snapshot(tenant_id, stadium_id)
            selected_latitude, selected_longitude, city_name = location

        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = client.get(
                    FORECAST_URL,
                    params={
                        "latitude": selected_latitude,
                        "longitude": selected_longitude,
                        "current": "temperature_2m,weather_code,wind_speed_10m",
                        "hourly": "precipitation_probability",
                        "forecast_days": 1,
                        "timezone": "auto",
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return self._fallback_snapshot(tenant_id, stadium_id)

        current = payload.get("current") or {}
        hourly = payload.get("hourly") or {}

        temperature = float(current.get("temperature_2m", 0.0))
        wind_kph = float(current.get("wind_speed_10m", 0.0))
        weather_code = int(current.get("weather_code", 0))
        current_time = str(current.get("time", ""))

        precip_probability = 0
        hourly_times = hourly.get("time") or []
        hourly_precip = hourly.get("precipitation_probability") or []
        if current_time in hourly_times:
            index = hourly_times.index(current_time)
            if index < len(hourly_precip):
                precip_probability = int(hourly_precip[index])
        elif hourly_precip:
            precip_probability = int(hourly_precip[0])

        return StadiumWeatherResponse(
            tenant_id=tenant_id,
            stadium_id=stadium_id,
            city_name=city_name,
            source="open-meteo",
            condition=WEATHER_CODE_LABELS.get(weather_code, "Live weather"),
            temperature_c=round(temperature, 1),
            precipitation_probability=max(0, min(100, precip_probability)),
            wind_kph=round(wind_kph, 1),
            updated_at=datetime.now(timezone.utc),
        )

    def _reverse_geocode_city(self, latitude: float, longitude: float) -> Optional[str]:
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = client.get(
                    "https://geocoding-api.open-meteo.com/v1/reverse",
                    params={
                        "latitude": latitude,
                        "longitude": longitude,
                        "count": 1,
                        "language": "en",
                        "format": "json",
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return None

        results = payload.get("results") or []
        if not results:
            return None

        top = results[0]
        city_parts = [
            str(top.get("name", "")).strip(),
            str(top.get("admin1", "")).strip(),
            str(top.get("country", "")).strip(),
        ]
        city_name = ", ".join(part for part in city_parts if part)
        return city_name or None

    def _resolve_location(self, stadium_id: str) -> Optional[tuple[float, float, str]]:
        normalized = stadium_id.strip().lower()
        if normalized in STADIUM_LOCATIONS:
            latitude, longitude, city_name = STADIUM_LOCATIONS[normalized]
            return latitude, longitude, city_name

        search_name = normalized.replace("-", " ")
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = client.get(
                    GEOCODE_URL,
                    params={
                        "name": f"{search_name} stadium",
                        "count": 1,
                        "language": "en",
                        "format": "json",
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return None

        results = payload.get("results") or []
        if not results:
            return None

        top = results[0]
        latitude = float(top.get("latitude", 0.0))
        longitude = float(top.get("longitude", 0.0))
        city_parts = [
            str(top.get("name", "")).strip(),
            str(top.get("admin1", "")).strip(),
            str(top.get("country", "")).strip(),
        ]
        city_name = ", ".join(part for part in city_parts if part)
        if not city_name:
            city_name = stadium_id.replace("-", " ").title()
        return latitude, longitude, city_name

    def _fallback_snapshot(self, tenant_id: str, stadium_id: str) -> StadiumWeatherResponse:
        status = self._store.get_stadium_status(tenant_id=tenant_id, stadium_id=stadium_id)
        zones = status.zones
        normalized = stadium_id.strip().lower()
        city_name = None
        if normalized in STADIUM_LOCATIONS:
            city_name = STADIUM_LOCATIONS[normalized][2]
        elif stadium_id:
            city_name = stadium_id.replace("-", " ").title()

        if zones:
            avg_weather_risk = sum(zone.weather_risk for zone in zones) / len(zones)
            avg_utilization = sum(zone.occupancy_ratio for zone in zones) / len(zones)
            temperature_c = 26.0 + (avg_utilization * 4.0) - (avg_weather_risk * 6.0)
            precip_probability = int(max(0, min(100, avg_weather_risk * 100)))
            wind_kph = round(9 + (avg_weather_risk * 16), 1)
            condition = "Estimated from live zone risk"
        else:
            temperature_c = 27.0
            precip_probability = 15
            wind_kph = 10.0
            condition = "Estimated baseline"

        return StadiumWeatherResponse(
            tenant_id=tenant_id,
            stadium_id=stadium_id,
            city_name=city_name,
            source="fallback",
            condition=condition,
            temperature_c=round(temperature_c, 1),
            precipitation_probability=precip_probability,
            wind_kph=wind_kph,
            updated_at=datetime.now(timezone.utc),
        )
