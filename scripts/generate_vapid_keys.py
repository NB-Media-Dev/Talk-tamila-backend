import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


key = ec.generate_private_key(ec.SECP256R1())
private_raw = key.private_numbers().private_value.to_bytes(32, "big")
public_raw = key.public_key().public_bytes(
    serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
)

print("VAPID_PUBLIC_KEY=" + _b64url(public_raw))
print("VAPID_PRIVATE_KEY=" + _b64url(private_raw))
print("VAPID_SUBJECT=mailto:your-email@example.com")