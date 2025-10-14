# Home Assistant Blueprints

This directory contains reusable automations that can be imported into your Home Assistant instance
with a single click. Each blueprint below includes a badge that opens the My Home Assistant import
flow. Update the `blueprint_url` in the links if you publish this repository under a different GitHub
organization or branch.

## Auto-lock door after duration

Automatically re-lock a smart lock after it has been left unlocked for a configurable amount of time.
The automation checks a companion door contact sensor before locking and sends notifications for
success, skipped (door open), or failure scenarios.

[![Import Auto-lock Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://raw.githubusercontent.com/your-org/hass/main/blueprints/auto_lock.yaml)

## CreditWatch notification webhook

Processes webhook payloads from the CreditWatch backend and forwards them to configurable Home
Assistant notify services. Supports per-target overrides so different webhook slugs can alert distinct
recipients.

[![Import CreditWatch Webhook Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://raw.githubusercontent.com/your-org/hass/main/blueprints/notification_webhook.yaml)

## Sunrise/Sunset scene control

Turns entities on at sunset (with optional offsets) and off at sunrise. Works with lights, switches,
and fans and allows specifying ±HH:MM:SS offsets for precise timing.

[![Import Sunrise/Sunset Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://raw.githubusercontent.com/your-org/hass/main/blueprints/on_off_sunrise_sunset.yaml)
