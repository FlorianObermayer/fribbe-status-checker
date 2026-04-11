from fastapi import APIRouter, Depends, HTTPException

from app.api.HybridAuth import HybridAuth
from app.api.Requests import CreateWardenRequest, UpdateWardenRequest
from app.api.Responses import WardenListResponse, WardenResponse
from app.api.Schema import requires_auth_extra
from app.services.internal.Model import Warden
from app.services.internal.WardenStore import WardenStore

router = APIRouter(prefix="/api/internal/wardens", tags=["Internal"])


@router.get("", response_model=WardenListResponse, openapi_extra=requires_auth_extra())
def list_wardens(_: str = Depends(HybridAuth())) -> WardenListResponse:
    wardens = WardenStore.get_instance().get_all()
    return WardenListResponse(wardens=[WardenResponse.from_warden(w) for w in wardens])


@router.post("", response_model=WardenResponse, status_code=201, openapi_extra=requires_auth_extra())
def create_warden(
    request: CreateWardenRequest,
    _: str = Depends(HybridAuth()),
) -> WardenResponse:
    warden = Warden(request.name, request.device_macs, request.device_names)
    try:
        WardenStore.get_instance().add(warden)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return WardenResponse.from_warden(warden)


@router.put("/{name}", response_model=WardenResponse, openapi_extra=requires_auth_extra())
def update_warden(
    name: str,
    request: UpdateWardenRequest,
    _: str = Depends(HybridAuth()),
) -> WardenResponse:
    store = WardenStore.get_instance()
    try:
        existing = store.by_name(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    updated = Warden(
        request.new_name if request.new_name is not None else existing.name,
        request.device_macs if request.device_macs is not None else existing.device_macs,
        request.device_names if request.device_names is not None else existing.device_names,
    )
    try:
        store.update(name, updated)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return WardenResponse.from_warden(updated)


@router.delete("/{name}", status_code=204, openapi_extra=requires_auth_extra())
def delete_warden(name: str, _: str = Depends(HybridAuth())) -> None:
    try:
        WardenStore.get_instance().delete(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
