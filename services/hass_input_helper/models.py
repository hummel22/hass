from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class SetValueRequest(BaseModel):
    value: Any
    measured_at: Optional[datetime] = None


class HelperType(str, Enum):
    INPUT_TEXT = "input_text"
    INPUT_NUMBER = "input_number"
    INPUT_BOOLEAN = "input_boolean"
    INPUT_SELECT = "input_select"


InputValue = Union[str, float, bool]


_slug_pattern = re.compile(r"[^a-z0-9-]+")
_entity_pattern = re.compile(r"^[a-zA-Z_]+\.[a-zA-Z0-9_]+$")
_topic_segment_pattern = re.compile(r"^[A-Za-z0-9_-]+$")


def slugify(value: str) -> str:
    slug = value.strip().lower().replace(" ", "-")
    slug = _slug_pattern.sub("-", slug)
    slug = slug.strip("-")
    return slug or "helper"


def clean_topic_segment(value: Optional[str], *, allow_empty: bool = False) -> Optional[str]:
    if value is None:
        if allow_empty:
            return None
        raise ValueError("Provide a valid MQTT topic segment.")
    cleaned = value.strip()
    if not cleaned:
        if allow_empty:
            return ""
        raise ValueError("Provide a valid MQTT topic segment.")
    normalised = cleaned.replace(" ", "_").lower()
    if not _topic_segment_pattern.match(normalised):
        raise ValueError(
            "MQTT topic segments may only contain letters, numbers, underscores, and hyphens."
        )
    return normalised


def clean_topic_path(value: str) -> str:
    cleaned = value.strip().strip("/")
    if not cleaned:
        raise ValueError("Provide a valid MQTT topic path.")
    if " " in cleaned:
        raise ValueError("MQTT topics cannot contain spaces.")
    return cleaned


def _validate_entity_id(helper_type: HelperType, entity_id: str) -> str:
    if not _entity_pattern.match(entity_id):
        raise ValueError("Entity ID must look like 'domain.object_id'.")
    if not entity_id.startswith(f"{helper_type.value}."):
        raise ValueError(
            f"Entity ID '{entity_id}' must start with '{helper_type.value}.' for helper type {helper_type.value}."
        )
    return entity_id


def coerce_helper_value(helper_type: HelperType, value: Any, options: Optional[List[str]] = None) -> InputValue:
    if value is None:
        raise ValueError("Value cannot be null for helper updates.")

    if helper_type == HelperType.INPUT_BOOLEAN:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lower = value.lower()
            if lower in {"true", "on", "1", "yes"}:
                return True
            if lower in {"false", "off", "0", "no"}:
                return False
        raise ValueError("Boolean helpers require a true/false value.")

    if helper_type == HelperType.INPUT_NUMBER:
        try:
            return float(value)
        except (TypeError, ValueError) as exc:  # noqa: PERF203
            raise ValueError("Number helpers require a numeric value.") from exc

    if helper_type == HelperType.INPUT_SELECT:
        if not options:
            raise ValueError("Select helpers must define allowed options.")
        if value not in options:
            raise ValueError(f"Value '{value}' is not one of the allowed options: {options}.")
        return str(value)

    # input_text fallback
    return str(value)


class InputHelperBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    entity_id: str
    helper_type: HelperType
    description: Optional[str] = Field(default=None, max_length=512)
    default_value: Optional[InputValue] = None
    options: Optional[List[str]] = None
    device_class: Optional[str] = Field(default=None, max_length=120)
    unit_of_measurement: Optional[str] = Field(default=None, max_length=64)
    component: str = Field(default="sensor", min_length=1, max_length=64)
    unique_id: str = Field(..., min_length=1, max_length=120)
    object_id: str = Field(..., min_length=1, max_length=120)
    node_id: Optional[str] = Field(default="hassems", max_length=120)
    state_topic: str = Field(..., min_length=1, max_length=255)
    availability_topic: str = Field(..., min_length=1, max_length=255)
    icon: Optional[str] = Field(default=None, max_length=120)
    state_class: Optional[str] = Field(default=None, max_length=64)
    force_update: bool = True
    device_name: str = Field(..., min_length=1, max_length=120)
    device_manufacturer: Optional[str] = Field(default="HASSEMS", max_length=120)
    device_model: Optional[str] = Field(default=None, max_length=120)
    device_sw_version: Optional[str] = Field(default=None, max_length=64)
    device_identifiers: List[str] = Field(default_factory=list)

    @field_validator("entity_id")
    @classmethod
    def ensure_entity_matches_type(cls, v: str, info: Field.ValidationInfo) -> str:  # type: ignore[name-defined]
        helper_type = info.data.get("helper_type")
        if helper_type is None:
            return v
        return _validate_entity_id(helper_type, v)

    @field_validator("component")
    @classmethod
    def validate_component(cls, v: str) -> str:
        return clean_topic_segment(v) or "sensor"

    @field_validator("unique_id", "object_id")
    @classmethod
    def validate_identifiers(cls, v: str) -> str:
        cleaned = clean_topic_segment(v)
        if not cleaned:
            raise ValueError("Provide a valid identifier (letters, numbers, underscores, hyphens).")
        return cleaned

    @field_validator("node_id")
    @classmethod
    def validate_node_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = clean_topic_segment(v, allow_empty=True)
        return cleaned or None

    @field_validator("state_topic", "availability_topic")
    @classmethod
    def validate_topics(cls, v: str) -> str:
        return clean_topic_path(v)

    @field_validator("icon", "device_manufacturer", "device_model", "device_sw_version")
    @classmethod
    def strip_optional(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None

    @field_validator("state_class")
    @classmethod
    def strip_state_class(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None

    @field_validator("device_identifiers")
    @classmethod
    def normalize_identifiers(cls, v: List[str]) -> List[str]:
        cleaned = []
        for item in v or []:
            text = str(item).strip()
            if not text:
                continue
            cleaned.append(text)
        return cleaned

    @field_validator("options")
    @classmethod
    def clean_options(cls, v: Optional[List[str]], info: Field.ValidationInfo) -> Optional[List[str]]:  # type: ignore[name-defined]
        if v is None:
            return None
        helper_type = info.data.get("helper_type")
        if helper_type != HelperType.INPUT_SELECT:
            return None
        cleaned = [str(item) for item in v if str(item).strip()]
        if not cleaned:
            raise ValueError("Select helpers must have at least one option.")
        return cleaned

    @field_validator("default_value")
    @classmethod
    def validate_default_value(cls, v: Optional[InputValue], info: Field.ValidationInfo) -> Optional[InputValue]:  # type: ignore[name-defined]
        helper_type = info.data.get("helper_type")
        options = info.data.get("options")
        if v is None or helper_type is None:
            return v
        return coerce_helper_value(helper_type, v, options)


class InputHelperCreate(InputHelperBase):
    pass


class InputHelperUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    entity_id: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=512)
    default_value: Optional[InputValue] = None
    options: Optional[List[str]] = None
    device_class: Optional[str] = Field(default=None, max_length=120)
    unit_of_measurement: Optional[str] = Field(default=None, max_length=64)
    component: Optional[str] = Field(default=None, min_length=1, max_length=64)
    unique_id: Optional[str] = Field(default=None, min_length=1, max_length=120)
    object_id: Optional[str] = Field(default=None, min_length=1, max_length=120)
    node_id: Optional[str] = Field(default=None, max_length=120)
    state_topic: Optional[str] = Field(default=None, min_length=1, max_length=255)
    availability_topic: Optional[str] = Field(default=None, min_length=1, max_length=255)
    icon: Optional[str] = Field(default=None, max_length=120)
    state_class: Optional[str] = Field(default=None, max_length=64)
    force_update: Optional[bool] = None
    device_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    device_manufacturer: Optional[str] = Field(default=None, max_length=120)
    device_model: Optional[str] = Field(default=None, max_length=120)
    device_sw_version: Optional[str] = Field(default=None, max_length=64)
    device_identifiers: Optional[List[str]] = None

    model_config = {"extra": "forbid"}

    @field_validator("entity_id")
    @classmethod
    def validate_entity_id(cls, v: Optional[str], info: Field.ValidationInfo) -> Optional[str]:  # type: ignore[name-defined]
        if v is None:
            return None
        helper_type = info.data.get("helper_type")
        if helper_type is None:
            return v
        return _validate_entity_id(helper_type, v)

    @field_validator("component")
    @classmethod
    def validate_component(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return clean_topic_segment(v)

    @field_validator("unique_id", "object_id")
    @classmethod
    def validate_identifiers(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = clean_topic_segment(v)
        if not cleaned:
            raise ValueError("Provide a valid identifier (letters, numbers, underscores, hyphens).")
        return cleaned

    @field_validator("node_id")
    @classmethod
    def validate_node_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = clean_topic_segment(v, allow_empty=True)
        return cleaned or None

    @field_validator("state_topic", "availability_topic")
    @classmethod
    def validate_topics(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return clean_topic_path(v)

    @field_validator("icon", "device_manufacturer", "device_model", "device_sw_version")
    @classmethod
    def strip_optional(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None

    @field_validator("state_class")
    @classmethod
    def strip_state_class(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None

    @field_validator("device_identifiers")
    @classmethod
    def normalize_device_identifiers(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        cleaned = [text.strip() for text in v if str(text).strip()]
        return cleaned


class InputHelper(BaseModel):
    slug: str
    name: str
    entity_id: str
    helper_type: HelperType
    description: Optional[str] = None
    default_value: Optional[InputValue] = None
    options: Optional[List[str]] = None
    last_value: Optional[InputValue] = None
    last_measured_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    device_class: Optional[str] = None
    unit_of_measurement: Optional[str] = None
    component: str
    unique_id: str
    object_id: str
    node_id: Optional[str] = None
    state_topic: str
    availability_topic: str
    icon: Optional[str] = None
    state_class: Optional[str] = None
    force_update: bool
    device_name: str
    device_manufacturer: Optional[str] = None
    device_model: Optional[str] = None
    device_sw_version: Optional[str] = None
    device_identifiers: List[str] = Field(default_factory=list)

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class HistoryPoint(BaseModel):
    measured_at: datetime
    recorded_at: datetime
    value: InputValue


class MQTTConfig(BaseModel):
    host: str = Field(..., min_length=1)
    port: int = Field(default=1883, ge=1, le=65535)
    username: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = Field(default=None, max_length=255)
    client_id: Optional[str] = Field(default=None, max_length=128)
    discovery_prefix: str = Field(default="homeassistant", min_length=1)
    use_tls: bool = False


class MQTTTestResponse(BaseModel):
    success: bool
    message: str


@dataclass
class InputHelperRecord:
    helper: InputHelper

    @classmethod
    def create(cls, payload: InputHelperCreate) -> "InputHelperRecord":
        now = datetime.now(timezone.utc)
        node_id = payload.node_id or "hassems"
        object_id = payload.object_id or slugify(payload.unique_id)
        identifiers = payload.device_identifiers or []
        if not identifiers:
            base_identifier = f"{node_id or 'hassems'}:{object_id}"
            identifiers = [base_identifier]
        helper = InputHelper(
            slug=slugify(payload.unique_id),
            name=payload.name,
            entity_id=payload.entity_id,
            helper_type=payload.helper_type,
            description=payload.description,
            default_value=payload.default_value,
            options=payload.options,
            last_value=payload.default_value,
            last_measured_at=now if payload.default_value is not None else None,
            created_at=now,
            updated_at=now,
            device_class=payload.device_class,
            unit_of_measurement=payload.unit_of_measurement,
            component=payload.component,
            unique_id=payload.unique_id,
            object_id=object_id,
            node_id=node_id,
            state_topic=payload.state_topic,
            availability_topic=payload.availability_topic,
            icon=payload.icon,
            state_class=payload.state_class,
            force_update=payload.force_update,
            device_name=payload.device_name,
            device_manufacturer=payload.device_manufacturer,
            device_model=payload.device_model,
            device_sw_version=payload.device_sw_version,
            device_identifiers=identifiers,
        )
        return cls(helper=helper)

    def update(self, payload: InputHelperUpdate) -> None:
        data = self.helper.model_dump()
        helper_type = self.helper.helper_type
        options = self.helper.options
        update_data = payload.model_dump(exclude_unset=True)

        if "options" in update_data:
            if helper_type != HelperType.INPUT_SELECT:
                raise ValueError("Only select helpers accept options.")
            cleaned = [str(item) for item in (payload.options or []) if str(item).strip()]
            if not cleaned:
                raise ValueError("Select helpers must provide at least one option.")
            options = cleaned

        if helper_type == HelperType.INPUT_SELECT and options is None:
            raise ValueError("Select helpers must define options.")

        if "name" in update_data:
            data["name"] = payload.name
        if "entity_id" in update_data:
            data["entity_id"] = _validate_entity_id(helper_type, payload.entity_id)
        if "description" in update_data:
            data["description"] = payload.description
        if "default_value" in update_data:
            default_value = update_data["default_value"]
            if default_value is None:
                data["default_value"] = None
            else:
                data["default_value"] = coerce_helper_value(helper_type, default_value, options)
        if "device_class" in update_data:
            data["device_class"] = payload.device_class
        if "unit_of_measurement" in update_data:
            data["unit_of_measurement"] = payload.unit_of_measurement
        if "component" in update_data and payload.component:
            data["component"] = payload.component
        if "unique_id" in update_data and payload.unique_id:
            data["unique_id"] = payload.unique_id
        if "object_id" in update_data and payload.object_id:
            data["object_id"] = payload.object_id
        if "node_id" in update_data:
            data["node_id"] = payload.node_id
        if "state_topic" in update_data and payload.state_topic:
            data["state_topic"] = payload.state_topic
        if "availability_topic" in update_data and payload.availability_topic:
            data["availability_topic"] = payload.availability_topic
        if "icon" in update_data:
            data["icon"] = payload.icon
        if "state_class" in update_data:
            data["state_class"] = payload.state_class
        if "force_update" in update_data and payload.force_update is not None:
            data["force_update"] = bool(payload.force_update)
        if "device_name" in update_data and payload.device_name:
            data["device_name"] = payload.device_name
        if "device_manufacturer" in update_data:
            data["device_manufacturer"] = payload.device_manufacturer
        if "device_model" in update_data:
            data["device_model"] = payload.device_model
        if "device_sw_version" in update_data:
            data["device_sw_version"] = payload.device_sw_version
        if "device_identifiers" in update_data and payload.device_identifiers is not None:
            cleaned_identifiers = [
                ident for ident in payload.device_identifiers if ident.strip()
            ]
            if cleaned_identifiers or payload.device_identifiers == []:
                data["device_identifiers"] = cleaned_identifiers
            else:
                data["device_identifiers"] = data.get("device_identifiers", [])
        if helper_type == HelperType.INPUT_SELECT:
            data["options"] = options
        data["last_value"] = data.get("last_value")
        data["updated_at"] = datetime.now(timezone.utc)

        self.helper = InputHelper(**data)

    def touch_last_value(self, value: InputValue, measured_at: datetime) -> None:
        now = datetime.now(timezone.utc)
        self.helper = self.helper.model_copy(
            update={
                "last_value": value,
                "last_measured_at": measured_at,
                "updated_at": now,
            }
        )

    def as_dict(self) -> Dict[str, Any]:
        return self.helper.model_dump(mode="json")


class HelperState(BaseModel):
    entity_id: str
    state: str
    last_changed: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "HelperState",
    "HelperType",
    "InputHelper",
    "InputHelperCreate",
    "InputHelperRecord",
    "InputHelperUpdate",
    "InputValue",
    "HistoryPoint",
    "MQTTConfig",
    "MQTTTestResponse",
    "SetValueRequest",
    "coerce_helper_value",
    "slugify",
]
