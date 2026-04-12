"""Tests for PushSubscriptionService.validate_subscription and has/add/remove behavior."""

import tempfile
from typing import Any
from unittest.mock import patch

import pytest

from app.services.PushSubscriptionService import PushSubscriptionService

# A realistic base64url-encoded value (length >= 10, valid alphabet)
_VALID_P256DH = "BMXnh6yJ52cJeZKnDFKwW385snzKJtqaVDDBuADUMsez"
_VALID_AUTH = "GTaYpIIoXyzABCDE"
_VALID_ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123"


def test_valid_subscription_does_not_raise():
    PushSubscriptionService.validate_subscription(_VALID_ENDPOINT, _VALID_P256DH, _VALID_AUTH)


def test_endpoint_must_be_https():
    with pytest.raises(ValueError, match="endpoint"):
        PushSubscriptionService.validate_subscription(
            "http://fcm.googleapis.com/fcm/send/abc123", _VALID_P256DH, _VALID_AUTH
        )


def test_endpoint_must_have_netloc():
    with pytest.raises(ValueError, match="endpoint"):
        PushSubscriptionService.validate_subscription("https://", _VALID_P256DH, _VALID_AUTH)


def test_p256dh_too_short():
    with pytest.raises(ValueError, match="p256dh"):
        PushSubscriptionService.validate_subscription(_VALID_ENDPOINT, "short", _VALID_AUTH)


def test_p256dh_invalid_chars():
    with pytest.raises(ValueError, match="p256dh"):
        PushSubscriptionService.validate_subscription(_VALID_ENDPOINT, "invalid chars!!", _VALID_AUTH)


def test_auth_too_short():
    with pytest.raises(ValueError, match="auth"):
        PushSubscriptionService.validate_subscription(_VALID_ENDPOINT, _VALID_P256DH, "short")


def test_auth_invalid_chars():
    with pytest.raises(ValueError, match="auth"):
        PushSubscriptionService.validate_subscription(_VALID_ENDPOINT, _VALID_P256DH, "invalid chars!!")


def test_validate_auth_only_valid_does_not_raise():
    PushSubscriptionService.validate_auth(_VALID_AUTH)


def test_validate_auth_only_too_short():
    with pytest.raises(ValueError, match="auth"):
        PushSubscriptionService.validate_auth("short")


def test_validate_auth_only_invalid_chars():
    with pytest.raises(ValueError, match="auth"):
        PushSubscriptionService.validate_auth("invalid chars!!")


def _make_service(tmpdir: str) -> PushSubscriptionService:
    with patch("app.env.LOCAL_DATA_PATH", tmpdir):
        return PushSubscriptionService("fake-private", "fake-public", "mailto:test@example.com")


def test_has_returns_false_when_not_present():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        assert svc.has(_VALID_AUTH) is False


def test_has_returns_true_after_add():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _VALID_AUTH)
        assert svc.has(_VALID_AUTH) is True


def test_has_returns_false_after_remove():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _VALID_AUTH)
        svc.remove(_VALID_AUTH)
        assert svc.has(_VALID_AUTH) is False


def test_add_stores_custom_topics():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _VALID_AUTH, topics=["presence"])
        assert svc.get_topics(_VALID_AUTH) == ["presence"]


def test_add_defaults_to_all_topics():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _VALID_AUTH)
        topics = svc.get_topics(_VALID_AUTH)
        assert set(topics) == {"presence", "notifications"}


def test_get_topics_returns_empty_for_unknown_auth():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        assert svc.get_topics(_VALID_AUTH) == []


def test_update_topics_returns_true_when_found():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _VALID_AUTH)
        assert svc.update_topics(_VALID_AUTH, ["presence"]) is True
        assert svc.get_topics(_VALID_AUTH) == ["presence"]


def test_update_topics_returns_false_when_not_found():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        assert svc.update_topics(_VALID_AUTH, ["presence"]) is False


_VALID_AUTH_2 = "GTaYpIIoXyzABCDF"
_VALID_ENDPOINT_2 = "https://fcm.googleapis.com/fcm/send/xyz789"


def test_send_to_topic_sync_skips_non_matching_subscribers():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _VALID_AUTH, topics=["presence"])
        svc.add(_VALID_ENDPOINT_2, _VALID_P256DH, _VALID_AUTH_2, topics=["notifications"])

        sent_to: list[str] = []

        def _fake_webpush(subscription_info: Any, data: Any, vapid_private_key: Any, vapid_claims: Any) -> None:
            sent_to.append(subscription_info["keys"]["auth"])

        with patch("app.services.PushSubscriptionService.webpush", _fake_webpush):
            svc.send_to_topic_sync("presence", "T", "B")

        assert sent_to == [_VALID_AUTH]


def test_send_to_topic_sync_sends_to_all_matching_subscribers():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        svc.add(_VALID_ENDPOINT, _VALID_P256DH, _VALID_AUTH, topics=["notifications", "presence"])
        svc.add(_VALID_ENDPOINT_2, _VALID_P256DH, _VALID_AUTH_2, topics=["notifications"])

        sent_to: list[str] = []

        def _fake_webpush(subscription_info: Any, data: Any, vapid_private_key: Any, vapid_claims: Any) -> None:
            sent_to.append(subscription_info["keys"]["auth"])

        with patch("app.services.PushSubscriptionService.webpush", _fake_webpush):
            svc.send_to_topic_sync("notifications", "T", "B")

        assert set(sent_to) == {_VALID_AUTH, _VALID_AUTH_2}
