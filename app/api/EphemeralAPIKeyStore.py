import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from app.api.Responses import ApiKey
from app.services.PersistentCollections import PersistentList

logger = logging.getLogger("uvicorn.error")


class EphemeralAPIKeyStore:
    @staticmethod
    def _get_path() -> str:
        result = os.environ["API_KEYS_PATH"]
        return result

    @staticmethod
    def load() -> list[ApiKey]:
        return PersistentList(EphemeralAPIKeyStore._get_path(), ApiKey).to_list()

    @staticmethod
    def save(keys: list[ApiKey]):
        try:
            persistent_list = PersistentList(EphemeralAPIKeyStore._get_path(), ApiKey)
            persistent_list.clear()
            persistent_list.extend(keys)

        except Exception as e:
            logger.error(f"EphemeralAPIKeyStore - failed to save api keys: {e}")

    @staticmethod
    def is_empty() -> bool:
        return len(EphemeralAPIKeyStore.load()) == 0

    @staticmethod
    def is_key_valid(key: str | None) -> bool:
        log_key = key[:4] if key is not None else None

        if key is None:
            logger.info(f"EphemeralAPIKeyStore::is_key_valid(api_key={log_key}...) - key is None)")
            return False
        now = datetime.now(tz=ZoneInfo("Europe/Berlin"))
        entries = EphemeralAPIKeyStore.load()
        for entry in entries:
            if entry.key != key:
                continue

            logger.info(
                f"EphemeralAPIKeyStore::is_key_valid(api_key={log_key}...) - found key (comment: {entry.comment or 'None'})"
            )
            valid_until = entry.valid_until
            if not valid_until:
                logger.error(
                    f"EphemeralAPIKeyStore::is_key_valid(api_key={log_key}...) - key is missing [valid_until] property"
                )
                return False
            try:
                now_with_tz = now if valid_until.tzinfo is None else datetime.now(valid_until.tzinfo)
                if valid_until >= now_with_tz:
                    logger.info(f"EphemeralAPIKeyStore::is_key_valid(api_key={log_key}...) - key is valid")
                    return True

                logger.warning(f"EphemeralAPIKeyStore::is_key_valid(api_key={log_key}...) - key is outdated")
                return False
            except Exception as e:
                logger.warning(
                    f"EphemeralAPIKeyStore::is_key_valid(api_key={log_key}...) - failed to compare datetime objects: {e}"
                )
                return False
        logger.warning(f"EphemeralAPIKeyStore::is_key_valid(api_key={log_key}...) - key not found in registered keys")
        return False
