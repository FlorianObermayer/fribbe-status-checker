import logging
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import app.env as env
from app.api.Responses import ApiKey
from app.services.PersistentCollections import PersistentList

_write_lock = threading.Lock()

logger = logging.getLogger("uvicorn.error")


class EphemeralAPIKeyStore:
    @staticmethod
    def _get_path() -> str:
        return env.API_KEYS_PATH

    @staticmethod
    def load() -> list[ApiKey]:
        return PersistentList(EphemeralAPIKeyStore._get_path(), ApiKey).to_list()

    @staticmethod
    def save(keys: list[ApiKey]):
        try:
            persistent_list = PersistentList(EphemeralAPIKeyStore._get_path(), ApiKey)
            persistent_list.clear()
            persistent_list.extend(keys)

        except Exception:
            logger.exception("EphemeralAPIKeyStore - failed to save api keys")

    @staticmethod
    def is_empty() -> bool:
        return len(EphemeralAPIKeyStore.load()) == 0

    @staticmethod
    def append(key: ApiKey, *, require_empty: bool = False) -> bool:
        """Append a key under a write lock.

        If require_empty=True the append only proceeds when the store is still
        empty at the time the lock is held, closing the TOCTOU bootstrap window.
        Returns True if the key was stored, False if require_empty was set and
        the store was no longer empty.
        """
        with _write_lock:
            keys = EphemeralAPIKeyStore.load()
            if require_empty and keys:
                return False
            keys.append(key)
            EphemeralAPIKeyStore.save(keys)
            return True

    @staticmethod
    def is_key_valid(key: str | None) -> bool:
        log_key = key[:2] if key is not None else None

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
