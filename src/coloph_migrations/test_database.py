from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from testcontainers.postgres import PostgresContainer

from .config import Config


@contextmanager
def temporary_database(config: Config) -> Iterator[str]:
    container = PostgresContainer(image=config.postgres_image, driver=None, shm_size="256mb")
    container.start()
    try:
        yield container.get_connection_url()
    finally:
        container.stop()
