from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.models import Job


def test_create_job_persists(
    client: TestClient, engine: Engine, job_data: dict[str, str]
) -> None:
    response = client.post("/jobs", json={**job_data, "remote": True})

    assert response.status_code == 201
    body = response.json()
    assert body == {
        **job_data, "remote": True, "id": body["id"],
        "created_at": body["created_at"], "match_score": 65,
    }
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
        for index, job in enumerate([newest, older, tied]):
            job.url = f"https://example.com/ordering/{index}"
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


def test_duplicate_url_returns_conflict(client: TestClient, job_data: dict[str, str]) -> None:
    assert client.post("/jobs", json=job_data).status_code == 201
    duplicate = client.post("/jobs", json=job_data)
    assert duplicate.status_code == 409
    assert client.post("/jobs", json={**job_data, "url": "https://example.com/new"}).status_code == 201


def test_create_job_missing_fields_does_not_persist(
    client: TestClient, engine: Engine
) -> None:
    response = client.post("/jobs", json={"title": "Incomplete"})
    assert response.status_code == 422
    with Session(engine) as session:
        assert session.scalars(select(Job)).all() == []


@pytest.fixture
def filter_jobs(engine: Engine, job_data: dict[str, str]) -> list[int]:
    with Session(engine) as session:
        jobs = [
            Job(**{**job_data, "title": "Python Developer", "remote": True,
                   "seniority": "Junior"}),
            Job(**{**job_data, "company": "PYTHON Labs", "remote": False,
                   "seniority": "JUNIOR", "description": "Build APIs"}),
            Job(**{**job_data, "location": "Python Valley", "remote": True,
                   "seniority": "senior", "description": "Build APIs"}),
            Job(**{**job_data, "remote": True, "seniority": "junior developer"}),
        ]
        for day, job in enumerate(jobs, start=1):
            job.created_at = datetime(2026, 1, day, tzinfo=timezone.utc)
            job.url = f"https://example.com/filter/{day}"
        session.add_all(jobs)
        session.commit()
        return [job.id for job in jobs]


@pytest.mark.parametrize("remote, indices", [("true", [3, 2, 0]), ("false", [1])])
def test_filter_remote(
    client: TestClient, filter_jobs: list[int], remote: str, indices: list[int]
) -> None:
    response = client.get("/jobs", params={"remote": remote})
    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == [filter_jobs[i] for i in indices]


def test_filter_seniority_exact_case_insensitive(
    client: TestClient, filter_jobs: list[int]
) -> None:
    response = client.get("/jobs", params={"seniority": "jUnIoR"})
    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == [filter_jobs[1], filter_jobs[0]]


@pytest.mark.parametrize("field", ["title", "company", "location", "description"])
def test_text_search_each_field(
    client: TestClient, engine: Engine, job_data: dict[str, str], field: str
) -> None:
    with Session(engine) as session:
        matching = Job(**{**job_data, field: "A NeEdLe inside text"})
        matching.url = "https://example.com/matching"
        session.add_all([matching, Job(**job_data)])
        session.commit()
        expected_id = matching.id
    response = client.get("/jobs", params={"q": "needle"})
    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == [expected_id]


@pytest.mark.parametrize("query", ["%", "_", "/"])
def test_text_search_treats_wildcards_literally(
    client: TestClient, engine: Engine, job_data: dict[str, str], query: str
) -> None:
    with Session(engine) as session:
        matching = Job(**{**job_data, "title": f"Literal {query} character"})
        matching.url = "https://example.com/matching"
        session.add_all([matching, Job(**job_data)])
        session.commit()
        expected_id = matching.id
    response = client.get("/jobs", params={"q": query})
    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == [expected_id]


def test_combined_filters(client: TestClient, filter_jobs: list[int]) -> None:
    response = client.get(
        "/jobs", params={"remote": "true", "seniority": "JUNIOR", "q": "pYtHoN"}
    )
    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == [filter_jobs[0]]


def test_pagination_applies_after_filters(
    client: TestClient, filter_jobs: list[int]
) -> None:
    response = client.get(
        "/jobs", params={"remote": "true", "limit": 1, "offset": 1}
    )
    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == [filter_jobs[2]]


@pytest.mark.parametrize(
    "params, indices",
    [({"limit": 2}, [3, 2]), ({"offset": 2}, [1, 0]),
     ({"limit": 100}, [3, 2, 1, 0]), ({"offset": 10}, [])],
)
def test_pagination(
    client: TestClient, filter_jobs: list[int], params: dict[str, int], indices: list[int]
) -> None:
    response = client.get("/jobs", params=params)
    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == [filter_jobs[i] for i in indices]


def test_default_limit_is_twenty(
    client: TestClient, engine: Engine, job_data: dict[str, str]
) -> None:
    with Session(engine) as session:
        jobs = [
            Job(**{**job_data, "url": f"https://example.com/page/{index}"},
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
            for index in range(21)
        ]
        session.add_all(jobs)
        session.commit()
        expected_ids = [job.id for job in reversed(jobs)][0:20]
    response = client.get("/jobs")
    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == expected_ids


@pytest.mark.parametrize(
    "params",
    [{"limit": "0"}, {"limit": "-1"}, {"limit": "101"}, {"limit": "abc"},
     {"limit": "1.5"}, {"offset": "-1"}, {"offset": "abc"}, {"offset": "1.5"}],
)
def test_invalid_pagination(client: TestClient, params: dict[str, str]) -> None:
    response = client.get("/jobs", params=params)
    assert response.status_code == 422


def test_filters_without_matches(client: TestClient, filter_jobs: list[int]) -> None:
    response = client.get("/jobs", params={"q": "no matching text"})
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "title, description, remote, seniority, expected",
    [
        ("Backend Python Developer", "FastAPI PostgreSQL SQLAlchemy Docker AWS Git", True, "junior", 100),
        ("Accountant", "Financial reporting", True, "senior", 0),
    ],
)
def test_api_match_scores(
    client: TestClient, job_data: dict[str, str], title: str, description: str,
    remote: bool, seniority: str, expected: int,
) -> None:
    created = client.post("/jobs", json={
        **job_data, "title": title, "description": description,
        "remote": remote, "seniority": seniority,
    })
    assert created.status_code == 201
    assert created.json()["match_score"] == expected
    detail = client.get(f"/jobs/{created.json()['id']}")
    assert detail.status_code == 200
    assert detail.json()["match_score"] == expected
    listing = client.get("/jobs")
    assert listing.status_code == 200
    assert listing.json()[0]["match_score"] == expected
