"""Import the Remotive public JSON format without changing existing jobs."""

import httpx
from pydantic import HttpUrl, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Job
from app.db.errors import is_job_url_conflict
from app.schemas.job import JobCreate, JobImportSummary
from app.services.job_normalization import html_to_text, infer_seniority


class ExternalJobSourceError(Exception):
    """The provider could not supply a valid jobs response."""


def fetch_jobs(source_url: str) -> list[object]:
    try:
        response = httpx.get(source_url, timeout=15.0, follow_redirects=True)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise ExternalJobSourceError("External job source request failed.") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise ExternalJobSourceError("External job source returned an invalid jobs response.")
    return payload["jobs"]


def normalize_remotive_job(record: object) -> JobCreate | None:
    if not isinstance(record, dict):
        return None
    fields = {}
    for field in ("title", "company_name", "candidate_required_location", "description", "url"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip() or "\x00" in value:
            return None
        fields[field] = value.strip()
    try:
        TypeAdapter(HttpUrl).validate_python(fields["url"])
    except ValidationError:
        return None
    description = html_to_text(fields["description"])
    if not description:
        return None
    return JobCreate(
        title=fields["title"],
        company=fields["company_name"],
        location=fields["candidate_required_location"],
        remote=True,
        seniority=infer_seniority(fields["title"]),
        description=description,
        url=fields["url"],
    )


def import_jobs(session: Session, source_url: str) -> JobImportSummary:
    records = fetch_jobs(source_url)
    normalized = [job for record in records if (job := normalize_remotive_job(record)) is not None]
    return persist_new_jobs(session, normalized, fetched=len(records))


def persist_new_jobs(
    session: Session, normalized: list[JobCreate], *, fetched: int
) -> JobImportSummary:
    urls = {job.url for job in normalized}
    created = 0
    try:
        seen = set(session.scalars(select(Job.url).where(Job.url.in_(urls)))) if urls else set()
        # Consistent lock ordering avoids deadlocks between overlapping batches.
        for job in sorted(normalized, key=lambda item: item.url):
            if job.url in seen:
                continue
            try:
                with session.begin_nested():
                    session.add(Job(**job.model_dump()))
                    session.flush()
            except IntegrityError as error:
                if not is_job_url_conflict(error):
                    raise
            else:
                created += 1
            seen.add(job.url)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
    return JobImportSummary(fetched=fetched, created=created, skipped=fetched - created)
