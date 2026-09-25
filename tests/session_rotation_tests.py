"""Unit tests for the session-rotation helper in ``app.api.hybrid_auth``."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

from app.api import hybrid_auth


def _patch_handler(monkeypatch: pytest.MonkeyPatch, handler: MagicMock) -> None:
    def _get_handler(_request: Request) -> object:
        return handler

    def _regenerate(_request: Request) -> str:
        return "new-session-id"

    monkeypatch.setattr(hybrid_auth, "get_session_handler", _get_handler)
    monkeypatch.setattr(hybrid_auth, "regenerate_session_id", _regenerate)


@pytest.mark.asyncio
async def test_rotate_session_id_removes_superseded_record(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = MagicMock()
    handler.session_id = "old-session-id"
    handler.store = MagicMock()
    handler.store.remove = AsyncMock()
    _patch_handler(monkeypatch, handler)

    await hybrid_auth.rotate_session_id(MagicMock())

    handler.store.remove.assert_awaited_once_with("old-session-id")


@pytest.mark.asyncio
async def test_rotate_session_id_skips_remove_without_previous_id(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = MagicMock()
    handler.session_id = None
    handler.store = MagicMock()
    handler.store.remove = AsyncMock()
    _patch_handler(monkeypatch, handler)

    await hybrid_auth.rotate_session_id(MagicMock())

    handler.store.remove.assert_not_awaited()
