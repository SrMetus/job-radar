from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobCreate(BaseModel):
    title: str
    company: str
    location: str
    remote: bool = False
    seniority: str
    description: str
    url: str


class JobRead(JobCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class JobImportSummary(BaseModel):
    fetched: int
    created: int
    skipped: int
