from fastapi import HTTPException, Request

from app.api.EphemeralAPIKeyHeader import EphemeralAPIKeyHeader
from app.api.EphemeralAPIKeyStore import EphemeralAPIKeyStore


class HybridAuth:
    def __init__(
        self,
        *,
        bypass_on_empty_api_key_list: bool = False,
        name: str = "api_key",
        auto_error: bool = True,
    ):
        self._auto_error = auto_error
        self._name = name
        self._bypass_on_empty_api_key_list = bypass_on_empty_api_key_list

    async def __call__(self, request: Request) -> str | None:
        # 1. Check Session and remove if not valid anymore
        api_key = request.session.get("api_key")
        if EphemeralAPIKeyStore.is_key_valid(api_key):
            return api_key
        else:
            request.session.clear()

        # 2. Check API Key Header
        api_key: str | None = await EphemeralAPIKeyHeader(
            name=self._name,
            bypass_on_empty_api_key_list=self._bypass_on_empty_api_key_list,
            auto_error=self._auto_error,
        )(request)
        if api_key:
            request.session["api_key"] = api_key
            return api_key

        if self._auto_error:
            raise HTTPException(status_code=401, detail="Not authenticated")

        return None
