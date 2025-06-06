#!/usr/bin/env python3
import os
from fastapi import FastAPI
from fastapi.responses import (
    HTMLResponse,
    JSONResponse
)
from StatusCheckerService import (
    StatusCheckerService,
    Status
)

app = FastAPI()

service =  StatusCheckerService()
service.start_status_check(os.environ["ROUTER_IP"], os.environ["ROUTER_USERNAME"], os.environ["ROUTER_PASSWORD"])

@app.get("/json")
async def json():
    status = service.get_status()
    return JSONResponse({"status": status})

@app.get("/")
async def root():
    status = service.get_status()
    if status == Status.Many:
        return HTMLResponse(content="""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
</head>
<body style="background-color:lightgreen;">
<h1>Es scheint ordentlich was los zu sein! Sideouten? Cocktails? Grillabend? :)</h1>
</body>
</html>""")
    elif status == Status.AFew:
        return HTMLResponse(content="""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
</head>
<body style="background-color:lightyellow;">
<h1>Es sind einige wenige da - komm vorbei und spiel mit!</h1>
</body>
</html>""")
    else:
        return HTMLResponse(content="""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
</head>
<body style="background-color:lightred;">
<h1>Möglicherweise ist niemand da. Schau doch vorbei und änder das!</h1>
</body>
</html>""")
