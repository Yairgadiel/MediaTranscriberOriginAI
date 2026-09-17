from datetime import datetime

from pydantic import BaseModel

from transcriber.domain.models.job import Job


class JobResponse(BaseModel):
    id: str
    status: str
    stage: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    expires_at: datetime | None
    duration_seconds: float | None
    text: str | None
    error: dict[str, str] | None
    status_url: str

    @classmethod
    def from_job(cls, job: Job) -> 'JobResponse':
        return cls(**job.as_dict(), status_url=f'/api/transcriptions/{job.id}')
