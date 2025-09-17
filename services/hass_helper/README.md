# HASS Helper Service

This service provides a small FastAPI application that connects to a Home Assistant instance,
collects entity and device metadata filtered by configured integrations, and stores the results
locally as JSON files. A lightweight web UI is bundled to manage integrations, blacklists, and
whitelists, and to trigger ingestion runs.

## Configuration

Set the following environment variables before starting the service:

- `HASS_BASE_URL` – Base URL of the Home Assistant instance (e.g. `http://homeassistant.local:8123`).
- `HASS_ACCESS_TOKEN` – Long-lived access token used to authenticate API requests.

## Data Files

The service reads and persists JSON data inside `services/hass_helper/data/`:

- `integrations.json` – Selected integration entries used during ingest.
- `entities.json` – Cached entities and devices from the most recent ingest run.
- `blacklist.json` – Entity and device IDs excluded during ingest.
- `whitelist.json` – Entity IDs that override blacklist filtering.

## Running the service

Use the provided `start.sh` script to create a virtual environment, install dependencies, and run
the API locally:

```bash
services/hass_helper/start.sh
```

The FastAPI app listens on `http://0.0.0.0:8000/` by default. Open the root URL in a browser to
access the management UI.
