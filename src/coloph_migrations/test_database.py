from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import os
import time
import uuid
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import psycopg
from psycopg import sql
from testcontainers.postgres import PostgresContainer

from .config import Config


LOCAL_DOCKER = "local-docker"


def _remote_cluster_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise ValueError("The configured test cluster must be a PostgreSQL URL or 'local-docker'")
    if parsed.path not in {"", "/", "/postgres"}:
        raise ValueError("The configured test cluster URL must connect to the postgres database")
    if parse_qs(parsed.query).get("sslmode") != ["verify-full"]:
        raise ValueError("Remote test cluster URLs must include sslmode=verify-full")
    return urlunsplit((parsed.scheme, parsed.netloc, "/postgres", parsed.query, parsed.fragment))


def _database_url(cluster_url: str, database: str) -> str:
    parsed = urlsplit(cluster_url)
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{database}", urlencode(parse_qs(parsed.query), doseq=True), ""))


@contextmanager
def _remote_temporary_database(cluster_url: str) -> Iterator[str]:
    timestamp = int(time.time())
    name = f"kbtest_{timestamp}_{uuid.uuid4().hex}"
    with psycopg.connect(cluster_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield _database_url(cluster_url, name)
    finally:
        with psycopg.connect(cluster_url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@contextmanager
def temporary_database(config: Config) -> Iterator[str]:
    if config.test_cluster_url_env:
        configured = os.environ.get(config.test_cluster_url_env)
        if not configured:
            raise ValueError(f"{config.test_cluster_url_env} is required")
        if configured != LOCAL_DOCKER:
            with _remote_temporary_database(_remote_cluster_url(configured)) as database_url:
                yield database_url
            return
    container = PostgresContainer(image=config.postgres_image, driver=None, shm_size="256mb")
    container.start()
    try:
        yield container.get_connection_url()
    finally:
        container.stop()
