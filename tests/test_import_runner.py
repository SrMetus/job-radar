from pathlib import Path
from unittest.mock import MagicMock, Mock

import httpx
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.models import Job
from app.schemas.job import JobImportSummary
from app.services import import_runner as runner
from app.services.job_import import ExternalJobSourceError


@pytest.fixture(autouse=True)
def source_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTERNAL_JOB_SOURCE_URL", "https://example.com/jobs")
    monkeypatch.setenv("PYTHON_ORG_JOBS_URL", "https://www.python.org/jobs/")


def test_successful_results_and_session_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    sessions = [Mock(spec=Session), Mock(spec=Session)]
    # Verify each source's session context is exited.
    contexts = [MagicMock(), MagicMock()]
    for context, session in zip(contexts, sessions):
        context.__enter__.return_value = session
    factory = Mock(side_effect=contexts)
    first = Mock(return_value=JobImportSummary(fetched=5, created=3, skipped=2))
    second = Mock(return_value=JobImportSummary(fetched=4, created=1, skipped=3))
    monkeypatch.setattr(runner, "import_jobs", first)
    monkeypatch.setattr(runner, "import_python_org_jobs", second)
    results = runner.run_all_imports(factory)
    assert results == [
        runner.SourceImportResult("remotive", 5, 3, 2),
        runner.SourceImportResult("python-org", 4, 1, 3),
    ]
    first.assert_called_once_with(sessions[0], "https://example.com/jobs")
    second.assert_called_once_with(sessions[1], "https://www.python.org/jobs/")
    for context in contexts:
        context.__exit__.assert_called_once_with(None, None, None)


@pytest.mark.parametrize("failure_index", [0, 1])
@pytest.mark.parametrize("error", [ExternalJobSourceError("private URL"), RuntimeError("private SQL")])
def test_source_failure_does_not_stop_other_source(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, failure_index: int, error: Exception,
) -> None:
    importers = [Mock(return_value=JobImportSummary(fetched=1, created=1, skipped=0)) for _ in range(2)]
    importers[failure_index].side_effect = error
    monkeypatch.setattr(runner, "import_jobs", importers[0])
    monkeypatch.setattr(runner, "import_python_org_jobs", importers[1])
    results = runner.run_all_imports(lambda: Session(engine))
    assert results[failure_index].failed
    assert results[failure_index].fetched is None
    assert results[failure_index].error == type(error).__name__
    assert not results[1 - failure_index].failed
    assert results[1 - failure_index].created == 1
    for importer in importers:
        importer.assert_called_once()


def test_failed_transaction_is_isolated(
    engine: Engine, job_data: dict[str, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(session: Session, source_url: str) -> JobImportSummary:
        session.add(Job(title="Missing required fields"))
        session.flush()
        raise AssertionError("Unreachable")

    def succeed(session: Session, source_url: str) -> JobImportSummary:
        session.add(Job(**job_data))
        session.commit()
        return JobImportSummary(fetched=1, created=1, skipped=0)

    monkeypatch.setattr(runner, "import_jobs", fail)
    monkeypatch.setattr(runner, "import_python_org_jobs", succeed)
    results = runner.run_all_imports(lambda: Session(engine))
    assert results[0].failed and results[0].error == "IntegrityError"
    assert results[1].created == 1
    with Session(engine) as session:
        assert session.scalars(select(Job)).one().title == job_data["title"]


def test_invalid_configuration_does_not_stop_other_source(
    engine: Engine, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXTERNAL_JOB_SOURCE_URL", "")
    first = Mock()
    second = Mock(return_value=JobImportSummary(fetched=0, created=0, skipped=0))
    monkeypatch.setattr(runner, "import_jobs", first)
    monkeypatch.setattr(runner, "import_python_org_jobs", second)
    results = runner.run_all_imports(lambda: Session(engine))
    assert results[0].failed and results[0].error == "ValueError"
    assert not results[1].failed
    first.assert_not_called()
    second.assert_called_once()


def test_real_importers_reuse_deduplication(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    html = (Path(__file__).parent / "fixtures/python_org_jobs.html").read_text()
    responses = [
        httpx.Response(200, json={"jobs": [{
            "title": "Python Developer", "company_name": "Example",
            "candidate_required_location": "Remote", "description": "Build APIs",
            "url": "https://www.python.org/jobs/1001/",
        }]}, request=httpx.Request("GET", "https://example.com/jobs")),
        httpx.Response(200, text=html, headers={"Content-Type": "text/html"},
                       request=httpx.Request("GET", "https://www.python.org/jobs/")),
    ]
    monkeypatch.setattr(httpx, "get", Mock(side_effect=responses * 2))
    first = runner.run_all_imports(lambda: Session(engine))
    second = runner.run_all_imports(lambda: Session(engine))
    assert [result.created for result in first] == [1, 1]
    assert [result.skipped for result in first] == [0, 1]
    assert [result.created for result in second] == [0, 0]
    assert [result.skipped for result in second] == [1, 2]
