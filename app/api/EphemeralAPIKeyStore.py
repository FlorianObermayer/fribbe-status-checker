import logging
import os
from typing import List

from app.api.Responses import ApiKey
from app.services.PersistentCollections import PersistentList

logger = logging.getLogger("uvicorn.error")


class EphemeralAPIKeyStore:
    @staticmethod
    def _get_path() -> str:
        return os.environ["API_KEYS_PATH"]

    @staticmethod
    def load() -> List[ApiKey]:
        return PersistentList(EphemeralAPIKeyStore._get_path(), ApiKey).to_list()

    @staticmethod
    def save(keys: List[ApiKey]):
        try:
            persistent_list = PersistentList(EphemeralAPIKeyStore._get_path(), ApiKey)
            persistent_list.clear()
            persistent_list.extend(keys)

        except Exception as e:
            logger.error(f"EphemeralAPIKeyStore - failed to save api keys: {e}")
