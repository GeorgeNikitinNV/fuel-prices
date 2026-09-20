from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


def _value(value: object | None, name: str, default: object) -> object:
    return value if value is not None else os.getenv(name, default)


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _stations(value: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if value:
        return tuple(item.strip() for item in value if item.strip())
    return tuple(
        item.strip()
        for item in os.getenv("FUEL_PRICES_STATIONS", "").split(",")
        if item.strip()
    )


@dataclass(frozen=True)
class Settings:
    home_lat: float = -37.7870
    home_lon: float = 175.2793
    radius_km: float = 30.0
    fuel_type: str = "PULP95"
    interval_minutes: int = 60
    db_path: Path = Path("data/fuel-prices.db")
    api_url: str = "https://petrolmate.com.au/api/v1/stations/area"
    api_key: str | None = None
    timeout_seconds: int = 20
    station_filters: tuple[str, ...] = ()
    mqtt_host: str | None = None
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_tls: bool = False
    mqtt_discovery_prefix: str = "homeassistant"
    mqtt_topic_prefix: str = "fuel_prices"
    log_level: str = "INFO"
    output_format: str = "table"
    sort_by: str = "price"

    @classmethod
    def from_sources(
        cls,
        *,
        env_file: Path = Path(".env"),
        home_lat: float | None = None,
        home_lon: float | None = None,
        radius_km: float | None = None,
        fuel_type: str | None = None,
        interval_minutes: int | None = None,
        db_path: Path | None = None,
        api_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: int | None = None,
        station_filters: list[str] | tuple[str, ...] | None = None,
        mqtt_host: str | None = None,
        mqtt_port: int | None = None,
        mqtt_username: str | None = None,
        mqtt_password: str | None = None,
        mqtt_tls: bool | None = None,
        mqtt_discovery_prefix: str | None = None,
        mqtt_topic_prefix: str | None = None,
        log_level: str | None = None,
        output_format: str | None = None,
        sort_by: str | None = None,
    ) -> "Settings":
        load_dotenv(env_file, override=False)
        return cls(
            home_lat=float(_value(home_lat, "FUEL_PRICES_LAT", cls.home_lat)),
            home_lon=float(_value(home_lon, "FUEL_PRICES_LON", cls.home_lon)),
            radius_km=float(_value(radius_km, "FUEL_PRICES_RADIUS_KM", cls.radius_km)),
            fuel_type=str(_value(fuel_type, "FUEL_PRICES_FUEL_TYPE", cls.fuel_type)).upper(),
            interval_minutes=int(
                _value(interval_minutes, "FUEL_PRICES_INTERVAL_MINUTES", cls.interval_minutes)
            ),
            db_path=Path(_value(db_path, "FUEL_PRICES_DB", str(cls.db_path))),
            api_url=str(_value(api_url, "FUEL_PRICES_API_URL", cls.api_url)),
            api_key=_value(api_key, "FUEL_PRICES_API_KEY", None) or None,
            timeout_seconds=int(
                _value(timeout_seconds, "FUEL_PRICES_TIMEOUT_SECONDS", cls.timeout_seconds)
            ),
            station_filters=_stations(station_filters),
            mqtt_host=_value(mqtt_host, "MQTT_HOST", None) or None,
            mqtt_port=int(_value(mqtt_port, "MQTT_PORT", cls.mqtt_port)),
            mqtt_username=_value(mqtt_username, "MQTT_USERNAME", None) or None,
            mqtt_password=_value(mqtt_password, "MQTT_PASSWORD", None) or None,
            mqtt_tls=_bool(_value(mqtt_tls, "MQTT_TLS", cls.mqtt_tls)),
            mqtt_discovery_prefix=str(
                _value(mqtt_discovery_prefix, "MQTT_DISCOVERY_PREFIX", cls.mqtt_discovery_prefix)
            ),
            mqtt_topic_prefix=str(
                _value(mqtt_topic_prefix, "MQTT_TOPIC_PREFIX", cls.mqtt_topic_prefix)
            ),
            log_level=str(_value(log_level, "FUEL_PRICES_LOG_LEVEL", cls.log_level)).upper(),
            output_format=str(
                _value(output_format, "FUEL_PRICES_OUTPUT_FORMAT", cls.output_format)
            ).lower(),
            sort_by=str(_value(sort_by, "FUEL_PRICES_SORT_BY", cls.sort_by)).lower(),
        )

    def validate(self) -> None:
        if not -90 <= self.home_lat <= 90:
            raise ValueError("--lat must be between -90 and 90")
        if not -180 <= self.home_lon <= 180:
            raise ValueError("--lon must be between -180 and 180")
        if not 0 < self.radius_km <= 30:
            raise ValueError("--radius-km must be greater than 0 and no more than 30")
        if not self.fuel_type:
            raise ValueError("--fuel-type cannot be empty")
        if self.interval_minutes <= 0:
            raise ValueError("--interval-minutes must be greater than 0")
        if self.timeout_seconds <= 0:
            raise ValueError("--timeout-seconds must be greater than 0")
        api_url = urlparse(self.api_url)
        if api_url.scheme != "https" or api_url.hostname != "petrolmate.com.au":
            raise ValueError("--api-url must be an HTTPS URL on petrolmate.com.au")
        if not 1 <= self.mqtt_port <= 65535:
            raise ValueError("--mqtt-port must be between 1 and 65535")
        if self.output_format not in {"table", "csv", "tsv", "json"}:
            raise ValueError("--format must be table, csv, tsv, or json")
        if self.sort_by not in {"price", "distance"}:
            raise ValueError("--sort must be price or distance")
