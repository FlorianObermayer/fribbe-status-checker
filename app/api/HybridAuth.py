import secrets

from fastapi import HTTPException, Request

import app.env as env
from app.api.EphemeralAPIKeyHeader import EphemeralAPIKeyHeader
from app.api.EphemeralAPIKeyStore import EphemeralAPIKeyStore


class AuthRedirectException(Exception):
    """Raised by PageAuth when the user is not authenticated. Handled by a registered exception handler that redirects to /auth."""

    def __init__(self, next_url: str):
        self.next_url = next_url


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
        # 1. Check Session and remove if not valid anymore
        admin_token = env.ADMIN_TOKEN

        # 1a. Admin session marker - token value is never stored in the session cookie
        if request.session.get("is_admin"):
            if admin_token:
                return admin_token
            # ADMIN_TOKEN was removed from env; invalidate the stale marker
            request.session.pop("is_admin", None)

        # 1b. Ephemeral key in session
        api_key = request.session.get("api_key")
        if EphemeralAPIKeyStore.is_key_valid(api_key):
            return api_key
        elif api_key:
            request.session.clear()

        # 2. Check API Key Header
        api_key: str | None = await EphemeralAPIKeyHeader(
            name=self._name,
            bypass_on_empty_api_key_list=self._bypass_on_empty_api_key_list,
            auto_error=self._auto_error,
        )(request)
        if api_key:
            if admin_token and secrets.compare_digest(api_key, admin_token):
                # Store a boolean marker only - never persist the token value into the cookie
                request.session["is_admin"] = True
            else:
                request.session["api_key"] = api_key
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
