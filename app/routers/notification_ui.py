from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

import markdown
import nh3
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.api.access_role import AccessRole
from app.api.hybrid_auth import HybridAuth, PageAuth
from app.api.requests import NOTIFICATION_FILTERS, NotificationFilterId, NotificationQuery
from app.api.schema import requires_auth_extra
from app.config import cfg
from app.dependencies import NotificationServiceDep
from app.routers._page_utils import show_toast, templates
from app.routers.nav_context import NavContext, Route

router = APIRouter()


@router.get(Route.URL_NOTIFICATION_CREATE, response_class=HTMLResponse, tags=["Notifications", "HTML"])
def get_notification_builder(
    request: Request,
    _: Annotated[str, Depends(PageAuth(min_role=AccessRole.NOTIFICATION_OPERATOR))],
) -> HTMLResponse:
    """Serve the notification creation page."""
    nav_ctx = NavContext(
        request,
        show_auth_button=False,
        show_notification_create_btn=False,
        show_preview_btn=True,
    )
    now = datetime.now(tz=ZoneInfo(cfg.TZ))
    valid_from_default = now.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    valid_until_default = now.replace(hour=23, minute=59, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    return templates.TemplateResponse(
        request,
        "notification-create.html",
        context={
            **nav_ctx,
            "valid_from_default": valid_from_default,
            "valid_until_default": valid_until_default,
        },
    )


@router.post(Route.URL_NOTIFICATION_CREATE, include_in_schema=False)
def post_notification_builder(
    svc: NotificationServiceDep,
    _: Annotated[str, Depends(PageAuth(min_role=AccessRole.NOTIFICATION_OPERATOR))],
    message: Annotated[str, Form()],
    valid_from: Annotated[str | None, Form()] = None,
    valid_until: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    """Create a notification from the form and redirect to its preview."""
    if not message.strip():
        response = RedirectResponse(url=Route.URL_NOTIFICATION_CREATE, status_code=303)
        show_toast(response, "Nachricht ist ein Pflichtfeld", "error")
        return response
    tz = ZoneInfo(cfg.TZ)
    try:
        parsed_from = datetime.fromisoformat(valid_from).replace(tzinfo=tz) if valid_from else None
        parsed_until = datetime.fromisoformat(valid_until).replace(tzinfo=tz) if valid_until else None
    except ValueError:
        response = RedirectResponse(url=Route.URL_NOTIFICATION_CREATE, status_code=303)
        show_toast(response, "Ungültiges Datum/Zeit-Format", "error")
        return response
    notification_id = svc.add(message, parsed_from, parsed_until, enabled=False)
    response = RedirectResponse(url=f"{Route.URL_NOTIFICATION_PREVIEW}?n_ids={notification_id}", status_code=303)
    show_toast(response, "Vorschau erstellt")
    return response


@router.get(
    Route.URL_NOTIFICATION_PREVIEW,
    tags=["Notifications"],
    openapi_extra=requires_auth_extra(),
)
def get_notification_preview(
    svc: NotificationServiceDep,
    request: Request,
    query: Annotated[NotificationQuery, Query()],
    _auth: Annotated[str, Depends(PageAuth())],
) -> HTMLResponse:
    """Serve a notification preview page."""
    nav_ctx = NavContext(
        request,
        show_auth_button=False,
        show_notification_create_btn=True,
    )

    selected_filter = query.n_ids[0] if len(query.n_ids) == 1 else NotificationFilterId.ALL_ACTIVE
    notifications = svc.get(query.n_ids)
    notification = notifications[0] if len(notifications) == 1 else None

    show_activate_btn = False
    show_delete_btn = False
    show_disable_btn = False

    if notification:
        show_activate_btn = not notification.is_outdated(0) and not notification.enabled
        show_disable_btn = notification.enabled
        show_delete_btn = True
    _nid = notification.id if notification else ""
    return templates.TemplateResponse(
        request,
        "preview.html",
        context={
            **nav_ctx,
            "bootstrap_mode": False,
            "app_url": cfg.APP_URL,
            "show_legal": cfg.features.is_legal_page_enabled(),
            "notification_filters": NOTIFICATION_FILTERS,
            "selected_filter": selected_filter,
            "notification_id": _nid or None,
            "url_enable": f"{Route.URL_NOTIFICATION_PREVIEW}/{_nid}/enable" if _nid else "",
            "url_disable": f"{Route.URL_NOTIFICATION_PREVIEW}/{_nid}/disable" if _nid else "",
            "url_delete": f"{Route.URL_NOTIFICATION_PREVIEW}/{_nid}/delete" if _nid else "",
            "show_activate_btn": show_activate_btn,
            "show_disable_btn": show_disable_btn,
            "show_delete_btn": show_delete_btn,
        },
    )


@router.post(
    f"{Route.URL_NOTIFICATION_PREVIEW}/{{notification_id}}/enable",
    include_in_schema=False,
)
def enable_notification(
    svc: NotificationServiceDep,
    request: Request,
    notification_id: str,
    _auth: Annotated[str, Depends(PageAuth(min_role=AccessRole.NOTIFICATION_OPERATOR))],
) -> RedirectResponse:
    """Enable a notification and redirect back to the preview page."""
    if not svc.update(notification_id, enabled=True):
        raise HTTPException(status_code=404, detail="Notification not found")
    preview_url = request.url_for("get_notification_preview").include_query_params(n_ids=notification_id)
    response = RedirectResponse(url=str(preview_url), status_code=303)
    show_toast(response, "Benachrichtigung aktiviert")
    return response


@router.post(
    f"{Route.URL_NOTIFICATION_PREVIEW}/{{notification_id}}/disable",
    include_in_schema=False,
)
def disable_notification(
    svc: NotificationServiceDep,
    request: Request,
    notification_id: str,
    _auth: Annotated[str, Depends(PageAuth(min_role=AccessRole.NOTIFICATION_OPERATOR))],
) -> RedirectResponse:
    """Disable a notification and redirect back to the preview page."""
    if not svc.update(notification_id, enabled=False):
        raise HTTPException(status_code=404, detail="Notification not found")
    preview_url = request.url_for("get_notification_preview").include_query_params(n_ids=notification_id)
    response = RedirectResponse(url=str(preview_url), status_code=303)
    show_toast(response, "Benachrichtigung deaktiviert")
    return response


@router.post(
    f"{Route.URL_NOTIFICATION_PREVIEW}/{{notification_id}}/delete",
    include_in_schema=False,
)
def delete_notification_action(
    svc: NotificationServiceDep,
    notification_id: str,
    _auth: Annotated[str, Depends(PageAuth(min_role=AccessRole.NOTIFICATION_OPERATOR))],
) -> RedirectResponse:
    """Delete a notification and redirect back to the preview page."""
    if not svc.delete(notification_id):
        raise HTTPException(status_code=404, detail="Notification not found")
    response = RedirectResponse(
        url=f"{Route.URL_NOTIFICATION_PREVIEW}?n_ids={NotificationFilterId.ALL_ACTIVE}", status_code=303
    )
    show_toast(response, "Benachrichtigung gelöscht")
    return response


@router.get(
    Route.URL_NOTIFICATIONS_CONTENT,
    response_class=HTMLResponse,
    include_in_schema=False,
)
def get_notification_content(
    svc: NotificationServiceDep,
    request: Request,
    query: Annotated[NotificationQuery, Query()],
    api_key: Annotated[str | None, Depends(HybridAuth(auto_error=False))],
) -> HTMLResponse:
    """Return a server-rendered HTML fragment of active notifications for the main page."""
    n_ids = query.filter_unprotected_n_ids() if api_key is None else query.n_ids
    notifications = svc.get(n_ids)
    if not notifications:
        return HTMLResponse("")
    items = [(n, nh3.clean(markdown.markdown(n.message))) for n in notifications]
    return templates.TemplateResponse(
        request,
        "_notification_items.html",
        context={"items": items},
    )


@router.get(
    Route.URL_NOTIFICATION_PREVIEW_CONTENT,
    response_class=HTMLResponse,
    include_in_schema=False,
)
def get_notification_preview_content(
    svc: NotificationServiceDep,
    request: Request,
    query: Annotated[NotificationQuery, Query()],
    _auth: Annotated[str, Depends(PageAuth())],
) -> HTMLResponse:
    """Return a server-rendered HTML fragment of notifications with preview ID controls."""
    notifications = svc.get(query.n_ids)
    if not notifications:
        return HTMLResponse("")
    selected_filter = query.n_ids[0] if len(query.n_ids) == 1 else NotificationFilterId.ALL_ACTIVE
    items = [
        (n, nh3.clean(markdown.markdown(n.message)), f"{Route.URL_NOTIFICATION_PREVIEW}?n_ids={n.id}")
        for n in notifications
    ]
    return templates.TemplateResponse(
        request,
        "_notification_preview_items.html",
        context={
            "items": items,
            "selected_filter": selected_filter,
        },
    )
