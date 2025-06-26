#!/usr/bin/env python3
from genericpath import exists
import os
from datetime import date, datetime, timedelta
from typing import List
from fastapi import FastAPI, Depends, Body
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import secrets
import json

from app.api.EphemeralAPIKeyQuery import EphemeralAPIKeyQuery
from app.services.internal.InternalService import InternalService
from app.services.MessageService import MessageService
from app.services.PresenceLevelService import (
    PresenceLevel,
    PresenceLevelService,
    PresenceThresholds,
)
from app.services.occupancy.Model import Occupancy
from app.services.occupancy.OccupancyService import OccupancyService
from app.services.occupancy.Model import OccupancySource
from app.services.occupancy.Model import OccupancyType


app = FastAPI()
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


class BaseResponse(BaseModel):
    last_updated: datetime | None
    last_error: str | None


class PresenceResponse(BaseResponse):
    level: PresenceLevel
    message: str
    thresholds: dict[PresenceLevel, int]


class OccupancyResponse(BaseResponse):
    type: OccupancyType
    source: OccupancySource
    messages: List[str]
    events: List[Occupancy]
    for_date: date


class StatusResponse(BaseModel):
    occupancy: OccupancyResponse
    presence: PresenceResponse


class DetailsResponse(BaseResponse):
    wardens_on_site: List[str]
    active_devices: int
    first_device_on_site: datetime | None
    last_device_on_site: datetime | None


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


@app.get("/", response_class=HTMLResponse)
async def get_html(for_date: str = "today"):  # keep unused variable for api reference
    with open("app/static/index.html") as f:
        return HTMLResponse(f.read())


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("app/static/images/favicon.ico")


@app.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
def robots():
    data = """User-agent: *\nDisallow: /"""
    return data


@app.get("/api/internal/details", response_model=DetailsResponse)
def details(_: str = Depends(EphemeralAPIKeyQuery(name="api_key"))):

    last_error = internal_service.get_last_error()
    wardens = internal_service.get_wardens_on_site()

    return DetailsResponse(
        last_updated=internal_service.get_last_updated(),
        last_error=last_error and str(last_error),
        wardens_on_site=[warden.name for warden in wardens],
        active_devices=internal_service.get_active_devices_ct(),
        first_device_on_site=internal_service.get_first_device_on_site(),
        last_device_on_site=internal_service.get_last_device_on_site(),
    )


class ApiKey(BaseModel):
    key: str
    comment: str | None
    valid_until: datetime | None


@app.post("/api/internal/api_key/create", response_model=ApiKey)
def create_api_key(
    comment: str = Body("", embed=True),
    valid_until: datetime = Body(None, embed=True),
    _: str = Depends(
        EphemeralAPIKeyQuery(name="api_key", bypass_on_empty_api_key_list=True)
    ),
) -> ApiKey:
    """
    Create a new API key, store it in the JSON file, and return it. Requires valid API key to create or no API keys to begin with at all (admin setup mode)
    - comment: Optional comment for the key
    - valid_until: Optional datetime (default: 6 months from now)
    """
    apikeys_path = os.environ["API_KEYS_PATH"]
    # Generate a new key
    new_key = secrets.token_urlsafe(48)

    valid_until = (valid_until or datetime.now() + timedelta(days=180)).replace(
        microsecond=0
    )

    new_api_key = ApiKey(key=new_key, comment=comment, valid_until=valid_until)

    keys: List[dict[str, str]] = []
    if exists(apikeys_path):
        # Load existing keys if it exists
        with open(apikeys_path, "r") as f:
            keys = json.load(f)

    if not keys:
        keys = []

    # Add new key
    keys.append(new_api_key.model_dump(mode="json"))
    # Save
    with open(apikeys_path, "w") as f:
        json.dump(keys, f, indent=2)

    EphemeralAPIKeyQuery.refresh_api_keys()

    return new_api_key
