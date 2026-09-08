from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core import config
from app.models import Job
from app.services import job_import


def test_database_conflict_is_skipped_and_session_remains_usable(
    engine: Engine, http_get: Mock, external_job: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = job_import.normalize_remotive_job(external_job)
    assert existing is not None
    with Session(engine) as session:
        session.add(Job(**existing.model_dump()))
        session.commit()
    mock_response(http_get, {"jobs": [external_job, {**external_job, "url": "https://remotive.com/new"}]})
    with Session(engine) as session:
        # Simulate a stale pre-check; the real unique constraint rejects the insert.
        with monkeypatch.context() as patch:
            patch.setattr(session, "scalars", lambda *args, **kwargs: [])
            result = job_import.import_jobs(session, "https://provider.example/jobs")
        assert result.model_dump() == {"fetched": 2, "created": 1, "skipped": 1}
        assert session.scalar(select(func.count()).select_from(Job)) == 2
        assert job_import.import_jobs(session, "https://provider.example/jobs").created == 0


def test_non_url_integrity_error_is_not_swallowed(
    engine: Engine, http_get: Mock, external_job: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlite3

    mock_response(http_get, {"jobs": [external_job]})
    with Session(engine) as session:
        with monkeypatch.context() as patch:
            patch.setattr(session, "flush", Mock(side_effect=IntegrityError(
                "INSERT", {}, sqlite3.IntegrityError("NOT NULL constraint failed: jobs.title")
            )))
            with pytest.raises(IntegrityError):
                job_import.import_jobs(session, "https://provider.example/jobs")
        assert session.scalar(select(func.count()).select_from(Job)) == 0


@pytest.fixture(autouse=True)
def source_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTERNAL_JOB_SOURCE_URL", "https://provider.example/jobs")


@pytest.fixture
def external_job() -> dict[str, object]:
    return {
        "title": "  Python Developer  ",
        "company_name": " Example Inc ",
        "candidate_required_location": " Worldwide ",
        "description": " <p>Build APIs.</p> ",
        "url": " https://remotive.com/remote-jobs/software-dev/example-123 ",
        "publication_date": "2025-01-01T00:00:00",
    }


@pytest.fixture(autouse=True)
def http_get(monkeypatch: pytest.MonkeyPatch) -> Mock:
    mock = Mock(side_effect=AssertionError("Test must provide a mocked HTTP response"))
    monkeypatch.setattr(job_import.httpx, "get", mock)
    return mock


def mock_response(http_get: Mock, payload: object, status: int = 200) -> None:
    http_get.side_effect = None
    http_get.return_value = httpx.Response(
        status, json=payload, request=httpx.Request("GET", "https://provider.example/jobs")
    )


def test_successful_import_and_normalization(
    client: TestClient, engine: Engine, http_get: Mock, external_job: dict[str, object]
) -> None:
    mock_response(http_get, {"jobs": [external_job]})
    response = client.post("/jobs/import")
    assert response.status_code == 200
    assert response.json() == {"fetched": 1, "created": 1, "skipped": 0}
    http_get.assert_called_once_with(
        "https://provider.example/jobs", timeout=15.0, follow_redirects=True
    )
    with Session(engine) as session:
        job = session.scalars(select(Job)).one()
        assert job.title == "Python Developer"
        assert job.company == "Example Inc"
        assert job.location == "Worldwide"
        assert job.remote is True
        assert job.seniority == "unknown"
        assert job.description == "Source: Remotive\n\n<p>Build APIs.</p>"
        assert job.url == str(external_job["url"]).strip()
        assert job.id is not None and job.created_at is not None


def test_repeated_and_in_batch_duplicates(
    client: TestClient, engine: Engine, http_get: Mock, external_job: dict[str, object]
) -> None:
    mock_response(http_get, {"jobs": [external_job, external_job]})
    first = client.post("/jobs/import")
    second = client.post("/jobs/import")
    assert first.status_code == second.status_code == 200
    assert first.json() == {"fetched": 2, "created": 1, "skipped": 1}
    assert second.json() == {"fetched": 2, "created": 0, "skipped": 2}
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1


def test_existing_manual_job_is_not_changed(
    client: TestClient, engine: Engine, http_get: Mock,
    external_job: dict[str, object], job_data: dict[str, str]
) -> None:
    created = client.post("/jobs", json={**job_data, "url": str(external_job["url"]).strip()})
    assert created.status_code == 201
    mock_response(http_get, {"jobs": [external_job]})
    response = client.post("/jobs/import")
    assert response.json() == {"fetched": 1, "created": 0, "skipped": 1}
    with Session(engine) as session:
        assert session.scalars(select(Job)).one().title == job_data["title"]


@pytest.mark.parametrize("field", ["title", "company_name", "candidate_required_location", "description", "url"])
@pytest.mark.parametrize("value", [None, " ", 123, "\x00"])
def test_incomplete_records_skipped(
    client: TestClient, http_get: Mock, external_job: dict[str, object], field: str, value: object
) -> None:
    mock_response(http_get, {"jobs": [{**external_job, field: value}, external_job]})
    response = client.post("/jobs/import")
    assert response.status_code == 200
    assert response.json() == {"fetched": 2, "created": 1, "skipped": 1}


def test_malformed_records_skipped(
    client: TestClient, http_get: Mock, external_job: dict[str, object]
) -> None:
    mock_response(http_get, {"jobs": [None, [], "bad", {}, {**external_job, "url": "javascript:bad"}, external_job]})
    response = client.post("/jobs/import")
    assert response.status_code == 200
    assert response.json() == {"fetched": 6, "created": 1, "skipped": 5}


@pytest.mark.parametrize("status", [429, 500, 404])
def test_external_http_failure(
    client: TestClient, engine: Engine, http_get: Mock, status: int, external_job: dict[str, object]
) -> None:
    mock_response(http_get, {"jobs": [external_job]}, status=status)
    response = client.post("/jobs/import")
    assert response.status_code == 502
    with Session(engine) as session:
        assert session.scalars(select(Job)).all() == []


def test_timeout(client: TestClient, http_get: Mock) -> None:
    http_get.side_effect = httpx.ReadTimeout("private upstream details")
    response = client.post("/jobs/import")
    assert response.status_code == 502
    assert "private" not in response.text


@pytest.mark.parametrize("payload", [[], None, {}, {"jobs": None}, {"jobs": {}}])
def test_invalid_envelope(client: TestClient, http_get: Mock, payload: object) -> None:
    mock_response(http_get, payload)
    assert client.post("/jobs/import").status_code == 502


def test_invalid_json(client: TestClient, http_get: Mock) -> None:
    http_get.side_effect = None
    http_get.return_value = httpx.Response(
        200, text="not json", request=httpx.Request("GET", "https://provider.example/jobs")
    )
    assert client.post("/jobs/import").status_code == 502


def test_empty_response(client: TestClient, engine: Engine, http_get: Mock) -> None:
    mock_response(http_get, {"jobs": []})
    response = client.post("/jobs/import")
    assert response.status_code == 200
    assert response.json() == {"fetched": 0, "created": 0, "skipped": 0}
    with Session(engine) as session:
        assert session.scalars(select(Job)).all() == []


@pytest.mark.parametrize("url", ["", "file:///tmp/jobs", "not a url"])
def test_invalid_configuration(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, http_get: Mock, url: str
) -> None:
    monkeypatch.setenv("EXTERNAL_JOB_SOURCE_URL", url)
    assert client.post("/jobs/import").status_code == 503
    http_get.assert_not_called()


def test_source_url_dotenv_and_environment_precedence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("EXTERNAL_JOB_SOURCE_URL=https://file.example/jobs\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.delenv("EXTERNAL_JOB_SOURCE_URL")
    assert config.get_external_job_source_url() == "https://file.example/jobs"
    monkeypatch.setenv("EXTERNAL_JOB_SOURCE_URL", "https://environment.example/jobs")
    assert config.get_external_job_source_url() == "https://environment.example/jobs"
