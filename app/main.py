#!/usr/bin/env python3
import logging
import os
from datetime import datetime, timedelta
from typing import Awaitable, Callable
from fastapi import FastAPI, Depends, Body, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

import secrets

from app.api.EphemeralAPIKeyHeader import EphemeralAPIKeyHeader
from app.api.EphemeralAPIKeyStore import EphemeralAPIKeyStore
from app.api.Responses import (
    ApiKeys,
    PresenceResponse,
    StatusResponse,
    DetailsResponse,
    OccupancyResponse,
    ApiKey,
)
from app.services.internal.InternalService import InternalService
from app.services.MessageService import MessageService
from app.services.PresenceLevelService import (
    PresenceLevelService,
    PresenceThresholds,
)
from app.services.occupancy.OccupancyService import OccupancyService
from app.services.occupancy.Model import OccupancyType
from app.services.NotificationService import NotificationService
from fastapi.responses import JSONResponse
import markdown


app = FastAPI()


@app.middleware("http")
async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    logger = logging.getLogger("uvicorn.error")
    api_key = request.headers.get("api_key")
    if api_key:
        logger.info(f"-H api_key[:4]={api_key[:4]}")
    response = await call_next(request)
    return response


app.mount("/static", StaticFiles(directory="app/static"), name="static")

presence_service = PresenceLevelService()
presence_service.start_polling(
    os.environ["ROUTER_IP"],
    os.environ["ROUTER_USERNAME"],
    os.environ["ROUTER_PASSWORD"],
)

occupancy_service = OccupancyService()
occupancy_service.start_polling()

internal_service = InternalService()
internal_service.start_polling(
    os.environ["ROUTER_IP"],
    os.environ["ROUTER_USERNAME"],
    os.environ["ROUTER_PASSWORD"],
)

message_service = MessageService()
notification_service = NotificationService()


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("app/static/images/favicon.ico")


@app.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
def robots():
    data = """User-agent: *\nDisallow: /"""
    return data


@app.get("/", response_class=HTMLResponse)
async def get_html(for_date: str = "today"):  # keep unused variable for api reference
    with open("app/static/index.html") as f:
        return HTMLResponse(f.read())


@app.get("/api/status", response_model=StatusResponse)
async def get_status(for_date: str = "today"):

    (
        occ_for_date,
        occ_messages,
        occ_events,
        occ_type,
        occ_source,
        occ_last_updated,
        occ_last_error,
    ) = occupancy_service.get_occupancy(for_date)

    occupancy_response = OccupancyResponse(
        last_updated=occ_last_updated,
        type=occ_type,
        source=occ_source,
        messages=occ_messages,
        events=occ_events,
        last_error=occ_last_error and str(occ_last_error),
        for_date=occ_for_date,
    )

    # Get the time_str of the first "fully occupying event", if any
    time_str = next(
        (
            event.time_str
            for event in occ_events
            if event.occupancy_type == OccupancyType.FULLY
        ),
        None,
    )

    presence_level = presence_service.get_level()
    presence_last_updated = presence_service.get_last_updated()
    presence_message = message_service.get_message(presence_level, occ_type, time_str)
    presence_last_error = presence_service.get_last_error()

    presence_response = PresenceResponse(
        level=presence_level,
        last_updated=presence_last_updated,
        message=presence_message,
        last_error=presence_last_error and str(presence_last_error),
        thresholds=PresenceThresholds.THRESHOLDS,
    )

    return StatusResponse(
        occupancy=occupancy_response,
        presence=presence_response,
    )


@app.get("/api/internal/details", response_model=DetailsResponse)
def details(_: str = Depends(EphemeralAPIKeyHeader())):

    last_error = internal_service.get_last_error()
    wardens = internal_service.get_wardens_on_site()

    return DetailsResponse(
        last_updated=internal_service.get_last_updated(),
        last_error=last_error and str(last_error),
        wardens_on_site=[warden.name for warden in wardens],
        active_devices=internal_service.get_active_devices_ct(),
        first_device_on_site=internal_service.get_first_device_on_site(),
        last_device_on_site=internal_service.get_last_device_on_site(),
        last_service_start=internal_service.get_last_service_started(),
    )


@app.post("/api/internal/api_key/create", response_model=ApiKey, tags=["API Keys"])
def create_api_key(
    comment: str = Body("", embed=True),
    valid_until: datetime = Body(None, embed=True),
    _: str = Depends(EphemeralAPIKeyHeader(bypass_on_empty_api_key_list=True)),
) -> ApiKey:
    """
    Create a new API key, store it in the JSON file, and return it. Requires valid API key to create or no API keys to begin with at all (admin setup mode)
    - comment: Optional comment for the key
    - valid_until: Optional datetime (default: 6 months from now)
    """
    # Generate a new key
    new_key = secrets.token_urlsafe(48)
    valid_until = (valid_until or datetime.now() + timedelta(days=180)).replace(
        microsecond=0
    )
    new_api_key = ApiKey(key=new_key, comment=comment, valid_until=valid_until)
    keys = EphemeralAPIKeyStore.load()
    if not keys:
        keys = []
    keys.append(new_api_key)
    EphemeralAPIKeyStore.save(keys)
    EphemeralAPIKeyHeader.refresh_api_keys()
    return new_api_key


@app.delete("/api/internal/api_key/delete", tags=["API Keys"])
def delete_api_key(
    key: str = Body(..., embed=True),
    _: str = Depends(EphemeralAPIKeyHeader()),
):
    """
    Deletes an API key by its value or prefix (at least 5 characters). Only deletes if there is a unique match.
    """
    if len(key) < 5:
        raise HTTPException(
            status_code=400, detail="Key prefix must be at least 5 characters long"
        )
    keys = EphemeralAPIKeyStore.load()
    matches = [k for k in keys if k.key.startswith(key)]
    if len(matches) == 0:
        raise HTTPException(status_code=404, detail="Api key not found")
    if len(matches) > 1:
        raise HTTPException(
            status_code=409, detail="Ambiguous key prefix: multiple matches found"
        )
    key_to_delete = matches[0].key
    keys = [k for k in keys if not (k.key == key_to_delete)]
    EphemeralAPIKeyStore.save(keys)
    EphemeralAPIKeyHeader.refresh_api_keys()


@app.get("/api/internal/api_key/list", response_model=ApiKeys, tags=["API Keys"])
def list_api_keys(_: str = Depends(EphemeralAPIKeyHeader())):
    """
    Returns all API keys as a list. Requires a valid API key for authentication.
    """
    keys = EphemeralAPIKeyStore.load()
    return ApiKeys(api_keys=keys)


@app.post("/api/notifications", tags=["Notifications"])
async def post_notification(
    message: str = Body(...),
    valid_from: datetime = Body(datetime.now()),
    valid_until: datetime = Body(None),
    enabled: bool = Body(True),
    _: str = Depends(EphemeralAPIKeyHeader()),
):
    notification_id = notification_service.add(
        message, valid_from, valid_until, enabled
    )
    return {"id": notification_id}


@app.get("/api/notifications/html", response_class=HTMLResponse, tags=["Notifications"])
async def get_notifications_as_html():
    notifications = notification_service.get_active()
    # Combine all active messages as markdown, convert to HTML
    html = "\n<hr/>".join(
        [f"<div>{markdown.markdown(n.message)}</div>" for n in notifications]
    )
    return HTMLResponse(html)


@app.get("/api/notifications", response_class=JSONResponse, tags=["Notifications"])
async def list_notifications(_: str = Depends(EphemeralAPIKeyHeader())):
    notifications = notification_service.list_all()
    return JSONResponse([notify.to_dict() for notify in notifications])


@app.delete("/api/notifications/{notification_id}", tags=["Notifications"])
async def delete_notification(
    notification_id: str, _: str = Depends(EphemeralAPIKeyHeader())
):
    if not notification_service.delete(notification_id):
        raise HTTPException(status_code=404, detail="Notification not found")


@app.put("/api/notifications/{notification_id}", tags=["Notifications"])
async def update_notification(
    notification_id: str,
    enabled: bool = Body(None),
    valid_until: datetime = Body(None),
    _: str = Depends(EphemeralAPIKeyHeader()),
):
    if not notification_service.update(notification_id, enabled, valid_until):
        raise HTTPException(status_code=404, detail="Notification not found")
