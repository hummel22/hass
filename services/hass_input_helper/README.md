# HASS Input Helper Service

A lightweight FastAPI service that helps manage Home Assistant input helpers (input_text,
input_number, input_boolean, and input_select). The app keeps a local catalogue of the helpers you
care about, exposes a REST API for CRUD operations, and proxies value updates to Home Assistant via
its REST API.

## Feature checklist

- [x] Persist a catalogue of input helpers in `data/input_helpers.json`.
- [x] CRUD endpoints to list, create, update, and delete helper definitions.
- [x] Validate helper metadata (entity IDs, select options, default values).
- [x] Forward value updates to Home Assistant for supported helper types.
- [x] Fetch the latest state of a helper directly from Home Assistant.
- [x] Provide a convenience script for local development (`start.sh`).

## Configuration

The service reads Home Assistant connection details from the following environment variables (load
from a `.env` file for convenience):

- `HASS_BASE_URL` – The base URL for your Home Assistant instance, e.g.
  `http://homeassistant.local:8123`.
- `HASS_ACCESS_TOKEN` – A long-lived access token generated in your Home Assistant user profile.

Copy the example file and edit the values:

```bash
cp services/hass_input_helper/.env.example services/hass_input_helper/.env
```

Without these values the service still starts, but any endpoint that talks to Home Assistant will
return a `503` error.

## Running locally

Create a virtual environment and start the API with the helper script:

```bash
services/hass_input_helper/start.sh
```

The application listens on `http://127.0.0.1:8100` by default.

## API overview

| Method | Path | Description |
| ------ | ---- | ----------- |
| `GET` | `/health` | Basic health probe. |
| `GET` | `/inputs` | List stored input helpers. |
| `POST` | `/inputs` | Create a new helper definition. |
| `PUT` | `/inputs/{slug}` | Update a helper definition. |
| `DELETE` | `/inputs/{slug}` | Remove a helper definition. |
| `POST` | `/inputs/{slug}/set` | Set the helper value in Home Assistant. |
| `GET` | `/inputs/{slug}/state` | Fetch the current Home Assistant state. |

Refer to the inline OpenAPI docs (`/docs`) for the exact request/response schema.
