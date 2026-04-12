"""Helpers for safely including sensitive tokens in log messages."""

from app import env

# Number of characters to reveal at the start of a token in log output.
# Enough to correlate across log lines; negligible exposure on MIN_TOKEN_LENGTH+ tokens.
_VISIBLE_PREFIX = max(8, env.MIN_TOKEN_LENGTH // 6)


def redact_key(key: str | None) -> str:
    """Return a redacted representation of *key* safe for use in log messages.

    Shows a short prefix followed by '…' so tokens can be correlated across
    log lines without exposing the full value.  Always returns a plain string
    so it can be passed directly as a ``%s`` log argument.

    Examples::

        redact_key(None)  # -> "<none>"
        redact_key("")  # -> "<empty>"
        redact_key("abcdef1234")  # -> "abcdef1…"
    """
    if key is None:
        return "<none>"
    if not key:
        return "<empty>"
    return key[:_VISIBLE_PREFIX] + "…"
