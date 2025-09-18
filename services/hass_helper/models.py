"""Pydantic models used by the hass_helper API."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class DomainEntry(BaseModel):
    domain: str = Field(..., description="Home Assistant domain identifier")
    title: Optional[str] = Field(None, description="Human readable name")


class DomainSelectionRequest(BaseModel):
    domain: str = Field(..., description="Domain to include during ingest")


class EntitiesIngestResponse(BaseModel):
    devices: List[Dict[str, Any]]


class BlacklistEntryRequest(BaseModel):
    target_type: Literal["entity", "device"]
    target_id: str


class WhitelistEntryRequest(BaseModel):
    entity_id: str


class MessageResponse(BaseModel):
    message: str


class EntityRecord(BaseModel):
    entity_id: str
    name: Optional[str] = None
    original_name: Optional[str] = None
    device_id: Optional[str] = None
    area_id: Optional[str] = None
    unique_id: Optional[str] = None
    integration_id: Optional[str] = None
    state: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    disabled_by: Optional[str] = None


class DeviceRecord(BaseModel):
    id: str
    name: Optional[str] = None
    name_by_user: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    sw_version: Optional[str] = None
    configuration_url: Optional[str] = None
    area_id: Optional[str] = None
    via_device_id: Optional[str] = None
    identifiers: List[Any] = Field(default_factory=list)
    integration_id: Optional[str] = None


class DeviceEntitiesRecord(DeviceRecord):
    entities: List[EntityRecord] = Field(default_factory=list)


class EntitiesResponse(BaseModel):
    entities: List[EntityRecord]
    devices: List[DeviceEntitiesRecord]


class BlacklistResponse(BaseModel):
    entities: List[str]
    devices: List[str]


class WhitelistResponse(BaseModel):
    entities: List[str]
