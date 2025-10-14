# HASS Helper Service

This service provides a small FastAPI application that connects to a Home Assistant instance,
collects entity and device metadata filtered by configured domains, and stores the results locally
as JSON files. A lightweight web UI is bundled to manage domains, blacklists, and whitelists, and
to trigger ingestion runs.

## Installation

### Prerequisites

- Python 3.10+
- Node.js 18+ (only required if you plan to rebuild the bundled web assets)

### Steps

```bash
# from the repository root
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r services/hass_helper/requirements.txt
```

Alternatively you can rely on the helper script (`services/hass_helper/start.sh`) which provisions
the virtual environment automatically before launching the app.

## Configuration

Set the following environment variables before starting the service. The application will
automatically load them from a `.env` file located either beside the code in
`services/hass_helper/.env` or at the repository root.

- `HASS_BASE_URL` – Base URL of the Home Assistant instance (e.g. `http://homeassistant.local:8123`).
- `HASS_ACCESS_TOKEN` – Long-lived access token used to authenticate API requests.

Use the provided `.env.example` as a template:

```bash
cp services/hass_helper/.env.example services/hass_helper/.env
# then edit services/hass_helper/.env with your Home Assistant details
```

## Data Files

The service reads and persists JSON data inside `services/hass_helper/data/`:

- `integrations.json` – Selected Home Assistant domains used during ingest.
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

## Container usage

Build a container image with the helper script (defaults to the `hass-helper:latest` tag):

```bash
services/hass_helper/build.sh
```

To build with a custom name or tag, pass them as arguments, e.g. `services/hass_helper/build.sh my-org/hass-helper v1`.

Run the service with Docker Compose, which mounts the local `data/` directory for persistence and
loads environment variables from `services/hass_helper/.env`:

```bash
cd services/hass_helper
docker compose up --build
```

Once the container is running, browse to `http://localhost:8000/` to use the UI.

## Enable the Home Assistant API

The helper relies on Home Assistant's REST API. Ensure the `api` integration is enabled and the
HTTP server is reachable from the network where `hass-helper` runs. Copy the
`configuration.example.yaml` file into your Home Assistant configuration directory and merge the
settings into your existing `configuration.yaml`:

```bash
cp services/hass_helper/configuration.example.yaml /path/to/home-assistant/configuration.example.yaml
# review the file and merge the sections into your existing configuration.yaml
```

At minimum you should:

1. Enable the `api:` integration so the REST endpoints are exposed.
2. Set `http.server_host: 0.0.0.0` (or another appropriate interface) so Home Assistant accepts
   connections from your `hass-helper` instance.
3. Configure `http.trusted_proxies` and `http.cors_allowed_origins` so requests from
   `hass-helper` (and the UI running on port `8000`) are permitted.

After updating `configuration.yaml`, restart Home Assistant to apply the changes. Generate a
long-lived access token from your Home Assistant user profile and place it in the `.env` file so
`hass-helper` can authenticate.

### Log viewing with Dozzle

Structured JSON logs are emitted to stdout for every Home Assistant HTTP call and key ingest
operations. A companion Compose file is provided to run [Dozzle](https://dozzle.dev/) for viewing
these logs alongside the application:

```bash
cd services/hass_helper
docker compose -f docker-compose.yml -f docker-compose.infra.yaml up
```

Dozzle is exposed on `http://localhost:9999/` and is pre-filtered to the `hass-helper` container.
