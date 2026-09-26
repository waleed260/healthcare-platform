"""Self-contained Web Push delivery (RFC 8291 encryption, RFC 8292 VAPID).

The platform already depends on ``cryptography`` for field encryption and TOTP;
this module reuses it for ECDH key agreement, AES-128-GCM record encryption, and
ES256 VAPID JWTs instead of pinning a separate push library. It never raises on
delivery failure: the worker must keep processing other tenants, and only a safe
status is recorded.

Payloads contain only the privacy-safe notification title/body. No patient
identifier, document content, token, or signed URL is ever placed on the wire.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_private_key

from app.core.config import Settings, get_settings
from app.core.security import decrypt_field

# One aes128gcm record is enough for these tiny payloads; the record size is the
# RFC 8188 "rs" field and caps the plaintext at rs - 16-byte tag - 1 delimiter.
RECORD_SIZE = 4096
MAX_PAYLOAD_BYTES = RECORD_SIZE - 17
VAPID_TOKEN_LIFETIME_SECONDS = 12 * 60 * 60
PUSH_TIMEOUT_SECONDS = 10.0

DELIVERED = "delivered"
GONE = "gone"
FAILED = "failed"
DISABLED = "disabled"

# A push service reporting these codes means the subscription is permanently
# invalid and must be revoked rather than retried.
GONE_STATUS_CODES = frozenset({404, 410})


@dataclass(frozen=True)
class PushResult:
    status: str
    status_code: int | None = None


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded)


def _hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def _hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    output = b""
    block = b""
    counter = 1
    while len(output) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        output += block
        counter += 1
    return output[:length]


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return _hkdf_expand(_hkdf_extract(salt, ikm), info, length)


def load_private_key(value: str) -> ec.EllipticCurvePrivateKey:
    """Accept a base64url raw P-256 scalar or a PEM encoded private key."""
    if value.startswith("-----BEGIN"):
        key = load_pem_private_key(value.encode(), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
            raise ValueError("VAPID private key must be an EC P-256 key")
        return key
    scalar = int.from_bytes(_b64url_decode(value), "big")
    return ec.derive_private_key(scalar, ec.SECP256R1())


def public_key_bytes(key: ec.EllipticCurvePublicKey | ec.EllipticCurvePrivateKey) -> bytes:
    public = key.public_key() if isinstance(key, ec.EllipticCurvePrivateKey) else key
    return public.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)


def vapid_public_key(settings: Settings | None = None) -> str:
    """Return the base64url VAPID public key, deriving it from the private key when needed."""
    settings = settings or get_settings()
    if settings.vapid_public_key:
        return settings.vapid_public_key
    return _b64url_encode(public_key_bytes(load_private_key(settings.vapid_private_key)))


def encrypt_web_push_payload(
    plaintext: bytes,
    p256dh: str,
    auth: str,
    *,
    salt: bytes | None = None,
    server_private_key: ec.EllipticCurvePrivateKey | None = None,
) -> tuple[bytes, bytes]:
    """Encrypt one aes128gcm record per RFC 8291.

    Returns ``(body, server_public_key)`` where ``server_public_key`` is the
    65-byte uncompressed ephemeral point the receiver needs to decrypt.
    """
    if len(plaintext) > MAX_PAYLOAD_BYTES:
        raise ValueError("push payload exceeds the single-record size limit")
    user_public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), _b64url_decode(p256dh))
    auth_secret = _b64url_decode(auth)
    server_private = server_private_key or ec.generate_private_key(ec.SECP256R1())
    server_public = public_key_bytes(server_private)
    salt = salt or secrets.token_bytes(16)

    ecdh_secret = server_private.exchange(ec.ECDH(), user_public)
    auth_info = b"WebPush: info\x00" + public_key_bytes(user_public) + server_public
    ikm = _hkdf(auth_secret, ecdh_secret, auth_info, 32)
    prk = _hkdf_extract(salt, ikm)
    cek = _hkdf_expand(prk, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf_expand(prk, b"Content-Encoding: nonce\x00", 12)

    # A single final record carries the 0x02 padding delimiter.
    ciphertext = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)
    body = salt + struct.pack(">I", RECORD_SIZE) + bytes([len(server_public)]) + server_public + ciphertext
    return body, server_public


def build_vapid_authorization(
    endpoint: str,
    *,
    private_key: ec.EllipticCurvePrivateKey,
    public_key_b64: str,
    subject: str,
    now: datetime | None = None,
) -> str:
    """Build the ``Authorization: vapid`` header containing a signed ES256 JWT."""
    current = now or datetime.now(timezone.utc)
    parsed = urlsplit(endpoint)
    audience = f"{parsed.scheme}://{parsed.netloc}"
    header = _b64url_encode(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    claims = _b64url_encode(
        json.dumps(
            {"aud": audience, "exp": int(current.timestamp()) + VAPID_TOKEN_LIFETIME_SECONDS, "sub": subject},
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{claims}".encode()
    r, s = decode_dss_signature(private_key.sign(signing_input, ec.ECDSA(hashes.SHA256())))
    signature = _b64url_encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={header}.{claims}.{signature}, k={public_key_b64}"


def _http_transport(url: str, body: bytes, headers: dict[str, str]) -> int:
    with httpx.Client(timeout=PUSH_TIMEOUT_SECONDS) as client:
        return client.post(url, content=body, headers=headers).status_code


def classify_status(status_code: int) -> str:
    if 200 <= status_code < 300:
        return DELIVERED
    if status_code in GONE_STATUS_CODES:
        return GONE
    return FAILED


def send_web_push(
    endpoint: str,
    p256dh: str,
    auth: str,
    payload: dict,
    *,
    settings: Settings | None = None,
    transport: Callable[[str, bytes, dict[str, str]], int] | None = None,
    now: datetime | None = None,
) -> PushResult:
    """Deliver one push message; never raises."""
    settings = settings or get_settings()
    if not settings.push_enabled:
        return PushResult(DISABLED)
    try:
        body, _ = encrypt_web_push_payload(json.dumps(payload, separators=(",", ":")).encode(), p256dh, auth)
        headers = {
            "Authorization": build_vapid_authorization(
                endpoint,
                private_key=load_private_key(settings.vapid_private_key),
                public_key_b64=vapid_public_key(settings),
                subject=settings.vapid_subject,
                now=now,
            ),
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "TTL": "900",
            "Urgency": "normal",
        }
        status_code = (transport or _http_transport)(endpoint, body, headers)
    except Exception:
        # A malformed subscription, bad key material, or transport error must not
        # abort the tenant-level job; it is recorded as a generic failure.
        return PushResult(FAILED)
    return PushResult(classify_status(status_code), status_code)


def notification_payload(notification: dict) -> dict:
    """Build a browser payload from the already privacy-safe stored fields."""
    return {"title": notification["title"], "body": notification["body"], "kind": notification["kind"]}


def deliver_notification_push(
    db,
    clinic_id,
    notifications: list[dict],
    *,
    transport: Callable[[str, bytes, dict[str, str]], int] | None = None,
    settings: Settings | None = None,
) -> dict[str, int]:
    """Push created notifications to each recipient's active subscriptions.

    Subscriptions the push service reports as gone are revoked. The function
    returns aggregate counts only and never raises.
    """
    from sqlalchemy import text

    counts = {"delivered": 0, "gone": 0, "failed": 0, "disabled": 0}
    settings = settings or get_settings()
    if not notifications:
        return counts
    if not settings.push_enabled:
        counts["disabled"] = len(notifications)
        return counts
    from app.db.tenant import set_tenant_context

    set_tenant_context(db, clinic_id)
    for notification in notifications:
        if notification.get("user_id") is None:
            continue
        subscriptions = db.execute(text("""
            SELECT id, endpoint, encrypted_credentials
            FROM browser_push_subscriptions
            WHERE clinic_id = :clinic_id AND user_id = :user_id AND revoked_at IS NULL
        """), {"clinic_id": clinic_id, "user_id": notification["user_id"]}).mappings().all()
        for subscription in subscriptions:
            try:
                credentials = json.loads(decrypt_field(subscription["encrypted_credentials"]))
            except Exception:
                counts["failed"] += 1
                continue
            result = send_web_push(
                subscription["endpoint"],
                credentials["p256dh"],
                credentials["auth"],
                notification_payload(notification),
                settings=settings,
                transport=transport,
            )
            counts[result.status] = counts.get(result.status, 0) + 1
            if result.status == GONE:
                db.execute(
                    text("UPDATE browser_push_subscriptions SET revoked_at = now() WHERE clinic_id = :clinic_id AND id = :id"),
                    {"clinic_id": clinic_id, "id": subscription["id"]},
                )
    db.commit()
    return counts
