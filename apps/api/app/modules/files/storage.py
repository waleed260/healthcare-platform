"""Small private-object adapter used by local/staging deployments.

Production deployments may replace this adapter with an encrypted object-store
implementation; callers never receive the root path or storage credentials.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.core.config import get_settings


SUPABASE_TIMEOUT_SECONDS = 30
STORAGE_READINESS_TIMEOUT_SECONDS = 2


def _use_supabase() -> bool:
    return get_settings().storage_backend.casefold() == "supabase"


def check_storage_readiness() -> bool:
    """Check the configured storage dependency without exposing provider details."""
    settings = get_settings()
    try:
        if _use_supabase():
            if not settings.supabase_url or not settings.supabase_service_role_key:
                return False
            headers = {
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "apikey": settings.supabase_service_role_key,
            }
            for bucket in (settings.supabase_private_bucket, settings.supabase_public_bucket):
                request = Request(
                    f"{settings.supabase_url.rstrip('/')}/storage/v1/bucket/{quote(bucket, safe='')}",
                    headers=headers,
                    method="GET",
                )
                with urlopen(request, timeout=STORAGE_READINESS_TIMEOUT_SECONDS):
                    pass
            return True
        for root_value, mode in (
            (settings.private_storage_root, 0o700),
            (settings.public_storage_root, 0o755),
        ):
            root = Path(root_value).expanduser()
            root.mkdir(mode=mode, parents=True, exist_ok=True)
            if not os.access(root, os.R_OK | os.W_OK | os.X_OK):
                return False
        return True
    except (HTTPError, URLError, OSError, RuntimeError, ValueError):
        return False


def _supabase_object_url(bucket: str, storage_key: str, *, public: bool = False) -> str:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Supabase storage is not configured")
    prefix = "/storage/v1/object/public/" if public else "/storage/v1/object/"
    encoded_key = quote(storage_key, safe="/")
    return f"{settings.supabase_url.rstrip('/')}{prefix}{quote(bucket, safe='')}/{encoded_key}"


def _supabase_request(method: str, bucket: str, storage_key: str, *, content: bytes | None = None, public: bool = False) -> bytes:
    settings = get_settings()
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }
    if content is not None:
        headers["Content-Type"] = "application/octet-stream"
        headers["x-upsert"] = "false"
    try:
        with urlopen(Request(_supabase_object_url(bucket, storage_key, public=public), data=content, headers=headers, method=method), timeout=SUPABASE_TIMEOUT_SECONDS) as response:
            return response.read()
    except (HTTPError, URLError, OSError) as exc:
        raise RuntimeError("Supabase storage operation failed") from exc


def _root() -> Path:
    root = Path(get_settings().private_storage_root).expanduser().resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


def _safe_path(storage_key: str) -> Path:
    relative = PurePosixPath(storage_key)
    if relative.is_absolute() or ".." in relative.parts or not storage_key:
        raise ValueError("invalid private storage key")
    root = _root()
    path = (root / Path(*relative.parts)).resolve()
    if path != root and root not in path.parents:
        raise ValueError("invalid private storage key")
    return path


def put_private_object(storage_key: str, content: bytes) -> None:
    if _use_supabase():
        _supabase_request("POST", get_settings().supabase_private_bucket, storage_key, content=content)
        return
    destination = _safe_path(storage_key)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.upload")
    try:
        temporary.write_bytes(content)
        temporary.chmod(0o600)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def read_private_object(storage_key: str) -> bytes:
    if _use_supabase():
        return _supabase_request("GET", get_settings().supabase_private_bucket, storage_key)
    return _safe_path(storage_key).read_bytes()


def delete_private_object(storage_key: str) -> None:
    if _use_supabase():
        _supabase_request("DELETE", get_settings().supabase_private_bucket, storage_key)
        return
    _safe_path(storage_key).unlink(missing_ok=True)


def _public_root() -> Path:
    root = Path(get_settings().public_storage_root).expanduser().resolve()
    root.mkdir(mode=0o755, parents=True, exist_ok=True)
    return root


def _safe_public_path(storage_key: str) -> Path:
    relative = PurePosixPath(storage_key)
    if relative.is_absolute() or ".." in relative.parts or not storage_key:
        raise ValueError("invalid public storage key")
    root = _public_root()
    path = (root / Path(*relative.parts)).resolve()
    if path != root and root not in path.parents:
        raise ValueError("invalid public storage key")
    return path


def put_public_object(storage_key: str, content: bytes) -> None:
    if _use_supabase():
        _supabase_request("POST", get_settings().supabase_public_bucket, storage_key, content=content)
        return
    destination = _safe_public_path(storage_key)
    destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.publish")
    try:
        temporary.write_bytes(content)
        temporary.chmod(0o644)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def read_public_object(storage_key: str) -> bytes:
    if _use_supabase():
        return _supabase_request("GET", get_settings().supabase_public_bucket, storage_key, public=True)
    return _safe_public_path(storage_key).read_bytes()
