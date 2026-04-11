from typing import Annotated

import markdown
import nh3
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.api.HybridAuth import HybridAuth
from app.api.Requests import NOTIFICATION_FILTERS, NotificationQuery, PostNotificationRequest, UpdateNotificationRequest
from app.api.Responses import (
    DeletedResponse,
    NotificationFilterResponse,
    NotificationResponse,
    PostNotificationResponse,
)
from app.api.Schema import requires_auth_extra
from app.dependencies import NotificationServiceDep

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get(
    "/filters",
    response_model=list[NotificationFilterResponse],
    openapi_extra=requires_auth_extra(),
)
async def get_notification_filters(_: str = Depends(HybridAuth())) -> list[NotificationFilterResponse]:
    return [NotificationFilterResponse(**f) for f in NOTIFICATION_FILTERS]


@router.get(
    "/list",
    response_model=list[NotificationResponse],
    openapi_extra=requires_auth_extra(),
)
async def list_notifications(
    svc: NotificationServiceDep,
    _: str = Depends(HybridAuth()),
) -> list[NotificationResponse]:
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
    api_key: str | None = Depends(HybridAuth(auto_error=False)),
) -> HTMLResponse:
    # Without an API Key, only allow "public" queries
    n_ids = request.filter_unprotected_n_ids() if api_key is None else request.n_ids

    notifications = svc.get(n_ids)

    if len(notifications) == 0:
        return HTMLResponse("")

    # Combine all queried messages as markdown, convert to sanitised HTML
    rendered_html = "\n<hr/>".join(
        [f'<div data-notification-id="{n.id}">{nh3.clean(markdown.markdown(n.message))}</div>' for n in notifications]
    )
    return HTMLResponse(rendered_html)


@router.post(
    "",
    response_model=PostNotificationResponse,
    openapi_extra=requires_auth_extra(),
)
async def post_notification(
    svc: NotificationServiceDep,
    request: PostNotificationRequest,
    _: str = Depends(HybridAuth()),
) -> PostNotificationResponse:
    notification_id = svc.add(request.message, request.valid_from, request.valid_until, request.enabled)
    return PostNotificationResponse(notification_id=notification_id)


@router.put(
    "/{notification_id}",
    openapi_extra=requires_auth_extra(),
)
async def update_notification(
    svc: NotificationServiceDep,
    notification_id: str,
    request: UpdateNotificationRequest,
    _: str = Depends(HybridAuth()),
) -> None:
    if not svc.update(notification_id, request.enabled, request.valid_from, request.valid_until):
        raise HTTPException(status_code=404, detail="Notification not found")


@router.delete(
    "/{notification_id}",
    openapi_extra=requires_auth_extra(),
)
async def delete_notification(
    svc: NotificationServiceDep,
    notification_id: str,
    _: str = Depends(HybridAuth()),
) -> None:
    if not svc.delete(notification_id):
        raise HTTPException(status_code=404, detail="Notification not found")


@router.delete(
    "",
    response_model=DeletedResponse,
    openapi_extra=requires_auth_extra(),
)
async def delete_notifications(
    svc: NotificationServiceDep,
    request: Annotated[NotificationQuery, Query()],
    _: str = Depends(HybridAuth()),
) -> DeletedResponse:
    count = svc.delete_many(request.n_ids)
    if count == 0:
        raise HTTPException(status_code=404, detail="No matching notifications found")
    return DeletedResponse(deleted=count)
