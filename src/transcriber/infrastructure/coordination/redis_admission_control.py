import time

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
