import logging
from typing import Optional
from fastapi import Request
from fastapi.security import APIKeyQuery
import json
import os
from datetime import datetime

logger = logging.getLogger("uvicorn.error")


class EphemeralAPIKeyQuery(APIKeyQuery):

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
    def _load_apikeys() -> list[dict[str, str]]:
        try:
            with open(os.environ["API_KEYS_PATH"]) as f:
                data = json.load(f)
                return data or []
        except Exception as e:
            logger.warning("CustomAPIKeyQuery - failed to load api keys")
            logger.error(f"Exception: {e}")
            return []

    _api_keys: list[dict[str, str]] = _load_apikeys()

    @staticmethod
    def refresh_api_keys():
        EphemeralAPIKeyQuery._api_keys = EphemeralAPIKeyQuery._load_apikeys()

    def _should_bypass_authentication(
        self,
    ):
        return (
            self._bypass_on_empty_api_key_list
            and len(EphemeralAPIKeyQuery._api_keys) == 0
        )

    def _is_key_valid(self, key: str) -> bool:
        now = datetime.now()
        for entry in EphemeralAPIKeyQuery._api_keys:
            if entry.get("key") == key:
                valid_until = entry.get("valid_until")
                if valid_until:
                    try:
                        valid_until_datetime = datetime.fromisoformat(valid_until)
                        if now > valid_until_datetime:
                            return False
                    except Exception:
                        return False
                return True
        return False

    async def __call__(self, request: Request) -> Optional[str]:

        if self._should_bypass_authentication():
            return None

        api_key = await super().__call__(request)

        if not api_key or not self._is_key_valid(api_key):
            api_key = None
            return self.check_api_key(api_key, self.auto_error)
