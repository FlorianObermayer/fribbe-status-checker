"""Auth-aware navigation context for Jinja2 page templates.

:class:`NavContext` is unpacked directly into :func:`~fastapi.templating.Jinja2Templates.TemplateResponse`
context dicts and drives ``_floating_btn_group.html``.

Use the :func:`when_signed_in` and :func:`when_role` helpers to express role-dependent
visibility as predicates rather than inline boolean logic in each route handler.
"""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import InitVar, dataclass, field, fields
from enum import StrEnum

from fastapi import Request

from app.api.access_role import AccessRole
from app.api.hybrid_auth import resolve_session_subject

type NavPredicate = Callable[[AccessRole | None], bool]


class Route(StrEnum):
    """Centralized route definitions for consistent URL references across the codebase and templates."""

    # Page routes
    URL_INDEX = "/"
    URL_LEGAL = "/legal"
    URL_AUTH = "/auth"
    URL_SIGNOUT = "/signout"
    URL_NOTIFICATION_CREATE = "/notification-create"
    URL_NOTIFICATION_PREVIEW = "/preview/notifications"
    URL_API_KEYS = "/api-keys"

    # HTML fragment routes (polled by JS)
    URL_STATUS_CONTENT = "/status/content"
    URL_NOTIFICATIONS_CONTENT = "/notifications/content"
    URL_NOTIFICATION_PREVIEW_CONTENT = "/preview/notifications/content"

    # API routes (called from JS)
    URL_API_PUSH_VAPID_KEY = "/api/push/vapid-key"
    URL_API_PUSH_STATUS = "/api/push/status"
    URL_API_PUSH_SUBSCRIBE = "/api/push/subscribe"
    URL_API_PUSH_UNSUBSCRIBE = "/api/push/unsubscribe"
    URL_API_PUSH_TOPICS = "/api/push/topics"


def _when_signed_in() -> NavPredicate:
    """Return a predicate that is True when the user is signed in with any role."""
    return lambda role: role is not None


def _when_role(min_role: AccessRole) -> NavPredicate:
    """Return a predicate that is True when the user has at least *min_role*."""
    return lambda role: role is not None and role >= min_role


def _resolve_predicate(*, val: bool | NavPredicate, role: AccessRole | None) -> bool:
    """Resolve *val* to a concrete bool, calling it with *role* if it is callable."""
    return val(role) if callable(val) else val


def _resolve_role(request: Request) -> AccessRole | None:
    """Return the resolved :class:`AccessRole` for the current session, or *None*.

    As a side effect, clears stale / legacy session entries.
    """
    result = resolve_session_subject(request)
    if result is not None:
        return result[1]

    # Clear stale / legacy session entries.
    if (
        request.session.get("api_key")
        or request.session.get("admin_token_hash")
        or request.session.get("auth_session_id")
    ):
        request.session.clear()

    return None


signed_in: NavPredicate = _when_signed_in()

reader_or_above: NavPredicate = _when_role(AccessRole.READER)

operator_or_above: NavPredicate = _when_role(AccessRole.NOTIFICATION_OPERATOR)

admin: NavPredicate = _when_role(AccessRole.ADMIN)


@dataclass
class NavContext(Mapping[str, object]):
    """Typed context for the floating navigation button group.

    Controls which buttons render in ``_floating_btn_group.html``.
    Unpack into a Jinja2 template context via ``**nav_ctx``.

    Each ``show_*`` parameter accepts a plain ``bool`` *or* a
    :data:`NavPredicate` — a ``Callable[[AccessRole | None], bool]``.
    Predicates are resolved in ``__post_init__`` against the actual session
    role, so call sites can use :func:`when_signed_in` and :func:`when_role`
    instead of hard-coding booleans.

    Args:
        request:                      Active request — ``signed_in``, ``role``, and ``show_back_btn`` are derived from it.
        show_auth_button:             Show the floating sign-in button.
                                      Set to False on /auth — the form IS the sign-in UI.
        show_notification_create_btn: Show the "create notification" button.
        show_preview_btn:             Show the "manage notifications" preview button.

    Note:
        Button target URLs (``url_auth``, ``url_notification_create``, ``url_preview``) are
        injected globally via the ``_base_context`` context processor in
        ``app/routers/_page_utils.py`` and are therefore available to
        ``_floating_btn_group.html`` without being fields here.

    """

    request: InitVar[Request]
    show_auth_button: bool | NavPredicate = False
    show_notification_create_btn: bool | NavPredicate = False
    show_api_keys_btn: bool | NavPredicate = False
    show_preview_btn: bool | NavPredicate = False
    role: AccessRole | None = field(init=False)
    signed_in: bool = field(init=False)
    show_back_btn: bool = field(init=False)

    def __post_init__(self, request: Request) -> None:
        """Derive runtime values from the request and nav query."""
        self.role = _resolve_role(request)
        self.signed_in = self.role is not None
        self.show_auth_button = _resolve_predicate(val=self.show_auth_button, role=self.role)
        self.show_notification_create_btn = _resolve_predicate(val=self.show_notification_create_btn, role=self.role)
        self.show_api_keys_btn = _resolve_predicate(val=self.show_api_keys_btn, role=self.role)
        self.show_preview_btn = _resolve_predicate(val=self.show_preview_btn, role=self.role)
        self.show_back_btn = request.url.path not in {Route.URL_INDEX, Route.URL_AUTH}

    def __iter__(self) -> Iterator[str]:
        """Allow unpacking as dict in template contexts."""
        return (f.name for f in fields(self))

    def __len__(self) -> int:
        """Allow unpacking as dict in template contexts."""
        return len(fields(self))

    def __getitem__(self, key: str) -> object:
        """Allow unpacking as dict in template contexts."""
        return getattr(self, key)
