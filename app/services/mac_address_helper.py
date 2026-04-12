def should_ignore_device(mac: str) -> bool:
    """Return True if the MAC address belongs to a known infrastructure device."""
    device_macs_to_ignore = {
        "2C:CF:67:DD:46:23",  # fribbepi
        "54:60:09:EE:19:28",  # chromecast-audio
    }

    return mac.lower() in [mac.lower() for mac in device_macs_to_ignore]
