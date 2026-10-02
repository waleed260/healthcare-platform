"""PostgreSQL evidence that failed-login rate limiting is durable.

Regression for the bug where ``_record_failure`` wrote the lockout counter in
the *request* transaction and the login route's ``except: db.rollback()`` then
erased it, so the 5-attempt/15-minute lock could never actually fire. The fix
commits each failure on an independent session; this test proves the counter
survives the rollback, the lock blocks even a correct password, expiry releases
it, and a successful login clears the bucket.

Runs in CI's PostgreSQL service; skipped when integration URLs are unset. It
requires DATABASE_URL to point at the same database as TEST_DATABASE_URL because
``_record_failure`` opens its own session from the app engine.
"""
from __future__ import annotations

import os
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password, hash_token, utc_now
from app.modules.identity.service import AuthenticationError, authenticate, normalize_email

pytestmark = pytest.mark.integration

_PASSWORD = "CorrectHorse9zz"


def _database_urls() -> tuple[str, str]:
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    return admin_url, runtime_url


def test_failed_logins_persist_and_lock_despite_request_rollback() -> None:
    admin_url, runtime_url = _database_urls()
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url)
    runtime_session = sessionmaker(bind=runtime, autoflush=False, autocommit=False, expire_on_commit=False)
    clinic_id, user_id = uuid4(), uuid4()
    email = f"lockme-{user_id}@example.test"
    ip_address = "203.0.113.77"
    bucket_key = hash_token(f"account:{normalize_email(email)}:ip:{ip_address}")
    try:
        with admin.begin() as connection:
            connection.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:id, 'Lockout Synthetic', :slug)"), {"id": clinic_id, "slug": f"lockout-{clinic_id}"})
            connection.execute(
                text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) VALUES (:id, :clinic_id, :email, 'Lockout User', :password_hash, 'active')"),
                {"id": user_id, "clinic_id": clinic_id, "email": normalize_email(email), "password_hash": hash_password(_PASSWORD)},
            )
            connection.execute(text("DELETE FROM auth_rate_limit_buckets WHERE bucket_key = :bucket_key"), {"bucket_key": bucket_key})

        # Five bad logins, each followed by the rollback the login route performs
        # in its AuthenticationError branch. The counter must survive every one.
        for attempt in range(1, 6):
            session = runtime_session()
            try:
                with pytest.raises(AuthenticationError):
                    authenticate(session, email, "wrong-password", ip_address, "pytest")
                session.rollback()
            finally:
                session.close()
            with runtime.connect() as connection:
                count = connection.execute(text("SELECT failure_count FROM auth_rate_limit_buckets WHERE bucket_key = :bucket_key"), {"bucket_key": bucket_key}).scalar_one()
            assert count == attempt, f"failure #{attempt} did not persist (counter={count})"

        # Locked: even the CORRECT password is refused while the lock holds.
        session = runtime_session()
        try:
            with pytest.raises(AuthenticationError):
                authenticate(session, email, _PASSWORD, ip_address, "pytest")
            session.rollback()
        finally:
            session.close()

        # Expiry: push the lock into the past, then the correct password works
        # and the successful login clears the bucket.
        with admin.begin() as connection:
            connection.execute(text("UPDATE auth_rate_limit_buckets SET locked_until = :past WHERE bucket_key = :bucket_key"), {"past": utc_now() - timedelta(minutes=1), "bucket_key": bucket_key})
        session = runtime_session()
        try:
            result = authenticate(session, email, _PASSWORD, ip_address, "pytest")
            session.commit()
            assert result.user_id == user_id
        finally:
            session.close()
        with runtime.connect() as connection:
            remaining = connection.execute(text("SELECT count(*) FROM auth_rate_limit_buckets WHERE bucket_key = :bucket_key"), {"bucket_key": bucket_key}).scalar_one()
        assert remaining == 0, "successful login did not clear the failure bucket"
    finally:
        with admin.begin() as connection:
            connection.execute(text("DELETE FROM sessions WHERE user_id = :user_id"), {"user_id": user_id})
            connection.execute(text("DELETE FROM auth_rate_limit_buckets WHERE bucket_key = :bucket_key"), {"bucket_key": bucket_key})
            connection.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
            connection.execute(text("DELETE FROM clinics WHERE id = :clinic_id"), {"clinic_id": clinic_id})
