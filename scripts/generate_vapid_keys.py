"""Generate a VAPID key pair for Web Push notifications.

Usage:
    uv run scripts/generate_vapid_keys.py
"""

import base64

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid  # type: ignore[import-untyped]


def main() -> None:
    v = Vapid()
    v.generate_keys()

    private_scalar = v.private_key.private_numbers().private_value.to_bytes(32, "big")  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    public_uncompressed = v.private_key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]

    base64.urlsafe_b64encode(private_scalar).rstrip(b"=").decode()  # pyright: ignore[reportUnknownArgumentType]
    base64.urlsafe_b64encode(public_uncompressed).rstrip(b"=").decode()  # pyright: ignore[reportUnknownArgumentType]


if __name__ == "__main__":
    main()
