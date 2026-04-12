import logging
import secrets

from fastapi import Request
from fastapi.security import APIKeyHeader

from app import env
from app.api.ephemeral_api_key_store import EphemeralAPIKeyStore

logger = logging.getLogger("uvicorn.error")


class EphemeralAPIKeyHeader(APIKeyHeader):
    """API key header that optionally bypasses auth when no keys exist."""

    def __init__(
        self,
        *,
        bypass_on_empty_api_key_list: bool = False,
        name: str = "api_key",
        auto_error: bool = True,
    ) -> None:
        super().__init__(name=name, auto_error=auto_error)
        self._bypass_on_empty_api_key_list = bypass_on_empty_api_key_list

    def _should_bypass_authentication(self) -> bool:
        return self._bypass_on_empty_api_key_list and EphemeralAPIKeyStore.is_empty() and not env.ADMIN_TOKEN

    async def __call__(self, request: Request) -> str | None:
        """Validate the API key from the request header."""
        if self._should_bypass_authentication():
            return None
        api_key = await super().__call__(request)
        if api_key and env.ADMIN_TOKEN and secrets.compare_digest(api_key, env.ADMIN_TOKEN):
            return api_key
        if not api_key or not EphemeralAPIKeyStore.is_key_valid(api_key):
            api_key = None
            return self.check_api_key(api_key)
        return api_key
