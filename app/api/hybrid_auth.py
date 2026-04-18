import hashlib
import logging
import secrets

from fastapi import HTTPException, Request
from starsessions import regenerate_session_id

from app.api.access_role import AccessRole
from app.api.ephemeral_api_key_header import EphemeralAPIKeyHeader
from app.api.ephemeral_api_key_store import EphemeralAPIKeyStore
from app.api.redact import redact
from app.config import cfg

_logger = logging.getLogger(__name__)


class AuthRedirectError(Exception):
    """Raised by PageAuth when the user is not authenticated. Handled by a registered exception handler that redirects to /auth."""

    def __init__(self, next_url: str) -> None:
        self.next_url = next_url


def resolve_session_subject(request: Request) -> tuple[str, AccessRole] | None:
    """Read session data from starsessions and validate it.

    Returns a ``(subject, role)`` tuple on success, or *None* after
    clearing an invalid / expired session.
    """
    kind = request.session.get("kind")

    if kind == "admin":
        admin_token = cfg.ADMIN_TOKEN
        if admin_token:
            subject_hash = request.session.get("subject_hash")
            if subject_hash and secrets.compare_digest(hashlib.sha256(admin_token.encode()).hexdigest(), subject_hash):
                return admin_token, AccessRole.ADMIN
        _logger.warning("Invalid admin session cleared (client %s)", request.client and request.client.host)
        request.session.clear()
        return None

    if kind == "api_key":
        subject = request.session.get("subject")
        if subject:
            role = EphemeralAPIKeyStore.get_valid_key_role(subject)
            if role is not None:
                return subject, role
        _logger.warning("Expired/invalid API key session cleared (client %s)", request.client and request.client.host)
        request.session.clear()
        return None

    if kind is not None:
        _logger.warning("Unknown session kind %r cleared (client %s)", kind, request.client and request.client.host)
        request.session.clear()

    return None


def create_session(request: Request, token: str) -> bool:
    """Populate *request.session* for *token*.  Returns True on success."""
    admin_token = cfg.ADMIN_TOKEN
    if admin_token and secrets.compare_digest(token, admin_token):
        request.session.clear()
        request.session["kind"] = "admin"
        request.session["subject_hash"] = hashlib.sha256(admin_token.encode()).hexdigest()
        _logger.info("Admin session created (client %s)", request.client and request.client.host)
        return True

    if not EphemeralAPIKeyStore.is_key_valid(token):
        _logger.warning(
            "Login failed — invalid token %s (client %s)", redact(token), request.client and request.client.host
        )
        return False

    request.session.clear()
    request.session["kind"] = "api_key"
    request.session["subject"] = token
    _logger.info("API key session created for %s (client %s)", redact(token), request.client and request.client.host)
    return True


def _resolve_header_role(api_key: str) -> AccessRole:
    """Determine the role for a credential supplied via the API key header."""
    admin_token = cfg.ADMIN_TOKEN
    if admin_token and secrets.compare_digest(api_key, admin_token):
        return AccessRole.ADMIN
    return EphemeralAPIKeyStore.get_valid_key_role(api_key) or AccessRole.READER


class HybridAuth:
    """Authenticate via server-side session or API key header.

    *min_role* controls the minimum :class:`AccessRole` required.
    Authenticated users whose role is below *min_role* receive a 403.
    """

    def __init__(
        self,
        *,
        min_role: AccessRole = AccessRole.READER,
        name: str = "api_key",
        auto_error: bool = True,
    ) -> None:
        self._min_role = min_role
        self._auto_error = auto_error
        self._name = name

    async def __call__(self, request: Request) -> str | None:
        """Resolve the authenticated subject from session or API key header."""
        # 1. Check server-side session (starsessions).
        result = resolve_session_subject(request)
        if result is not None:
            subject, role = result
            request.state.auth_via_session = True
            request.state.auth_role = role
            if role < self._min_role:
                raise HTTPException(status_code=403, detail="Insufficient permissions")
            return subject

        # Remove legacy auth material from older cookies.
        _legacy_keys = ("admin_token_hash", "api_key", "auth_session_id", "is_admin")
        if any(request.session.get(k) for k in _legacy_keys):
            request.session.clear()

        # 2. Check API key header and persist a session on success.
        api_key: str | None = await EphemeralAPIKeyHeader(
            name=self._name,
            auto_error=self._auto_error,
        )(request)
        if api_key:
            role = _resolve_header_role(api_key)
            request.state.auth_via_session = False
            request.state.auth_role = role
            create_session(request, api_key)
            regenerate_session_id(request)
            if role < self._min_role:
                raise HTTPException(status_code=403, detail="Insufficient permissions")
            return api_key

        if self._auto_error:
            raise HTTPException(status_code=401, detail="Not authenticated")

        return None


class PageAuth:
    """Auth dependency for HTML page routes. Redirects to /auth instead of returning 401."""

    def __init__(self, *, min_role: AccessRole = AccessRole.READER) -> None:
        self._min_role = min_role
        self._hybrid_auth = HybridAuth(auto_error=False)

    async def __call__(self, request: Request) -> str:
        """Resolve the authenticated subject or redirect to /auth."""
        api_key = await self._hybrid_auth(request)
        if api_key is None:
            next_path = request.url.path
            if request.url.query:
                next_path += "?" + request.url.query
            raise AuthRedirectError(next_url=next_path)
        role: AccessRole = getattr(request.state, "auth_role", AccessRole.READER)
        if role < self._min_role:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return api_key
