"""Shared template instance, base context processor, and toast helper for page routers."""

import json
from typing import Literal

from fastapi import Request, Response
from fastapi.templating import Jinja2Templates

from app import env
from app.api.requests import NotificationFilterId
from app.routers.nav_context import Route


def _base_context(request: Request) -> dict[str, object]:
    flash_message, flash_type = _read_toast_from_request(request)
    return {
        "version": env.BUILD_VERSION,
        "content_hash_version": env.CONTENT_HASH_VERSION,
        # Page URLs (used in navigation, forms, links)
        "url_index": Route.URL_INDEX,
        "url_legal": Route.URL_LEGAL,
        "url_auth": Route.URL_AUTH,
        "url_signout": Route.URL_SIGNOUT,
        "url_notification_create": Route.URL_NOTIFICATION_CREATE,
        "url_preview": f"{Route.URL_NOTIFICATION_PREVIEW}?n_ids={NotificationFilterId.ALL_ACTIVE}",
        "url_notification_preview": Route.URL_NOTIFICATION_PREVIEW,
        # HTML fragment URLs (polled by JS)
        "url_status_content": Route.URL_STATUS_CONTENT,
        "url_notifications_content": Route.URL_NOTIFICATIONS_CONTENT,
        "url_notification_preview_content": Route.URL_NOTIFICATION_PREVIEW_CONTENT,
        # API URLs (called from JS)
        "url_api_push_vapid_key": Route.URL_API_PUSH_VAPID_KEY,
        "url_api_push_status": Route.URL_API_PUSH_STATUS,
        "url_api_push_subscribe": Route.URL_API_PUSH_SUBSCRIBE,
        "url_api_push_unsubscribe": Route.URL_API_PUSH_UNSUBSCRIBE,
        "url_api_push_topics": Route.URL_API_PUSH_TOPICS,
        # CSRF token for native HTML form submissions (signout form).
        # The field name matches the header name so FormFieldCSRFMiddleware can validate both paths.
        "csrf_token": request.cookies.get("csrftoken", ""),
        "csrf_field_name": "x-csrf-token",
        # Flash message set by POST-redirect routes; auto-expires via max_age.
        "flash_message": flash_message,
        "flash_type": flash_type or "success",
        "toast_display_ms": env.TOAST_DISPLAY_SECONDS * 1000,
    }


templates = Jinja2Templates(directory="app/templates", context_processors=[_base_context])


def show_toast(response: Response, message: str, status: Literal["success", "error"] = "success") -> None:
    """Set a one-time toast message to be rendered on the next page."""
    flash_data = json.dumps({"message": message, "type": status})
    response.set_cookie(
        "flash",
        flash_data,
        max_age=env.TOAST_DISPLAY_SECONDS,
        httponly=True,
        secure=env.HTTPS_ONLY,
        samesite="strict",
    )


def _read_toast_from_request(request: Request) -> tuple[str, str]:
    """Read and return any toast message from the request cookies."""
    flash_raw = request.cookies.get("flash", "")
    flash_message = ""
    flash_type = "success"
    if flash_raw:
        try:
            flash_data = json.loads(flash_raw)
            flash_message = flash_data.get("message", "")
            flash_type = flash_data.get("type", "success")
        except (json.JSONDecodeError, TypeError):
            pass
    return flash_message, flash_type
