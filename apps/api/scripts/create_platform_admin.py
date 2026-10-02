"""Create or reactivate a platform-administrator account (no clinic, is_platform_admin=true).

    PLATFORM_ADMIN_EMAIL=you@example.com python scripts/create_platform_admin.py

Reads the owner/admin connection from DATABASE_MIGRATION_URL, SEED_DATABASE_URL or DATABASE_URL.
Password: ADMIN_PASSWORD if set, otherwise a strong one is generated and printed once.
Platform admins are MFA-mandatory, so the first sign-in forces authenticator enrollment.
"""
from __future__ import annotations

import os
import secrets
import sys

import psycopg

from app.core.security import hash_password
from app.modules.identity.service import normalize_email

email = os.environ.get("PLATFORM_ADMIN_EMAIL")
if not email:
    raise SystemExit("set PLATFORM_ADMIN_EMAIL")
display = os.environ.get("PLATFORM_ADMIN_NAME", email.split("@")[0].replace(".", " ").title())
password = os.environ.get("ADMIN_PASSWORD") or (secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") + secrets.choice("abcdefghijkmnpqrstuvwxyz") + secrets.choice("23456789") + "-" + secrets.token_urlsafe(12))

raw = os.environ.get("DATABASE_MIGRATION_URL") or os.environ.get("SEED_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not raw:
    raise SystemExit("set DATABASE_MIGRATION_URL (owner connection)")
dsn = raw.replace("postgresql+psycopg://", "postgresql://")

with psycopg.connect(dsn, autocommit=True) as conn:
    row = conn.execute(
        """
        INSERT INTO users (clinic_id, normalized_email, display_name, password_hash, status, is_platform_admin)
        VALUES (NULL, %s, %s, %s, 'active', true)
        ON CONFLICT (normalized_email) DO UPDATE
          SET display_name = EXCLUDED.display_name,
              password_hash = EXCLUDED.password_hash,
              status = 'active',
              is_platform_admin = true,
              clinic_id = NULL,
              version = users.version + 1
        RETURNING id, (xmax = 0) AS created
        """,
        (normalize_email(email), display, hash_password(password)),
    ).fetchone()

print(f"platform admin {'created' if row[1] else 'updated'}: {normalize_email(email)}  (id {row[0]})")
if not os.environ.get("ADMIN_PASSWORD"):
    print(f"temporary password: {password}")
    print("Sign in, you will be required to set up an authenticator (MFA), then change this password.", file=sys.stderr)
