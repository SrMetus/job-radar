from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field

from app.services.job_scoring import calculate_match_score


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

    @computed_field
    @property
    def match_score(self) -> int:
        return calculate_match_score(
            title=self.title, description=self.description,
            remote=self.remote, seniority=self.seniority,
        )


class JobImportSummary(BaseModel):
    fetched: int
    created: int
    skipped: int
