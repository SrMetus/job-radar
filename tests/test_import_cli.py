import runpy
import sys
from types import ModuleType
from unittest.mock import MagicMock, Mock

import pytest

from app.services import import_runner as runner
from app.schemas.job import JobImportSummary


@pytest.mark.parametrize("failures", [(False, False), (True, False), (False, True), (True, True)])
def test_module_exit_summary_and_session_cleanup(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    failures: tuple[bool, bool],
) -> None:
    monkeypatch.setenv("EXTERNAL_JOB_SOURCE_URL", "https://example.com/jobs")
    monkeypatch.setenv("PYTHON_ORG_JOBS_URL", "https://www.python.org/jobs/")
    # Inject DB setup so executing the real module cannot touch a local database.
    database = ModuleType("app.db.session")
    contexts = [MagicMock(), MagicMock()]
    factory = Mock(side_effect=contexts)
    monkeypatch.setattr(database, "SessionLocal", factory, raising=False)
    monkeypatch.setitem(sys.modules, "app.db.session", database)
    for name, failed in zip(("import_jobs", "import_python_org_jobs"), failures):
        importer = Mock(return_value=JobImportSummary(fetched=3, created=1, skipped=2))
        if failed:
            importer.side_effect = RuntimeError("private connection credentials")
        monkeypatch.setattr(runner, name, importer)

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("app.tasks.import_jobs", run_name="__main__")
    assert exit_info.value.code == int(any(failures))
    output = capsys.readouterr().out
    assert len(output.splitlines()) == 2
    for source, failed in zip(("remotive", "python-org"), failures):
        expected = ("FAILED (RuntimeError) fetched=unknown created=unknown skipped=unknown"
                    if failed else "OK fetched=3 created=1 skipped=2")
        assert f"{source}: {expected}" in output
    assert "private" not in output
    assert factory.call_count == 2
    for context in contexts:
        context.__exit__.assert_called_once()


def test_cli_setup_failure_is_nonzero_and_sanitized(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    from app.tasks import import_jobs as cli

    monkeypatch.setitem(sys.modules, "app.db.session", None)
    assert cli.main() == 1
    assert capsys.readouterr().err == "Import command failed: ModuleNotFoundError\n"
