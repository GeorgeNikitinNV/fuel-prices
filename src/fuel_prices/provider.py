from __future__ import annotations

import json
import logging
import math
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

from .config import Settings

LOGGER = logging.getLogger(__name__)
API_MAX_RADIUS_KM = 25.0
API_MAX_STATIONS = 50
EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class Station:
    provider_id: str
    name: str
    brand: str
    address: str
    latitude: float
    longitude: float
    distance_km: float
    fuel_type: str
    price_cents: float | None
    provider_updated_at: str | None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _destination(lat: float, lon: float, distance_km: float, bearing_degrees: float) -> tuple[float, float]:
    angular_distance = distance_km / EARTH_RADIUS_KM
    bearing = math.radians(bearing_degrees)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), (math.degrees(lon2) + 540) % 360 - 180


def query_centers(settings: Settings) -> list[tuple[float, float, float]]:
    if settings.radius_km <= API_MAX_RADIUS_KM:
        return [(settings.home_lat, settings.home_lon, settings.radius_km)]

    offset_km = settings.radius_km - 20.0
    centers = [(settings.home_lat, settings.home_lon, API_MAX_RADIUS_KM)]
    centers.extend(
        (*_destination(settings.home_lat, settings.home_lon, offset_km, bearing), API_MAX_RADIUS_KM)
        for bearing in range(0, 360, 45)
    )
    return centers


def _float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _first(*values: object) -> object | None:
    return next((value for value in values if value not in (None, "")), None)


def _station_id(raw: dict[str, object], latitude: float, longitude: float) -> str:
    provider_id = _first(raw.get("id"), raw.get("station_id"))
    if provider_id is not None:
        return str(provider_id)
    return f"{raw.get('name', 'station')}:{latitude:.6f}:{longitude:.6f}"


def _selected_fuel(raw: dict[str, object], fuel_type: str) -> dict[str, object] | None:
    target = fuel_type.upper()
    fuels = raw.get("fuels")
    if isinstance(fuels, list):
        for fuel in fuels:
            if isinstance(fuel, dict) and str(fuel.get("type", "")).upper() == target:
                return fuel
    if str(raw.get("fuel_code", "")).upper() == target:
        return raw
    return None


def normalize_stations(payloads: list[dict[str, object]], settings: Settings) -> list[Station]:
    stations: dict[str, Station] = {}
    filters = tuple(item.casefold() for item in settings.station_filters)

    for payload in payloads:
        for raw in payload.get("stations", []):
            if not isinstance(raw, dict):
                continue
            latitude = _float(_first(raw.get("lat"), raw.get("latitude")))
            longitude = _float(_first(raw.get("lng"), raw.get("longitude")))
            if latitude is None or longitude is None:
                continue

            distance_km = haversine_km(settings.home_lat, settings.home_lon, latitude, longitude)
            if distance_km > settings.radius_km:
                continue

            name = str(raw.get("name") or "Unknown station")
            brand = str(raw.get("brand") or "")
            address = str(raw.get("address") or "")
            searchable = f"{name} {brand} {address}".casefold()
            if filters and not any(item in searchable for item in filters):
                continue

            fuel = _selected_fuel(raw, settings.fuel_type)
            if fuel is None:
                continue
            station = Station(
                provider_id=_station_id(raw, latitude, longitude),
                name=name,
                brand=brand,
                address=address,
                latitude=latitude,
                longitude=longitude,
                distance_km=distance_km,
                fuel_type=settings.fuel_type,
                price_cents=_float(fuel.get("price")),
                provider_updated_at=str(_first(fuel.get("updated"), raw.get("timestamp")) or "") or None,
            )
            existing = stations.get(station.provider_id)
            if existing is None or (existing.price_cents is None and station.price_cents is not None):
                stations[station.provider_id] = station

    if settings.sort_by == "distance":
        key = lambda station: (station.distance_km, station.name.casefold())
    else:
        key = lambda station: (
            station.price_cents is None,
            station.price_cents if station.price_cents is not None else float("inf"),
            station.distance_km,
            station.name.casefold(),
        )
    return sorted(stations.values(), key=key)


def _fetch(settings: Settings, latitude: float, longitude: float, radius_km: float) -> dict[str, object]:
    query = urllib.parse.urlencode(
        {"lat": latitude, "lng": longitude, "radius": round(radius_km * 1000), "limit": API_MAX_STATIONS}
    )
    request = urllib.request.Request(
        f"{settings.api_url}?{query}",
        headers={
            "Accept": "application/json",
            "User-Agent": "fuel-prices/0.2",
            **({"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=settings.timeout_seconds) as response:
        payload = json.load(response)
    if not payload.get("success", True):
        raise RuntimeError(payload)
    if int(payload.get("count", 0)) > API_MAX_STATIONS:
        LOGGER.warning("provider response is capped at %s stations", API_MAX_STATIONS)
    return payload


def fetch_stations(settings: Settings) -> list[Station]:
    centers = query_centers(settings)
    payloads = []
    for index, (latitude, longitude, radius_km) in enumerate(centers, 1):
        LOGGER.info("fetching area %s/%s (radius %.1f km)", index, len(centers), radius_km)
        payloads.append(_fetch(settings, latitude, longitude, radius_km))
    return normalize_stations(payloads, settings)


def fetched_at() -> datetime:
    return datetime.now(timezone.utc)
