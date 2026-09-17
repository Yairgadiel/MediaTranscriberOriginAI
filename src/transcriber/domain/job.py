from dataclasses import dataclass, asdict
from enum import StrEnum
import time

class Status(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class Job:
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

    def as_dict(self):
        return asdict(self)

class JobError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)
