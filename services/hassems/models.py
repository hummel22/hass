from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator


class SetValueRequest(BaseModel):
    value: Any
    measured_at: Optional[datetime] = None


class EntityTransportType(str, Enum):
    MQTT = "mqtt"
    HASSEMS = "hassems"


class HelperType(str, Enum):
    INPUT_TEXT = "input_text"
    INPUT_NUMBER = "input_number"
    INPUT_BOOLEAN = "input_boolean"
    INPUT_SELECT = "input_select"


class HASSEMSStatisticsMode(str, Enum):
    LINEAR = "linear"
    STEP = "step"


InputValue = Union[str, float, bool]


_slug_pattern = re.compile(r"[^a-z0-9-]+")
_identifier_pattern = re.compile(r"[^a-z0-9_]+")
_entity_pattern = re.compile(r"^[a-zA-Z_]+\.[a-zA-Z0-9_]+$")
_topic_segment_pattern = re.compile(r"^[A-Za-z0-9_-]+$")


def slugify(value: str) -> str:
    slug = value.strip().lower().replace(" ", "-")
    slug = _slug_pattern.sub("-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    return slug or "helper"


def slugify_identifier(value: str) -> str:
    slug = value.strip().lower().replace(" ", "_")
    slug = _identifier_pattern.sub("_", slug)
    slug = re.sub(r"_+", "_", slug)
    slug = slug.strip("_")
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
    type: HelperType
    entity_type: EntityTransportType = EntityTransportType.MQTT
    description: Optional[str] = Field(default=None, max_length=512)
    default_value: Optional[InputValue] = None
    options: Optional[List[str]] = None
    device_class: Optional[str] = Field(default=None, max_length=120)
    unit_of_measurement: Optional[str] = Field(default=None, max_length=64)
    component: str = Field(default="sensor", min_length=1, max_length=64)
    unique_id: str = Field(..., min_length=1, max_length=120)
    object_id: str = Field(..., min_length=1, max_length=120)
    node_id: Optional[str] = Field(default=None, max_length=120)
    state_topic: Optional[str] = Field(default=None, max_length=255)
    availability_topic: Optional[str] = Field(default=None, max_length=255)
    icon: Optional[str] = Field(default=None, max_length=120)
    state_class: Optional[str] = Field(default=None, max_length=64)
    force_update: bool = True
    device_name: str = Field(..., min_length=1, max_length=120)
    device_id: str = Field(..., min_length=1, max_length=120)
    device_manufacturer: Optional[str] = Field(default=None, max_length=120)
    device_model: Optional[str] = Field(default=None, max_length=120)
    device_sw_version: Optional[str] = Field(default=None, max_length=64)
    device_identifiers: List[str] = Field(default_factory=list)
    statistics_mode: Optional[HASSEMSStatisticsMode] = Field(
        default=HASSEMSStatisticsMode.LINEAR
    )

    @field_validator("entity_id")
    @classmethod
    def ensure_entity_matches_type(cls, v: str, info: Field.ValidationInfo) -> str:  # type: ignore[name-defined]
        helper_type = info.data.get("type")
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

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, v: str) -> str:
        cleaned = clean_topic_segment(v)
        if not cleaned:
            raise ValueError("Provide a valid device ID (letters, numbers, underscores, hyphens).")
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
    def validate_topics(
        cls, v: Optional[str], info: Field.ValidationInfo
    ) -> Optional[str]:  # type: ignore[name-defined]
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            return None
        return clean_topic_path(cleaned)

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

    @field_validator("statistics_mode")
    @classmethod
    def validate_statistics_mode(
        cls, v: Optional[HASSEMSStatisticsMode] | str | None
    ) -> Optional[HASSEMSStatisticsMode]:
        if v in (None, ""):
            return None
        if isinstance(v, HASSEMSStatisticsMode):
            return v
        try:
            return HASSEMSStatisticsMode(str(v))
        except ValueError as exc:
            raise ValueError("Statistics mode must be 'linear' or 'step'.") from exc

    @field_validator("options")
    @classmethod
    def clean_options(cls, v: Optional[List[str]], info: Field.ValidationInfo) -> Optional[List[str]]:  # type: ignore[name-defined]
        if v is None:
            return None
        helper_type = info.data.get("type")
        if helper_type != HelperType.INPUT_SELECT:
            return None
        cleaned = [str(item) for item in v if str(item).strip()]
        if not cleaned:
            raise ValueError("Select helpers must have at least one option.")
        return cleaned

    @field_validator("default_value")
    @classmethod
    def validate_default_value(cls, v: Optional[InputValue], info: Field.ValidationInfo) -> Optional[InputValue]:  # type: ignore[name-defined]
        helper_type = info.data.get("type")
        options = info.data.get("options")
        if v is None or helper_type is None:
            return v
        return coerce_helper_value(helper_type, v, options)

    @model_validator(mode="after")
    def enforce_transport_requirements(self) -> "InputHelperBase":
        try:
            entity_type = (
                self.entity_type
                if isinstance(self.entity_type, EntityTransportType)
                else EntityTransportType(str(self.entity_type))
            )
        except ValueError:
            entity_type = EntityTransportType.MQTT

        if entity_type == EntityTransportType.MQTT:
            if not self.state_topic:
                raise ValueError("MQTT helpers require a state topic.")
            if not self.availability_topic:
                raise ValueError("MQTT helpers require an availability topic.")
            self.node_id = self.node_id or "hassems"
            self.force_update = bool(self.force_update)
            if not self.device_manufacturer:
                self.device_manufacturer = "HASSEMS"
            identifiers = [
                str(item).strip()
                for item in (self.device_identifiers or [])
                if str(item).strip()
            ]
            if not identifiers and self.unique_id:
                base_identifier = f"{self.node_id or 'hassems'}:{self.unique_id}"
                identifiers = [base_identifier]
            self.device_identifiers = identifiers
            self.statistics_mode = None
        else:
            self.node_id = None
            self.state_topic = None
            self.availability_topic = None
            self.force_update = False
            self.device_manufacturer = None
            self.device_model = None
            self.device_sw_version = None
            self.device_identifiers = []
            if not self.statistics_mode:
                self.statistics_mode = HASSEMSStatisticsMode.LINEAR

        return self


class InputHelperCreate(InputHelperBase):
    @model_validator(mode="before")
    @classmethod
    def autofill_identifiers(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values

        data = dict(values)
        raw_name = str(data.get("name") or "").strip()
        raw_device_name = str(data.get("device_name") or "").strip()

        device_input = data.get("device_id")
        if device_input:
            device_id = slugify_identifier(str(device_input))
        elif raw_device_name:
            device_id = slugify_identifier(raw_device_name)
        else:
            device_id = None
        if device_id:
            data["device_id"] = device_id

        name_slug = slugify_identifier(raw_name) if raw_name else None

        unique_input = data.get("unique_id")
        if unique_input:
            unique_id = slugify_identifier(str(unique_input))
        elif device_id and name_slug:
            unique_id = slugify_identifier(f"{device_id}_{name_slug}")
        elif name_slug:
            unique_id = name_slug
        else:
            unique_id = None
        if unique_id:
            data["unique_id"] = unique_id

        object_input = data.get("object_id")
        if object_input:
            object_id = slugify_identifier(str(object_input))
        elif unique_id:
            object_id = unique_id
        else:
            object_id = None
        if object_id:
            data["object_id"] = object_id

        helper_type = data.get("type")
        if isinstance(helper_type, HelperType):
            helper_domain = helper_type.value
        else:
            helper_domain = str(helper_type).strip() if helper_type else ""

        if helper_domain:
            device_slug = slugify_identifier(raw_device_name)
            slug_parts = [part for part in (device_slug, name_slug) if part]
            if slug_parts:
                candidate_slug = "_".join(slug_parts)
                entity_id = f"{helper_domain}.{candidate_slug}"
                existing = str(data.get("entity_id") or "").strip()
                if not existing:
                    data["entity_id"] = entity_id

        entity_id_value = str(data.get("entity_id") or "").strip()
        entity_type_value = data.get("entity_type") or EntityTransportType.MQTT
        try:
            entity_type = (
                entity_type_value
                if isinstance(entity_type_value, EntityTransportType)
                else EntityTransportType(str(entity_type_value))
            )
        except ValueError:
            entity_type = EntityTransportType.MQTT

        if entity_type == EntityTransportType.MQTT:
            node_id_input = data.get("node_id")
            node_segment = (
                slugify_identifier(str(node_id_input)) if node_id_input else "hassems"
            )
            data["node_id"] = node_segment

            topic_segment: Optional[str] = name_slug
            if not topic_segment and entity_id_value:
                entity_suffix = entity_id_value.split(".", 1)[-1]
                topic_segment = slugify_identifier(entity_suffix)

            if device_id and topic_segment:
                base_topic = f"{node_segment}/{device_id}/{topic_segment}"
                if not str(data.get("state_topic") or "").strip():
                    data["state_topic"] = f"{base_topic}/state"
                if not str(data.get("availability_topic") or "").strip():
                    data["availability_topic"] = f"{base_topic}/availability"

            identifiers = data.get("device_identifiers")
            if not identifiers and device_id and unique_id:
                data["device_identifiers"] = [f"{node_segment}:{unique_id}"]
            data["force_update"] = bool(data.get("force_update", True))
        else:
            data["node_id"] = None
            data["state_topic"] = None
            data["availability_topic"] = None
            data["force_update"] = False
            data["device_identifiers"] = []
            data["device_manufacturer"] = None
            data["device_model"] = None
            data["device_sw_version"] = None

        return data


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
    device_id: Optional[str] = Field(default=None, min_length=1, max_length=120)
    device_manufacturer: Optional[str] = Field(default=None, max_length=120)
    device_model: Optional[str] = Field(default=None, max_length=120)
    device_sw_version: Optional[str] = Field(default=None, max_length=64)
    device_identifiers: Optional[List[str]] = None
    statistics_mode: Optional[HASSEMSStatisticsMode] = None

    model_config = {"extra": "forbid"}

    @field_validator("entity_id")
    @classmethod
    def validate_entity_id(cls, v: Optional[str], info: Field.ValidationInfo) -> Optional[str]:  # type: ignore[name-defined]
        if v is None:
            return None
        helper_type = info.data.get("type")
        if helper_type is None:
            return v
        return _validate_entity_id(helper_type, v)

    @field_validator("component")
    @classmethod
    def validate_component(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return clean_topic_segment(v)

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = clean_topic_segment(v)
        if not cleaned:
            raise ValueError("Provide a valid device ID (letters, numbers, underscores, hyphens).")
        return cleaned

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

    @field_validator("statistics_mode")
    @classmethod
    def validate_statistics_mode_update(
        cls, v: Optional[HASSEMSStatisticsMode] | str | None
    ) -> Optional[HASSEMSStatisticsMode]:
        if v in (None, ""):
            return None
        if isinstance(v, HASSEMSStatisticsMode):
            return v
        try:
            return HASSEMSStatisticsMode(str(v))
        except ValueError as exc:
            raise ValueError("Statistics mode must be 'linear' or 'step'.") from exc

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
    type: HelperType
    entity_type: EntityTransportType = EntityTransportType.MQTT
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
    state_topic: Optional[str] = None
    availability_topic: Optional[str] = None
    icon: Optional[str] = None
    state_class: Optional[str] = None
    force_update: bool
    device_name: str
    device_id: str
    device_manufacturer: Optional[str] = None
    device_model: Optional[str] = None
    device_sw_version: Optional[str] = None
    device_identifiers: List[str] = Field(default_factory=list)
    statistics_mode: Optional[HASSEMSStatisticsMode] = None
    history_cursor: Optional[str] = None
    history_changed_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class HistoryPoint(BaseModel):
    id: int
    measured_at: datetime
    recorded_at: datetime
    value: InputValue


class HistoryPointUpdate(BaseModel):
    value: InputValue
    measured_at: Optional[datetime] = None


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


class ApiUserBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Provide a descriptive name for the API user.")
        return cleaned


class ApiUserCreate(ApiUserBase):
    token: str = Field(..., min_length=8, max_length=255)

    @field_validator("token")
    @classmethod
    def strip_token(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("API tokens must contain at least one non-space character.")
        return cleaned


class ApiUserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    token: Optional[str] = Field(default=None, min_length=8, max_length=255)

    @field_validator("name")
    @classmethod
    def validate_optional_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Provide a descriptive name for the API user.")
        return cleaned

    @field_validator("token")
    @classmethod
    def validate_optional_token(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("API tokens must contain at least one non-space character.")
        return cleaned

    @model_validator(mode="after")
    def ensure_updates_present(self) -> "ApiUserUpdate":
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update.")
        return self


class ApiUser(ApiUserBase):
    id: int
    token: str
    is_superuser: bool = False
    created_at: datetime
    updated_at: datetime


class WebhookRegistration(BaseModel):
    description: Optional[str] = Field(default=None, max_length=255)
    webhook_url: AnyHttpUrl
    secret: Optional[str] = Field(default=None, max_length=255)
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("secret")
    @classmethod
    def strip_secret(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class WebhookSubscription(WebhookRegistration):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


class IntegrationConnectionOwner(BaseModel):
    id: int
    name: str
    is_superuser: bool = False


class IntegrationConnectionBase(BaseModel):
    entry_id: str = Field(..., min_length=1, max_length=120)
    title: Optional[str] = Field(default=None, max_length=255)
    helper_count: int = Field(default=0, ge=0)
    included_helpers: Optional[List[str]] = None
    ignored_helpers: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("entry_id")
    @classmethod
    def strip_entry_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Provide a valid config entry id.")
        return cleaned

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("included_helpers", "ignored_helpers")
    @classmethod
    def normalise_helper_list(
        cls, value: Optional[List[str]]
    ) -> Optional[List[str]]:
        if not value:
            return None
        cleaned = []
        seen = set()
        for item in value:
            text = str(item).strip()
            if not text:
                continue
            if text in seen:
                continue
            seen.add(text)
            cleaned.append(text)
        return cleaned or None


class IntegrationConnectionCreate(IntegrationConnectionBase):
    last_seen: Optional[datetime] = None


class IntegrationConnectionDetail(IntegrationConnectionBase):
    id: int
    api_user_id: int
    owner: IntegrationConnectionOwner
    created_at: datetime
    updated_at: datetime
    last_seen: Optional[datetime] = None


class IntegrationConnectionSummary(IntegrationConnectionDetail):
    metadata: Optional[Dict[str, Any]] = None


class IntegrationConnectionHistoryItem(BaseModel):
    helper_slug: str
    helper_name: str
    value: Any
    measured_at: Optional[datetime] = None
    recorded_at: datetime


@dataclass
class InputHelperRecord:
    helper: InputHelper

    @classmethod
    def create(cls, payload: InputHelperCreate) -> "InputHelperRecord":
        now = datetime.now(timezone.utc)
        is_mqtt = payload.entity_type == EntityTransportType.MQTT
        node_id = payload.node_id or ("hassems" if is_mqtt else None)
        object_id = payload.object_id or slugify_identifier(payload.unique_id)
        device_id = payload.device_id or slugify_identifier(payload.device_name)
        identifiers = payload.device_identifiers or []
        if is_mqtt:
            if not identifiers:
                base_identifier = f"{node_id or 'hassems'}:{payload.unique_id}"
                identifiers = [base_identifier]
        else:
            identifiers = []
        state_topic = payload.state_topic if is_mqtt else None
        availability_topic = payload.availability_topic if is_mqtt else None
        force_update = bool(payload.force_update) if is_mqtt else False
        device_manufacturer = payload.device_manufacturer if is_mqtt else None
        device_model = payload.device_model if is_mqtt else None
        device_sw_version = payload.device_sw_version if is_mqtt else None
        statistics_mode = (
            payload.statistics_mode
            if payload.entity_type == EntityTransportType.HASSEMS
            else None
        )
        history_cursor = (
            secrets.token_hex(16)
            if payload.entity_type == EntityTransportType.HASSEMS
            else None
        )

        helper = InputHelper(
            slug=slugify(payload.unique_id),
            name=payload.name,
            entity_id=payload.entity_id,
            type=payload.type,
            entity_type=payload.entity_type,
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
            state_topic=state_topic,
            availability_topic=availability_topic,
            icon=payload.icon,
            state_class=payload.state_class,
            force_update=force_update,
            device_name=payload.device_name,
            device_id=device_id,
            device_manufacturer=device_manufacturer,
            device_model=device_model,
            device_sw_version=device_sw_version,
            device_identifiers=identifiers,
            statistics_mode=statistics_mode,
            history_cursor=history_cursor,
            history_changed_at=None,
        )
        return cls(helper=helper)

    def update(self, payload: InputHelperUpdate) -> None:
        data = self.helper.model_dump()
        helper_type = self.helper.type
        options = self.helper.options
        update_data = payload.model_dump(exclude_unset=True)
        data["entity_type"] = self.helper.entity_type
        is_mqtt = self.helper.entity_type == EntityTransportType.MQTT

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
            data["unique_id"] = slugify_identifier(payload.unique_id)
        if "object_id" in update_data and payload.object_id:
            data["object_id"] = slugify_identifier(payload.object_id)
        if is_mqtt and "node_id" in update_data:
            data["node_id"] = payload.node_id
        if is_mqtt and "state_topic" in update_data and payload.state_topic:
            data["state_topic"] = payload.state_topic
        if is_mqtt and "availability_topic" in update_data and payload.availability_topic:
            data["availability_topic"] = payload.availability_topic
        if "icon" in update_data:
            data["icon"] = payload.icon
        if "state_class" in update_data:
            data["state_class"] = payload.state_class
        if is_mqtt and "force_update" in update_data and payload.force_update is not None:
            data["force_update"] = bool(payload.force_update)
        if "device_name" in update_data and payload.device_name:
            data["device_name"] = payload.device_name
        if "device_id" in update_data and payload.device_id:
            data["device_id"] = slugify_identifier(payload.device_id)
        if is_mqtt and "device_manufacturer" in update_data:
            data["device_manufacturer"] = payload.device_manufacturer
        if is_mqtt and "device_model" in update_data:
            data["device_model"] = payload.device_model
        if is_mqtt and "device_sw_version" in update_data:
            data["device_sw_version"] = payload.device_sw_version
        if is_mqtt and "device_identifiers" in update_data and payload.device_identifiers is not None:
            cleaned_identifiers = [
                ident for ident in payload.device_identifiers if ident.strip()
            ]
            if cleaned_identifiers or payload.device_identifiers == []:
                data["device_identifiers"] = cleaned_identifiers
            else:
                data["device_identifiers"] = data.get("device_identifiers", [])
        if "statistics_mode" in update_data:
            if self.helper.entity_type != EntityTransportType.HASSEMS:
                raise ValueError("Statistics mode is only available for HASSEMS helpers.")
            mode = payload.statistics_mode or HASSEMSStatisticsMode.LINEAR
            data["statistics_mode"] = mode
        if helper_type == HelperType.INPUT_SELECT:
            data["options"] = options
        data["last_value"] = data.get("last_value")
        data["updated_at"] = datetime.now(timezone.utc)

        if not is_mqtt:
            data["node_id"] = None
            data["state_topic"] = None
            data["availability_topic"] = None
            data["force_update"] = False
            data["device_manufacturer"] = None
            data["device_model"] = None
            data["device_sw_version"] = None
            data["device_identifiers"] = []
            data["statistics_mode"] = data.get("statistics_mode") or HASSEMSStatisticsMode.LINEAR

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
    "EntityTransportType",
    "HASSEMSStatisticsMode",
    "InputHelper",
    "InputHelperCreate",
    "InputHelperRecord",
    "InputHelperUpdate",
    "InputValue",
    "HistoryPoint",
    "HistoryPointUpdate",
    "MQTTConfig",
    "MQTTTestResponse",
    "SetValueRequest",
    "coerce_helper_value",
    "slugify",
]
