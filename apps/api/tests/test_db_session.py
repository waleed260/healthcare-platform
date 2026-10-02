import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.session import engine


def _connect():
    try:
        return engine.connect()
    except OperationalError:
        pytest.skip("no database reachable")


def test_connections_bind_parameters_client_side() -> None:
    # Client-side binding avoids server-side prepared statements (pooler-safe) and untyped-NULL inference errors.
    with _connect() as connection:
        assert connection.connection.driver_connection.cursor_factory is psycopg.ClientCursor


def test_untyped_null_cursor_parameter_works_against_a_real_database() -> None:
    # The list endpoints use "(:cursor IS NULL OR col > :cursor)".
    with _connect() as connection:
        assert connection.execute(text("SELECT (:cursor IS NULL OR 1 > :cursor) AS ok"), {"cursor": None}).scalar_one() is True
