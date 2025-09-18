"""FastAPI application powering the hass_helper service."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .hass_client import HomeAssistantClient, HomeAssistantError, HomeAssistantSettings
from .models import (
    BlacklistEntryRequest,
    BlacklistResponse,
    EntitiesResponse,
    IntegrationEntry,
    IntegrationSelectionRequest,
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


@app.get("/api/integrations/available", response_model=List[IntegrationEntry])
async def available_integrations() -> List[IntegrationEntry]:
    ensure_hass_configured()
    try:
        integrations = await hass_client.fetch_integrations()
    except HomeAssistantError as exc:
        raise translate_error(exc) from exc
    return [
        IntegrationEntry(
            entry_id=entry.get("entry_id", ""),
            domain=entry.get("domain"),
            title=entry.get("title"),
        )
        for entry in integrations
        if entry.get("entry_id")
    ]


@app.get("/api/integrations/selected", response_model=List[IntegrationEntry])
async def selected_integrations() -> List[IntegrationEntry]:
    return [IntegrationEntry(**entry) for entry in repository.get_selected_integrations()]


@app.post("/api/integrations/selected", response_model=List[IntegrationEntry])
async def add_integration(request: IntegrationSelectionRequest) -> List[IntegrationEntry]:
    ensure_hass_configured()
    try:
        integrations = await hass_client.fetch_integrations()
    except HomeAssistantError as exc:
        raise translate_error(exc) from exc

    target = next(
        (entry for entry in integrations if entry.get("entry_id") == request.integration_id),
        None,
    )
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")

    repository.add_integration(target)
    return [IntegrationEntry(**entry) for entry in repository.get_selected_integrations()]


@app.delete("/api/integrations/selected/{integration_id}", response_model=List[IntegrationEntry])
async def delete_integration(integration_id: str) -> List[IntegrationEntry]:
    repository.remove_integration(integration_id)
    return [IntegrationEntry(**entry) for entry in repository.get_selected_integrations()]


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


async def _ingest_entities() -> EntitiesResponse:
    selected = repository.get_selected_integrations()
    integration_ids = {entry.get("entry_id") for entry in selected if entry.get("entry_id")}
    if not integration_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No integrations have been selected for ingestion.",
        )

    ensure_hass_configured()

    try:
        entity_registry, device_registry, states = await asyncio.gather(
            hass_client.fetch_entity_registry(),
            hass_client.fetch_device_registry(),
            hass_client.fetch_states(),
        )
    except HomeAssistantError as exc:
        raise translate_error(exc) from exc

    state_map: Dict[str, Dict[str, Any]] = {}
    for state in states:
        entity_id = state.get("entity_id")
        if entity_id:
            state_map[entity_id] = state

    blacklist = repository.get_blacklist()
    whitelist = repository.get_whitelist()

    entities: List[Dict[str, object]] = []
    for entry in entity_registry:
        config_entry_id = entry.get("config_entry_id")
        if config_entry_id not in integration_ids:
            continue
        entity_id = entry.get("entity_id")
        if not entity_id:
            continue
        device_id = entry.get("device_id")
        if not repository.is_entity_allowed(
            entity_id,
            device_id,
            blacklist=blacklist,
            whitelist=whitelist,
        ):
            continue
        state_info = state_map.get(entity_id, {})
        entities.append(
            {
                "entity_id": entity_id,
                "name": entry.get("name"),
                "original_name": entry.get("original_name"),
                "device_id": device_id,
                "area_id": entry.get("area_id"),
                "unique_id": entry.get("unique_id"),
                "integration_id": config_entry_id,
                "state": state_info.get("state"),
                "attributes": state_info.get("attributes", {}),
                "disabled_by": entry.get("disabled_by"),
            }
        )

    allowed_devices = {entity["device_id"] for entity in entities if entity.get("device_id")}
    blacklist_devices = set(blacklist.get("devices", []))

    devices: List[Dict[str, object]] = []
    for device in device_registry:
        device_id = device.get("id")
        if not device_id or device_id not in allowed_devices:
            continue
        if device_id in blacklist_devices:
            continue
        identifiers_raw = device.get("identifiers") or []
        identifiers: List[object] = []
        for identifier in identifiers_raw:
            if isinstance(identifier, (set, tuple)):
                identifiers.append(list(identifier))
            else:
                identifiers.append(identifier)
        devices.append(
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
            }
        )

    repository.save_entities(entities, devices)
    return EntitiesResponse(entities=entities, devices=devices)


@app.get("/api/entities", response_model=EntitiesResponse)
async def get_entities() -> EntitiesResponse:
    data = repository.get_entities()
    return EntitiesResponse(entities=data.get("entities", []), devices=data.get("devices", []))


@app.post("/api/entities/ingest", response_model=EntitiesResponse)
async def ingest_entities() -> EntitiesResponse:
    return await _ingest_entities()


@app.post("/api/entities/refresh", response_model=EntitiesResponse, include_in_schema=False)
async def refresh_entities() -> EntitiesResponse:
    return await _ingest_entities()
