from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException

from app.api.EphemeralAPIKeyStore import EphemeralAPIKeyStore, RemoveResult
from app.api.HybridAuth import HybridAuth
from app.api.Requests import CreateApiKeyRequest, DeleteApiKeyRequest
from app.api.Responses import ApiKey, ApiKeys, MaskedApiKey
from app.api.Schema import requires_auth_extra

router = APIRouter(prefix="/api/internal", tags=["API Keys"])


@router.post(
    "/api_key",
    response_model=ApiKey,
    openapi_extra=requires_auth_extra(),
)
def create_api_key(
    request: CreateApiKeyRequest,
    auth_subject: str | None = Depends(HybridAuth(bypass_on_empty_api_key_list=True)),
) -> ApiKey:
    """
    Create a new API key, store it in the JSON file, and return it. Requires valid API key to create or no API keys to begin with at all (admin setup mode)
    - comment: Optional comment for the key
    - valid_until: Optional datetime (default: 6 months from now)
    """
    valid_until = (request.valid_until or datetime.now(tz=ZoneInfo("Europe/Berlin")) + timedelta(days=180)).replace(
        microsecond=0
    )
    new_api_key = ApiKey.generate_new(request.comment, valid_until)
    bootstrap_mode = auth_subject is None
    appended = EphemeralAPIKeyStore.append(new_api_key, require_empty=bootstrap_mode)
    if not appended:
        raise HTTPException(status_code=409, detail="Bootstrap window closed: store is no longer empty")
    return new_api_key


@router.delete(
    "/api_key",
    openapi_extra=requires_auth_extra(),
)
def delete_api_key(
    request: DeleteApiKeyRequest,
    _: str = Depends(HybridAuth()),
) -> None:
    """
    Deletes an API key by its value or prefix (at least 5 characters). Only deletes if there is a unique match.
    """
    if len(request.key) < 5:
        raise HTTPException(status_code=400, detail="Key prefix must be at least 5 characters long")
    result = EphemeralAPIKeyStore.remove(request.key)
    if result == RemoveResult.NOT_FOUND:
        raise HTTPException(status_code=404, detail="Api key not found")
    if result == RemoveResult.AMBIGUOUS:
        raise HTTPException(status_code=409, detail="Ambiguous key prefix: multiple matches found")


@router.get(
    "/api_keys",
    response_model=ApiKeys,
    openapi_extra=requires_auth_extra(),
)
def list_api_keys(_: str | None = Depends(HybridAuth())) -> ApiKeys:
    """
    Returns all API keys as a masked list. Full key values are only shown at creation time.
    """
    keys = EphemeralAPIKeyStore.load()
    return ApiKeys(api_keys=[MaskedApiKey.from_api_key(k) for k in keys])
