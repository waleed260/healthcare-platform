from collections.abc import Generator

import psycopg
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()
# ClientCursor binds parameters client-side (like psycopg2). Server-side binding cannot infer the type of an
# untyped NULL used as ``(:cursor IS NULL OR col > :cursor)``, which the list endpoints rely on, and it also
# never creates server-side prepared statements, so pooled (PgBouncer/Neon) connections are safe.
# The connect timeout is configurable because scale-to-zero databases need a moment to wake.
engine = create_engine(_settings.database_url, pool_pre_ping=True, connect_args={"connect_timeout": _settings.database_connect_timeout, "cursor_factory": psycopg.ClientCursor})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
