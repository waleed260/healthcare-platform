from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()
# prepare_threshold=None keeps psycopg compatible with PgBouncer transaction pooling (Neon pooled URLs);
# the connect timeout is configurable because scale-to-zero databases need a moment to wake.
engine = create_engine(_settings.database_url, pool_pre_ping=True, connect_args={"connect_timeout": _settings.database_connect_timeout, "prepare_threshold": None})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
