from __future__ import annotations

import json
import re
from datetime import datetime

import paho.mqtt.client as mqtt

from .config import Settings
from .provider import Station


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return value or "station"


def _publish(client: mqtt.Client, topic: str, payload: str, *, retain: bool = True) -> None:
    result = client.publish(topic, payload, qos=1, retain=retain)
    result.wait_for_publish()
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        raise RuntimeError(f"MQTT publish failed for {topic}: {result.rc}")


def publish_snapshot(settings: Settings, stations: list[Station], fetched_at: datetime) -> None:
    if not settings.mqtt_host:
        return

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="fuel-prices")
    if settings.mqtt_username:
        client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
    if settings.mqtt_tls:
        client.tls_set()

    status_topic = f"{settings.mqtt_topic_prefix}/status"
    client.will_set(status_topic, "offline", qos=1, retain=True)
    client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)
    client.loop_start()
    try:
        _publish(client, status_topic, "online")
        for station in stations:
            entity_id = f"{_slug(station.brand)}_{_slug(station.name)}_{station.provider_id}"
            base_topic = f"{settings.mqtt_topic_prefix}/{entity_id}"
            discovery_topic = f"{settings.mqtt_discovery_prefix}/sensor/{entity_id}/config"
            config = {
                "name": f"{station.name} {station.fuel_type} price",
                "unique_id": f"fuel_prices_{station.provider_id}_{station.fuel_type.lower()}",
                "state_topic": f"{base_topic}/state",
                "json_attributes_topic": f"{base_topic}/attributes",
                "availability_topic": status_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "unit_of_measurement": "NZD/L",
                "suggested_display_precision": 3,
                "icon": "mdi:gas-station",
                "device": {
                    "identifiers": [f"fuel_prices_{station.provider_id}"],
                    "name": station.name,
                    "manufacturer": "Petrolmate",
                    "model": "Fuel station",
                },
            }
            attributes = {
                "latitude": station.latitude,
                "longitude": station.longitude,
                "brand": station.brand,
                "address": station.address,
                "fuel_type": station.fuel_type,
                "distance_km": round(station.distance_km, 2),
                "provider_updated_at": station.provider_updated_at,
                "fetched_at": fetched_at.isoformat(),
            }
            _publish(client, discovery_topic, json.dumps(config))
            _publish(client, f"{base_topic}/attributes", json.dumps(attributes))
            state = "" if station.price_cents is None else f"{station.price_cents / 100:.3f}"
            _publish(client, f"{base_topic}/state", state)
    finally:
        client.loop_stop()
        client.disconnect()
