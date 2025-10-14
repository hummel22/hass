# MQTT Discovery for Home Assistant — Reference

This document provides a worked example for publishing MQTT discovery data for a height sensor as
well as supporting notes about topics, state payloads, and popular configuration keys.

## Discovery topic structure

```
homeassistant/sensor/child_metrics/eleanors_height/config
```

| Segment | Meaning | Notes |
| ------- | ------- | ----- |
| `homeassistant` | Discovery prefix | Home Assistant listens for discovery payloads here (configurable in the MQTT integration). |
| `sensor` | Component/platform | Determines which MQTT integration is created (`sensor`, `binary_sensor`, `switch`, etc.). |
| `child_metrics` | Optional node_id | Organisational folder. Must match `[A-Za-z0-9_-]+`. Many devices omit it. |
| `eleanors_height` | object_id | Per-entity bucket. Typically matches the unique ID. |
| `config` | Fixed suffix | Signals that the payload contains discovery configuration. |

General pattern: `<discovery_prefix>/<component>/[<node_id>/]<object_id>/config`

Only discovery topics must follow this pattern. State and availability topics are entirely up to you.

## Discovery payload example

Retain the payload below on `homeassistant/sensor/child_metrics/eleanors_height/config`:

```json
{
  "name": "Eleanor's Height",
  "unique_id": "eleanors_height",
  "state_topic": "child/eleanors_height/state",
  "availability_topic": "child/eleanors_height/availability",
  "device_class": "distance",
  "unit_of_measurement": "in",
  "state_class": "measurement",
  "force_update": true,
  "value_template": "{{ value_json.value | float }}",
  "json_attributes_topic": "child/eleanors_height/state",
  "json_attributes_template": "{{ {'measured_at': value_json.measured_at} | tojson }}",
  "device": {
    "identifiers": ["child_metrics:eleanors_height"],
    "manufacturer": "HASSEMS",
    "model": "Input Number",
    "name": "Child Metrics"
  }
}
```

### Key fields

- `unique_id` – Required for device registry support and to avoid duplicate entities.
- `state_topic` – Where HASSEMS publishes value payloads (`{"value": 63.25, "measured_at": "..."}`).
- `availability_topic` – Optional but recommended online/offline indicator. Defaults to
  `payload_available`/`payload_not_available`.
- `value_template` – Extracts the sensor state from the JSON payload. Adjust when publishing strings.
- `json_attributes_template` – Selectively expose additional JSON attributes (e.g. `measured_at`).
- `device` – Groups entities under a single device in Home Assistant's Devices view.

Publishing an empty payload to the same config topic removes the discovery entry.

## State & availability publishes

State payloads can be raw numbers or JSON. HASSEMS uses JSON so Home Assistant receives both the
value and `measured_at` timestamp:

```json
{
  "value": 63.25,
  "measured_at": "2025-10-13T20:41:00-05:00"
}
```

Recommended availability payloads:

```
# Online
mosquitto_pub -t child/eleanors_height/availability -m 'online'
# Offline
mosquitto_pub -t child/eleanors_height/availability -m 'offline'
```

## Useful configuration keys

| Key | Required | Purpose | Notes |
| --- | -------- | ------- | ----- |
| `unique_id` | No* | Uniquely identify the entity. Required when `device` is present. |
| `name` | No | Friendly name shown in the UI. |
| `state_topic` | Yes | Topic Home Assistant subscribes to for values. |
| `value_template` | No | Jinja template that extracts a value from the payload. |
| `unit_of_measurement` | No | Unit string (must match the chosen device class). |
| `device_class` | No | Categorises the measurement (temperature, distance, humidity, ...). |
| `state_class` | No | Controls statistics handling (`measurement`, `total`, `total_increasing`). |
| `availability_topic` | No | Topic that reports `online`/`offline`. |
| `force_update` | No | Emit events even when the value does not change (great for charts). |
| `json_attributes_topic` | No | Topic Home Assistant should read for extra attributes. |
| `device` | No* | Device registry metadata (name, identifiers, connections). Requires `unique_id`. |

A full list of device classes, state classes, and supported MQTT platforms lives in the Home
Assistant developer documentation:

- <https://developers.home-assistant.io/docs/core/entity/sensor>
- <https://www.home-assistant.io/integrations/mqtt/> (platforms that support discovery)

## Quick checklist

- Discovery topic: `homeassistant/<component>/[node_id/]<object_id>/config`
- State topic: your namespace (e.g. `child/eleanors_height/state`)
- Availability topic: optional but recommended (`child/eleanors_height/availability`)
- `device_class`, `unit_of_measurement`, and `state_class` should align for clean graphs
- Retain discovery payloads so entities survive Home Assistant restarts
