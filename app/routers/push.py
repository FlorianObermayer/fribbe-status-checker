from fastapi import APIRouter, HTTPException

from app.api.requests import PatchPushTopicsRequest, PushAuthRequest, PushSubscribeRequest
from app.api.responses import PushStatusResponse, VapidKeyResponse
from app.dependencies import PushSubscriptionServiceDep
from app.services.push_subscription_service import PushSubscriptionService

router = APIRouter(prefix="/api/push", tags=["Push Notifications"])


@router.get("/vapid-key")
async def get_vapid_key(svc: PushSubscriptionServiceDep) -> VapidKeyResponse:
    """Return the public VAPID key for client-side subscription."""
    return VapidKeyResponse(public_key=svc.get_public_key())


@router.post("/status")
async def push_status(
    request: PushAuthRequest,
    svc: PushSubscriptionServiceDep,
) -> PushStatusResponse:
    """Return the subscription status for a given auth token."""
    try:
        PushSubscriptionService.validate_auth(request.auth)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    subscribed = svc.has(request.auth)
    subscribed_to = svc.get_topics(request.auth) if subscribed else []
    return PushStatusResponse(subscribed=subscribed, topics=subscribed_to)


@router.post("/subscribe", status_code=201)
async def push_subscribe(
    request: PushSubscribeRequest,
    svc: PushSubscriptionServiceDep,
) -> None:
    """Register a new push subscription."""
    try:
        PushSubscriptionService.validate_subscription(request.endpoint, request.p256dh, request.auth)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    svc.add(request.endpoint, request.p256dh, request.auth, request.topics)


@router.delete("/unsubscribe")
async def push_unsubscribe(
    request: PushAuthRequest,
    svc: PushSubscriptionServiceDep,
) -> None:
    """Remove a push subscription."""
    if not svc.remove(request.auth):
        raise HTTPException(status_code=404, detail="Subscription not found")


@router.patch("/topics")
async def update_push_topics(
    request: PatchPushTopicsRequest,
    svc: PushSubscriptionServiceDep,
) -> None:
    """Update the topics for an existing push subscription."""
    try:
        PushSubscriptionService.validate_auth(request.auth)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if not svc.update_topics(request.auth, request.topics):
        raise HTTPException(status_code=404, detail="Subscription not found")
