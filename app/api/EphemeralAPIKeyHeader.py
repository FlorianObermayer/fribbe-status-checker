import logging

from fastapi import Request
from fastapi.security import APIKeyHeader

from app.api.EphemeralAPIKeyStore import EphemeralAPIKeyStore

logger = logging.getLogger("uvicorn.error")


class EphemeralAPIKeyHeader(APIKeyHeader):
    def __init__(
        self,
        *,
        bypass_on_empty_api_key_list: bool = False,
        name: str = "api_key",
        auto_error: bool = True,
    ):
        super().__init__(name=name, auto_error=auto_error)
        self._bypass_on_empty_api_key_list = bypass_on_empty_api_key_list

    def _should_bypass_authentication(self):
        return self._bypass_on_empty_api_key_list and EphemeralAPIKeyStore.is_empty()

    async def __call__(self, request: Request) -> str | None:
        if self._should_bypass_authentication():
            return None
        api_key = await super().__call__(request)
        if not api_key or not EphemeralAPIKeyStore.is_key_valid(api_key):
            api_key = None
            return self.check_api_key(api_key)
        return api_key
