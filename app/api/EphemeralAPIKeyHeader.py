import logging
from typing import Optional
from fastapi import Request
from fastapi.security import APIKeyHeader
from datetime import datetime

from app.api.EphemeralAPIKeyStore import EphemeralAPIKeyStore

logger = logging.getLogger("uvicorn.error")


class EphemeralAPIKeyHeader(APIKeyHeader):
    _api_keys: list[dict[str, str]] = EphemeralAPIKeyStore.load_json()

    def __init__(
        self,
        *,
        bypass_on_empty_api_key_list: bool = False,
        name: str = "api_key",
        auto_error: bool = True,
    ):
        super().__init__(name=name, auto_error=auto_error)
        self._bypass_on_empty_api_key_list = bypass_on_empty_api_key_list

    @staticmethod
    def refresh_api_keys():
        EphemeralAPIKeyHeader._api_keys = EphemeralAPIKeyStore.load_json()

    def _should_bypass_authentication(self):
        return (
            self._bypass_on_empty_api_key_list
            and len(EphemeralAPIKeyHeader._api_keys) == 0
        )

    def _is_key_valid(self, key: str) -> bool:
        now = datetime.now()
        for entry in EphemeralAPIKeyHeader._api_keys:
            if entry.get("key") != key:
                continue
            valid_until = entry.get("valid_until")
            if not valid_until:
                return False
            try:
                valid_until_datetime = datetime.fromisoformat(valid_until)
                now_with_tz = (
                    now
                    if valid_until_datetime.tzinfo is None
                    else datetime.now(valid_until_datetime.tzinfo)
                )
                return valid_until_datetime >= now_with_tz
            except Exception as e:
                logger.warning(
                    f"CustomAPIKeyQuery::_is_key_valid - failed to compare datetime objects: {e}"
                )
                return False
        return False

    async def __call__(self, request: Request) -> Optional[str]:
        if self._should_bypass_authentication():
            return None
        api_key = await super().__call__(request)
        if not api_key or not self._is_key_valid(api_key):
            api_key = None
            return self.check_api_key(api_key, self.auto_error)
