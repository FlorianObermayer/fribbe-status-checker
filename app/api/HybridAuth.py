import hashlib
import secrets

from fastapi import HTTPException, Request
from starsessions import regenerate_session_id

import app.env as env
from app.api.EphemeralAPIKeyHeader import EphemeralAPIKeyHeader
from app.api.EphemeralAPIKeyStore import EphemeralAPIKeyStore


class AuthRedirectException(Exception):
    """Raised by PageAuth when the user is not authenticated. Handled by a registered exception handler that redirects to /auth."""

    def __init__(self, next_url: str):
        self.next_url = next_url


def resolve_session_subject(request: Request) -> str | None:
    """Read session data from starsessions and validate it.

    Returns the authenticated subject (admin token value or API key) on
    success, or *None* after clearing an invalid / expired session.
    """
    kind = request.session.get("kind")

    if kind == "admin":
        admin_token = env.ADMIN_TOKEN
        if admin_token:
            subject_hash = request.session.get("subject_hash")
            if subject_hash and secrets.compare_digest(hashlib.sha256(admin_token.encode()).hexdigest(), subject_hash):
                return admin_token
        request.session.clear()
        return None

    if kind == "api_key":
        subject = request.session.get("subject")
        if subject and EphemeralAPIKeyStore.is_key_valid(subject):
            return subject
        request.session.clear()
        return None

    if kind is not None:
        request.session.clear()

    return None


def create_session(request: Request, token: str) -> bool:
    """Populate *request.session* for *token*.  Returns True on success."""
    admin_token = env.ADMIN_TOKEN
    if admin_token and secrets.compare_digest(token, admin_token):
        request.session.clear()
        request.session["kind"] = "admin"
        request.session["subject_hash"] = hashlib.sha256(admin_token.encode()).hexdigest()
        return True

    if not EphemeralAPIKeyStore.is_key_valid(token):
        return False

    request.session.clear()
    request.session["kind"] = "api_key"
    request.session["subject"] = token
    return True


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
        # 1. Check server-side session (starsessions).
        session_subject = resolve_session_subject(request)
        if session_subject is not None:
            request.state.auth_via_session = True
            return session_subject

        # Remove legacy auth material from older cookies.
        _legacy_keys = ("admin_token_hash", "api_key", "auth_session_id", "is_admin")
        if any(request.session.get(k) for k in _legacy_keys):
            request.session.clear()

        # 2. Check API key header and persist a session on success.
        admin_token = env.ADMIN_TOKEN
        # Bootstrap bypass: store is empty and no ADMIN_TOKEN configured — allow through
        if self._bypass_on_empty_api_key_list and EphemeralAPIKeyStore.is_empty() and not admin_token:
            return None

        api_key: str | None = await EphemeralAPIKeyHeader(
            name=self._name,
            bypass_on_empty_api_key_list=self._bypass_on_empty_api_key_list,
            auto_error=self._auto_error,
        )(request)
        if api_key:
            request.state.auth_via_session = False
            create_session(request, api_key)
            regenerate_session_id(request)
            return api_key

        if self._auto_error:
            raise HTTPException(status_code=401, detail="Not authenticated")

        return None


class PageAuth:
    """Auth dependency for HTML page routes. Redirects to /auth instead of returning 401."""

    def __init__(self) -> None:
        self._hybrid_auth = HybridAuth(auto_error=False)

    async def __call__(self, request: Request) -> str:
        api_key = await self._hybrid_auth(request)
        if api_key is None:
            next_path = request.url.path
            if request.url.query:
                next_path += "?" + request.url.query
            raise AuthRedirectException(next_url=next_path)
        return api_key
