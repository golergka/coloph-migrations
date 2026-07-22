from contextlib import contextmanager
from pathlib import Path

import pytest

from coloph_migrations.config import Config
from coloph_migrations import test_database


def _config() -> Config:
    return Config(
        root=Path.cwd(),
        migrations_dir=Path("migrations"),
        schema_snapshot=Path("schema.sql"),
        test_cluster_url_env="TEST_CLUSTER_DSN",
    )


def test_missing_configured_cluster_uses_local_docker(monkeypatch):
    monkeypatch.delenv("TEST_CLUSTER_DSN", raising=False)

    observed = []

    class Container:
        def __init__(self, **kwargs):
            observed.append(kwargs)

        def start(self):
            observed.append("start")

        def get_connection_url(self):
            return "postgresql://local/test"

        def stop(self):
            observed.append("stop")

    monkeypatch.setattr(test_database, "PostgresContainer", Container)
    with test_database.temporary_database(_config()) as database_url:
        assert database_url == "postgresql://local/test"
    assert observed[1:] == ["start", "stop"]


@pytest.mark.parametrize(
    "value, message",
    [
        ("mysql://db/postgres?sslmode=verify-full", "PostgreSQL URL"),
        ("postgresql://db/example?sslmode=verify-full", "postgres database"),
        ("postgresql://db/postgres?sslmode=require", "sslmode=verify-full"),
    ],
)
def test_remote_cluster_validation(value, message):
    with pytest.raises(ValueError, match=message):
        test_database._remote_cluster_url(value)


def test_local_docker_sentinel_uses_container(monkeypatch):
    observed = []

    class Container:
        def __init__(self, **kwargs):
            observed.append(kwargs)

        def start(self):
            observed.append("start")

        def get_connection_url(self):
            return "postgresql://local/test"

        def stop(self):
            observed.append("stop")

    monkeypatch.setenv("TEST_CLUSTER_DSN", "local-docker")
    monkeypatch.setattr(test_database, "PostgresContainer", Container)
    with test_database.temporary_database(_config()) as database_url:
        assert database_url == "postgresql://local/test"
    assert observed[1:] == ["start", "stop"]


def test_remote_cluster_allocates_database(monkeypatch):
    observed = []

    @contextmanager
    def remote(cluster_url):
        observed.append(cluster_url)
        yield "postgresql://remote/kbtest_1"

    monkeypatch.setenv("TEST_CLUSTER_DSN", "postgresql://test@db/postgres?sslmode=verify-full")
    monkeypatch.setattr(test_database, "_remote_temporary_database", remote)
    with test_database.temporary_database(_config()) as database_url:
        assert database_url == "postgresql://remote/kbtest_1"
    assert observed == ["postgresql://test@db/postgres?sslmode=verify-full"]
