import logging
import secrets

from fastapi import Request
from fastapi.security import APIKeyHeader

from app.api.ephemeral_api_key_store import EphemeralAPIKeyStore
from app.config import cfg

logger = logging.getLogger("uvicorn.error")


class EphemeralAPIKeyHeader(APIKeyHeader):
    """API key header that validates against the ephemeral key store."""

    def __init__(
        self,
        *,
        name: str = "api_key",
        auto_error: bool = True,
    ) -> None:
        super().__init__(name=name, auto_error=auto_error)

    async def __call__(self, request: Request) -> str | None:
        """Validate the API key from the request header."""
        api_key = await super().__call__(request)
        if api_key and cfg.ADMIN_TOKEN and secrets.compare_digest(api_key, cfg.ADMIN_TOKEN):
            return api_key
        if not api_key or not EphemeralAPIKeyStore.is_key_valid(api_key):
            api_key = None
            return self.check_api_key(api_key)
        return api_key
