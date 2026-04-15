from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.access_role import AccessRole
from app.api.hybrid_auth import HybridAuth
from app.api.requests import ConfigRequest
from app.api.responses import DetailsResponse
from app.api.schema import requires_auth_extra
from app.dependencies import InternalServiceDep
from app.services.presence_thresholds import PresenceThresholds

router = APIRouter(tags=["Internal"])


@router.get(
    "/api/internal/details",
    openapi_extra=requires_auth_extra(),
)
def details(
    svc: InternalServiceDep,
    _: Annotated[str, Depends(HybridAuth())],
) -> DetailsResponse:
    """Return detailed device-tracking information."""
    last_error = svc.get_last_error()
    wardens = svc.get_wardens_on_site()

    return DetailsResponse(
        last_updated=svc.get_last_updated(),
        last_error=last_error and str(last_error),
        wardens_on_site=[warden.name for warden in wardens],
        active_devices=svc.get_active_devices_ct(),
        first_device_on_site=svc.get_first_device_on_site(),
        last_device_on_site=svc.get_last_device_on_site(),
        last_service_start=svc.get_last_service_started(),
    )


@router.patch(
    "/api/internal/config",
    response_class=Response,
    tags=["Config"],
    openapi_extra=requires_auth_extra(),
)
async def config(request: ConfigRequest, _: Annotated[str, Depends(HybridAuth(min_role=AccessRole.ADMIN))]) -> Response:
    """Update presence detection thresholds."""
    if not any((request.threshold_min_non_empty_ct, request.threshold_min_many_ct)):
        return Response(status_code=304)  # ^= Not Modified

    thresholds = PresenceThresholds()

    if request.threshold_min_non_empty_ct:
        thresholds.min_non_empty_ct = request.threshold_min_non_empty_ct

    if request.threshold_min_many_ct:
        thresholds.min_many_ct = request.threshold_min_many_ct

    return Response()
