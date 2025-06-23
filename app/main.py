#!/usr/bin/env python3
import os
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.services.MessageService import MessageService
from app.services.StatusCheckerService import Status, StatusCheckerService

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")

status_service = StatusCheckerService()
status_service.start_status_check(
    os.environ["ROUTER_IP"],
    os.environ["ROUTER_USERNAME"],
    os.environ["ROUTER_PASSWORD"],
)
message_service = MessageService()


class StatusResponse(BaseModel):
    status: Status
    last_updated: datetime
    message: str


@app.get("/api/status", response_model=StatusResponse)
async def get_status():

    current_status = status_service.get_status()
    last_updated = status_service.get_last_updated()
    message = message_service.get_message(current_status, last_updated)

    return StatusResponse(
        status=current_status, last_updated=last_updated, message=message
    )


@app.get("/", response_class=HTMLResponse)
async def get_html():
    with open("app/static/index.html") as f:
        return HTMLResponse(f.read())


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("app/static/images/favicon.ico")
