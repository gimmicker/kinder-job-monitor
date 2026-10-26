"""푸시용 VAPID 키 한 쌍 생성 (최초 1회). 출력값을 GitHub Secrets에 넣는다.

사용: python scripts/gen_vapid.py
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


key = ec.generate_private_key(ec.SECP256R1())
priv = key.private_numbers().private_value.to_bytes(32, "big")
pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
print("VAPID_PUBLIC_KEY =", b64(pub))
print("VAPID_PRIVATE_KEY =", b64(priv))
print("\n※ 개인키(PRIVATE)는 GitHub Secrets에만 넣고 어디에도 붙여넣지 마세요.")
