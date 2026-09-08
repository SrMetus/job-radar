import sqlite3

from sqlalchemy.exc import IntegrityError


def is_job_url_conflict(error: IntegrityError) -> bool:
    diagnostic = getattr(error.orig, "diag", None)
    if diagnostic is not None:
        return diagnostic.constraint_name == "uq_jobs_url"
    return (
        isinstance(error.orig, sqlite3.IntegrityError)
        and str(error.orig) == "UNIQUE constraint failed: jobs.url"
    )
