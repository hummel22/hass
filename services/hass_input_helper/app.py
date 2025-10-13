from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List, Optional

import logging
import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .hass_client import HomeAssistantClient
from .models import (
    HistoryPoint,
    HelperState,
    InputHelper,
    InputHelperCreate,
    InputHelperUpdate,
    MQTTConfig,
    MQTTTestResponse,
    SetValueRequest,
    coerce_helper_value,
)
from .mqtt_service import MQTTError, publish_value, verify_connection
from .storage import InputHelperStore

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")
load_dotenv()  # fall back to repo/root .env if present

DATA_FILE = BASE_DIR / "data" / "input_helpers.db"
store = InputHelperStore(DATA_FILE)
ha_client = HomeAssistantClient.from_env()

app = FastAPI(title="HASS Input Helper Service", version="0.1.0")

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_store() -> InputHelperStore:
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


@app.get("/health")
def healthcheck() -> dict:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def landing_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/config/mqtt", response_model=MQTTConfig)
def read_mqtt_config(store: InputHelperStore = Depends(get_store)) -> MQTTConfig:
    config = store.get_mqtt_config()
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MQTT configuration not found.")
    return config


@app.put("/config/mqtt", response_model=MQTTConfig)
def update_mqtt_config(payload: MQTTConfig, store: InputHelperStore = Depends(get_store)) -> MQTTConfig:
    return store.save_mqtt_config(payload)


@app.post("/config/mqtt/test", response_model=MQTTTestResponse)
async def test_mqtt_config(store: InputHelperStore = Depends(get_store)) -> MQTTTestResponse:
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


@app.get("/inputs", response_model=List[InputHelper])
def list_inputs(store: InputHelperStore = Depends(get_store)) -> List[InputHelper]:
    return store.list_helpers()


@app.post("/inputs", response_model=InputHelper, status_code=status.HTTP_201_CREATED)
def create_input_helper(
    payload: InputHelperCreate,
    store: InputHelperStore = Depends(get_store),
) -> InputHelper:
    try:
        return store.create_helper(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@app.put("/inputs/{slug}", response_model=InputHelper)
def update_input_helper(
    slug: str,
    payload: InputHelperUpdate,
    store: InputHelperStore = Depends(get_store),
) -> InputHelper:
    if not payload.model_fields_set:
        helper_record = store.get_helper(slug)
        if helper_record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Helper '{slug}' not found.")
        return helper_record.helper

    try:
        return store.update_helper(slug, payload)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@app.delete(
    "/inputs/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_input_helper(slug: str, store: InputHelperStore = Depends(get_store)) -> Response:
    try:
        store.delete_helper(slug)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/inputs/{slug}/history", response_model=List[HistoryPoint])
def get_helper_history(slug: str, store: InputHelperStore = Depends(get_store)) -> List[HistoryPoint]:
    record = store.get_helper(slug)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Helper '{slug}' not found.")
    return store.list_history(slug)


@app.post("/inputs/{slug}/set", response_model=InputHelper)
async def set_helper_value(
    slug: str,
    request: SetValueRequest,
    store: InputHelperStore = Depends(get_store),
    client: Optional[HomeAssistantClient] = Depends(get_optional_client),
) -> InputHelper:
    record = store.get_helper(slug)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Helper '{slug}' not found.")

    try:
        coerced = coerce_helper_value(record.helper.helper_type, request.value, record.helper.options)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if client is not None:
        try:
            await client.set_helper_value(record.helper, coerced)
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text or exc.response.reason_phrase
            raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc

    mqtt_config = store.get_mqtt_config()
    if mqtt_config is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MQTT configuration not provided. Save broker settings before publishing values.",
        )

    try:
        await asyncio.to_thread(publish_value, mqtt_config, record.helper, coerced)
    except MQTTError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return store.set_last_value(slug, coerced)


@app.get("/inputs/{slug}/state", response_model=HelperState)
async def get_helper_state(
    slug: str,
    store: InputHelperStore = Depends(get_store),
    client: HomeAssistantClient = Depends(get_client),
) -> HelperState:
    record = store.get_helper(slug)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Helper '{slug}' not found.")

    try:
        state = await client.get_state(record.helper.entity_id)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or exc.response.reason_phrase
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    return HelperState(**state)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    if ha_client is not None:
        await ha_client.aclose()
