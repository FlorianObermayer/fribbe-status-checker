#!/usr/bin/env python3
import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from StatusCheckerService import StatusCheckerService, Status

app = FastAPI()

service =  StatusCheckerService()
service.start_status_check(os.environ["ROUTER_IP"], os.environ["ROUTER_USERNAME"], os.environ["ROUTER_PASSWORD"])

# create a html_templates dict which holds the html values for every Status
html_templates = {}
for status in Status:
    with open(f"html_templates/{status.value}.html", "r") as file:
        html_templates[status.value] = file.read()

@app.get("/json")
async def json():
    status = service.get_status()
    return JSONResponse({"status": status})

@app.get("/")
async def root():
    status = service.get_status()
    return HTMLResponse(html_templates[status])
