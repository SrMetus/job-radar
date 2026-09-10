"""Run every supported source independently, without scheduling or HTTP concerns."""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_external_job_source_url, get_python_org_jobs_url
from app.services.job_import import import_jobs
from app.services.python_org_import import import_python_org_jobs


@dataclass(frozen=True)
class SourceImportResult:
    source: str
    fetched: int | None = None
    created: int | None = None
    skipped: int | None = None
    failed: bool = False
    error: str | None = None


def run_all_imports(session_factory: Callable[[], Session]) -> list[SourceImportResult]:
    """Attempt both sources, including reporting missing/invalid configuration.

    Each importer owns its commit. A fresh session per source isolates failures;
    closing it rolls back unfinished work. Counts are unknown on failure.
    """
    sources = (
        ("remotive", get_external_job_source_url, import_jobs),
        ("python-org", get_python_org_jobs_url, import_python_org_jobs),
    )
    results = []
    for source, get_url, importer in sources:
        try:
            source_url = get_url()
            with session_factory() as session:
                summary = importer(session, source_url)
        except Exception as error:
            # Provider, configuration, database and unexpected source failures
            # must not stop the batch. Never expose URLs, SQL or credentials.
            results.append(SourceImportResult(
                source=source, failed=True, error=type(error).__name__,
            ))
        else:
            results.append(SourceImportResult(source=source, **summary.model_dump()))
    return results
