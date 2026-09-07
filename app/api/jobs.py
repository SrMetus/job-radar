from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.api.dependencies import SessionDep
from app.models import Job
from app.schemas.job import JobCreate, JobRead

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def create_job(job_in: JobCreate, session: SessionDep) -> Job:
    job = Job(**job_in.model_dump())
    session.add(job)
    session.commit()
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


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: int, session: SessionDep) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job
