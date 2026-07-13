from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    container = PostgresContainer(image="pgvector/pgvector:pg17", driver=None, shm_size="256mb")
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture
def database_url(postgres_container: PostgresContainer) -> Iterator[str]:
    admin_url = postgres_container.get_connection_url()
    name = f"parity_{uuid4().hex}"
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    parsed = urlsplit(admin_url)
    url = urlunsplit((parsed.scheme, parsed.netloc, f"/{name}", parsed.query, parsed.fragment))
    try:
        yield url
    finally:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
