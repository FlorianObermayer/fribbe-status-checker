from typing import Annotated

import markdown
import nh3
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.api.hybrid_auth import HybridAuth
from app.api.requests import NOTIFICATION_FILTERS, NotificationQuery, PostNotificationRequest, UpdateNotificationRequest
from app.api.responses import (
    DeletedResponse,
    NotificationFilterResponse,
    NotificationResponse,
    PostNotificationResponse,
)
from app.api.schema import requires_auth_extra
from app.dependencies import NotificationServiceDep

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get(
    "/filters",
    openapi_extra=requires_auth_extra(),
)
async def get_notification_filters(_: Annotated[str, Depends(HybridAuth())]) -> list[NotificationFilterResponse]:
    """Return the available notification filter options."""
    return [NotificationFilterResponse(**f) for f in NOTIFICATION_FILTERS]


@router.get(
    "/list",
    openapi_extra=requires_auth_extra(),
)
async def list_notifications(
    svc: NotificationServiceDep,
    _: Annotated[str, Depends(HybridAuth())],
) -> list[NotificationResponse]:
    """Return all stored notifications."""
    return [NotificationResponse.from_notification(n) for n in svc.list_all()]


@router.get(
    "",
    response_class=HTMLResponse,
    tags=["HTML"],
    openapi_extra=requires_auth_extra(),
)
async def get_notifications_as_html(
    svc: NotificationServiceDep,
    request: Annotated[NotificationQuery, Query()],
    api_key: Annotated[str | None, Depends(HybridAuth(auto_error=False))],
) -> HTMLResponse:
    """Return active notifications as rendered HTML."""
    # Without an API Key, only allow "public" queries
    n_ids = request.filter_unprotected_n_ids() if api_key is None else request.n_ids

    notifications = svc.get(n_ids)

    if len(notifications) == 0:
        return HTMLResponse("")

    # Combine all queried messages as markdown, convert to sanitized HTML
    rendered_html = "\n<hr/>".join(
        [f'<div data-notification-id="{n.id}">{nh3.clean(markdown.markdown(n.message))}</div>' for n in notifications],
    )
    return HTMLResponse(rendered_html)


@router.post(
    "",
    openapi_extra=requires_auth_extra(),
)
async def post_notification(
    svc: NotificationServiceDep,
    request: PostNotificationRequest,
    _: Annotated[str, Depends(HybridAuth())],
) -> PostNotificationResponse:
    """Create a new notification."""
    notification_id = svc.add(request.message, request.valid_from, request.valid_until, enabled=request.enabled)
    return PostNotificationResponse(notification_id=notification_id)


@router.put(
    "/{notification_id}",
    openapi_extra=requires_auth_extra(),
)
async def update_notification(
    svc: NotificationServiceDep,
    notification_id: str,
    request: UpdateNotificationRequest,
    _: Annotated[str, Depends(HybridAuth())],
) -> None:
    """Update an existing notification."""
    if not svc.update(
        notification_id,
        enabled=request.enabled,
        valid_from=request.valid_from,
        valid_until=request.valid_until,
    ):
        raise HTTPException(status_code=404, detail="Notification not found")


@router.delete(
    "/{notification_id}",
    openapi_extra=requires_auth_extra(),
)
async def delete_notification(
    svc: NotificationServiceDep,
    notification_id: str,
    _: Annotated[str, Depends(HybridAuth())],
) -> None:
    """Delete a notification by ID."""
    if not svc.delete(notification_id):
        raise HTTPException(status_code=404, detail="Notification not found")


@router.delete(
    "",
    openapi_extra=requires_auth_extra(),
)
async def delete_notifications(
    svc: NotificationServiceDep,
    request: Annotated[NotificationQuery, Query()],
    _: Annotated[str, Depends(HybridAuth())],
) -> DeletedResponse:
    """Delete notifications matching the given filter."""
    count = svc.delete_many(request.n_ids)
    if count == 0:
        raise HTTPException(status_code=404, detail="No matching notifications found")
    return DeletedResponse(deleted=count)
