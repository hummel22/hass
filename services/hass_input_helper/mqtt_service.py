from __future__ import annotations

import json
from datetime import datetime, timezone
from threading import Event
from typing import Optional
from uuid import uuid4

from paho.mqtt import client as mqtt_client

from .models import InputHelper, InputValue, MQTTConfig


class MQTTError(RuntimeError):
    """Raised when the MQTT broker rejects an operation."""


def _build_client(config: MQTTConfig, *, suffix: Optional[str] = None) -> mqtt_client.Client:
    client_id = config.client_id or f"hass-input-helper-{uuid4().hex[:8]}"
    if suffix:
        client_id = f"{client_id}-{suffix}"
    client = mqtt_client.Client(client_id=client_id, clean_session=True)
    if config.username:
        client.username_pw_set(config.username, config.password or "")
    if config.use_tls:
        client.tls_set()
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
        raise MQTTError("Timed out while waiting for a response from the MQTT broker.")


def publish_value(config: MQTTConfig, helper: InputHelper, value: InputValue, *, timeout: float = 5.0) -> None:
    """Publish an updated helper value to the configured MQTT topic."""

    client = _build_client(config, suffix="publisher")
    topic_prefix = config.topic_prefix.rstrip("/") or "homeassistant/input_helper"
    topic = f"{topic_prefix}/{helper.slug}"

    payload = json.dumps(
        {
            "entity_id": helper.entity_id,
            "value": value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "device_class": helper.device_class,
            "unit_of_measurement": helper.unit_of_measurement,
            "helper_type": helper.helper_type,
        },
        default=str,
    )

    info = None
    loop_started = False

    try:
        rc = client.connect(config.host, config.port, keepalive=30)
        if rc != 0:
            raise MQTTError(f"MQTT broker rejected the connection (code {rc}).")
        client.loop_start()
        loop_started = True
        info = client.publish(topic, payload, qos=0, retain=False)
        info.wait_for_publish(timeout=timeout)
    finally:
        if loop_started:
            client.loop_stop()
        client.disconnect()

    if info is None or info.rc != mqtt_client.MQTT_ERR_SUCCESS:
        raise MQTTError(f"Failed to publish value to MQTT (code {getattr(info, 'rc', 'unknown')}).")


__all__ = ["MQTTError", "publish_value", "verify_connection"]
