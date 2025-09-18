"""FastAPI application powering the hass_helper service."""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .hass_client import HomeAssistantClient, HomeAssistantError, HomeAssistantSettings
from .logging_config import setup_logging
from .models import (
    BlacklistEntryRequest,
    BlacklistResponse,
    DomainEntry,
    DomainSelectionRequest,
    EntitiesResponse,
    WhitelistEntryRequest,
    WhitelistResponse,
)
from .storage import DataRepository

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR = BASE_DIR / "data"

for env_path in (
    BASE_DIR / ".env",
    BASE_DIR.parent / ".env",
    Path.cwd() / ".env",
):
    load_dotenv(dotenv_path=env_path, override=False)

setup_logging()
logger = logging.getLogger("hass_helper.app")

settings = HomeAssistantSettings(
    base_url=os.getenv("HASS_BASE_URL", "http://homeassistant.local:8123"),
    access_token=os.getenv("HASS_ACCESS_TOKEN", ""),
)

repository = DataRepository(DATA_DIR)
hass_client = HomeAssistantClient(settings)

app = FastAPI(title="Home Assistant Helper", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def ensure_hass_configured() -> None:
    if not hass_client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Home Assistant credentials are not configured. Set HASS_BASE_URL and HASS_ACCESS_TOKEN.",
        )


def translate_error(exc: HomeAssistantError) -> HTTPException:
    status_code = status.HTTP_502_BAD_GATEWAY
    if exc.status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}:
        status_code = exc.status_code
    return HTTPException(status_code=status_code, detail=str(exc))


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await hass_client.close()


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="UI not found")
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


def _format_domain_title(domain: str) -> str:
    cleaned = domain.replace("_", " ").replace("-", " ")
    if cleaned.upper() in {"MQTT", "ZIGBEE", "Z-WAVE", "Z WAVE", "ZIGBEE2MQTT"}:
        return cleaned.upper()
    return cleaned.title()


@app.get("/api/integrations/available", response_model=List[DomainEntry])
async def available_integrations() -> List[DomainEntry]:
    ensure_hass_configured()
    try:
        domains = await hass_client.fetch_domains()
    except HomeAssistantError as exc:
        raise translate_error(exc) from exc
    entries = [
        DomainEntry(domain=domain, title=_format_domain_title(domain))
        for domain in domains
    ]
    return sorted(entries, key=lambda item: (item.title or item.domain or "").lower())


@app.get("/api/integrations/selected", response_model=List[DomainEntry])
async def selected_integrations() -> List[DomainEntry]:
    return [DomainEntry(**entry) for entry in repository.get_selected_domains()]


@app.post("/api/integrations/selected", response_model=List[DomainEntry])
async def add_domain(request: DomainSelectionRequest) -> List[DomainEntry]:
    ensure_hass_configured()
    try:
        domains = await hass_client.fetch_domains()
    except HomeAssistantError as exc:
        raise translate_error(exc) from exc

    if request.domain not in domains:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")

    title = _format_domain_title(request.domain)
    logger.info("Domain added to selection", extra={"domain": request.domain})
    repository.add_domain(request.domain, title=title)
    return [DomainEntry(**entry) for entry in repository.get_selected_domains()]


@app.delete("/api/integrations/selected/{domain}", response_model=List[DomainEntry])
async def delete_domain(domain: str) -> List[DomainEntry]:
    repository.remove_domain(domain)
    logger.info("Domain removed from selection", extra={"domain": domain})
    return [DomainEntry(**entry) for entry in repository.get_selected_domains()]


@app.get("/api/blacklist", response_model=BlacklistResponse)
async def get_blacklist() -> BlacklistResponse:
    data = repository.get_blacklist()
    return BlacklistResponse(**data)


@app.post("/api/blacklist", response_model=BlacklistResponse)
async def add_blacklist_entry(request: BlacklistEntryRequest) -> BlacklistResponse:
    try:
        data = repository.add_to_blacklist(request.target_type, request.target_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return BlacklistResponse(**data)


@app.delete("/api/blacklist/{target_type}/{target_id}", response_model=BlacklistResponse)
async def remove_blacklist_entry(target_type: str, target_id: str) -> BlacklistResponse:
    try:
        data = repository.remove_from_blacklist(target_type, target_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return BlacklistResponse(**data)


@app.get("/api/whitelist", response_model=WhitelistResponse)
async def get_whitelist() -> WhitelistResponse:
    data = repository.get_whitelist()
    return WhitelistResponse(**data)


@app.post("/api/whitelist", response_model=WhitelistResponse)
async def add_whitelist_entry(request: WhitelistEntryRequest) -> WhitelistResponse:
    data = repository.add_to_whitelist(request.entity_id)
    return WhitelistResponse(**data)


@app.delete("/api/whitelist/{entity_id}", response_model=WhitelistResponse)
async def remove_whitelist_entry(entity_id: str) -> WhitelistResponse:
    data = repository.remove_from_whitelist(entity_id)
    return WhitelistResponse(**data)


def _build_filtered_snapshot(
    raw_devices: List[Dict[str, Any]],
    *,
    allowed_domains: set[str] | None = None,
) -> EntitiesResponse:
    blacklist = repository.get_blacklist()
    whitelist = repository.get_whitelist()
    if allowed_domains is None:
        allowed_domains = {
            entry.get("domain")
            for entry in repository.get_selected_domains()
            if entry.get("domain")
        }

    blacklist_devices = set(blacklist.get("devices", []))

    filtered_entities: List[Dict[str, Any]] = []
    filtered_devices: List[Dict[str, Any]] = []
    seen_entities: set[str] = set()
    seen_devices: set[str] = set()

    def _normalize_identifiers(values: Any) -> List[Any]:
        result: List[Any] = []
        if isinstance(values, list):
            iterable = values
        elif isinstance(values, (set, tuple)):
            iterable = list(values)
        else:
            iterable = [values] if values else []
        for item in iterable:
            if isinstance(item, (set, tuple, list)):
                result.append(list(item))
            else:
                result.append(item)
        return result

    devices_sorted = sorted(
        [device for device in raw_devices if isinstance(device, dict)],
        key=lambda item: (item.get("id") or "").lower(),
    )

    for device in devices_sorted:
        device_id = device.get("id")
        if not device_id or device_id in seen_devices:
            continue

        integration_id = device.get("integration_id") or device.get("integration")
        if allowed_domains and (
            not integration_id or integration_id not in allowed_domains
        ):
            continue
        if device_id in blacklist_devices:
            continue

        identifiers = _normalize_identifiers(device.get("identifiers") or [])

        entity_records = []
        entities = device.get("entities")
        if not isinstance(entities, list):
            entities = []

        # Sort entities for stable ordering.
        entities_sorted = sorted(
            [entity for entity in entities if isinstance(entity, dict)],
            key=lambda entry: (entry.get("entity_id") or "").lower(),
        )

        for entity in entities_sorted:
            entity_id = entity.get("entity_id")
            if not entity_id or entity_id in seen_entities:
                continue
            entity_integration = (
                entity.get("integration_id")
                or entity.get("integration")
                or integration_id
            )
            if allowed_domains and (
                not entity_integration or entity_integration not in allowed_domains
            ):
                continue
            device_ref = entity.get("device_id") or device_id
            if not repository.is_entity_allowed(
                entity_id,
                device_ref,
                blacklist=blacklist,
                whitelist=whitelist,
            ):
                continue

            attributes = entity.get("attributes")
            if not isinstance(attributes, dict):
                attributes = {}

            record = {
                "entity_id": entity_id,
                "name": entity.get("name") or entity.get("original_name"),
                "original_name": entity.get("original_name") or entity.get("name"),
                "device_id": device_ref,
                "area_id": entity.get("area_id") or device.get("area_id"),
                "unique_id": entity.get("unique_id"),
                "integration_id": entity_integration,
                "state": entity.get("state"),
                "attributes": attributes,
                "disabled_by": entity.get("disabled_by"),
            }
            entity_records.append(record)
            filtered_entities.append(record)
            seen_entities.add(entity_id)

        if not entity_records:
            continue

        filtered_devices.append(
            {
                "id": device_id,
                "name": device.get("name"),
                "name_by_user": device.get("name_by_user"),
                "manufacturer": device.get("manufacturer"),
                "model": device.get("model"),
                "sw_version": device.get("sw_version"),
                "configuration_url": device.get("configuration_url"),
                "area_id": device.get("area_id"),
                "via_device_id": device.get("via_device_id"),
                "identifiers": identifiers,
                "integration_id": integration_id,
                "entities": entity_records,
            }
        )
        seen_devices.add(device_id)

    return EntitiesResponse(entities=filtered_entities, devices=filtered_devices)


async def _ingest_entities() -> EntitiesResponse:
    selected = repository.get_selected_domains()
    selected_domains = sorted(
        {entry.get("domain") for entry in selected if entry.get("domain")}
    )
    if not selected_domains:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No domains have been selected for ingestion.",
        )

    ensure_hass_configured()

    logger.info(
        "Starting entity ingest",
        extra={"domains": selected_domains},
    )

    try:
        snapshots = await asyncio.gather(
            *[
                hass_client.fetch_domain_devices(domain)
                for domain in selected_domains
            ]
        )
    except HomeAssistantError as exc:
        raise translate_error(exc) from exc

    device_map: Dict[str, Dict[str, Any]] = {}
    for domain, devices in zip(selected_domains, snapshots):
        if not isinstance(devices, list):
            continue
        for device in devices:
            if not isinstance(device, dict):
                continue
            device_id = device.get("id")
            if not device_id:
                continue

            integration_id = (
                device.get("integration_id")
                or device.get("integration")
                or domain
            )

            # Shallow copy scalar fields and normalise the entity list.
            sanitized = {
                key: value
                for key, value in device.items()
                if key != "entities"
            }
            sanitized["integration_id"] = integration_id

            entities_raw = device.get("entities")
            normalized_entities: List[Dict[str, Any]] = []
            if isinstance(entities_raw, list):
                for entity in entities_raw:
                    if not isinstance(entity, dict):
                        continue
                    entity_record = dict(entity)
                    if not entity_record.get("integration_id"):
                        entity_record["integration_id"] = (
                            entity_record.get("integration") or integration_id
                        )
                    if not entity_record.get("device_id"):
                        entity_record["device_id"] = device_id
                    normalized_entities.append(entity_record)
            normalized_entities.sort(
                key=lambda entry: (entry.get("entity_id") or "").lower()
            )

            existing = device_map.get(device_id)
            if existing:
                if not existing.get("integration_id"):
                    existing["integration_id"] = integration_id
                existing_entities = existing.setdefault("entities", [])
                seen_entity_ids = {
                    entry.get("entity_id")
                    for entry in existing_entities
                    if isinstance(entry, dict)
                }
                for entity in normalized_entities:
                    entity_id = entity.get("entity_id")
                    if not entity_id or entity_id in seen_entity_ids:
                        continue
                    existing_entities.append(entity)
                    seen_entity_ids.add(entity_id)
            else:
                sanitized["entities"] = normalized_entities
                device_map[device_id] = sanitized

    raw_devices = [
        device_map[key]
        for key in sorted(device_map.keys(), key=lambda item: str(item).lower())
    ]

    repository.save_entities(raw_devices)

    filtered = _build_filtered_snapshot(
        raw_devices,
        allowed_domains=set(selected_domains),
    )

    logger.info(
        "Entity ingest completed",
        extra={
            "entity_count": len(filtered.entities),
            "device_count": len(filtered.devices),
        },
    )
    return filtered


@app.get("/api/entities", response_model=EntitiesResponse)
async def get_entities() -> EntitiesResponse:
    data = repository.get_entities()
    raw_devices = data.get("devices", []) if isinstance(data, dict) else []
    allowed_domains = {
        entry.get("domain")
        for entry in repository.get_selected_domains()
        if entry.get("domain")
    }
    return _build_filtered_snapshot(
        list(raw_devices),
        allowed_domains=set(allowed_domains),
    )


@app.post("/api/entities/ingest", response_model=EntitiesResponse)
async def ingest_entities() -> EntitiesResponse:
    return await _ingest_entities()


@app.post("/api/entities/refresh", response_model=EntitiesResponse, include_in_schema=False)
async def refresh_entities() -> EntitiesResponse:
    return await _ingest_entities()
