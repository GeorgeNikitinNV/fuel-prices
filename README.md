# Fuel Prices

Hourly fuel price collection for a configurable location, with SQLite history and MQTT discovery for Home Assistant.

The default fuel is Premium 95 (PULP95). The default location preserves the original Hamilton coordinates. Petrolmate currently requires no API key.

## Install

    uv sync
    cp .env.example .env
    fuel-prices --help

Keep secrets in .env or the process environment. CLI values override environment values; environment values override defaults.

## Configure

    FUEL_PRICES_LAT=-37.7870
    FUEL_PRICES_LON=175.2793
    FUEL_PRICES_RADIUS_KM=30
    FUEL_PRICES_FUEL_TYPE=PULP95
    FUEL_PRICES_INTERVAL_MINUTES=60
    FUEL_PRICES_DB=./data/fuel-prices.db

    MQTT_HOST=homeassistant.local
    MQTT_PORT=1883
    MQTT_USERNAME=
    MQTT_PASSWORD=

Use FUEL_PRICES_STATIONS as a comma-separated list to limit results. Matching is case-insensitive against station name, brand, and address. Empty means all stations in the radius.

The CLI accepts the same settings. For example:

    fuel-prices --radius-km 30 --fuel-type PULP95 fetch
    fuel-prices --station "Gull Te Rapa" --station "Pak 'n Save Mill Street" fetch
    fuel-prices --sort distance stations
    fuel-prices --sort price stations
    fuel-prices --format csv stations > prices.csv
    fuel-prices --format tsv stations > prices.tsv
    fuel-prices --format json stations > prices.json
    fuel-prices stations

## Commands

    fuel-prices fetch       # fetch, store, and publish one snapshot
    fuel-prices run         # fetch immediately, then repeat hourly
    fuel-prices stations    # list matching stations without writing data

run keeps running until stopped. It retries failed updates on the next interval and stores data before publishing to MQTT.

The default output is a readable table. Use csv, tsv, or json when piping results into another tool. The output format can also be set with FUEL_PRICES_OUTPUT_FORMAT.

Results are sorted by price by default. Use --sort distance or set FUEL_PRICES_SORT_BY=distance for nearest-first results.

## Storage

The default database is data/fuel-prices.db. It contains station metadata and append-only price observations, including provider update timestamps and fetch timestamps.

The provider accepts a maximum 25 km request radius. A configured radius above 25 km and up to 30 km is covered with offset queries, deduplicated by station ID, then filtered by exact distance.

## Home Assistant

The app publishes one MQTT sensor per station using MQTT Discovery. Each sensor has the price as its state and latitude/longitude, station metadata, fuel type, and timestamps as attributes.

Ensure the Home Assistant MQTT integration and a broker are available, then configure MQTT_HOST with the broker's real hostname or LAN IP. MQTT credentials require TLS. The discovery prefix defaults to homeassistant. Leave MQTT_HOST empty to collect and store prices without publishing to Home Assistant.

Add a native map card:

    type: map
    show_all: true
    default_zoom: 10

Station sensors are locatable because their MQTT attributes include latitude and longitude. Selecting a marker shows its current price and metadata.

Reference documentation:

    https://petrolmate.com.au/home-assistant
    https://www.home-assistant.io/dashboards/map/
    https://www.home-assistant.io/integrations/sensor.mqtt/

## Development

    uv run python -m unittest discover -s tests
    python3 main.py --help

main.py remains as a small compatibility launcher; the installed fuel-prices command is the supported interface.
