from datetime import datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from app import env
from app.api.access_role import AccessRole
from app.api.ephemeral_api_key_store import EphemeralAPIKeyStore
from app.api.hybrid_auth import PageAuth
from app.api.requests import AuthRedirectQuery
from app.dependencies import (
    MessageServiceDep,
    OccupancyServiceDep,
    PresenceServiceDep,
    WeatherServiceDep,
)
from app.format import seconds_to_human
from app.routers._page_utils import templates
from app.routers.nav_context import NavContext, Route, admin, operator_or_above
from app.services.datetime_parser import format_date_long, format_datetime
from app.services.occupancy.model import OccupancySource, OccupancyType
from app.services.presence_level import PresenceLevel
from app.services.presence_thresholds import PresenceThresholds

router = APIRouter()


@router.get(Route.URL_INDEX, response_class=HTMLResponse, tags=["HTML"])
def get_html(request: Request, for_date: str | None = None) -> HTMLResponse:
    """Serve the main index page with injected runtime config."""
    bootstrap_mode = EphemeralAPIKeyStore.is_empty() and not env.ADMIN_TOKEN
    nav_ctx = NavContext(
        request,
        show_auth_button=env.is_login_button_enabled(),
        show_notification_create_btn=operator_or_above,
        show_api_keys_btn=admin,
        show_preview_btn=operator_or_above,
    )
    _today = datetime.now(tz=ZoneInfo(env.TZ)).date()
    today_str = _today.isoformat()
    max_date_str = (_today + timedelta(days=365)).isoformat()
    return templates.TemplateResponse(
        request,
        "index.html",
        context={
            **nav_ctx,
            "bootstrap_mode": bootstrap_mode,
            "app_url": env.APP_URL,
            "show_legal": env.is_legal_page_enabled(),
            "for_date_value": for_date or today_str,
            "today_str": today_str,
            "max_date_str": max_date_str,
        },
    )


def _build_occupancy_header(source: OccupancySource, for_date: str | None, for_date_iso: str) -> str:
    """Build the occupancy card header string."""
    if source == OccupancySource.EVENT_CALENDAR:
        return f"Veranstaltungen ({format_date_long(for_date_iso)})" if for_date else "Heutige Veranstaltungen"
    return f"Belegungsplan ({format_date_long(for_date_iso)})" if for_date else "Heutiger Belegungsplan"


def _build_combined_updated_text(
    presence_last_updated: datetime | None,
    occupancy_last_updated: datetime | None,
) -> str:
    """Build the combined 'last updated' text."""
    parts: list[str] = []
    if presence_last_updated:
        parts.append(f"Anwesenheit vom {format_datetime(presence_last_updated)}")
    if occupancy_last_updated:
        parts.append(f"Belegung vom {format_datetime(occupancy_last_updated)}")
    return " - ".join(parts) if parts else "Aktualisiert: Nie"


def _build_status_context(
    occupancy_svc: OccupancyServiceDep,
    presence_svc: PresenceServiceDep,
    message_svc: MessageServiceDep,
    weather_svc: WeatherServiceDep,
    for_date: str | None,
) -> dict[str, object]:
    """Build the template context for the status content fragment."""
    daily_occupancy = occupancy_svc.get_occupancy(for_date or "today")

    time_str = next(
        (event.time_str for event in daily_occupancy.events if event.occupancy_type == OccupancyType.FULLY),
        None,
    )
    weather = weather_svc.get_condition() if weather_svc is not None else None
    presence_level = presence_svc.get_level()
    presence_last_updated = presence_svc.get_last_updated()
    presence_message = message_svc.get_status_message(
        presence_level,
        daily_occupancy.occupancy_type,
        time_str,
        weather,
    ).message

    thresholds = PresenceThresholds().get_thresholds()
    _today = datetime.now(tz=ZoneInfo(env.TZ)).date()

    return {
        "presence": {
            "level": presence_level.value,
            "message": presence_message,
        },
        "occupancy": {
            "type": daily_occupancy.occupancy_type.value,
            "source": daily_occupancy.occupancy_source.value,
            "messages": daily_occupancy.lines,
        },
        "thresholds": {
            "empty": thresholds.get(PresenceLevel.EMPTY, 0),
            "few": thresholds.get(PresenceLevel.FEW, 0),
            "many": thresholds.get(PresenceLevel.MANY, 0),
        },
        "occupancy_header": _build_occupancy_header(
            daily_occupancy.occupancy_source,
            for_date,
            daily_occupancy.date.isoformat(),
        ),
        "combined_updated_text": _build_combined_updated_text(
            presence_last_updated,
            daily_occupancy.last_updated,
        ),
        "for_date_value": for_date or _today.isoformat(),
        "today_str": _today.isoformat(),
        "max_date_str": (_today + timedelta(days=365)).isoformat(),
    }


@router.get(
    Route.URL_STATUS_CONTENT,
    response_class=HTMLResponse,
    include_in_schema=False,
)
def get_status_content(  # noqa: PLR0913
    request: Request,
    occupancy_svc: OccupancyServiceDep,
    presence_svc: PresenceServiceDep,
    message_svc: MessageServiceDep,
    weather_svc: WeatherServiceDep,
    for_date: str | None = None,
) -> HTMLResponse:
    """Return server-rendered status HTML fragment for polling."""
    ctx = _build_status_context(occupancy_svc, presence_svc, message_svc, weather_svc, for_date)
    return templates.TemplateResponse(request, "_status_content.html", context=ctx)


@router.get(Route.URL_LEGAL, response_class=HTMLResponse, include_in_schema=False)
def get_legal_page(
    request: Request,
) -> HTMLResponse:
    """Serve the Impressum & Datenschutz page.

    Returns 404 when the legal page is not configured.
    """
    if not env.is_legal_page_enabled():
        raise HTTPException(status_code=404, detail="Legal page not configured")
    nav_ctx = NavContext(
        request,
        show_auth_button=False,
    )
    return templates.TemplateResponse(
        request,
        "legal.html",
        context={
            **nav_ctx,
            "operator_name": env.OPERATOR_NAME,
            "operator_email": env.OPERATOR_EMAIL,
            "session_max_age": seconds_to_human(env.SESSION_MAX_AGE_SECONDS),
            "feature_presence": env.is_presence_enabled(),
            "feature_push": env.is_push_enabled(),
            "feature_weather": env.is_weather_enabled(),
        },
    )


@router.get(Route.URL_AUTH, response_class=HTMLResponse, include_in_schema=False)
def get_auth_page(request: Request, redirect: Annotated[AuthRedirectQuery, Depends()]) -> HTMLResponse:
    """Serve the authentication page."""
    nav_ctx = NavContext(
        request,
        show_auth_button=False,
    )
    return templates.TemplateResponse(
        request,
        "auth.html",
        context={**nav_ctx, "next_url": redirect.next},
    )


@router.get(Route.URL_API_KEYS, response_class=HTMLResponse, tags=["HTML"])
def get_api_keys_page(
    request: Request,
    _: Annotated[str, Depends(PageAuth(min_role=AccessRole.ADMIN))],
) -> HTMLResponse:
    """Serve the API key management page."""
    nav_ctx = NavContext(
        request,
        show_auth_button=False,
        show_api_keys_btn=False,
    )
    roles = [{"value": r.value, "label": r.display_name()} for r in AccessRole]
    role_labels = {r.value: r.display_name() for r in AccessRole}
    return templates.TemplateResponse(
        request,
        "api-keys.html",
        context={
            **nav_ctx,
            "roles": roles,
            "role_labels": role_labels,
            "admin_role_label": AccessRole.ADMIN.display_name(),
            "default_validity_days": env.DEFAULT_API_KEY_VALIDITY_DAYS,
            "comment_min_length": env.API_KEY_COMMENT_MIN_LENGTH,
            "comment_max_length": env.API_KEY_COMMENT_MAX_LENGTH,
        },
    )
