from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text

from qaswarm.config import Settings, get_settings
from qaswarm.db import session as db_session
from qaswarm.db.models import Base
from qaswarm.db.seed import seed

TEST_DB_URL = os.environ.get("AQS_TEST_DATABASE_URL")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if TEST_DB_URL:
        return
    skip = pytest.mark.skip(
        reason="AQS_TEST_DATABASE_URL is not set; PostgreSQL integration tests skipped"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    return Settings(
        database_url=TEST_DB_URL or "postgresql+psycopg://unused",
        dev_auth=True,
        lease_ttl_seconds=90,
        backoff_seconds=[30, 120],
        idempotency_ttl_hours=24,
        sse_heartbeat_seconds=1,
    )


@pytest.fixture(scope="session")
def engine(test_settings: Settings) -> Iterator[Engine]:
    if not TEST_DB_URL:
        pytest.skip("AQS_TEST_DATABASE_URL is not set")
    eng = create_engine(TEST_DB_URL, future=True, pool_pre_ping=True)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    db_session.set_engine(eng)
    get_settings.cache_clear()
    os.environ["AQS_DATABASE_URL"] = TEST_DB_URL
    os.environ["AQS_DEV_AUTH"] = "true"
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def clean_db(engine: Engine) -> Iterator[Engine]:
    """Truncate every table before each integration test and re-seed the sample org."""
    with engine.begin() as conn:
        tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    seed()
    yield engine


@pytest.fixture
def app(clean_db: Engine, test_settings: Settings):  # type: ignore[no-untyped-def]
    from qaswarm.api.app import create_app

    application = create_app(test_settings)
    application.dependency_overrides[get_settings] = lambda: test_settings
    return application


@pytest.fixture
def client(app) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-Dev-User": "usr_test_lead", "X-Dev-Role": "QA Lead"}


@pytest.fixture
def engineer_headers() -> dict[str, str]:
    return {"X-Dev-User": "usr_test_engineer", "X-Dev-Role": "QA Engineer"}


@pytest.fixture
def viewer_headers() -> dict[str, str]:
    return {"X-Dev-User": "usr_test_viewer", "X-Dev-Role": "Viewer"}
