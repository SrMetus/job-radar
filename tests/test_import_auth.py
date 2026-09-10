from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.api import jobs
from app.api.dependencies import get_db
from app.core import config
from app.main import app
from app.schemas.job import JobImportSummary


@pytest.mark.parametrize("endpoint, importer", [
    ("/jobs/import", "import_jobs"),
    ("/jobs/import/python-org", "import_python_org_jobs"),
])
@pytest.mark.parametrize("secret", [None, "", "wrong", "test-secret"])
def test_import_authentication(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
    endpoint: str, importer: str, secret: str | None,
) -> None:
    monkeypatch.setenv("IMPORT_SECRET", "test-secret")
    monkeypatch.setenv("EXTERNAL_JOB_SOURCE_URL", "https://example.com/jobs")
    monkeypatch.setenv("PYTHON_ORG_JOBS_URL", "https://www.python.org/jobs/")
    service = Mock(return_value=JobImportSummary(fetched=2, created=1, skipped=1))
    monkeypatch.setattr(jobs, importer, service)
    database = Mock()
    # A rejected request must not even initialize the database.
    original = app.dependency_overrides[get_db]

    def tracked_db():
        database()
        yield from original()

    monkeypatch.setitem(app.dependency_overrides, get_db, tracked_db)
    headers = {} if secret is None else {"X-Import-Secret": secret}
    response = client.post(endpoint, headers=headers)
    if secret == "test-secret":
        assert response.status_code == 200
        assert response.json() == {"fetched": 2, "created": 1, "skipped": 1}
        service.assert_called_once()
    else:
        assert response.status_code == 403
        service.assert_not_called()
        database.assert_not_called()
        assert "test-secret" not in response.text


@pytest.mark.parametrize("endpoint", ["/jobs/import", "/jobs/import/python-org"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_unconfigured_secret_disables_imports(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    endpoint: str, value: str | None,
) -> None:
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    monkeypatch.delenv("IMPORT_SECRET", raising=False)
    if value is not None:
        monkeypatch.setenv("IMPORT_SECRET", value)
    service = Mock()
    monkeypatch.setattr(jobs, "import_jobs", service)
    monkeypatch.setattr(jobs, "import_python_org_jobs", service)
    assert client.post(endpoint, headers={"X-Import-Secret": "anything"}).status_code == 503
    service.assert_not_called()
    assert client.get("/health").status_code == 200
    assert client.get("/jobs").status_code == 200


def test_import_secret_dotenv_and_environment_precedence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("IMPORT_SECRET=file-test-secret\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.delenv("IMPORT_SECRET", raising=False)
    assert config.get_import_secret() == "file-test-secret"
    monkeypatch.setenv("IMPORT_SECRET", "environment-test-secret")
    assert config.get_import_secret() == "environment-test-secret"
