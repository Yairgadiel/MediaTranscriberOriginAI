from enum import StrEnum
import time

from pydantic import BaseModel, ConfigDict

class Status(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class Job(BaseModel):
    """The application-owned record for a transcription request."""

    model_config = ConfigDict(frozen=False)
    id: str
    status: str = Status.QUEUED
    stage: str | None = None
    created_at: float = 0
    started_at: float | None = None
    finished_at: float | None = None
    expires_at: float | None = None
    duration_seconds: float | None = None
    text: str | None = None
    error: dict[str, str] | None = None

    @classmethod
    def new(cls, job_id: str):
        return cls(id=job_id, created_at=time.time())

    def as_dict(self) -> dict:
        return self.model_dump(mode='json')

class JobError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)
