# HASS Input Helper Service

A lightweight FastAPI service that helps manage Home Assistant input helpers (input_text,
input_number, input_boolean, and input_select). The app keeps a local catalogue of the helpers you
care about, exposes a REST API for CRUD operations, and proxies value updates to Home Assistant via
its REST API.

## Feature checklist

- [x] Persist a catalogue of input helpers and MQTT settings in `data/input_helpers.db` (SQLite).
- [x] CRUD endpoints to list, create, update, and delete helper definitions.
- [x] Validate helper metadata (entity IDs, select options, default values).
- [x] Forward value updates to Home Assistant for supported helper types.
- [x] Publish helper values to MQTT topics and retain a local history timeline.
- [x] Fetch the latest state of a helper directly from Home Assistant.
- [x] Provide a convenience script for local development (`start.sh`).
- [x] Minimal landing page to manage MQTT connectivity and helper catalogue.

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

The application listens on `http://127.0.0.1:8100` by default. Opening the root path renders a
minimal UI to:

- Configure the MQTT broker connection stored in SQLite.
- Test the Mosquitto/MQTT connection directly from the browser.
- Create, edit, and delete helper entities (including device class and unit metadata).
- View helper history and publish new values to MQTT.

The UI uses the REST endpoints documented below, so you can also interact with the API directly.

## API overview

| Method | Path | Description |
| ------ | ---- | ----------- |
| `GET` | `/health` | Basic health probe. |
| `GET` | `/inputs` | List stored input helpers. |
| `POST` | `/inputs` | Create a new helper definition. |
| `PUT` | `/inputs/{slug}` | Update a helper definition. |
| `DELETE` | `/inputs/{slug}` | Remove a helper definition. |
| `POST` | `/inputs/{slug}/set` | Set the helper value in Home Assistant and publish to MQTT. |
| `GET` | `/inputs/{slug}/history` | Retrieve the stored history for a helper. |
| `GET` | `/inputs/{slug}/state` | Fetch the current Home Assistant state. |
| `GET` | `/config/mqtt` | Retrieve the stored MQTT configuration. |
| `PUT` | `/config/mqtt` | Save or update the MQTT configuration. |
| `POST` | `/config/mqtt/test` | Test the stored MQTT configuration. |

Refer to the inline OpenAPI docs (`/docs`) for the exact request/response schema.

## Connecting to the Home Assistant MQTT add-on

1. Install the **Mosquitto broker** add-on from the Home Assistant add-on store. Start the add-on
   and ensure it is configured to start on boot.
2. In Home Assistant, create a dedicated user account for MQTT (Settings → People & Services →
   Users). Note the username and password.
3. Enable the built-in **MQTT integration** (Settings → Devices & Services → Add integration →
   MQTT). When prompted, provide the Mosquitto broker host (typically `homeassistant.local` or your
   Home Assistant IP), port `1883`, and the user credentials created above.
4. Open the input helper UI at `http://127.0.0.1:8100/` and fill in the same host, port, username,
   and password in the MQTT broker card. Save the configuration and press **Test connection** to
   validate the credentials. The configuration is stored in SQLite and reused across restarts.
5. Create entities via the UI, then publish new helper values. Each publish action updates Home
   Assistant (when configured), writes to MQTT under `<topic_prefix>/<slug>`, and stores a timestamped
   history entry in SQLite for charting.
