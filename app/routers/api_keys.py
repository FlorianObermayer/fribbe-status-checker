from datetime import datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException

from app import env
from app.api.access_role import AccessRole
from app.api.ephemeral_api_key_store import EphemeralAPIKeyStore, RemoveResult
from app.api.hybrid_auth import HybridAuth
from app.api.requests import CreateApiKeyRequest, DeleteApiKeyRequest
from app.api.responses import ApiKey, ApiKeys, MaskedApiKey
from app.api.schema import requires_auth_extra

router = APIRouter(prefix="/api/internal", tags=["API Keys"])

MIN_KEY_PREFIX_LENGTH = 5


@router.post(
    "/api_key",
    openapi_extra=requires_auth_extra(),
)
def create_api_key(
    request: CreateApiKeyRequest,
    _auth_subject: Annotated[str, Depends(HybridAuth(min_role=AccessRole.ADMIN))],
) -> ApiKey:
    """Create a new API key, store it in the JSON file, and return it.

    Requires ADMIN role authentication.

    - comment: Required comment for the key. Length constraints are validated by `CreateApiKeyRequest`.
    - valid_until: Optional datetime. Defaults to now plus `env.DEFAULT_API_KEY_VALIDITY_DAYS`.
    """
    valid_until = (
        request.valid_until or datetime.now(tz=ZoneInfo(env.TZ)) + timedelta(days=env.DEFAULT_API_KEY_VALIDITY_DAYS)
    ).replace(
        microsecond=0,
    )
    new_api_key = ApiKey.generate_new(request.comment, valid_until, request.role)
    appended = EphemeralAPIKeyStore.append(new_api_key)
    if not appended:
        raise HTTPException(status_code=500, detail="Failed to save API key")
    return new_api_key


@router.delete(
    "/api_key",
    openapi_extra=requires_auth_extra(),
)
def delete_api_key(
    request: DeleteApiKeyRequest,
    auth_subject: Annotated[str, Depends(HybridAuth(min_role=AccessRole.ADMIN))],
) -> None:
    """Delete an API key by its value or prefix (at least 5 characters). Only delete if there is a unique match."""
    authenticated_with_stored_key = EphemeralAPIKeyStore.get_valid_key_role(auth_subject) is not None
    if authenticated_with_stored_key and (auth_subject.startswith(request.key) or request.key.startswith(auth_subject)):
        raise HTTPException(status_code=403, detail="Cannot delete your own API key")
    result = EphemeralAPIKeyStore.remove(request.key)
    if result == RemoveResult.NOT_FOUND:
        raise HTTPException(status_code=404, detail="API key not found")
    if result == RemoveResult.AMBIGUOUS:
        raise HTTPException(status_code=409, detail="Ambiguous key prefix: multiple matches found")


@router.get(
    "/api_keys",
    openapi_extra=requires_auth_extra(),
)
def list_api_keys(auth_subject: Annotated[str | None, Depends(HybridAuth(min_role=AccessRole.ADMIN))]) -> ApiKeys:
    """Return all API keys as a masked list. Full key values are only shown at creation time."""
    keys = EphemeralAPIKeyStore.load()
    self_prefix = _resolve_self_prefix(auth_subject, keys) if auth_subject else None
    admin_prefix = MaskedApiKey.get_masked_prefix(env.ADMIN_TOKEN) if env.ADMIN_TOKEN else None
    return ApiKeys(
        api_keys=[MaskedApiKey.from_api_key(k) for k in keys],
        self_key_prefix=self_prefix,
        admin_token_prefix=admin_prefix,
    )


def _resolve_self_prefix(auth_subject: str, keys: list[ApiKey]) -> str | None:
    """Return the masked prefix for the caller's own key, or None if authenticated via ADMIN_TOKEN."""
    for k in keys:
        if k.key == auth_subject:
            return MaskedApiKey.from_api_key(k).key_prefix
    return None
