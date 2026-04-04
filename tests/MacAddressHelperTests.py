"""Tests for MacAddressHelper.should_ignore_device."""

from app.services.MacAddressHelper import should_ignore_device

# Known infrastructure MACs hardcoded in the helper
_FRIBBEPI_MAC = "2C:CF:67:DD:46:23"
_CHROMECAST_MAC = "54:60:09:EE:19:28"


def test_known_mac_is_ignored():
    assert should_ignore_device(_FRIBBEPI_MAC) is True
    assert should_ignore_device(_CHROMECAST_MAC) is True


def test_known_mac_lowercase_is_ignored():
    assert should_ignore_device(_FRIBBEPI_MAC.lower()) is True
    assert should_ignore_device(_CHROMECAST_MAC.lower()) is True


def test_unknown_mac_is_not_ignored():
    assert should_ignore_device("AA:BB:CC:DD:EE:FF") is False


def test_empty_mac_is_not_ignored():
    assert should_ignore_device("") is False
