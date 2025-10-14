# HASSEMS Home Assistant Integration

This folder contains a custom Home Assistant integration that connects to the HASSEMS service and
exposes helper entities (numbers, sensors, selects, switches, and texts) directly inside Home
Assistant. The integration retrieves metadata through HASSEMS's REST API and keeps entities in sync
via an update coordinator.

## Installation

### Prerequisites

- Home Assistant 2023.8 or newer
- A running instance of the HASSEMS service with network reachability from Home Assistant

### Steps

1. Copy the `custom_components/hassems` directory into your Home Assistant configuration folder:

   ```bash
   # from the repository root
   cp -R services/hass_integration/custom_components/hassems \
         /path/to/home-assistant/config/custom_components/hassems
   ```

2. Restart Home Assistant so the integration is discovered.

3. Navigate to **Settings → Devices & Services → Integrations** and click **+ Add Integration**.
4. Search for **HASSEMS** and follow the prompts:
   - Enter the base URL of the HASSEMS service (for example `http://hassems.local:8100`).
   - Provide the API token if you configured one in HASSEMS.

After setup completes, the integration will create entities for each helper maintained by HASSEMS.

## Updating

To upgrade, replace the `custom_components/hassems` folder with the latest copy from this repository
and restart Home Assistant. Existing configuration flows persist, so you will not need to reconfigure
unless connection details have changed.

## Development tips

- Use the `logger` integration in Home Assistant to set `custom_components.hassems` to `debug` while
you iterate on API responses or entity behavior.
- The integration's `manifest.json` declares version information; update it when publishing a new
release.
