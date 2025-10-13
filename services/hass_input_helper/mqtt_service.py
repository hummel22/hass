from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from threading import Event
from typing import Any, Optional
from uuid import uuid4

from paho.mqtt import client as mqtt_client

from .models import HelperType, InputHelper, InputValue, MQTTConfig


class MQTTError(RuntimeError):
    """Raised when the MQTT broker rejects an operation."""


logger = logging.getLogger(__name__)

DEFAULT_DISCOVERY_PREFIX = "homeassistant"


def _build_client(config: MQTTConfig, *, suffix: Optional[str] = None) -> mqtt_client.Client:
    client_id = config.client_id or f"hass-input-helper-{uuid4().hex[:8]}"
    if suffix:
        client_id = f"{client_id}-{suffix}"
    client = mqtt_client.Client(client_id=client_id, clean_session=True)
    if config.username:
        client.username_pw_set(config.username, config.password or "")
    if config.use_tls:
        client.tls_set()
    logger.debug(
        "Prepared MQTT client",
        extra={
            "mqtt_client_id": client_id,
            "mqtt_use_tls": config.use_tls,
            "mqtt_username_present": bool(config.username),
        },
    )
    return client


def verify_connection(config: MQTTConfig, *, timeout: float = 5.0) -> None:
    """Attempt to connect to the MQTT broker to verify credentials."""

    client = _build_client(config, suffix="probe")
    event = Event()
    result = {"rc": None}
    loop_started = False

    def on_connect(client: mqtt_client.Client, userdata, flags, rc):  # type: ignore[no-redef]
        result["rc"] = rc
        event.set()

    client.on_connect = on_connect

    try:
        logger.info(
            "Probing MQTT broker",
            extra={
                "mqtt_host": config.host,
                "mqtt_port": config.port,
                "mqtt_use_tls": config.use_tls,
                "mqtt_username_present": bool(config.username),
            },
        )
        rc = client.connect(config.host, config.port, keepalive=30)
        if rc != 0:
            raise MQTTError(f"MQTT broker rejected the connection (code {rc}).")
        client.loop_start()
        loop_started = True
        event.wait(timeout)
    finally:
        if loop_started:
            client.loop_stop()
        client.disconnect()

    rc = result["rc"]
    if rc is None:
        logger.warning(
            "MQTT broker probe timed out",
            extra={
                "mqtt_host": config.host,
                "mqtt_port": config.port,
                "mqtt_timeout": timeout,
            },
        )
        raise MQTTError("Timed out while waiting for a response from the MQTT broker.")
    logger.info(
        "MQTT broker probe completed",
        extra={
            "mqtt_host": config.host,
            "mqtt_port": config.port,
            "mqtt_return_code": rc,
        },
    )


def _state_topic(config: MQTTConfig, helper: InputHelper) -> str:
    topic_prefix = config.topic_prefix.rstrip("/") or "homeassistant/input_helper"
    return f"{topic_prefix}/{helper.slug}"


def _availability_topic(config: MQTTConfig, helper: InputHelper) -> str:
    topic_prefix = config.topic_prefix.rstrip("/") or "homeassistant/input_helper"
    return f"{topic_prefix}/{helper.slug}/availability"


def _publish(
    config: MQTTConfig,
    topic: str,
    payload: str,
    *,
    retain: bool = False,
    timeout: float = 5.0,
) -> None:
    client = _build_client(config, suffix="publisher")

    info = None
    loop_started = False

    try:
        logger.info(
            "Connecting to MQTT broker for publish",
            extra={
                "mqtt_host": config.host,
                "mqtt_port": config.port,
                "mqtt_topic": topic,
                "mqtt_use_tls": config.use_tls,
                "mqtt_retain": retain,
            },
        )
        rc = client.connect(config.host, config.port, keepalive=30)
        if rc != 0:
            raise MQTTError(f"MQTT broker rejected the connection (code {rc}).")
        client.loop_start()
        loop_started = True
        info = client.publish(topic, payload, qos=0, retain=retain)
        info.wait_for_publish(timeout=timeout)
    finally:
        if loop_started:
            client.loop_stop()
        client.disconnect()

    if info is None or info.rc != mqtt_client.MQTT_ERR_SUCCESS:
        raise MQTTError(
            f"Failed to publish value to MQTT (code {getattr(info, 'rc', 'unknown')})."
        )
    logger.info(
        "Published payload to MQTT",
        extra={
            "mqtt_topic": topic,
            "mqtt_payload_length": len(payload),
            "mqtt_publish_code": info.rc if info is not None else None,
        },
    )


def publish_value(
    config: MQTTConfig,
    helper: InputHelper,
    value: InputValue,
    measured_at: datetime,
    *,
    timeout: float = 5.0,
) -> None:
    """Publish an updated helper value to the configured MQTT topic."""

    measured_iso = measured_at.astimezone(timezone.utc).isoformat()
    payload = json.dumps(
        {
            "entity_id": helper.entity_id,
            "value": value,
            "measured_at": measured_iso,
            "device_class": helper.device_class,
            "unit_of_measurement": helper.unit_of_measurement,
            "helper_type": helper.helper_type.value,
        },
        default=str,
    )

    topic = _state_topic(config, helper)
    _publish(config, topic, payload, retain=False, timeout=timeout)


def _discovery_topic(helper: InputHelper, discovery_prefix: str = DEFAULT_DISCOVERY_PREFIX) -> str:
    sanitized_prefix = discovery_prefix.strip("/") or DEFAULT_DISCOVERY_PREFIX
    return f"{sanitized_prefix}/sensor/{helper.slug}/config"


def _value_template(helper: InputHelper) -> str:
    if helper.helper_type == HelperType.INPUT_NUMBER:
        return "{{ value_json.value | float }}"
    if helper.helper_type == HelperType.INPUT_BOOLEAN:
        return "{{ value_json.value | lower }}"
    return "{{ value_json.value }}"


def _state_class(helper: InputHelper) -> Optional[str]:
    if helper.helper_type == HelperType.INPUT_NUMBER:
        return "measurement"
    return None


def publish_discovery_config(
    config: MQTTConfig,
    helper: InputHelper,
    *,
    discovery_prefix: str = DEFAULT_DISCOVERY_PREFIX,
    timeout: float = 5.0,
) -> None:
    """Publish a retained MQTT discovery payload for Home Assistant."""

    state_topic = _state_topic(config, helper)
    availability_topic = _availability_topic(config, helper)
    payload: dict[str, Any] = {
        "name": helper.name,
        "uniq_id": helper.slug,
        "stat_t": state_topic,
        "val_tpl": _value_template(helper),
        "json_attr_t": state_topic,
        "json_attr_tpl": "{{ {'measured_at': value_json.measured_at} | tojson }}",
        "avty_t": availability_topic,
        "pl_avail": "online",
        "pl_not_avail": "offline",
        "dev": {
            "identifiers": [f"hass_input_helper:{helper.slug}"],
            "manufacturer": "HASS Input Helper",
            "model": helper.helper_type.value.replace("_", " ").title(),
            "name": helper.name,
            "sw_version": "1.0.0",
        },
    }

    if helper.device_class:
        payload["dev_cla"] = helper.device_class
    if helper.unit_of_measurement:
        payload["unit_of_meas"] = helper.unit_of_measurement

    state_class = _state_class(helper)
    if state_class:
        payload["stat_cla"] = state_class

    topic = _discovery_topic(helper, discovery_prefix)
    logger.info(
        "Publishing MQTT discovery payload",
        extra={
            "mqtt_topic": topic,
            "mqtt_state_topic": state_topic,
            "mqtt_device_class": payload.get("dev_cla"),
            "mqtt_unit": payload.get("unit_of_meas"),
        },
    )
    _publish(config, topic, json.dumps(payload), retain=True, timeout=timeout)


def publish_availability(
    config: MQTTConfig,
    helper: InputHelper,
    available: bool,
    *,
    timeout: float = 5.0,
) -> None:
    topic = _availability_topic(config, helper)
    payload = "online" if available else "offline"
    logger.info(
        "Publishing MQTT availability",
        extra={
            "mqtt_topic": topic,
            "mqtt_payload": payload,
            "mqtt_helper_slug": helper.slug,
        },
    )
    _publish(config, topic, payload, retain=True, timeout=timeout)


def clear_discovery_config(
    config: MQTTConfig,
    helper: InputHelper,
    *,
    discovery_prefix: str = DEFAULT_DISCOVERY_PREFIX,
    timeout: float = 5.0,
) -> None:
    """Remove the retained MQTT discovery payload for a helper."""

    topic = _discovery_topic(helper, discovery_prefix)
    logger.info(
        "Clearing MQTT discovery payload",
        extra={
            "mqtt_topic": topic,
            "mqtt_helper_slug": helper.slug,
        },
    )
    _publish(config, topic, "", retain=True, timeout=timeout)


__all__ = [
    "MQTTError",
    "clear_discovery_config",
    "publish_availability",
    "publish_discovery_config",
    "publish_value",
    "verify_connection",
]
