# Home Assistant Entity Management System (HASSEMS)

HASSEMS is a FastAPI application that manages Home Assistant helper entities, publishes Home
Assistant MQTT discovery payloads, and stores helper history in SQLite. The bundled web console lets
you configure broker access, publish test values, and manage discovery metadata without hand-writing
JSON.

## Feature checklist

- [x] Persist helper definitions, MQTT credentials, and history in `data/input_helpers.db` (SQLite).
- [x] Create, update, delete, and list helpers via REST endpoints that validate metadata with Pydantic.
- [x] Configure MQTT connectivity from the UI and verify credentials with a single "Test connection"
      action.
- [x] Publish retained MQTT discovery payloads that follow the
      `<discovery_prefix>/<component>/[<node_id>/]<object_id>/config` pattern Home Assistant expects.
- [x] Surface measured timestamps alongside helper history and allow backdating through date & time
      pickers.
- [x] Provide rich UI helpers such as dropdowns for device classes, units, state classes, and discovery
      components plus inline tooltips describing each setting.

## Configuration

HASSEMS still supports optional REST calls to Home Assistant. Configure them by setting the following
environment variables (for development, copy `.env.example`):

- `HASS_BASE_URL` – Base URL for Home Assistant (e.g. `http://homeassistant.local:8123`).
- `HASS_ACCESS_TOKEN` – Long-lived access token created from your Home Assistant profile.

Without these variables MQTT publishing continues to function, but routes that call the Home
Assistant HTTP API will return `503`.

## Running locally

Create a virtual environment and launch the API using the included helper script:

```bash
services/hass_input_helper/start.sh
```

The server listens on `http://127.0.0.1:8100`. Visiting the root renders the HASSEMS console where
you can:

- Configure the Mosquitto broker credentials that are stored in SQLite (discovery prefix is locked to
  `homeassistant` for compatibility with the integration).
- Review broker connectivity logs via the **Test connection** button.
- Create helpers with full discovery metadata (component, unique ID, object ID, node ID defaulting
  to `hassems`, topics, icon, device class, unit, state class, and device registry fields).
- Edit existing helpers, regenerate discovery payloads, and inspect state/availability topics.
- Review helper history with inline charts and publish new readings that include `measured_at`
  timestamps selected via date/time pickers.

## API overview

| Method | Path | Description |
| ------ | ---- | ----------- |
| `GET`  | `/health` | Basic health probe. |
| `GET`  | `/inputs` | List stored helpers and their metadata. |
| `POST` | `/inputs` | Create a helper definition and publish discovery + availability payloads. |
| `PUT`  | `/inputs/{slug}` | Update a helper definition and refresh discovery payloads. |
| `DELETE` | `/inputs/{slug}` | Delete a helper and clear the retained discovery payload. |
| `POST` | `/inputs/{slug}/set` | Publish a new helper value (optionally with `measured_at`). |
| `GET`  | `/inputs/{slug}/history` | Return persisted history for a helper. |
| `GET`  | `/config/mqtt` | Fetch stored MQTT configuration. |
| `PUT`  | `/config/mqtt` | Save MQTT configuration (discovery prefix forced to `homeassistant`). |
| `POST` | `/config/mqtt/test` | Attempt a broker connection using the stored credentials. |

Refer to `/docs` for detailed schemas.

## MQTT discovery & telemetry

Every helper publish triggers three MQTT messages:

1. **Discovery** – Retained payload on
   `homeassistant/<component>/[node_id/]<object_id>/config` using the metadata you configure in the UI.
2. **Availability** – Retained payload on the helper-specific availability topic (defaults to
   `online`/`offline`).
3. **State** – JSON payload on the helper's state topic containing both the `value` and
   `measured_at` timestamp.

Discovery payloads include a `value_template` so Home Assistant extracts the numeric/textual `value`
from the JSON body. The same publish updates the entity's `measured_at` attribute via
`json_attributes_topic`. You can review a fully annotated discovery example in
[`MQTT_README.md`](./MQTT_README.md).

## Connecting to Home Assistant's MQTT add-on

1. Install the **Mosquitto broker** add-on and enable the MQTT integration within Home Assistant.
2. Create a dedicated MQTT user (Settings → People & Services → Users) and note the credentials.
3. Open HASSEMS at `http://127.0.0.1:8100`, enter the broker host/port, credentials, and click **Save
   configuration**. The discovery prefix is automatically set to `homeassistant`.
4. Press **Test connection** to confirm the broker accepts the credentials.
5. Create helpers with the desired discovery metadata. Each save republishes a retained discovery
   payload so Home Assistant discovers or updates the entity automatically.
6. Use the value publishing form to send new readings. The payload includes the helper's metadata and
   the `measured_at` timestamp selected through the date/time pickers.

## Additional references

- [`MQTT_README.md`](./MQTT_README.md) – Expanded guide covering MQTT discovery patterns, example
  payloads, and supported device classes/state classes.
- `services/hass_input_helper/mqtt_service.py` – Implementation of discovery/state publishing if you
  need to integrate HASSEMS concepts into other tooling.

Enjoy building and managing MQTT-discovered helpers without editing YAML!
