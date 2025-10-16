from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Header, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .hass_client import HomeAssistantClient
from .models import (
    ApiUser,
    ApiUserCreate,
    ApiUserUpdate,
    EntityTransportType,
    HistoryPoint,
    HistoryPointUpdate,
    EntityState,
    ManagedEntity,
    ManagedEntityCreate,
    ManagedEntityUpdate,
    IntegrationConnectionCreate,
    IntegrationConnectionDetail,
    IntegrationConnectionHistoryItem,
    IntegrationConnectionSummary,
    MQTTConfig,
    MQTTTestResponse,
    SetValueRequest,
    WebhookRegistration,
    WebhookSubscription,
    coerce_entity_value,
)
from .mqtt_service import (
    MQTTError,
    clear_discovery_config,
    publish_availability,
    publish_discovery_config,
    publish_value,
    verify_connection,
)
from .storage import HISTORICAL_THRESHOLD, ManagedEntityStore
from .webhooks import WebhookNotifier

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")
load_dotenv()  # fall back to repo/root .env if present

STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)

DATA_FILE = BASE_DIR / "data" / "managed_entities.db"
store = ManagedEntityStore(DATA_FILE)
SUPERUSER_NAME = "HASSEMS Superuser"
SUPERUSER_TOKEN = "hassems-super-token"
store.ensure_superuser(name=SUPERUSER_NAME, token=SUPERUSER_TOKEN)
notifier = WebhookNotifier(store)
ha_client = HomeAssistantClient.from_env()

app = FastAPI(title="Home Assistant Entity Management System", version="0.2.0")

logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_store() -> ManagedEntityStore:
    return store


def get_client() -> HomeAssistantClient:
    if ha_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Home Assistant client not configured. Provide HASS_BASE_URL and HASS_ACCESS_TOKEN.",
        )
    return ha_client


def get_optional_client() -> Optional[HomeAssistantClient]:
    return ha_client


def require_api_user(
    x_hassems_token: Optional[str] = Header(default=None, alias="X-HASSEMS-Token"),
    authorization: Optional[str] = Header(default=None),
    store: ManagedEntityStore = Depends(get_store),
) -> ApiUser:
    token = (x_hassems_token or "").strip()
    if not token and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            token = value.strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Provide a valid HASSEMS API token in the X-HASSEMS-Token header or an Authorization bearer token.",
        )
    user = store.get_api_user_by_token(token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API token.")
    return user


api_router = APIRouter()


@api_router.get("/health")
def healthcheck() -> dict:
    return {"status": "ok"}


@api_router.get("/config/mqtt", response_model=Optional[MQTTConfig])
def read_mqtt_config(store: ManagedEntityStore = Depends(get_store)) -> Optional[MQTTConfig]:
    config = store.get_mqtt_config()
    if config is None:
        return None
    return config
@api_router.put("/config/mqtt", response_model=MQTTConfig)
def update_mqtt_config(payload: MQTTConfig, store: ManagedEntityStore = Depends(get_store)) -> MQTTConfig:
    return store.save_mqtt_config(payload)
@api_router.post("/config/mqtt/test", response_model=MQTTTestResponse)
async def test_mqtt_config(store: ManagedEntityStore = Depends(get_store)) -> MQTTTestResponse:
    config = store.get_mqtt_config()
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MQTT configuration not found.")

    try:
        logger.info(
            "Received MQTT connection test request",
            extra={
                "mqtt_host": config.host,
                "mqtt_port": config.port,
                "mqtt_use_tls": config.use_tls,
                "mqtt_username_present": bool(config.username),
            },
        )
        await asyncio.to_thread(verify_connection, config)
        return MQTTTestResponse(success=True, message="Successfully connected to the MQTT broker.")
    except MQTTError as exc:
        logger.warning("MQTT connection test failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error during MQTT connection test")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@api_router.get("/users", response_model=List[ApiUser])
def list_api_users(store: ManagedEntityStore = Depends(get_store)) -> List[ApiUser]:
    return store.list_api_users()


@api_router.post("/users", response_model=ApiUser, status_code=status.HTTP_201_CREATED)
def create_api_user(payload: ApiUserCreate, store: ManagedEntityStore = Depends(get_store)) -> ApiUser:
    try:
        return store.create_api_user(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@api_router.post("/users/generate-token")
def generate_api_token() -> Dict[str, str]:
    token = secrets.token_urlsafe(32)
    return {"token": token}


@api_router.put("/users/{user_id}", response_model=ApiUser)
def update_api_user(
    user_id: int,
    payload: ApiUserUpdate,
    store: ManagedEntityStore = Depends(get_store),
) -> ApiUser:
    try:
        return store.update_api_user(user_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@api_router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_api_user(user_id: int, store: ManagedEntityStore = Depends(get_store)) -> Response:
    try:
        store.delete_api_user(user_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@api_router.get("/entities", response_model=List[ManagedEntity])
def list_entities(store: ManagedEntityStore = Depends(get_store)) -> List[ManagedEntity]:
    return store.list_entities()
@api_router.post("/entities", response_model=ManagedEntity, status_code=status.HTTP_201_CREATED)
async def create_entity(
    payload: ManagedEntityCreate,
    store: ManagedEntityStore = Depends(get_store),
) -> ManagedEntity:
    config = store.get_mqtt_config() if payload.entity_type == EntityTransportType.MQTT else None
    if payload.entity_type == EntityTransportType.MQTT and config is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MQTT configuration not provided. Save broker settings before creating entities.",
        )

    try:
        entity = store.create_entity(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if entity.entity_type == EntityTransportType.MQTT and config is not None:
        try:
            await asyncio.to_thread(publish_discovery_config, config, entity)
            await asyncio.to_thread(publish_availability, config, entity, True)
        except MQTTError as exc:
            logger.warning("Failed to publish MQTT discovery payload during entity creation: %s", exc)
            try:
                store.delete_entity(entity.slug)
            except Exception:  # noqa: BLE001
                logger.exception("Unable to roll back entity creation after MQTT failure")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error publishing MQTT discovery payload during entity creation")
            try:
                store.delete_entity(entity.slug)
            except Exception:  # noqa: BLE001
                logger.exception("Unable to roll back entity creation after unexpected MQTT failure")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    if entity.entity_type == EntityTransportType.HASSEMS:
        await notifier.entity_created(entity)
    return entity
@api_router.put("/entities/{slug}", response_model=ManagedEntity)
async def update_entity(
    slug: str,
    payload: ManagedEntityUpdate,
    store: ManagedEntityStore = Depends(get_store),
) -> ManagedEntity:
    if not payload.model_fields_set:
        entity_record = store.get_entity(slug)
        if entity_record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Entity '{slug}' not found.")
        return entity_record.entity

    try:
        entity = store.update_entity(slug, payload)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if entity.entity_type == EntityTransportType.MQTT:
        config = store.get_mqtt_config()
        if config is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MQTT configuration not provided. Save broker settings before updating entities.",
            )

        try:
            await asyncio.to_thread(publish_discovery_config, config, entity)
            await asyncio.to_thread(publish_availability, config, entity, True)
        except MQTTError as exc:
            logger.warning("Failed to publish MQTT discovery payload during entity update: %s", exc)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error publishing MQTT discovery payload during entity update")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    if entity.entity_type == EntityTransportType.HASSEMS:
        await notifier.entity_updated(entity)
    return entity
@api_router.delete(
    "/entities/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_entity(slug: str, store: ManagedEntityStore = Depends(get_store)) -> Response:
    record = store.get_entity(slug)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Entity '{slug}' not found.")

    store.delete_entity(slug)

    if record.entity.entity_type != EntityTransportType.MQTT:
        if record.entity.entity_type == EntityTransportType.HASSEMS:
            await notifier.entity_deleted(record.entity)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    config = store.get_mqtt_config()
    if config is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    try:
        await asyncio.to_thread(publish_availability, config, record.entity, False)
        await asyncio.to_thread(clear_discovery_config, config, record.entity)
    except MQTTError as exc:
        logger.warning("Failed to clear MQTT discovery payload: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error clearing MQTT discovery payload")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@api_router.get("/entities/{slug}/history", response_model=List[HistoryPoint])
def get_entity_history(slug: str, store: ManagedEntityStore = Depends(get_store)) -> List[HistoryPoint]:
    record = store.get_entity(slug)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Entity '{slug}' not found.")
    return store.list_history(slug)


@api_router.put("/entities/{slug}/history/{history_id}", response_model=HistoryPoint)
def update_entity_history_point(
    slug: str,
    history_id: int,
    request: HistoryPointUpdate,
    store: ManagedEntityStore = Depends(get_store),
) -> HistoryPoint:
    record = store.get_entity(slug)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Entity '{slug}' not found.")

    entity = record.entity
    try:
        coerced = coerce_entity_value(entity.type, request.value, entity.options)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    measured_at = request.measured_at
    if measured_at is not None:
        if measured_at.tzinfo is None:
            measured_at = measured_at.replace(tzinfo=timezone.utc)
        else:
            measured_at = measured_at.astimezone(timezone.utc)

    try:
        return store.update_history_point(
            slug,
            history_id,
            HistoryPointUpdate(value=coerced, measured_at=measured_at),
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="History entry not found.") from exc


@api_router.delete("/entities/{slug}/history/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entity_history_point(
    slug: str,
    history_id: int,
    store: ManagedEntityStore = Depends(get_store),
) -> Response:
    record = store.get_entity(slug)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Entity '{slug}' not found.")

    try:
        store.delete_history_point(slug, history_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="History entry not found.") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
@api_router.post("/entities/{slug}/set", response_model=ManagedEntity)
async def set_entity_value(
    slug: str,
    request: SetValueRequest,
    store: ManagedEntityStore = Depends(get_store),
    client: Optional[HomeAssistantClient] = Depends(get_optional_client),
) -> ManagedEntity:
    record = store.get_entity(slug)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Entity '{slug}' not found.")

    try:
        coerced = coerce_entity_value(record.entity.type, request.value, record.entity.options)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    measured_at = request.measured_at or datetime.now(timezone.utc)
    if measured_at.tzinfo is None:
        measured_at = measured_at.replace(tzinfo=timezone.utc)
    measured_at_utc = measured_at.astimezone(timezone.utc)
    cutoff = datetime.now(timezone.utc) - HISTORICAL_THRESHOLD
    is_historic = measured_at_utc <= cutoff

    if client is not None and record.entity.entity_type == EntityTransportType.MQTT:
        try:
            await client.set_entity_value(record.entity, coerced)
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text or exc.response.reason_phrase
            raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc

    if record.entity.entity_type == EntityTransportType.MQTT:
        mqtt_config = store.get_mqtt_config()
        if mqtt_config is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MQTT configuration not provided. Save broker settings before publishing values.",
            )

        try:
            await asyncio.to_thread(publish_value, mqtt_config, record.entity, coerced, measured_at)
        except MQTTError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    entity_after = store.set_last_value(slug, coerced, measured_at=measured_at)
    last_measured_after: Optional[datetime] = None
    if entity_after.last_measured_at is not None:
        last_measured_after = entity_after.last_measured_at
        if last_measured_after.tzinfo is None:
            last_measured_after = last_measured_after.replace(tzinfo=timezone.utc)
        else:
            last_measured_after = last_measured_after.astimezone(timezone.utc)
    should_notify = last_measured_after == measured_at_utc
    if should_notify and entity_after.entity_type == EntityTransportType.HASSEMS:
        await notifier.entity_value(
            entity_after,
            value=coerced,
            measured_at=measured_at,
            historic=is_historic,
            historic_cursor=entity_after.history_cursor,
        )
    return entity_after


@api_router.get("/integrations/home-assistant/entities", response_model=List[ManagedEntity])
def integration_list_entities(
    store: ManagedEntityStore = Depends(get_store),
    _: ApiUser = Depends(require_api_user),
) -> List[ManagedEntity]:
    return store.list_entities_by_kind(
        EntityTransportType.HASSEMS, only_enabled=True
    )


@api_router.get("/integrations/home-assistant/entities/{slug}", response_model=ManagedEntity)
def integration_get_entity(
    slug: str,
    store: ManagedEntityStore = Depends(get_store),
    _: ApiUser = Depends(require_api_user),
) -> ManagedEntity:
    record = store.get_entity(slug)
    if (
        record is None
        or record.entity.entity_type != EntityTransportType.HASSEMS
        or not record.entity.ha_enabled
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Entity '{slug}' not found.")
    return record.entity


@api_router.get(
    "/integrations/home-assistant/entities/{slug}/history",
    response_model=List[HistoryPoint],
)
def integration_get_history(
    slug: str,
    full: bool = Query(default=False),
    store: ManagedEntityStore = Depends(get_store),
    _: ApiUser = Depends(require_api_user),
) -> List[HistoryPoint]:
    record = store.get_entity(slug)
    if (
        record is None
        or record.entity.entity_type != EntityTransportType.HASSEMS
        or not record.entity.ha_enabled
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Entity '{slug}' not found.")
    limit = 0 if full else 200
    return store.list_history(slug, limit=limit)


@api_router.post(
    "/integrations/home-assistant/entities/{slug}/set",
    response_model=ManagedEntity,
)
async def integration_set_entity_value(
    slug: str,
    request: SetValueRequest,
    _: ApiUser = Depends(require_api_user),
    store: ManagedEntityStore = Depends(get_store),
    client: Optional[HomeAssistantClient] = Depends(get_optional_client),
) -> ManagedEntity:
    record = store.get_entity(slug)
    if (
        record is None
        or record.entity.entity_type != EntityTransportType.HASSEMS
        or not record.entity.ha_enabled
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Entity '{slug}' not found.")
    return await set_entity_value(slug, request, store=store, client=client)


@api_router.get(
    "/integrations/home-assistant/webhooks",
    response_model=List[WebhookSubscription],
)
def integration_list_webhooks(
    user: ApiUser = Depends(require_api_user),
    store: ManagedEntityStore = Depends(get_store),
) -> List[WebhookSubscription]:
    target_user_id = None if user.is_superuser else user.id
    return store.list_webhook_subscriptions(target_user_id)


@api_router.post(
    "/integrations/home-assistant/webhooks",
    response_model=WebhookSubscription,
    status_code=status.HTTP_201_CREATED,
)
def integration_register_webhook(
    payload: WebhookRegistration,
    user: ApiUser = Depends(require_api_user),
    store: ManagedEntityStore = Depends(get_store),
) -> WebhookSubscription:
    try:
        return store.save_webhook_subscription(user.id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@api_router.delete(
    "/integrations/home-assistant/webhooks/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def integration_delete_webhook(
    subscription_id: int,
    user: ApiUser = Depends(require_api_user),
    store: ManagedEntityStore = Depends(get_store),
) -> Response:
    target_user_id = None if user.is_superuser else user.id
    try:
        store.delete_webhook_subscription(subscription_id, user_id=target_user_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@api_router.get(
    "/integrations/home-assistant/connections",
    response_model=List[IntegrationConnectionSummary],
)
def integration_list_connections(
    store: ManagedEntityStore = Depends(get_store),
) -> List[IntegrationConnectionSummary]:
    return store.list_integration_connections()


@api_router.get(
    "/integrations/home-assistant/connections/{entry_id}",
    response_model=IntegrationConnectionDetail,
)
def integration_get_connection(
    entry_id: str,
    store: ManagedEntityStore = Depends(get_store),
) -> IntegrationConnectionDetail:
    record = store.get_integration_connection(entry_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration connection '{entry_id}' not found.",
        )
    return record


@api_router.get(
    "/integrations/home-assistant/connections/{entry_id}/history",
    response_model=List[IntegrationConnectionHistoryItem],
)
def integration_get_connection_history(
    entry_id: str,
    store: ManagedEntityStore = Depends(get_store),
) -> List[IntegrationConnectionHistoryItem]:
    try:
        return store.list_integration_connection_history(entry_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@api_router.post(
    "/integrations/home-assistant/connections",
    response_model=IntegrationConnectionDetail,
)
def integration_upsert_connection(
    payload: IntegrationConnectionCreate,
    user: ApiUser = Depends(require_api_user),
    store: ManagedEntityStore = Depends(get_store),
) -> IntegrationConnectionDetail:
    try:
        return store.save_integration_connection(user, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@api_router.delete(
    "/integrations/home-assistant/connections/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def integration_delete_connection(
    entry_id: str,
    user: ApiUser = Depends(require_api_user),
    store: ManagedEntityStore = Depends(get_store),
) -> Response:
    try:
        store.delete_integration_connection(
            entry_id,
            user_id=None if user.is_superuser else user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@api_router.get("/entities/{slug}/state", response_model=EntityState)
async def get_entity_state(
    slug: str,
    store: ManagedEntityStore = Depends(get_store),
    client: HomeAssistantClient = Depends(get_client),
) -> EntityState:
    record = store.get_entity(slug)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Entity '{slug}' not found.")

    entity = record.entity
    if entity.entity_type != EntityTransportType.MQTT:
        attributes: Dict[str, Any] = {
            "entity_type": entity.entity_type.value,
        }
        if entity.unit_of_measurement:
            attributes["unit_of_measurement"] = entity.unit_of_measurement
        if entity.device_class:
            attributes["device_class"] = entity.device_class
        state_value = entity.last_value
        return EntityState(
            entity_id=entity.entity_id,
            state="" if state_value is None else str(state_value),
            last_changed=entity.last_measured_at,
            last_updated=entity.updated_at,
            attributes=attributes,
        )

    try:
        state = await client.get_state(entity.entity_id)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or exc.response.reason_phrase
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    return EntityState(**state)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    if ha_client is not None:
        await ha_client.aclose()


app.include_router(api_router, prefix="/api")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
