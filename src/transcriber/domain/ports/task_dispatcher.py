from typing import Protocol

class TaskDispatcher(Protocol):
    def dispatch(self, job_id: str) -> None: ...
