from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.models import Job
from app.services import python_org_import as scraper

pytestmark = pytest.mark.usefixtures("authorize_imports")

SOURCE = "https://www.python.org/jobs/"


@pytest.fixture
def html() -> str:
    return (Path(__file__).parent / "fixtures/python_org_jobs.html").read_text()


@pytest.fixture(autouse=True)
def http_get(monkeypatch: pytest.MonkeyPatch, html: str) -> Mock:
    monkeypatch.setenv("PYTHON_ORG_JOBS_URL", SOURCE)
    mock = Mock(return_value=httpx.Response(
        200, text=html, headers={"Content-Type": "text/html"},
        request=httpx.Request("GET", SOURCE),
    ))
    monkeypatch.setattr(scraper.httpx, "get", mock)
    return mock


def test_parsing_and_normalization(html: str) -> None:
    fetched, jobs = scraper.parse_python_org_jobs(html, SOURCE)
    assert fetched == len(jobs) == 2
    assert jobs[0].title == "Python Backend Developer"
    assert jobs[0].company == "Example & Co"
    assert jobs[0].location == "Remote, Argentina"
    assert jobs[0].url == SOURCE + "1001/"
    assert jobs[0].remote is True
    assert jobs[0].seniority == "unknown"
    assert "Back end" in jobs[0].description
    assert "Python.org" not in jobs[0].description
    assert jobs[0].url not in jobs[0].description
    assert jobs[1].remote is False


def test_import_and_repeat(client: TestClient, engine: Engine, http_get: Mock) -> None:
    first = client.post("/jobs/import/python-org")
    assert first.status_code == 200
    assert first.json() == {"fetched": 2, "created": 2, "skipped": 0}
    assert client.post("/jobs/import/python-org").json() == {"fetched": 2, "created": 0, "skipped": 2}
    with Session(engine) as session:
        assert len(session.scalars(select(Job)).all()) == 2
    assert http_get.call_count == 2


def test_duplicate_cards(client: TestClient, http_get: Mock, html: str) -> None:
    http_get.return_value = httpx.Response(200, text=html.replace("1002", "1001"),
        headers={"Content-Type": "text/html"}, request=httpx.Request("GET", SOURCE))
    assert client.post("/jobs/import/python-org").json() == {"fetched": 2, "created": 1, "skipped": 1}


@pytest.mark.parametrize("old, new", [
    ("listing-company-name", "missing-company"),
    ("listing-location", "missing-location"),
    ("/jobs/1001/", "javascript:alert(1)"),
    ("/jobs/1001/", "https://evil.example/jobs/1001/"),
    (" Python Backend Developer ", " "),
    (" Example &amp; Co", " "),
])
def test_missing_or_invalid_records(html: str, old: str, new: str) -> None:
    fetched, jobs = scraper.parse_python_org_jobs(html.replace(old, new, 1), SOURCE)
    assert fetched == 2
    assert len(jobs) == 1


def test_malformed_html_skips_incomplete_cards() -> None:
    fetched, jobs = scraper.parse_python_org_jobs('<ol class="list-recent-jobs"><li><h2>Broken', SOURCE)
    assert fetched == 1 and jobs == []


def test_unrecognized_page() -> None:
    with pytest.raises(scraper.ExternalJobSourceError, match="listing was not found"):
        scraper.parse_python_org_jobs("<html>Access denied</html>", SOURCE)


@pytest.mark.parametrize("status", [403, 429, 500, 302])
def test_http_errors(client: TestClient, http_get: Mock, status: int) -> None:
    http_get.return_value = httpx.Response(status, request=httpx.Request("GET", SOURCE))
    assert client.post("/jobs/import/python-org").status_code == 502


def test_non_html_response(client: TestClient, http_get: Mock) -> None:
    http_get.return_value = httpx.Response(200, json={}, request=httpx.Request("GET", SOURCE))
    assert client.post("/jobs/import/python-org").status_code == 502


def test_timeout(client: TestClient, http_get: Mock) -> None:
    http_get.side_effect = httpx.ReadTimeout("timeout")
    assert client.post("/jobs/import/python-org").status_code == 502


def test_empty_listing() -> None:
    assert scraper.parse_python_org_jobs('<ol class="list-recent-jobs"></ol>', SOURCE) == (0, [])


def test_invalid_configuration(client: TestClient, monkeypatch: pytest.MonkeyPatch, http_get: Mock) -> None:
    monkeypatch.setenv("PYTHON_ORG_JOBS_URL", "https://other.example/jobs/")
    assert client.post("/jobs/import/python-org").status_code == 503
    http_get.assert_not_called()
