from app.config import cfg


def should_ignore_device(mac: str) -> bool:
    """Return True if the MAC address is in the configured list of ignored MAC addresses."""
    return mac.lower() in cfg.IGNORED_MAC_ADDRESSES
