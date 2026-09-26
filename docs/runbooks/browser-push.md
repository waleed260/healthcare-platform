# Browser push notifications

Browser push is optional and opt-in. When it is enabled, the overdue follow-up
job delivers the already-stored, privacy-safe notification title/body to each
recipient's active subscriptions after the notification transaction commits.

## Configuration

Set all of the following together. A partially configured identity fails closed
at startup, and an unset identity simply skips delivery (`disabled`).

| Variable | Purpose |
| --- | --- |
| `VAPID_SUBJECT` | `mailto:` address or `https://` contact URL sent as the JWT `sub` claim |
| `VAPID_PRIVATE_KEY` | base64url raw P-256 scalar, or a PEM private key |
| `VAPID_PUBLIC_KEY` | optional base64url P-256 public key; derived from the private key when omitted |

Generate a key pair (the private value is the base64url scalar and the public
value is the base64url uncompressed point):

```bash
python - <<'PY'
import base64
from cryptography.hazmat.primitives.asymmetric import ec

private = ec.generate_private_key(ec.SECP256R1())
scalar = private.private_numbers().private_value.to_bytes(32, "big")
public = private.public_key().public_bytes(
    ec.Encoding.X962, ec.PublicFormat.UncompressedPoint
)
print("VAPID_PRIVATE_KEY=" + base64.urlsafe_b64encode(scalar).decode().rstrip("="))
print("VAPID_PUBLIC_KEY=" + base64.urlsafe_b64encode(public).decode().rstrip("="))
PY
```

Treat `VAPID_PRIVATE_KEY` as a secret: store it in the deployment secret store,
never in the repository, and rotate it only alongside the public key that the
workspace serves. The public key is exposed to authenticated users at
`GET /api/v1/operations/notifications/push-config`.

## Behavior and safety

- Each message is encrypted with RFC 8291 `aes128gcm`; the request is
  authenticated with an ES256 VAPID JWT (RFC 8292). The platform does not add a
  push-delivery dependency; it reuses the pinned `cryptography` primitives.
- Only the stored `title`, `body`, and `kind` are sent. No patient identifier,
  document content, session token, or signed URL is ever placed on the wire.
- A push service returning `404` or `410` permanently invalidates a
  subscription; the worker revokes that row instead of retrying. Other failures
  are counted and retried by the next overdue-notification run.
- Delivery runs outside the database transaction, so a push-provider outage
  cannot roll back or block notification storage.

## Verification

The unit suite covers encryption round-trips, HKDF agreement with the
`cryptography` reference, VAPID signature verification, status-code mapping, and
gone-subscription revocation. End-to-end delivery against a real push service
(Chrome/Firefox) remains part of the pilot environment evidence.
