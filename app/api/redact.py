"""Helpers for safely including sensitive tokens in log messages."""

import hashlib
import hmac
import secrets

# Random salt generated once per process. Prevents reverse-lookup of hashes
# across restarts and makes log hashes unverifiable without the running instance.
_SALT: bytes = secrets.token_bytes(32)


def redact(value: str | None) -> str:
    """Return a redacted representation of *value* safe for use in log messages.

    Returns a short hex digest of an HMAC-SHA-256 keyed with a per-run random
    salt, so sensitive values can be correlated across log lines within one
    application run without exposing any sensitive data or allowing offline
    reversal.  Always returns a plain string so it can be passed directly as a
    ``%s`` log argument.

    Examples::

        redact(None)  # -> "<none>"
        redact("")  # -> "<empty>"
        redact("abc")  # -> "[hash:a3f1c2d4]"
    """
    if value is None:
        return "<none>"
    if not value:
        return "<empty>"
    digest = hmac.new(_SALT, value.encode(), hashlib.sha256).hexdigest()[:8]
    return f"[hash:{digest}]"
