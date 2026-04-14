"""Extended CSRF middleware that accepts the token from a hidden form field in addition to the header.

The base starlette-csrf middleware only reads from the request header. For native HTML form
submissions (e.g. the signout button) the token must come from a hidden ``<input>``.
The field name matches the header name so there is a single constant across both paths.
"""

import functools

from starlette.requests import Request
from starlette.types import Message, Receive, Scope, Send
from starlette_csrf.middleware import CSRFMiddleware


class FormFieldCSRFMiddleware(CSRFMiddleware):
    """CSRFMiddleware that also accepts the token from a form field as a fallback."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process a request, validating the CSRF token from header or form field."""
        if scope["type"] not in ("http", "websocket"):  # pragma: no cover
            await self.app(scope, receive, send)
            return

        # Pass `receive` so that `request.form()` can read the body.
        request = Request(scope, receive)
        csrf_cookie = request.cookies.get(self.cookie_name)

        # Read the body eagerly so we can validate a form-field CSRF token.
        # The ASGI receive callable can only be consumed once, so after reading
        # we build a replay callable that returns the cached bytes to the downstream app.
        body: bytes = await request.body()

        _replayed = False

        async def replay_receive() -> Message:
            nonlocal _replayed
            if not _replayed:
                _replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        if self._url_is_required(request.url) or (
            request.method not in self.safe_methods
            and not self._url_is_exempt(request.url)
            and self._has_sensitive_cookies(request.cookies)
        ):
            submitted_csrf_token = await self._get_submitted_csrf_token(request)
            if (
                not csrf_cookie
                or not submitted_csrf_token
                or not self._csrf_tokens_match(csrf_cookie, submitted_csrf_token)
            ):
                response = self._get_error_response(request)
                await response(scope, replay_receive, send)
                return

        send = functools.partial(self.send, send=send, scope=scope)
        await self.app(scope, replay_receive, send)

    async def _get_submitted_csrf_token(self, request: Request) -> str | None:
        header_token = await super()._get_submitted_csrf_token(request)
        if header_token:
            return header_token
        # Fall back to a same-named form field for native HTML form submissions.
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            form = await request.form()
            return form.get(self.header_name)  # type: ignore[return-value]
        return None
