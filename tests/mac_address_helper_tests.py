"""Tests for MacAddressHelper.should_ignore_device."""

import os

import pytest

from app.config import cfg
from app.services.mac_address_helper import should_ignore_device

_MAC_A = "2C:CF:67:DD:46:23"
_MAC_B = "54:60:09:EE:19:28"


def test_configured_mac_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "IGNORED_MAC_ADDRESSES", frozenset({_MAC_A.lower(), _MAC_B.lower()}))
    assert should_ignore_device(_MAC_A) is True
    assert should_ignore_device(_MAC_B) is True


def test_configured_mac_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "IGNORED_MAC_ADDRESSES", frozenset({_MAC_A.lower()}))
    assert should_ignore_device(_MAC_A.upper()) is True
    assert should_ignore_device(_MAC_A.lower()) is True


def test_unknown_mac_is_not_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "IGNORED_MAC_ADDRESSES", frozenset({_MAC_A.lower()}))
    assert should_ignore_device("AA:BB:CC:DD:EE:FF") is False


def test_empty_mac_is_not_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "IGNORED_MAC_ADDRESSES", frozenset({_MAC_A.lower()}))
    assert should_ignore_device("") is False


def test_unconfigured_ignores_no_macs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "IGNORED_MAC_ADDRESSES", frozenset())
    assert should_ignore_device(_MAC_A) is False
    assert should_ignore_device(_MAC_B) is False


def test_env_parsing_whitespace_and_commas(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reload parses comma-separated MACs with surrounding whitespace correctly."""
    monkeypatch.setitem(os.environ, "IGNORED_MAC_ADDRESSES", f"  {_MAC_A}  ,  {_MAC_B}  ")
    cfg.reload()
    assert _MAC_A.lower() in cfg.IGNORED_MAC_ADDRESSES
    assert _MAC_B.lower() in cfg.IGNORED_MAC_ADDRESSES


def test_env_empty_string_means_no_ignores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IGNORED_MAC_ADDRESSES", "")
    cfg.reload()
    assert frozenset() == cfg.IGNORED_MAC_ADDRESSES


def test_env_unset_means_no_ignores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IGNORED_MAC_ADDRESSES", raising=False)
    cfg.reload()
    assert frozenset() == cfg.IGNORED_MAC_ADDRESSES
