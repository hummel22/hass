from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class SetValueRequest(BaseModel):
    value: Any


class HelperType(str, Enum):
    INPUT_TEXT = "input_text"
    INPUT_NUMBER = "input_number"
    INPUT_BOOLEAN = "input_boolean"
    INPUT_SELECT = "input_select"


InputValue = Union[str, float, bool]


_slug_pattern = re.compile(r"[^a-z0-9-]+")
_entity_pattern = re.compile(r"^[a-zA-Z_]+\.[a-zA-Z0-9_]+$")


def slugify(value: str) -> str:
    slug = value.strip().lower().replace(" ", "-")
    slug = _slug_pattern.sub("-", slug)
    slug = slug.strip("-")
    return slug or "helper"


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

    @field_validator("entity_id")
    @classmethod
    def ensure_entity_matches_type(cls, v: str, info: Field.ValidationInfo) -> str:  # type: ignore[name-defined]
        helper_type = info.data.get("helper_type")
        if helper_type is None:
            return v
        return _validate_entity_id(helper_type, v)

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

    model_config = {"extra": "forbid"}


class InputHelper(BaseModel):
    slug: str
    name: str
    entity_id: str
    helper_type: HelperType
    description: Optional[str] = None
    default_value: Optional[InputValue] = None
    options: Optional[List[str]] = None
    last_value: Optional[InputValue] = None
    created_at: datetime
    updated_at: datetime
    device_class: Optional[str] = None
    unit_of_measurement: Optional[str] = None

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class HistoryPoint(BaseModel):
    timestamp: datetime
    value: InputValue


class MQTTConfig(BaseModel):
    host: str = Field(..., min_length=1)
    port: int = Field(default=1883, ge=1, le=65535)
    username: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = Field(default=None, max_length=255)
    client_id: Optional[str] = Field(default=None, max_length=128)
    topic_prefix: str = Field(default="homeassistant/input_helper", min_length=1)
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
        helper = InputHelper(
            slug=slugify(payload.name),
            name=payload.name,
            entity_id=payload.entity_id,
            helper_type=payload.helper_type,
            description=payload.description,
            default_value=payload.default_value,
            options=payload.options,
            last_value=payload.default_value,
            created_at=now,
            updated_at=now,
            device_class=payload.device_class,
            unit_of_measurement=payload.unit_of_measurement,
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
        if helper_type == HelperType.INPUT_SELECT:
            data["options"] = options
        data["last_value"] = data.get("last_value")
        data["updated_at"] = datetime.now(timezone.utc)

        self.helper = InputHelper(**data)

    def touch_last_value(self, value: InputValue) -> None:
        self.helper = self.helper.model_copy(
            update={"last_value": value, "updated_at": datetime.now(timezone.utc)}
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
