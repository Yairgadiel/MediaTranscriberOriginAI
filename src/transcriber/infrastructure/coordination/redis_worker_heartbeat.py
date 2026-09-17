import threading

class RedisWorkerHeartbeat:
    def __init__(self, client, ttl=20):
        self.client, self.ttl = client, ttl
        self.current_job = None
        self.model_ready = False
        self.stop = threading.Event()

    def ready(self):
        return bool(self.client.exists('worker:ready'))

    def job_alive(self, job_id):
        return bool(self.client.exists('worker:job:' + job_id))

    def run(self):
        while not self.stop.is_set():
            try:
                if self.model_ready:
                    self.client.set('worker:ready', '1', ex=self.ttl)
                if self.current_job:
                    self.client.set('worker:job:' + self.current_job, '1', ex=self.ttl)
            except Exception:
                pass  # Readiness expires; admission fails closed on Redis errors.
            self.stop.wait(3)
