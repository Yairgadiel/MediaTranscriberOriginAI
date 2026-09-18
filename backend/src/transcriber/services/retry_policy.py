"""Small bounded retry helper for explicitly transient pre-inference work."""
import logging
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar('T')
log = logging.getLogger(__name__)


def retry_transient(operation: Callable[[], T], *, retryable: Callable[[Exception], bool],
                    job_id: str | None, event: str, max_attempts: int,
                    delay: float, max_delay: float,
                    sleep: Callable[[float], None] = time.sleep) -> T:
    """Run at most ``max_attempts`` times, logging metadata but no user content."""
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except Exception as exc:
            if not retryable(exc) or attempt == max_attempts:
                if retryable(exc):
                    log.warning('job=%s event=%s attempts=%s outcome=exhausted', job_id, event, attempt)
                raise
            wait = min(delay * (2 ** (attempt - 1)), max_delay)
            log.warning('job=%s event=%s attempt=%s max_attempts=%s delay_seconds=%s',
                        job_id, event, attempt, max_attempts, wait)
            sleep(wait)
    raise AssertionError('bounded retry loop must return or raise')
