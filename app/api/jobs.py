from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import SessionDep
from app.db.errors import is_job_url_conflict
from app.core.config import get_external_job_source_url, get_python_org_jobs_url
from app.models import Job
from app.schemas.job import JobCreate, JobImportSummary, JobRead
from app.services.job_import import ExternalJobSourceError, import_jobs
from app.services.python_org_import import import_python_org_jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def create_job(job_in: JobCreate, session: SessionDep) -> Job:
    job = Job(**job_in.model_dump())
    session.add(job)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        if is_job_url_conflict(error):
            raise HTTPException(status_code=409, detail="A job with this URL already exists") from None
        raise
    session.refresh(job)
    return job


@router.get("", response_model=list[JobRead])
def list_jobs(
    session: SessionDep,
    remote: bool | None = None,
    seniority: str | None = None,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Job]:
    statement = select(Job).order_by(Job.created_at.desc(), Job.id.desc())
    if remote is not None:
        statement = statement.where(Job.remote == remote)
    if seniority is not None:
        statement = statement.where(func.lower(Job.seniority) == func.lower(seniority))
    if q is not None:
        statement = statement.where(
            or_(
                Job.title.icontains(q, autoescape=True),
                Job.company.icontains(q, autoescape=True),
                Job.location.icontains(q, autoescape=True),
                Job.description.icontains(q, autoescape=True),
            )
        )
    statement = statement.limit(limit).offset(offset)
    return list(session.scalars(statement).all())


@router.post("/import", response_model=JobImportSummary)
def import_external_jobs(session: SessionDep) -> JobImportSummary:
    try:
        source_url = get_external_job_source_url()
    except ValueError as error:
        raise HTTPException(status_code=503, detail=str(error)) from None
    try:
        return import_jobs(session, source_url)
    except ExternalJobSourceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from None


@router.post("/import/python-org", response_model=JobImportSummary)
def import_html_jobs(session: SessionDep) -> JobImportSummary:
    try:
        source_url = get_python_org_jobs_url()
    except ValueError as error:
        raise HTTPException(status_code=503, detail=str(error)) from None
    try:
        return import_python_org_jobs(session, source_url)
    except ExternalJobSourceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from None


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: int, session: SessionDep) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job
