import logging
import secrets
import threading
from datetime import datetime
from enum import Enum
from zoneinfo import ZoneInfo

from app import env
from app.api.access_role import AccessRole
from app.api.redact import redact_key
from app.api.responses import ApiKey
from app.services.persistent_collections import PersistentList

_write_lock = threading.Lock()

logger = logging.getLogger("uvicorn.error")


class RemoveResult(Enum):
    """Result of an API key removal operation."""

    DELETED = "deleted"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


class EphemeralAPIKeyStore:
    """Thread-safe persistent store for ephemeral API keys."""

    @staticmethod
    def _get_path() -> str:
        return env.API_KEYS_PATH

    @staticmethod
    def load() -> list[ApiKey]:
        """Load all API keys from disk."""
        return PersistentList(EphemeralAPIKeyStore._get_path(), ApiKey).to_list()

    @staticmethod
    def save(keys: list[ApiKey]) -> None:
        """Overwrite the key store with the given list."""
        persistent_list = PersistentList(EphemeralAPIKeyStore._get_path(), ApiKey)
        persistent_list.clear()
        persistent_list.extend(keys)

    @staticmethod
    def is_empty() -> bool:
        """Return True if the key store contains no keys."""
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
            try:
                EphemeralAPIKeyStore.save(keys)
            except Exception:
                logger.exception("EphemeralAPIKeyStore - failed to save api keys")
                return False
            return True

    @staticmethod
    def remove(key_prefix: str) -> RemoveResult:
        """Remove a key whose value starts with *key_prefix* under the write lock."""
        with _write_lock:
            keys = EphemeralAPIKeyStore.load()
            matches = [k for k in keys if k.key.startswith(key_prefix)]
            if len(matches) == 0:
                return RemoveResult.NOT_FOUND
            if len(matches) > 1:
                return RemoveResult.AMBIGUOUS
            key_to_delete = matches[0].key
            EphemeralAPIKeyStore.save([k for k in keys if k.key != key_to_delete])
            return RemoveResult.DELETED

    @staticmethod
    def is_key_valid(key: str | None) -> bool:
        """Check whether a key is present and not expired."""
        if key is None:
            logger.info("EphemeralAPIKeyStore::is_key_valid(api_key=%s) - key is None", redact_key(key))
            return False
        now = datetime.now(tz=ZoneInfo("Europe/Berlin"))
        entries = EphemeralAPIKeyStore.load()
        for entry in entries:
            if not secrets.compare_digest(entry.key, key):
                continue

            logger.info(
                "EphemeralAPIKeyStore::is_key_valid(api_key=%s) - found key (comment: %s)",
                redact_key(key),
                entry.comment or "None",
            )
            valid_until = entry.valid_until
            if not valid_until:
                logger.error(
                    "EphemeralAPIKeyStore::is_key_valid(api_key=%s) - key is missing [valid_until] property",
                    redact_key(key),
                )
                return False
            try:
                now_with_tz = now if valid_until.tzinfo is None else datetime.now(valid_until.tzinfo)
                if valid_until >= now_with_tz:
                    logger.info("EphemeralAPIKeyStore::is_key_valid(api_key=%s) - key is valid", redact_key(key))
                    return True

                logger.warning("EphemeralAPIKeyStore::is_key_valid(api_key=%s) - key is outdated", redact_key(key))
                return False
            except (TypeError, OverflowError) as e:
                logger.warning(
                    "EphemeralAPIKeyStore::is_key_valid(api_key=%s) - failed to compare datetime objects: %s",
                    redact_key(key),
                    e,
                )
                return False
        logger.warning(
            "EphemeralAPIKeyStore::is_key_valid(api_key=%s) - key not found in registered keys", redact_key(key)
        )
        return False

    @staticmethod
    def get_valid_key_role(key: str | None) -> AccessRole | None:
        """Return the role for a valid (present and not expired) API key, or None."""
        if key is None:
            return None
        now = datetime.now(tz=ZoneInfo("Europe/Berlin"))
        entries = EphemeralAPIKeyStore.load()
        for entry in entries:
            if not secrets.compare_digest(entry.key, key):
                continue
            valid_until = entry.valid_until
            if not valid_until:
                return None
            try:
                now_with_tz = now if valid_until.tzinfo is None else datetime.now(valid_until.tzinfo)
                if valid_until >= now_with_tz:
                    return entry.role
                return None
            except (TypeError, OverflowError):
                return None
        return None
