#!/usr/bin/env python3
import os
from datetime import date, datetime
from typing import List
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.services.MessageService import MessageService
from app.services.PresenceLevelService import PresenceLevel, PresenceLevelService
from app.services.occupancy.Occupancy import Occupancy
from app.services.occupancy.OccupancyService import OccupancyService
from app.services.occupancy.OccupancySource import OccupancySource
from app.services.occupancy.OccupancyType import OccupancyType

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

message_service = MessageService()


class PresenceResponse(BaseModel):
    level: PresenceLevel
    last_updated: datetime
    message: str
    last_error: str | None


class OccupancyResponse(BaseModel):
    last_updated: datetime
    type: OccupancyType
    source: OccupancySource
    messages: List[str]
    last_error: str | None
    events: List[Occupancy]
    for_date: date


class StatusResponse(BaseModel):
    occupancy: OccupancyResponse
    presence: PresenceResponse


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
    presence_message = message_service.get_message(
        presence_level, occ_type, time_str, presence_last_updated
    )
    presence_last_error = presence_service.get_last_error()

    presence_response = PresenceResponse(
        level=presence_level,
        last_updated=presence_last_updated,
        message=presence_message,
        last_error=presence_last_error and str(presence_last_error),
    )

    return StatusResponse(
        occupancy=occupancy_response,
        presence=presence_response,
    )


@app.get("/", response_class=HTMLResponse)
async def get_html(for_date: str = "today"):
    with open("app/static/index.html") as f:
        return HTMLResponse(f.read())


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("app/static/images/favicon.ico")
