from fastapi import APIRouter, HTTPException

from app.api.Requests import PushAuthRequest, PushSubscribeRequest
from app.api.Responses import PushStatusResponse, VapidKeyResponse
from app.dependencies import PushSubscriptionServiceDep
from app.services.PushSubscriptionService import PushSubscriptionService

router = APIRouter(prefix="/api/push", tags=["Push Notifications"])


@router.get("/vapid-key", response_model=VapidKeyResponse)
async def get_vapid_key(svc: PushSubscriptionServiceDep) -> VapidKeyResponse:
    return VapidKeyResponse(public_key=svc.get_public_key())


@router.post("/status", response_model=PushStatusResponse)
async def push_status(
    request: PushAuthRequest,
    svc: PushSubscriptionServiceDep,
) -> PushStatusResponse:
    try:
        PushSubscriptionService.validate_auth(request.auth)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return PushStatusResponse(subscribed=svc.has(request.auth))


@router.post("/subscribe", status_code=201)
async def push_subscribe(
    request: PushSubscribeRequest,
    svc: PushSubscriptionServiceDep,
) -> None:
    try:
        PushSubscriptionService.validate_subscription(request.endpoint, request.p256dh, request.auth)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    svc.add(request.endpoint, request.p256dh, request.auth)


@router.delete("/unsubscribe")
async def push_unsubscribe(
    request: PushAuthRequest,
    svc: PushSubscriptionServiceDep,
) -> None:
    if not svc.remove(request.auth):
        raise HTTPException(status_code=404, detail="Subscription not found")
