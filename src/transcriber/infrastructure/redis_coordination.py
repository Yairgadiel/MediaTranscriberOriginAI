import time
import threading
from uuid import uuid4

class RedisAdmissionControl:
    def __init__(self, client, settings):
        self.client, self.settings = client, settings

    def reserve(self, job_id, free_bytes):
        # Expired reservations remain charged until maintenance has cleaned files.
        script = """
        if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then return 0 end
        local used = 0
        for _,v in ipairs(redis.call('HVALS', KEYS[2])) do used = used + tonumber(v) end
        if used + tonumber(ARGV[4]) + tonumber(ARGV[6]) > tonumber(ARGV[5]) then return 0 end
        redis.call('ZADD', KEYS[1], ARGV[2], ARGV[1])
        redis.call('HSET', KEYS[2], ARGV[1], ARGV[4])
        return 1
        """
        s = self.settings
        return bool(self.client.eval(script, 2, 'admission:leases', 'admission:bytes', job_id,
                                     time.time() + s.upload_timeout + s.cleanup_grace,
                                     s.max_jobs, s.reservation_bytes, free_bytes, s.disk_margin_bytes))

    def renew(self, job_id, seconds):
        return bool(self.client.zadd('admission:leases', {job_id: time.time() + seconds}, xx=True, ch=True))

    def release(self, job_id):
        self.client.eval("redis.call('ZREM', KEYS[1], ARGV[1]); redis.call('HDEL', KEYS[2], ARGV[1]); return 1",
                         2, 'admission:leases', 'admission:bytes', job_id)

    def expired(self):
        return self.client.zrangebyscore('admission:leases', '-inf', time.time())


class RedisWorkerHeartbeat:
    """One worker child; expiring readiness survives neither crashes nor outages."""
    def __init__(self, client, ttl=20):
        self.client, self.ttl = client, ttl
        self.token = uuid4().hex
        self.current_job = None
        self.stop = threading.Event()
        self._thread = None

    def ready(self):
        return bool(self.client.exists('worker:ready'))

    def job_alive(self, job_id):
        return bool(self.client.exists('worker:job:' + job_id))

    def mark_not_ready(self):
        """A replacement child must not inherit readiness from its predecessor."""
        self.client.delete('worker:ready')

    def shutdown(self):
        self.stop.set()
        if self._thread:
            self._thread.join(timeout=4)
        # Do not remove readiness that a newly loaded replacement has published.
        self.client.eval("""
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            redis.call('DEL', KEYS[1])
        end
        return 1
        """, 1, 'worker:ready', self.token)

    def start(self):
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def run(self):
        while not self.stop.is_set():
            try:
                if self.stop.is_set():
                    return
                self.client.set('worker:ready', self.token, ex=self.ttl)
                if self.current_job:
                    self.client.set('worker:job:' + self.current_job, '1', ex=self.ttl)
            except Exception:
                pass  # Keys expire; admission fails closed.
            self.stop.wait(3)
