import json
import logging
import os
from typing import List

from app.api.Responses import ApiKey

logger = logging.getLogger("uvicorn.error")


class EphemeralAPIKeyStore:
    @staticmethod
    def _get_path() -> str:
        return os.environ["API_KEYS_PATH"]

    @staticmethod
    def load() -> List[ApiKey]:
        try:
            with open(EphemeralAPIKeyStore._get_path()) as f:
                data = json.load(f)
                return data or []
        except Exception as e:
            logger.warning(f"EphemeralAPIKeyStore - failed to load api keys: {e}")
            return []

    @staticmethod
    def load_json() -> List[dict[str, str]]:
        try:
            with open(EphemeralAPIKeyStore._get_path()) as f:
                data = json.load(f)
                return data or []
        except Exception as e:
            logger.warning(f"EphemeralAPIKeyStore - failed to load api keys: {e}")
            return []

    @staticmethod
    def save(keys: List[dict[str, str]] | List[ApiKey]):
        try:
            with open(EphemeralAPIKeyStore._get_path(), "w") as f:
                json.dump(keys, f, indent=2)
        except Exception as e:
            logger.error(f"EphemeralAPIKeyStore - failed to save api keys: {e}")
