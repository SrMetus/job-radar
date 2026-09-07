from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import Job


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
def job_data() -> dict[str, str]:
    return {
        "title": "Backend Developer",
        "company": "Example Company",
        "location": "Buenos Aires",
        "seniority": "junior",
        "description": "Build Python APIs.",
        "url": "https://example.com/jobs/1",
    }


def test_create_job_persists(
    client: TestClient, engine: Engine, job_data: dict[str, str]
) -> None:
    response = client.post("/jobs", json={**job_data, "remote": True})

    assert response.status_code == 201
    body = response.json()
    assert body == {**job_data, "remote": True, "id": body["id"], "created_at": body["created_at"]}
    assert isinstance(body["id"], int)
    assert datetime.fromisoformat(body["created_at"])
    with Session(engine) as session:
        saved = session.get(Job, body["id"])
        assert saved is not None
        assert saved.title == job_data["title"]
        assert saved.remote is True


def test_get_job(client: TestClient, job_data: dict[str, str]) -> None:
    created = client.post("/jobs", json=job_data)
    assert created.status_code == 201
    body = created.json()
    assert body["remote"] is False

    response = client.get(f"/jobs/{body['id']}")

    assert response.status_code == 200
    assert response.json() == body


def test_list_jobs_newest_first(
    client: TestClient, engine: Engine, job_data: dict[str, str]
) -> None:
    with Session(engine) as session:
        # Insert out of chronological order; two jobs share the newest timestamp.
        newest = Job(**job_data, created_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
        older = Job(**job_data, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        tied = Job(**job_data, created_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
        session.add_all([newest, older, tied])
        session.commit()
        expected_ids = [tied.id, newest.id, older.id]

    response = client.get("/jobs")

    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == expected_ids


def test_list_jobs_empty(client: TestClient) -> None:
    response = client.get("/jobs")
    assert response.status_code == 200
    assert response.json() == []


def test_get_job_not_found(client: TestClient) -> None:
    response = client.get("/jobs/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found"}


def test_create_job_missing_fields_does_not_persist(
    client: TestClient, engine: Engine
) -> None:
    response = client.post("/jobs", json={"title": "Incomplete"})
    assert response.status_code == 422
    with Session(engine) as session:
        assert session.scalars(select(Job)).all() == []
