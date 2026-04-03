#!/usr/bin/env python3
import html
import json
import logging
import os
import secrets
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

import markdown
from fastapi import (
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from secure import ContentSecurityPolicy, Secure
from starlette.middleware.sessions import SessionMiddleware

from app.api.EphemeralAPIKeyStore import EphemeralAPIKeyStore
from app.api.HybridAuth import HybridAuth
from app.api.Requests import NOTIFICATION_FILTERS, NotificationQuery
from app.api.Responses import (
    ApiKey,
    ApiKeys,
    DetailsResponse,
    OccupancyResponse,
    PostNotificationResponse,
    PresenceResponse,
    StatusResponse,
    WardenListResponse,
    WardenResponse,
)
from app.api.Schema import requires_auth_extra, update_openapi_schema
from app.services.internal.InternalService import InternalService
from app.services.internal.Model import Warden
from app.services.internal.WardenStore import WardenStore
from app.services.MessageService import MessageService
from app.services.NotificationService import NotificationService
from app.services.occupancy.Model import OccupancyType
from app.services.occupancy.OccupancyService import OccupancyService
from app.services.PresenceLevelService import (
    PresenceLevelService,
)
from app.services.PresenceThresholds import PresenceThresholds
from app.version import VERSION

app = FastAPI(version=VERSION)
_csp = (
    ContentSecurityPolicy()
    .default_src("'self'", "https://*.fribbe-beach.de")
    .script_src("'self'", "https://*.fribbe-beach.de")
    .style_src("'self'", "https://*.fribbe-beach.de", "https://fonts.googleapis.com")
    .font_src("'self'", "https://*.fribbe-beach.de", "https://fonts.gstatic.com")
    .object_src("'none'")
    .img_src("'self'", "https://*.fribbe-beach.de", "data:")
)
secure_headers = Secure(csp=_csp)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SESSION_SECRET_KEY"],
    session_cookie="session_cookie",
    max_age=60 * 60 * 24 * 7,  # 7 Days or until api key expires
    https_only=os.environ.get("HTTPS_ONLY", "true").lower() == "true",
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]):
    response = await call_next(request)
    if request.url.path not in ("/docs", "/redoc", "/openapi.json"):
        await secure_headers.set_headers_async(response)  # type: ignore
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    logger = logging.getLogger("uvicorn.error")
    api_key = request.headers.get("api_key")
    if api_key:
        logger.info(f"-H api_key[:2]={api_key[:2]}")
    response = await call_next(request)
    return response


app.mount("/static", StaticFiles(directory="app/static"), name="static")

presence_service = PresenceLevelService()
presence_service.start_polling(
    os.environ["ROUTER_IP"],
    os.environ["ROUTER_USERNAME"],
    os.environ["ROUTER_PASSWORD"],
    int(os.environ["PRESENCE_POLLING_INTERVAL_SECONDS"]),
    int(os.environ["PRESENCE_POLLING_DELAY_SECONDS"]),
)

occupancy_service = OccupancyService()
occupancy_service.start_polling(int(os.environ["OCCUPANCY_POLLING_INTERVAL_SECONDS"]))

internal_service = InternalService()
internal_service.start_polling(
    os.environ["ROUTER_IP"],
    os.environ["ROUTER_USERNAME"],
    os.environ["ROUTER_PASSWORD"],
    int(os.environ["INTERNAL_POLLING_INTERVAL_SECONDS"]),
    int(os.environ["INTERNAL_POLLING_DELAY_SECONDS"]),
)

message_service = MessageService()
notification_service = NotificationService()
notification_service.start_cleanup_job()


@app.get("/api/version")
async def version():
    return {"version": app.version}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("app/static/images/favicon.ico")


@app.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
def robots():
    data = """User-agent: *
Allow: /$
Allow: /sitemap.xml
Disallow: /api/
Disallow: /preview/
Disallow: /notification-create
Disallow: /static/

Sitemap: https://status.fribbe-beach.de/sitemap.xml"""
    return data


@app.get("/sitemap.xml", response_class=Response, include_in_schema=False)
def sitemap():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://status.fribbe-beach.de/</loc>
        <changefreq>always</changefreq>
        <priority>1.0</priority>
    </url>
</urlset>"""
    return Response(content=xml, media_type="application/xml")


@app.get("/", response_class=HTMLResponse, tags=["HTML"])
async def get_html(request: Request, for_date: str = "today"):  # keep unused variable for api reference
    api_key = request.session.get("api_key")
    signed_in = EphemeralAPIKeyStore.is_key_valid(api_key)
    with open("app/static/index.html") as f:
        content = f.read()
    content = content.replace("__SIGNED_IN__", json.dumps(signed_in))
    return HTMLResponse(content)


@app.get("/api/status", response_model=StatusResponse, tags=["Status"])
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
        (event.time_str for event in occ_events if event.occupancy_type == OccupancyType.FULLY),
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
        thresholds=PresenceThresholds().get_thresholds(),
    )

    return StatusResponse(
        occupancy=occupancy_response,
        presence=presence_response,
    )


@app.get(
    "/api/internal/details",
    response_model=DetailsResponse,
    tags=["Internal"],
    openapi_extra=requires_auth_extra(),
)
def details(_: str = Depends(HybridAuth())):

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


@app.post(
    "/api/internal/api_key",
    response_model=ApiKey,
    tags=["API Keys"],
    openapi_extra=requires_auth_extra(),
)
def create_api_key(
    comment: str = Body("", embed=True),
    valid_until: datetime = Body(None, embed=True),
    _: str | None = Depends(HybridAuth(bypass_on_empty_api_key_list=True)),
) -> ApiKey:
    """
    Create a new API key, store it in the JSON file, and return it. Requires valid API key to create or no API keys to begin with at all (admin setup mode)
    - comment: Optional comment for the key
    - valid_until: Optional datetime (default: 6 months from now)
    """
    # Generate a new key
    new_key = secrets.token_urlsafe(48)
    valid_until = (valid_until or datetime.now(tz=ZoneInfo("Europe/Berlin")) + timedelta(days=180)).replace(
        microsecond=0
    )
    new_api_key = ApiKey(key=new_key, comment=comment, valid_until=valid_until)
    keys = EphemeralAPIKeyStore.load()
    if not keys:
        keys = []
    keys.append(new_api_key)
    EphemeralAPIKeyStore.save(keys)
    return new_api_key


@app.delete(
    "/api/internal/api_key",
    tags=["API Keys"],
    openapi_extra=requires_auth_extra(),
)
def delete_api_key(
    key: str = Body(..., embed=True),
    _: str = Depends(HybridAuth()),
):
    """
    Deletes an API key by its value or prefix (at least 5 characters). Only deletes if there is a unique match.
    """
    if len(key) < 5:
        raise HTTPException(status_code=400, detail="Key prefix must be at least 5 characters long")
    keys = EphemeralAPIKeyStore.load()
    matches = [k for k in keys if k.key.startswith(key)]
    if len(matches) == 0:
        raise HTTPException(status_code=404, detail="Api key not found")
    if len(matches) > 1:
        raise HTTPException(status_code=409, detail="Ambiguous key prefix: multiple matches found")
    key_to_delete = matches[0].key
    keys = [k for k in keys if not (k.key == key_to_delete)]
    EphemeralAPIKeyStore.save(keys)


@app.get(
    "/api/internal/api_keys",
    response_model=ApiKeys,
    tags=["API Keys"],
    openapi_extra=requires_auth_extra(),
)
def list_api_keys(_: str | None = Depends(HybridAuth())):
    """
    Returns all API keys as a list. Requires a valid API key for authentication.
    """
    keys = EphemeralAPIKeyStore.load()
    return ApiKeys(api_keys=keys)


@app.post(
    "/api/notifications",
    tags=["Notifications"],
    openapi_extra=requires_auth_extra(),
    response_model=PostNotificationResponse,
)
async def post_notification(
    message: str = Body(...),
    valid_from: datetime = Body(None),
    valid_until: datetime = Body(None),
    enabled: bool = Body(True),
    _: str = Depends(HybridAuth()),
):
    notification_id = notification_service.add(message, valid_from, valid_until, enabled)
    return {"notification_id": notification_id}


@app.get(
    "/api/notifications",
    response_class=HTMLResponse,
    tags=["Notifications", "HTML"],
    openapi_extra=requires_auth_extra(),
)
async def get_notifications_as_html(
    request: Annotated[NotificationQuery, Query()],
    api_key: str | None = Depends(HybridAuth(auto_error=False)),
):

    # Without an API Key, only allow "public" queries
    n_ids = request.filter_unprotected_n_ids() if api_key is None else request.n_ids

    notifications = notification_service.get(n_ids)

    if len(notifications) == 0:
        return HTMLResponse("")

    # Combine all queried messages as markdown, convert to HTML
    html = """
<style>
    img {
        max-width: 100%;
        height: auto;

    }
</style>
""" + "\n<hr/>".join(
        [f'<div data-notification-id="{n.id}">{markdown.markdown(n.message)}</div>' for n in notifications]
    )
    return HTMLResponse(html)


@app.get(
    "/api/notifications/filters",
    response_class=JSONResponse,
    tags=["Notifications"],
    openapi_extra=requires_auth_extra(),
)
async def get_notification_filters(_: str = Depends(HybridAuth())):
    return JSONResponse(NOTIFICATION_FILTERS)


@app.get(
    "/api/notifications/list",
    response_class=JSONResponse,
    tags=["Notifications"],
    openapi_extra=requires_auth_extra(),
)
async def list_notifications(_: str = Depends(HybridAuth())):
    notifications = notification_service.list_all()
    return JSONResponse([notify.to_dict() for notify in notifications])


@app.delete(
    "/api/notifications/{notification_id}",
    tags=["Notifications"],
    openapi_extra=requires_auth_extra(),
)
async def delete_notification(notification_id: str, _: str = Depends(HybridAuth())):
    if not notification_service.delete(notification_id):
        raise HTTPException(status_code=404, detail="Notification not found")


@app.delete(
    "/api/notifications",
    tags=["Notifications"],
    openapi_extra=requires_auth_extra(),
)
async def delete_notifications(
    request: Annotated[NotificationQuery, Query()],
    _: str = Depends(HybridAuth()),
):
    count = notification_service.delete_many(request.n_ids)
    if count == 0:
        raise HTTPException(status_code=404, detail="No matching notifications found")
    return JSONResponse({"deleted": count})


@app.put(
    "/api/notifications/{notification_id}",
    tags=["Notifications"],
    openapi_extra=requires_auth_extra(),
)
async def update_notification(
    notification_id: str,
    enabled: bool = Body(None),
    valid_from: datetime = Body(None),
    valid_until: datetime = Body(None),
    _: str = Depends(HybridAuth()),
):
    if not notification_service.update(notification_id, enabled, valid_from, valid_until):
        raise HTTPException(status_code=404, detail="Notification not found")


@app.get(
    "/preview/notifications",
    tags=["Notifications"],
    openapi_extra=requires_auth_extra(),
)
async def get_notification_preview(
    _: NotificationQuery = Query(...),
    __: str = Depends(HybridAuth()),
):  # keep unused variable for api reference
    with open("app/static/index.html") as f:
        content = f.read()
    content = content.replace("__SIGNED_IN__", json.dumps(True))
    return HTMLResponse(content)


def sanitize_next(next_url: str) -> str:
    if not next_url.startswith("/") or next_url.startswith("//"):
        return "/"
    return next_url


@app.get("/auth", response_class=HTMLResponse, include_in_schema=False)
async def get_auth_page(request: Request, next: str = "/"):
    next = sanitize_next(next)
    api_key = request.session.get("api_key")
    signed_in = EphemeralAPIKeyStore.is_key_valid(api_key)
    with open("app/static/auth.html") as f:
        content = f.read()
    safe_next = html.escape(next, quote=True)
    content = content.replace("__NEXT_DATA__", safe_next)
    content = content.replace("__SIGNED_IN__", json.dumps(signed_in))
    return HTMLResponse(content)


@app.post("/auth", include_in_schema=False)
async def post_auth(request: Request, token: str = Body(...), next: str = Body("/")):
    next = sanitize_next(next)
    if not EphemeralAPIKeyStore.is_key_valid(token):
        raise HTTPException(status_code=401, detail="Invalid token")
    request.session["api_key"] = token
    return JSONResponse({"redirect": next})


@app.post("/signout", include_in_schema=False)
async def signout(request: Request):
    request.session.clear()
    return JSONResponse({"redirect": "/"})


@app.get("/notification-create", response_class=HTMLResponse, tags=["Notifications", "HTML"])
async def get_notification_builder(api_key: str | None = Depends(HybridAuth(auto_error=False))):
    if api_key is None:
        return RedirectResponse(url="/auth?next=/notification-create", status_code=302)
    with open("app/static/notification-create.html") as f:
        return HTMLResponse(f.read())


@app.patch("/internal/config", response_class=HTMLResponse, tags=["Config"], openapi_extra=requires_auth_extra())
async def config(threshold_min_non_empty_ct: int = Body(None, gt=0), threshold_min_many_ct: int = Body(None, gt=1)):
    if not any((threshold_min_non_empty_ct, threshold_min_many_ct)):
        return Response(status_code=304)  # ^= Not Modified

    thresholds = PresenceThresholds()

    if threshold_min_non_empty_ct:
        thresholds.min_non_empty_ct = threshold_min_non_empty_ct

    if threshold_min_many_ct:
        thresholds.min_many_ct = threshold_min_many_ct

    return Response()


@app.get(
    "/api/internal/wardens",
    response_model=WardenListResponse,
    tags=["Internal"],
    openapi_extra=requires_auth_extra(),
)
def list_wardens(_: str = Depends(HybridAuth())) -> WardenListResponse:
    wardens = WardenStore.get_instance().get_all()
    return WardenListResponse(
        wardens=[WardenResponse(name=w.name, device_macs=w.device_macs, device_names=w.device_names) for w in wardens]
    )


@app.post(
    "/api/internal/wardens",
    response_model=WardenResponse,
    status_code=201,
    tags=["Internal"],
    openapi_extra=requires_auth_extra(),
)
def create_warden(
    name: str = Body(..., embed=True),
    device_macs: list[str] = Body([], embed=True),
    device_names: list[str] = Body([], embed=True),
    _: str = Depends(HybridAuth()),
) -> WardenResponse:
    warden = Warden(name, device_macs, device_names)
    try:
        WardenStore.get_instance().add(warden)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return WardenResponse(name=warden.name, device_macs=warden.device_macs, device_names=warden.device_names)


@app.put(
    "/api/internal/wardens/{name}",
    response_model=WardenResponse,
    tags=["Internal"],
    openapi_extra=requires_auth_extra(),
)
def update_warden(
    name: str,
    new_name: str | None = Body(None, embed=True),
    device_macs: list[str] | None = Body(None, embed=True),
    device_names: list[str] | None = Body(None, embed=True),
    _: str = Depends(HybridAuth()),
) -> WardenResponse:
    store = WardenStore.get_instance()
    try:
        existing = store.by_name(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    updated = Warden(
        new_name if new_name is not None else existing.name,
        device_macs if device_macs is not None else existing.device_macs,
        device_names if device_names is not None else existing.device_names,
    )
    try:
        store.update(name, updated)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return WardenResponse(name=updated.name, device_macs=updated.device_macs, device_names=updated.device_names)


@app.delete(
    "/api/internal/wardens/{name}",
    status_code=204,
    tags=["Internal"],
    openapi_extra=requires_auth_extra(),
)
def delete_warden(name: str, _: str = Depends(HybridAuth())) -> None:
    try:
        WardenStore.get_instance().delete(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


update_openapi_schema(app)
