# HASSEMS Home Assistant Integration

This folder documents the custom Home Assistant integration that connects to the HASSEMS service and
exposes helper entities (numbers, sensors, selects, switches, and texts) directly inside Home
Assistant. The integration retrieves metadata through HASSEMS's REST API and keeps entities in sync
via an update coordinator. The integration's source code is located in `custom_components/hassems/`
so it can be installed through HACS without additional restructuring.

## Installation

### Prerequisites

- Home Assistant 2023.8 or newer
- A running instance of the HASSEMS service with network reachability from Home Assistant

### Option A: Install through HACS (recommended)

1. In Home Assistant open **HACS → Integrations → ⋮ → Custom repositories**.
2. Add this repository's URL and set the category to **Integration**.
3. Locate **HASSEMS** in the HACS integrations catalog and click **Download**.
4. Restart Home Assistant so the integration is discovered.

### Option B: Manual installation

1. Copy the `custom_components/hassems` directory into your Home Assistant configuration folder:

   ```bash
   # from the repository root
   cp -R custom_components/hassems \
         /path/to/home-assistant/config/custom_components/hassems
   ```

2. Restart Home Assistant so the integration is discovered.

### Configure the integration

1. Navigate to **Settings → Devices & Services → Integrations** and click **+ Add Integration**.
2. Search for **HASSEMS** and follow the prompts:
   - Enter the base URL of the HASSEMS service (for example `http://hassems.local:8100`).
   - Provide the API token if you configured one in HASSEMS.

After setup completes, the integration will create entities for each helper maintained by HASSEMS.

## Updating

- **HACS** – Use **HACS → Integrations** to check for updates and reinstall the latest release.
- **Manual install** – Replace the `custom_components/hassems` folder with the latest copy from this
  repository and restart Home Assistant. Existing configuration flows persist, so you will not need
  to reconfigure unless connection details have changed.

## Development tips

- Use the `logger` integration in Home Assistant to set `custom_components.hassems` to `debug` while
you iterate on API responses or entity behavior.
- The integration's `manifest.json` declares version information; update it when publishing a new
release.
