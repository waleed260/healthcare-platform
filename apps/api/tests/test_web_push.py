import base64
import json
from datetime import datetime, timezone

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import Settings
from app.modules.operations import push


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def make_identity():
    private = ec.generate_private_key(ec.SECP256R1())
    public = push.public_key_bytes(private)
    return private, b64url(public)


def test_hkdf_matches_the_cryptography_reference() -> None:
    ikm, salt, info = b"input-key-material", b"salty-salt-value", b"WebPush: info\x00example"
    reference = HKDF(algorithm=hashes.SHA256(), length=42, salt=salt, info=info).derive(ikm)
    assert push._hkdf(salt, ikm, info, 42) == reference


def test_payload_encryption_round_trips_with_the_subscriber_private_key() -> None:
    ua_private, ua_public = make_identity()
    auth_secret = b"\x01" * 16
    plaintext = b"A follow-up task is overdue."
    body, server_public = push.encrypt_web_push_payload(
        plaintext,
        ua_public,
        b64url(auth_secret),
        salt=b"\x02" * 16,
    )

    salt, record_size, key_length = body[:16], body[16:20], body[20]
    assert record_size == push.RECORD_SIZE.to_bytes(4, "big")
    assert key_length == len(server_public) == 65
    server_key = body[21:21 + key_length]
    ciphertext = body[21 + key_length:]

    server_point = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), server_key)
    ecdh_secret = ua_private.exchange(ec.ECDH(), server_point)
    auth_info = b"WebPush: info\x00" + push.public_key_bytes(ua_private.public_key()) + server_key
    ikm = push._hkdf(auth_secret, ecdh_secret, auth_info, 32)
    prk = push._hkdf_extract(salt, ikm)
    cek = push._hkdf_expand(prk, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = push._hkdf_expand(prk, b"Content-Encoding: nonce\x00", 12)
    decrypted = AESGCM(cek).decrypt(nonce, ciphertext, None)
    assert decrypted == plaintext + b"\x02"


def test_oversized_payload_is_rejected() -> None:
    _, ua_public = make_identity()
    with pytest.raises(ValueError):
        push.encrypt_web_push_payload(b"x" * (push.MAX_PAYLOAD_BYTES + 1), ua_public, b64url(b"\x03" * 16))


def test_vapid_authorization_is_a_verifiable_es256_jwt() -> None:
    private, public_b64 = make_identity()
    endpoint = "https://push.example.test/send/abc"
    now = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    header = push.build_vapid_authorization(
        endpoint, private_key=private, public_key_b64=public_b64, subject="mailto:ops@example.test", now=now
    )

    assert header.startswith("vapid t=")
    token, key = header.removeprefix("vapid t=").split(", k=")
    assert key == public_b64
    header_b64, claims_b64, signature_b64 = token.split(".")
    assert json.loads(push._b64url_decode(header_b64)) == {"typ": "JWT", "alg": "ES256"}
    claims = json.loads(push._b64url_decode(claims_b64))
    assert claims["aud"] == "https://push.example.test"
    assert claims["sub"] == "mailto:ops@example.test"
    assert claims["exp"] == int(now.timestamp()) + push.VAPID_TOKEN_LIFETIME_SECONDS

    raw_signature = push._b64url_decode(signature_b64)
    r, s = int.from_bytes(raw_signature[:32], "big"), int.from_bytes(raw_signature[32:], "big")
    private.public_key().verify(
        encode_dss_signature(r, s),
        f"{header_b64}.{claims_b64}".encode(),
        ec.ECDSA(hashes.SHA256()),
    )


def test_send_maps_push_service_status_codes() -> None:
    _, ua_public = make_identity()
    private, public_b64 = make_identity()
    settings = Settings(
        vapid_subject="mailto:ops@example.test",
        vapid_private_key=b64url(private.private_numbers().private_value.to_bytes(32, "big")),
        vapid_public_key=public_b64,
    )
    captured: dict = {}

    def transport(url, body, headers):
        captured.update(url=url, body=body, headers=headers)
        return 201

    result = push.send_web_push(
        "https://push.example.test/send/abc",
        ua_public,
        b64url(b"\x04" * 16),
        {"title": "Follow-up needs attention", "body": "Open the dashboard to review it."},
        settings=settings,
        transport=transport,
    )
    assert result.status == push.DELIVERED
    assert captured["headers"]["Content-Encoding"] == "aes128gcm"
    assert "vapid t=" in captured["headers"]["Authorization"]
    assert "Follow-up" not in captured["body"].decode("latin-1")  # encrypted, never plaintext

    for status_code, expected in ((200, push.DELIVERED), (410, push.GONE), (404, push.GONE), (500, push.FAILED)):
        result = push.send_web_push(
            "https://push.example.test/send/abc", ua_public, b64url(b"\x05" * 16), {"title": "t", "body": "b"},
            settings=settings, transport=lambda url, body, headers, code=status_code: code,
        )
        assert result.status == expected, status_code


def test_send_is_disabled_without_vapid_identity() -> None:
    _, ua_public = make_identity()
    result = push.send_web_push("https://push.example.test/send/abc", ua_public, b64url(b"\x06" * 16), {"title": "t", "body": "b"})
    assert result.status == push.DISABLED


def test_partial_vapid_configuration_fails_closed() -> None:
    with pytest.raises(ValueError, match="VAPID_SUBJECT and VAPID_PRIVATE_KEY"):
        Settings(vapid_private_key="some-key")
    with pytest.raises(ValueError, match="VAPID_SUBJECT must be"):
        Settings(vapid_subject="ops@example.test", vapid_private_key="some-key")


def test_notification_payload_contains_only_safe_fields() -> None:
    payload = push.notification_payload(
        {"id": "x", "user_id": "y", "kind": "follow_up_overdue", "title": "t", "body": "b", "source_job_key": "secret"}
    )
    assert payload == {"title": "t", "body": "b", "kind": "follow_up_overdue"}


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self, subscriptions):
        self.subscriptions = subscriptions
        self.revoked = []
        self.commits = 0

    def execute(self, statement, parameters=None):
        sql = str(statement)
        if "FROM browser_push_subscriptions" in sql:
            return _Rows([row for row in self.subscriptions if row["user_id"] == parameters["user_id"]])
        if "UPDATE browser_push_subscriptions" in sql:
            self.revoked.append(parameters["id"])
        return _Rows([])

    def commit(self):
        self.commits += 1


def test_delivery_revokes_subscriptions_reported_as_gone(monkeypatch) -> None:
    private, public_b64 = make_identity()
    _, subscriber_public = make_identity()
    settings = Settings(
        vapid_subject="mailto:ops@example.test",
        vapid_private_key=b64url(private.private_numbers().private_value.to_bytes(32, "big")),
        vapid_public_key=public_b64,
    )
    credentials = json.dumps({"p256dh": subscriber_public, "auth": b64url(b"\x07" * 16)})
    monkeypatch.setattr(push, "decrypt_field", lambda value: credentials)
    db = _FakeDB([
        {"id": "sub-1", "user_id": "user-1", "endpoint": "https://push.example.test/gone", "encrypted_credentials": "enc"},
        {"id": "sub-2", "user_id": "user-2", "endpoint": "https://push.example.test/other", "encrypted_credentials": "enc"},
    ])
    counts = push.deliver_notification_push(
        db,
        "clinic-1",
        [{"id": "n1", "user_id": "user-1", "kind": "follow_up_overdue", "title": "t", "body": "b"}],
        settings=settings,
        transport=lambda url, body, headers: 410,
    )
    assert counts["gone"] == 1
    assert db.revoked == ["sub-1"]
    assert db.commits == 1


def test_delivery_is_disabled_without_touching_subscriptions() -> None:
    db = _FakeDB([])
    counts = push.deliver_notification_push(db, "clinic-1", [{"id": "n1", "user_id": "user-1", "kind": "k", "title": "t", "body": "b"}])
    assert counts["disabled"] == 1
    assert db.revoked == []
