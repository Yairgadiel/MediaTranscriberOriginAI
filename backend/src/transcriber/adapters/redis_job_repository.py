"""Redis implementation of the domain JobRepository contract."""
import json
import time

from transcriber.domain.contracts import RedisClient
from transcriber.domain.models.job import Job
from transcriber.domain.repositories.job_repository import JobRepository

TRANSITION = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local job = cjson.decode(raw)
if job.status ~= ARGV[1] then return 0 end
local patch = cjson.decode(ARGV[2])
for k,v in pairs(patch) do job[k] = v end
redis.call('SET', KEYS[1], cjson.encode(job))
if tonumber(ARGV[3]) > 0 then
  redis.call('EXPIRE', KEYS[1], ARGV[3])
  redis.call('SREM', KEYS[2], job.id)
end
return 1
"""


class RedisJobRepository(JobRepository):
    def __init__(self, client: RedisClient, ttl: int = 86400):
        self.client, self.ttl = client, ttl
        self.transition = client.register_script(TRANSITION)

    def create(self, job: Job) -> None:
        script = """
        if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
        redis.call('SET', KEYS[1], ARGV[1])
        redis.call('SADD', KEYS[2], ARGV[2])
        return 1
        """
        if not self.client.eval(script, 2, 'job:' + job.id, 'jobs:active', json.dumps(job.as_dict()), job.id):
            raise ValueError('Job already exists')

    def get(self, job_id):
        raw = self.client.get('job:' + job_id)
        return Job(**json.loads(raw)) if raw else None

    def _change(self, job_id, expected, patch, ttl=0):
        return bool(self.transition(keys=['job:' + job_id, 'jobs:active'],
                                    args=[expected, json.dumps(patch), ttl]))

    def claim(self, job_id):
        return self._change(job_id, 'queued', {'status': 'processing', 'stage': 'validating', 'started_at': time.time()})

    def stage(self, job_id, stage):
        self._change(job_id, 'processing', {'stage': stage})

    def _finish(self, job_id, expected, patch):
        now = time.time()
        return self._change(job_id, expected, {**patch, 'stage': None, 'finished_at': now,
                                              'expires_at': now + self.ttl}, self.ttl)

    def complete(self, job_id, text, duration):
        return self._finish(job_id, 'processing', {'status': 'completed', 'text': text, 'duration_seconds': duration})

    def fail(self, job_id, code, message, expected):
        return self._finish(job_id, expected, {'status': 'failed', 'error': {'code': code, 'message': message}})

    def active(self):
        jobs = [self.get(i) for i in self.client.smembers('jobs:active')]
        return [j for j in jobs if j is not None]
