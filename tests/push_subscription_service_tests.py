"""Tests for PushSubscriptionService.validate_subscription and has/add/remove behavior."""

import ipaddress
import tempfile
from typing import Any
from unittest.mock import patch

import pytest

from app.services import push_subscription_service as push_module
from app.services.push_subscription_service import PushSubscriptionService, PushTopic

# A realistic base64url-encoded value (length >= 10, valid alphabet)
_VALID_P256DH = "BMXnh6yJ52cJeZKnDFKwW385snzKJtqaVDDBuADUMsez"
_VALID_AUTH = "GTaYpIIoXyzABCDE"
_VALID_ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123"

# A stable globally routable address so tests never depend on real DNS.
_PUBLIC_IP = ipaddress.ip_address("93.184.216.34")


def _resolve_to(*addresses: ipaddress.IPv4Address | ipaddress.IPv6Address) -> Any:  # noqa: ANN401
    """Patch the endpoint host resolver to return fixed addresses."""
    return patch.object(push_module, "_resolve_push_host", return_value=list(addresses))


def test_valid_subscription_does_not_raise() -> None:
    with _resolve_to(_PUBLIC_IP):
        PushSubscriptionService.validate_subscription(_VALID_ENDPOINT, _VALID_P256DH, _VALID_AUTH)


def test_endpoint_must_be_https() -> None:
    with pytest.raises(ValueError, match="endpoint"):
        PushSubscriptionService.validate_subscription(
            "http://fcm.googleapis.com/fcm/send/abc123",
            _VALID_P256DH,
            _VALID_AUTH,
        )


def test_endpoint_must_have_netloc() -> None:
    with pytest.raises(ValueError, match="endpoint"):
        PushSubscriptionService.validate_subscription("https://", _VALID_P256DH, _VALID_AUTH)


def test_endpoint_accepts_public_host() -> None:
    with _resolve_to(_PUBLIC_IP):
        PushSubscriptionService.validate_subscription(
            "https://push.example.com/send/1",
            _VALID_P256DH,
            _VALID_AUTH,
        )


def test_endpoint_rejects_non_https_scheme() -> None:
    with pytest.raises(ValueError, match="https"):
        PushSubscriptionService.validate_subscription(
            "ftp://push.example.com/send/1",
            _VALID_P256DH,
            _VALID_AUTH,
        )


def test_endpoint_rejects_userinfo() -> None:
    with pytest.raises(ValueError, match="userinfo"):
        PushSubscriptionService.validate_subscription(
            "https://user:pass@127.0.0.1:8443/x",
            _VALID_P256DH,
            _VALID_AUTH,
        )


def test_endpoint_rejects_loopback_address() -> None:
    with _resolve_to(ipaddress.ip_address("127.0.0.1")), pytest.raises(ValueError, match="public address"):
        PushSubscriptionService.validate_subscription("https://localhost:8443/x", _VALID_P256DH, _VALID_AUTH)


def test_endpoint_rejects_ipv6_loopback_address() -> None:
    with _resolve_to(ipaddress.ip_address("::1")), pytest.raises(ValueError, match="public address"):
        PushSubscriptionService.validate_subscription("https://[::1]:8443/x", _VALID_P256DH, _VALID_AUTH)


def test_endpoint_rejects_private_address() -> None:
    with _resolve_to(ipaddress.ip_address("10.0.0.5")), pytest.raises(ValueError, match="public address"):
        PushSubscriptionService.validate_subscription("https://internal.example/x", _VALID_P256DH, _VALID_AUTH)


def test_endpoint_rejects_link_local_address() -> None:
    with _resolve_to(ipaddress.ip_address("169.254.169.254")), pytest.raises(ValueError, match="public address"):
        PushSubscriptionService.validate_subscription("https://metadata.example/x", _VALID_P256DH, _VALID_AUTH)


def test_endpoint_rejects_when_any_resolved_address_is_non_public() -> None:
    """A name resolving to a mix of public and private addresses must fail closed."""
    with (
        _resolve_to(_PUBLIC_IP, ipaddress.ip_address("192.168.1.1")),
        pytest.raises(ValueError, match="public address"),
    ):
        PushSubscriptionService.validate_subscription("https://mixed.example/x", _VALID_P256DH, _VALID_AUTH)


def test_endpoint_rejects_unresolvable_host() -> None:
    with (
        patch.object(push_module, "_resolve_push_host", side_effect=OSError("name resolution failed")),
        pytest.raises(ValueError, match="could not be resolved"),
    ):
        PushSubscriptionService.validate_subscription(
            "https://does-not-resolve.invalid/x",
            _VALID_P256DH,
            _VALID_AUTH,
        )


def test_p256dh_too_short() -> None:
    with pytest.raises(ValueError, match="p256dh"):
        PushSubscriptionService.validate_subscription(_VALID_ENDPOINT, "short", _VALID_AUTH)


def test_p256dh_invalid_chars() -> None:
    with pytest.raises(ValueError, match="p256dh"):
        PushSubscriptionService.validate_subscription(_VALID_ENDPOINT, "invalid chars!!", _VALID_AUTH)


def test_auth_too_short() -> None:
    with pytest.raises(ValueError, match="auth"):
        PushSubscriptionService.validate_subscription(_VALID_ENDPOINT, _VALID_P256DH, "short")


def test_auth_invalid_chars() -> None:
    with pytest.raises(ValueError, match="auth"):
        PushSubscriptionService.validate_subscription(_VALID_ENDPOINT, _VALID_P256DH, "invalid chars!!")


def test_validate_auth_only_valid_does_not_raise() -> None:
    PushSubscriptionService.validate_auth(_VALID_AUTH)


def test_validate_auth_only_too_short() -> None:
    with pytest.raises(ValueError, match="auth"):
        PushSubscriptionService.validate_auth("short")


def test_validate_auth_only_invalid_chars() -> None:
    with pytest.raises(ValueError, match="auth"):
        PushSubscriptionService.validate_auth("invalid chars!!")


def _make_service(tmpdir: str) -> PushSubscriptionService:
    with patch("app.config.cfg.LOCAL_DATA_PATH", tmpdir):
        return PushSubscriptionService("fake-private", "fake-public", "mailto:test@example.com")


def test_has_returns_false_when_not_present() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        assert svc.has(_VALID_AUTH) is False


def test_has_returns_true_after_add() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _VALID_AUTH)
        assert svc.has(_VALID_AUTH) is True


def test_has_returns_false_after_remove() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _VALID_AUTH)
        svc.remove(_VALID_AUTH)
        assert svc.has(_VALID_AUTH) is False


def test_add_stores_custom_topics() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _VALID_AUTH, topics=[PushTopic.PRESENCE])
        assert svc.get_topics(_VALID_AUTH) == [PushTopic.PRESENCE]


def test_add_defaults_to_all_topics() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _VALID_AUTH)
        topics = svc.get_topics(_VALID_AUTH)
        assert set(topics) == {PushTopic.PRESENCE, PushTopic.NOTIFICATIONS}


def test_get_topics_returns_empty_for_unknown_auth() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        assert svc.get_topics(_VALID_AUTH) == []


def test_update_topics_returns_true_when_found() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _VALID_AUTH)
        assert svc.update_topics(_VALID_AUTH, [PushTopic.PRESENCE]) is True
        assert svc.get_topics(_VALID_AUTH) == [PushTopic.PRESENCE]


def test_update_topics_returns_false_when_not_found() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        assert svc.update_topics(_VALID_AUTH, [PushTopic.PRESENCE]) is False


_VALID_AUTH_2 = "GTaYpIIoXyzABCDF"
_VALID_ENDPOINT_2 = "https://fcm.googleapis.com/fcm/send/xyz789"


def test_send_to_topic_sync_skips_non_matching_subscribers() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _VALID_AUTH, topics=[PushTopic.PRESENCE])
        svc.add(_VALID_ENDPOINT_2, _VALID_P256DH, _VALID_AUTH_2, topics=[PushTopic.NOTIFICATIONS])

        sent_to: list[str] = []

        def _fake_webpush(subscription_info: Any, **_kwargs: Any) -> None:  # noqa: ANN401
            sent_to.append(subscription_info["keys"]["auth"])

        with patch("app.services.push_subscription_service.webpush", _fake_webpush):
            svc.send_to_topic_sync(PushTopic.PRESENCE, "T", "B")

        assert sent_to == [_VALID_AUTH]


def test_send_to_topic_sync_sends_to_all_matching_subscribers() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _VALID_AUTH, topics=[PushTopic.NOTIFICATIONS, PushTopic.PRESENCE])
        svc.add(_VALID_ENDPOINT_2, _VALID_P256DH, _VALID_AUTH_2, topics=[PushTopic.NOTIFICATIONS])

        sent_to: list[str] = []

        def _fake_webpush(subscription_info: Any, **_kwargs: Any) -> None:  # noqa: ANN401
            sent_to.append(subscription_info["keys"]["auth"])

        with patch("app.services.push_subscription_service.webpush", _fake_webpush):
            svc.send_to_topic_sync(PushTopic.NOTIFICATIONS, "T", "B")

        assert set(sent_to) == {_VALID_AUTH, _VALID_AUTH_2}


# ---------------------------------------------------------------------------
# Delivery bounds (timeout + redirect-free session)
# ---------------------------------------------------------------------------


def test_send_bounds_request_time_and_disables_redirects() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _VALID_AUTH, topics=[PushTopic.PRESENCE])

        captured: dict[str, Any] = {}

        def _fake_webpush(*_args: Any, **kwargs: Any) -> None:  # noqa: ANN401
            captured.update(kwargs)

        with patch("app.services.push_subscription_service.webpush", _fake_webpush):
            svc.send_to_topic_sync(PushTopic.PRESENCE, "T", "B")

        assert captured["timeout"] == push_module._PUSH_REQUEST_TIMEOUT_SECONDS
        assert captured["requests_session"] is push_module._PUSH_SESSION
        assert push_module._PUSH_SESSION.max_redirects == 0


# ---------------------------------------------------------------------------
# Subscription store cap
# ---------------------------------------------------------------------------

_AUTH_1 = "GTaYpIIoXyzAAAAAA"
_AUTH_2 = "GTaYpIIoXyzBBBBBB"
_AUTH_3 = "GTaYpIIoXyzCCCCCC"


def test_add_rejects_new_subscription_at_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(push_module, "_MAX_SUBSCRIPTIONS", 2)
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _AUTH_1)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _AUTH_2)

        with pytest.raises(ValueError, match="limit"):
            svc.add(_VALID_ENDPOINT, _VALID_P256DH, _AUTH_3)

        assert svc.has(_AUTH_3) is False
        assert len(svc._store) == 2


def test_add_can_replace_existing_subscription_at_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(push_module, "_MAX_SUBSCRIPTIONS", 2)
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _AUTH_1)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _AUTH_2)

        # Re-registering an existing auth must succeed and must not grow the store
        svc.add(_VALID_ENDPOINT_2, _VALID_P256DH, _AUTH_2)

        assert len(svc._store) == 2
        assert svc.has(_AUTH_2) is True


def test_freed_slot_can_be_reused_after_remove(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(push_module, "_MAX_SUBSCRIPTIONS", 2)
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _AUTH_1)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _AUTH_2)

        assert svc.remove(_AUTH_1) is True
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _AUTH_3)

        assert svc.has(_AUTH_3) is True
