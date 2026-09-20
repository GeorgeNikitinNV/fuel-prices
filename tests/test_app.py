import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fuel_prices.config import Settings
from fuel_prices.mqtt import publish_snapshot
from fuel_prices.provider import Station, normalize_stations, query_centers


class AppTests(unittest.TestCase):
    def test_cli_values_override_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("FUEL_PRICES_RADIUS_KM=12\nFUEL_PRICES_FUEL_TYPE=ULP\n")
            old_values = {
                name: os.environ.pop(name, None)
                for name in ("FUEL_PRICES_RADIUS_KM", "FUEL_PRICES_FUEL_TYPE")
            }
            try:
                settings = Settings.from_sources(
                    env_file=env_file,
                    radius_km=30,
                    fuel_type="PULP95",
                )
            finally:
                for name, value in old_values.items():
                    if value is not None:
                        os.environ[name] = value
                    else:
                        os.environ.pop(name, None)

        self.assertEqual(settings.radius_km, 30)
        self.assertEqual(settings.fuel_type, "PULP95")

    def test_sensitive_endpoints_require_tls_and_the_provider_host(self) -> None:
        with self.assertRaisesRegex(ValueError, "MQTT credentials"):
            Settings(mqtt_username="user").validate()
        with self.assertRaisesRegex(ValueError, "petrolmate.com.au"):
            Settings(api_url="http://example.com").validate()

    def test_thirty_km_search_uses_offset_queries(self) -> None:
        settings = Settings(radius_km=30)
        centers = query_centers(settings)
        self.assertEqual(len(centers), 9)
        self.assertTrue(all(radius <= 25 for _, _, radius in centers))

    def test_normalize_filters_fuel_and_deduplicates(self) -> None:
        settings = Settings(radius_km=30, fuel_type="PULP95", station_filters=("mill street",))
        payload = {
            "stations": [
                {
                    "id": 123,
                    "name": "Pak 'n Save Mill Street",
                    "brand": "Pak 'n Save",
                    "address": "17 Mill Street",
                    "lat": -37.77908611,
                    "lng": 175.27376706,
                    "fuels": [{"type": "PULP95", "price": 340.6}],
                },
                {
                    "id": 123,
                    "name": "Pak 'n Save Mill Street",
                    "brand": "Pak 'n Save",
                    "address": "17 Mill Street",
                    "lat": -37.77908611,
                    "lng": 175.27376706,
                    "fuels": [{"type": "PULP95", "price": 340.6}],
                },
            ]
        }

        stations = normalize_stations([payload], settings)

        self.assertEqual(len(stations), 1)
        self.assertEqual(stations[0].price_cents, 340.6)

    def test_normalize_can_sort_by_distance(self) -> None:
        settings = Settings(radius_km=30, fuel_type="PULP95", sort_by="distance")
        payload = {
            "stations": [
                {
                    "id": 1,
                    "name": "Far cheap",
                    "lat": -37.90,
                    "lng": 175.28,
                    "fuels": [{"type": "PULP95", "price": 300}],
                },
                {
                    "id": 2,
                    "name": "Near expensive",
                    "lat": -37.79,
                    "lng": 175.28,
                    "fuels": [{"type": "PULP95", "price": 400}],
                },
            ]
        }

        stations = normalize_stations([payload], settings)

        self.assertEqual([station.name for station in stations], ["Near expensive", "Far cheap"])

    def test_mqtt_publishes_discovery_state_and_coordinates(self) -> None:
        published = []

        class Result:
            rc = 0

            def wait_for_publish(self) -> None:
                pass

        class Client:
            def __init__(self, *args, **kwargs):
                pass

            def username_pw_set(self, *args, **kwargs):
                pass

            def will_set(self, *args, **kwargs):
                pass

            def connect(self, *args, **kwargs):
                pass

            def loop_start(self):
                pass

            def loop_stop(self):
                pass

            def disconnect(self):
                pass

            def publish(self, topic, payload, **kwargs):
                published.append((topic, payload))
                return Result()

        station = Station(
            provider_id="123/#",
            name="Gull Te Rapa",
            brand="Gull",
            address="736 Te Rapa Road",
            latitude=-37.753508,
            longitude=175.242085,
            distance_km=5,
            fuel_type="PULP95",
            price_cents=334.6,
            provider_updated_at=None,
        )
        with patch("fuel_prices.mqtt.mqtt.Client", Client):
            publish_snapshot(Settings(mqtt_host="broker"), [station], datetime.now(timezone.utc))

        self.assertTrue(any(topic.endswith("/config") for topic, _ in published))
        self.assertTrue(any(topic.endswith("/state") and payload == "3.346" for topic, payload in published))
        self.assertTrue(any('"latitude": -37.753508' in payload for _, payload in published))
        self.assertTrue(all("#" not in topic for topic, _ in published))


if __name__ == "__main__":
    unittest.main()
