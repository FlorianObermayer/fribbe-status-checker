#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["pywebpush>=2.3.0"]
# ///
"""Generate a VAPID key pair for Web Push notifications.

Usage:
    uv run scripts/generate_vapid_keys.py
"""

import base64

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid  # type: ignore[import-untyped]


def main():
    v = Vapid()
    v.generate_keys()

    private_scalar = v.private_key.private_numbers().private_value.to_bytes(32, "big")  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    public_uncompressed = v.private_key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]

    private_key = base64.urlsafe_b64encode(private_scalar).rstrip(b"=").decode()  # pyright: ignore[reportUnknownArgumentType]
    public_key = base64.urlsafe_b64encode(public_uncompressed).rstrip(b"=").decode()  # pyright: ignore[reportUnknownArgumentType]

    print("Add these to your .env file:\n")
    print(f"VAPID_PRIVATE_KEY={private_key}")
    print(f"VAPID_PUBLIC_KEY={public_key}")
    print("VAPID_CLAIM_SUBJECT=mailto:your@email.com  # or https://yourdomain.com")


if __name__ == "__main__":
    main()
