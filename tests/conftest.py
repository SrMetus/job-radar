from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app


@pytest.fixture
def engine() -> Generator[Engine, None, None]:
    database = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(database)
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def client(engine: Engine) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        del app.dependency_overrides[get_db]


@pytest.fixture
def authorize_imports(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMPORT_SECRET", "test-only-import-secret")
    client.headers["X-Import-Secret"] = "test-only-import-secret"


@pytest.fixture
def job_data() -> dict[str, str]:
    return {
        "title": "Backend Developer",
        "company": "Example Company",
        "location": "Buenos Aires",
        "seniority": "junior",
        "description": "Build Python APIs.",
        "url": "https://example.com/jobs/1",
    }


