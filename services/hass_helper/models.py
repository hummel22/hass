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
    friendly_name: Optional[str] = None
    object_id: Optional[str] = None
    device: Optional[str] = None
    area: Optional[str] = None
    integration_id: Optional[str] = None
    unit_of_measurement: Optional[str] = None
    native_unit_of_measurement: Optional[str] = None
    device_class: Optional[str] = None
    state_class: Optional[str] = None
    icon: Optional[str] = None
    last_changed: Optional[str] = None
    entity_category: Optional[str] = None
    disabled_by: Optional[str] = None

    class Config:
        extra = "allow"


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


class MQTTConfig(BaseModel):
    host: str = Field(..., description="MQTT broker hostname")
    port: int = Field(1883, ge=1, le=65535, description="MQTT broker port")
    username: Optional[str] = Field(None, description="MQTT username")
    password: Optional[str] = Field(None, description="MQTT password")
    client_id: Optional[str] = Field(None, description="MQTT client identifier")
    topic_prefix: Optional[str] = Field(None, description="Topic prefix for entity publications")


class MQTTConfigResponse(MQTTConfig):
    pass


class MQTTTestRequest(MQTTConfig):
    pass


class MQTTTestResponse(BaseModel):
    success: bool
    message: str


class ManagedEntity(BaseModel):
    entity_id: str
    name: Optional[str] = None
    unit_of_measurement: Optional[str] = None
    device_class: Optional[str] = None
    state_class: Optional[str] = None
    icon: Optional[str] = None
    data_type: Optional[str] = None
    topic: Optional[str] = None
    description: Optional[str] = None
    last_value: Optional[str] = None
    last_updated: Optional[str] = None


class EntityCreateRequest(BaseModel):
    entity_id: str = Field(..., description="Unique Home Assistant entity identifier")
    name: str = Field(..., description="Friendly entity name")
    unit_of_measurement: Optional[str] = Field(
        None, description="Measurement unit presented in Home Assistant"
    )
    device_class: Optional[str] = Field(None, description="Home Assistant device class")
    state_class: Optional[str] = Field(None, description="Home Assistant state class")
    icon: Optional[str] = Field(None, description="Material Design icon name")
    data_type: Optional[str] = Field(None, description="Expected data type (e.g. number, text)")
    topic: Optional[str] = Field(None, description="Custom MQTT topic for this entity")
    description: Optional[str] = Field(None, description="Optional notes about the entity")


class EntityUpdateRequest(BaseModel):
    entity_id: Optional[str] = Field(
        None,
        description="Updated Home Assistant entity identifier",
    )
    name: Optional[str] = Field(None, description="Friendly entity name")
    unit_of_measurement: Optional[str] = Field(
        None, description="Measurement unit presented in Home Assistant"
    )
    device_class: Optional[str] = Field(None, description="Home Assistant device class")
    state_class: Optional[str] = Field(None, description="Home Assistant state class")
    icon: Optional[str] = Field(None, description="Material Design icon name")
    data_type: Optional[str] = Field(None, description="Expected data type")
    topic: Optional[str] = Field(None, description="Custom MQTT topic for this entity")
    description: Optional[str] = Field(None, description="Optional notes about the entity")


class EntityDataPoint(BaseModel):
    value: str
    recorded_at: str


class EntityDetailResponse(ManagedEntity):
    history: List[EntityDataPoint] = Field(default_factory=list)


class DataPointRequest(BaseModel):
    value: str
