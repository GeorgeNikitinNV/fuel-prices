from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .provider import Station


SCHEMA = """
CREATE TABLE IF NOT EXISTS stations (
    provider_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    brand TEXT NOT NULL,
    address TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    last_seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_observations (
    id INTEGER PRIMARY KEY,
    provider_id TEXT NOT NULL REFERENCES stations(provider_id),
    fuel_type TEXT NOT NULL,
    price_cents_per_litre REAL,
    fetched_at TEXT NOT NULL,
    provider_updated_at TEXT,
    UNIQUE(provider_id, fuel_type, fetched_at)
);
CREATE INDEX IF NOT EXISTS price_observations_lookup
    ON price_observations(provider_id, fuel_type, fetched_at);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path

    def save(self, stations: list[Station], fetched_at: datetime) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = fetched_at.isoformat()
        with sqlite3.connect(self.path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(SCHEMA)
            for station in stations:
                connection.execute(
                    """
                    INSERT INTO stations (
                        provider_id, name, brand, address, latitude, longitude, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(provider_id) DO UPDATE SET
                        name=excluded.name,
                        brand=excluded.brand,
                        address=excluded.address,
                        latitude=excluded.latitude,
                        longitude=excluded.longitude,
                        last_seen_at=excluded.last_seen_at
                    """,
                    (
                        station.provider_id,
                        station.name,
                        station.brand,
                        station.address,
                        station.latitude,
                        station.longitude,
                        timestamp,
                    ),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO price_observations (
                        provider_id, fuel_type, price_cents_per_litre,
                        fetched_at, provider_updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        station.provider_id,
                        station.fuel_type,
                        station.price_cents,
                        timestamp,
                        station.provider_updated_at,
                    ),
                )
