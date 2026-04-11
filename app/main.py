#!/usr/bin/env python3
import html
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated
from urllib.parse import quote
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

import app.env as env
from app.api.EphemeralAPIKeyStore import EphemeralAPIKeyStore
from app.api.HybridAuth import AuthRedirectException, HybridAuth, PageAuth
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
from app.services.PushSubscriptionService import PushSubscriptionService
from app.services.WeatherService import WeatherService
from app.version import VERSION

env.validate()

_licenses_path = Path(__file__).parent / "licenses.json"
_third_party_licenses: list[dict[str, str]] = json.loads(_licenses_path.read_text()) if _licenses_path.exists() else []

app = FastAPI(
    title="Fribbe Status Checker",
    version=VERSION,
    license_info={
        "name": "MIT",
        "url": "https://github.com/FlorianObermayer/fribbe-status-checker/blob/main/LICENSE",
    },
)
_csp = (
    ContentSecurityPolicy()
    .default_src("'self'", "https://*.fribbe-beach.de")
    .script_src("'self'", "https://*.fribbe-beach.de")
    .style_src(
        "'self'",
        "https://*.fribbe-beach.de",
        "https://fonts.googleapis.com",
    )
    .font_src("'self'", "https://*.fribbe-beach.de", "https://fonts.gstatic.com")
    .object_src("'none'")
    .img_src("'self'", "https://*.fribbe-beach.de", "https://img.shields.io", "data:")
)
secure_headers = Secure(csp=_csp)

app.add_middleware(
    SessionMiddleware,
    secret_key=env.SESSION_SECRET_KEY,
    session_cookie="session_cookie",
    max_age=60 * 60 * 24 * 7,  # 7 Days or until api key expires
    https_only=env.HTTPS_ONLY,
)


@app.exception_handler(AuthRedirectException)
async def auth_redirect_handler(request: Request, exc: AuthRedirectException) -> RedirectResponse:
    safe_next = sanitize_next(exc.next_url)
    return RedirectResponse(url=f"/auth?next={quote(safe_next, safe='/:?=&')}", status_code=302)


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

occupancy_service = OccupancyService()
occupancy_service.start_polling(env.OCCUPANCY_POLLING_INTERVAL_SECONDS)

internal_service = InternalService()
internal_service.start_polling(
    env.ROUTER_IP,
    env.ROUTER_USERNAME,
    env.ROUTER_PASSWORD,
    env.INTERNAL_POLLING_INTERVAL_SECONDS,
    env.INTERNAL_POLLING_DELAY_SECONDS,
)

message_service = MessageService()
notification_service = NotificationService()
notification_service.start_cleanup_job()

weather_service: WeatherService | None = None

if env.OPENWEATHERMAP_API_KEY and env.WEATHER_LAT is not None and env.WEATHER_LON is not None:
    weather_service = WeatherService(env.OPENWEATHERMAP_API_KEY, env.WEATHER_LAT, env.WEATHER_LON)
else:
    logging.getLogger("uvicorn.error").warning("OpenWeatherMap not configured; weather-aware messages disabled")

push_subscription_service: PushSubscriptionService | None = None

if env.VAPID_PRIVATE_KEY and env.VAPID_PUBLIC_KEY and env.VAPID_CLAIM_SUBJECT:
    push_subscription_service = PushSubscriptionService(
        env.VAPID_PRIVATE_KEY, env.VAPID_PUBLIC_KEY, env.VAPID_CLAIM_SUBJECT
    )
else:
    logging.getLogger("uvicorn.error").warning("VAPID keys not configured; push notifications disabled")

presence_service = PresenceLevelService(weather_service, message_service, push_subscription_service, occupancy_service)

presence_service.start_polling(
    env.ROUTER_IP,
    env.ROUTER_USERNAME,
    env.ROUTER_PASSWORD,
    env.PRESENCE_POLLING_INTERVAL_SECONDS,
    env.PRESENCE_POLLING_DELAY_SECONDS,
)


@app.get("/api/version")
async def version():
    return {"version": app.version}


@app.get("/api/licenses")
async def licenses():
    return _third_party_licenses


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("app/static/images/favicon.ico")


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    return FileResponse(
        "app/static/sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@app.get("/api/push/vapid-key", tags=["Push Notifications"])
async def get_vapid_key():
    if push_subscription_service is None:
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    return {"public_key": push_subscription_service.get_public_key()}


@app.get("/api/push/status", tags=["Push Notifications"])
async def push_status(auth: str = Query(...)):
    if push_subscription_service is None:
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    return {"subscribed": push_subscription_service.has(auth)}


@app.post("/api/push/subscribe", status_code=201, tags=["Push Notifications"])
async def push_subscribe(
    endpoint: str = Body(...),
    p256dh: str = Body(...),
    auth: str = Body(...),
):
    if push_subscription_service is None:
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    try:
        PushSubscriptionService.validate_subscription(endpoint, p256dh, auth)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    push_subscription_service.add(endpoint, p256dh, auth)


@app.delete("/api/push/unsubscribe", tags=["Push Notifications"])
async def push_unsubscribe(auth: str = Body(..., embed=True)):
    if push_subscription_service is None:
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    if not push_subscription_service.remove(auth):
        raise HTTPException(status_code=404, detail="Subscription not found")


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
    is_admin_session = bool(request.session.get("is_admin") and env.ADMIN_TOKEN)
    signed_in = EphemeralAPIKeyStore.is_key_valid(api_key) or is_admin_session
    with Path("app/static/index.html").open() as f:
        content = f.read()
    bootstrap_mode = EphemeralAPIKeyStore.is_empty() and not env.ADMIN_TOKEN
    content = content.replace("__SIGNED_IN__", json.dumps(signed_in))
    content = content.replace("__SHOW_ADMIN_AUTH__", json.dumps(env.SHOW_ADMIN_AUTH))
    content = content.replace("__BOOTSTRAP_MODE__", json.dumps(bootstrap_mode))
    content = content.replace("__VERSION__", VERSION)
    return HTMLResponse(content)


@app.get("/api/status", response_model=StatusResponse, tags=["Status"])
async def get_status(for_date: str = "today"):

    daily_occupancy = occupancy_service.get_occupancy(for_date)

    occupancy_response = OccupancyResponse.from_daily(daily_occupancy)

    # Get the time_str of the first "fully occupying event", if any
    time_str = next(
        (event.time_str for event in daily_occupancy.events if event.occupancy_type == OccupancyType.FULLY),
        None,
    )
    weather = weather_service.get_condition() if weather_service is not None else None
    presence_level = presence_service.get_level()
    presence_last_updated = presence_service.get_last_updated()
    presence_message = message_service.get_status_message(
        presence_level, daily_occupancy.occupancy_type, time_str, weather
    ).message
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
    auth_subject: str | None = Depends(HybridAuth(bypass_on_empty_api_key_list=True)),
) -> ApiKey:
    """
    Create a new API key, store it in the JSON file, and return it. Requires valid API key to create or no API keys to begin with at all (admin setup mode)
    - comment: Optional comment for the key
    - valid_until: Optional datetime (default: 6 months from now)
    """
    # Generate a new key
    valid_until = (valid_until or datetime.now(tz=ZoneInfo("Europe/Berlin")) + timedelta(days=180)).replace(
        microsecond=0
    )
    new_api_key = ApiKey.generate_new(comment, valid_until)
    bootstrap_mode = auth_subject is None
    appended = EphemeralAPIKeyStore.append(new_api_key, require_empty=bootstrap_mode)
    if not appended:
        raise HTTPException(status_code=409, detail="Bootstrap window closed: store is no longer empty")
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
    keys = [k for k in keys if k.key != key_to_delete]
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
    __: str = Depends(PageAuth()),
):  # keep unused variable for api reference
    with Path("app/static/index.html").open() as f:
        content = f.read()
    content = content.replace("__SIGNED_IN__", json.dumps(True))
    content = content.replace("__VERSION__", VERSION)
    return HTMLResponse(content)


def sanitize_next(next_url: str) -> str:
    if not next_url.startswith("/") or next_url.startswith("//"):
        return "/"
    return next_url


@app.get("/auth", response_class=HTMLResponse, include_in_schema=False)
async def get_auth_page(request: Request, next: str = "/"):
    next = sanitize_next(next)
    api_key = request.session.get("api_key")
    is_admin_session = bool(request.session.get("is_admin") and env.ADMIN_TOKEN)
    signed_in = EphemeralAPIKeyStore.is_key_valid(api_key) or is_admin_session
    with Path("app/static/auth.html").open() as f:
        content = f.read()
    safe_next = html.escape(next, quote=True)
    content = content.replace("__NEXT_DATA__", safe_next)
    content = content.replace("__SIGNED_IN__", json.dumps(signed_in))
    content = content.replace("__VERSION__", VERSION)
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
async def get_notification_builder(_: str = Depends(PageAuth())):
    with Path("app/static/notification-create.html").open() as f:
        content = f.read()
    content = content.replace("__VERSION__", VERSION)
    return HTMLResponse(content)


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
