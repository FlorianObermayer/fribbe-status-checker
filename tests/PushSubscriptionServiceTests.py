"""Tests for PushSubscription.validate_subscription."""

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
