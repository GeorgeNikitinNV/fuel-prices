from __future__ import annotations

import csv
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import typer

from .config import Settings
from .mqtt import publish_snapshot
from .provider import Station, fetched_at, fetch_stations
from .storage import Database

app = typer.Typer(help="Collect fuel prices and publish them to Home Assistant.")


def _settings(ctx: typer.Context) -> Settings:
    return ctx.obj


def _station_rows(stations: list[Station]) -> list[dict[str, object]]:
    return [
        {
            "id": station.provider_id,
            "name": station.name,
            "brand": station.brand,
            "fuel_type": station.fuel_type,
            "price_nzd_per_l": (
                None if station.price_cents is None else round(station.price_cents / 100, 3)
            ),
            "distance_km": round(station.distance_km, 1),
            "latitude": station.latitude,
            "longitude": station.longitude,
            "address": station.address,
            "provider_updated_at": station.provider_updated_at,
        }
        for station in stations
    ]


def _print_stations(stations: list[Station], output_format: str) -> None:
    rows = _station_rows(stations)
    if output_format == "json":
        typer.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if output_format in {"csv", "tsv"}:
        fields = [
            "id", "name", "brand", "fuel_type", "price_nzd_per_l",
            "distance_km", "latitude", "longitude", "address", "provider_updated_at",
        ]
        writer = csv.DictWriter(
            sys.stdout,
            fieldnames=fields,
            delimiter="," if output_format == "csv" else "\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
        return
    if not rows:
        return

    columns = ["id", "name", "brand", "fuel_type", "price_nzd_per_l", "distance_km", "address"]
    values = [[str(row[column] if row[column] is not None else "") for column in columns] for row in rows]
    headers = ["ID", "NAME", "BRAND", "FUEL", "PRICE NZD/L", "KM", "ADDRESS"]
    widths = [
        max(len(header), *(len(row[index]) for row in values))
        for index, header in enumerate(headers)
    ]
    typer.echo("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    typer.echo("  ".join("-" * width for width in widths))
    for row in values:
        typer.echo("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def _fetch_once(settings: Settings) -> list[Station]:
    timestamp = fetched_at()
    stations = fetch_stations(settings)
    Database(settings.db_path).save(stations, timestamp)
    publish_snapshot(settings, stations, timestamp)
    return stations


@app.callback()
def main(
    ctx: typer.Context,
    env_file: Path = typer.Option(Path(".env"), "--env-file", help="Environment file to load."),
    lat: Optional[float] = typer.Option(None, "--lat", help="Home latitude."),
    lon: Optional[float] = typer.Option(None, "--lon", help="Home longitude."),
    radius_km: Optional[float] = typer.Option(None, "--radius-km", help="Search radius, up to 30 km."),
    fuel_type: Optional[str] = typer.Option(None, "--fuel-type", help="Fuel code, default PULP95."),
    interval_minutes: Optional[int] = typer.Option(None, "--interval-minutes", help="Run interval."),
    db_path: Optional[Path] = typer.Option(None, "--db", help="SQLite database path."),
    api_url: Optional[str] = typer.Option(None, "--api-url", help="Provider API URL."),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="Optional provider API key."),
    timeout_seconds: Optional[int] = typer.Option(None, "--timeout-seconds", help="HTTP timeout."),
    station: list[str] = typer.Option([], "--station", help="Station/name filter; repeatable."),
    mqtt_host: Optional[str] = typer.Option(None, "--mqtt-host", help="MQTT broker host."),
    mqtt_port: Optional[int] = typer.Option(None, "--mqtt-port", help="MQTT broker port."),
    mqtt_username: Optional[str] = typer.Option(None, "--mqtt-username", help="MQTT username."),
    mqtt_password: Optional[str] = typer.Option(None, "--mqtt-password", help="MQTT password."),
    mqtt_tls: Optional[bool] = typer.Option(None, "--mqtt-tls/--no-mqtt-tls", help="Use MQTT TLS."),
    mqtt_discovery_prefix: Optional[str] = typer.Option(None, "--mqtt-discovery-prefix"),
    mqtt_topic_prefix: Optional[str] = typer.Option(None, "--mqtt-topic-prefix"),
    log_level: Optional[str] = typer.Option(None, "--log-level"),
    output_format: Optional[str] = typer.Option(
        None, "--format", help="Output format: table, csv, tsv, or json."
    ),
    sort_by: Optional[str] = typer.Option(
        None, "--sort", help="Sort by price or distance."
    ),
) -> None:
    try:
        settings = Settings.from_sources(
            env_file=env_file,
            home_lat=lat,
            home_lon=lon,
            radius_km=radius_km,
            fuel_type=fuel_type,
            interval_minutes=interval_minutes,
            db_path=db_path,
            api_url=api_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            station_filters=station,
            mqtt_host=mqtt_host,
            mqtt_port=mqtt_port,
            mqtt_username=mqtt_username,
            mqtt_password=mqtt_password,
            mqtt_tls=mqtt_tls,
            mqtt_discovery_prefix=mqtt_discovery_prefix,
            mqtt_topic_prefix=mqtt_topic_prefix,
            log_level=log_level,
            output_format=output_format,
            sort_by=sort_by,
        )
        settings.validate()
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error

    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(levelname)s %(message)s",
    )
    ctx.obj = settings


@app.command()
def fetch(ctx: typer.Context) -> None:
    """Fetch, store, and publish one snapshot."""
    settings = _settings(ctx)
    _print_stations(_fetch_once(settings), settings.output_format)


@app.command()
def run(ctx: typer.Context) -> None:
    """Fetch immediately, then repeat at the configured interval."""
    settings = _settings(ctx)
    while True:
        try:
            stations = _fetch_once(settings)
            logging.info("stored and published %s stations", len(stations))
            _print_stations(stations, settings.output_format)
        except Exception:
            logging.exception("fetch failed; retrying on the next interval")
        logging.info("next update in %s minutes; press Ctrl+C to stop", settings.interval_minutes)
        try:
            time.sleep(settings.interval_minutes * 60)
        except KeyboardInterrupt:
            typer.echo("stopped")
            return


@app.command()
def stations(ctx: typer.Context) -> None:
    """List matching stations without writing to SQLite or MQTT."""
    settings = _settings(ctx)
    _print_stations(fetch_stations(settings), settings.output_format)


if __name__ == "__main__":
    app()
