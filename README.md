# Home Assistant Automations & Services

This repository collects reusable Home Assistant tooling that can be mixed and matched to build a
smarter home. It is organized around three services plus a set of blueprints for automations.

- **`services/hass_helper`** – A FastAPI web app that syncs metadata from Home Assistant, lets you
  manage domain allow/deny lists, and persists entity information for other tooling.
- **`services/hassems`** – The Home Assistant Entity Management System used to curate helpers and
  publish MQTT discovery payloads with a bundled management UI.
- **`services/hass_integration`** – Documentation for the custom Home Assistant integration that
  consumes HASSEMS metadata so entities are available natively within Home Assistant. The actual
  integration code lives in `custom_components/hassems/` for compatibility with HACS.
- **`blueprints/`** – Automations for common scenarios such as auto-locking doors, sunrise/sunset
  controls, and webhook-driven notifications.

Each service folder includes step-by-step installation and runtime instructions. The blueprints
README describes what each automation does and includes one-click import buttons for My Home
Assistant.

## Getting started

1. **Choose a service** – Review the READMEs in `services/` to decide which components you want to
   deploy. They can be run independently or together.
2. **Configure Home Assistant access** – Most services require a long-lived access token and the base
   URL for your Home Assistant instance. Copy the relevant `.env.example` file in each service folder
   and fill in your credentials.
3. **Run locally or with Docker** – Use the provided `start.sh` scripts for local development or the
   `Dockerfile`/`docker-compose.yml` configurations to containerize the services.
4. **Import blueprints** – Visit `blueprints/README.md` for a description of each automation and the
   quick-import links.

## Repository layout

```text
.
├── blueprints/            # Home Assistant automation blueprints
├── custom_components/     # HASSEMS Home Assistant integration
├── services/
│   ├── hass_helper/       # Metadata ingestion and helper UI
│   ├── hassems/           # Helper management service with MQTT support
│   └── hass_integration/  # Custom integration for Home Assistant
└── README.md              # Project overview (this file)
```

## Contributing

Contributions and enhancements are welcome. Please open an issue or submit a pull request describing
new automations, service improvements, or bug fixes.
