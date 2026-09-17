from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRANSCRIBER_")
    redis_url: str = "redis://redis:6379/0"
    work_dir: Path = Path("/work")
    model_cache: str = "/models"
    model_id: str = "Systran/faster-whisper-base.en"
    model_revision: str = "3d3d5dee26484f91867d81cb899cfcf72b96be6c"
    cpu_threads: int = Field(4, ge=1, le=32)
    max_upload_bytes: int = Field(4 * 1024**3, ge=1)
    max_duration_seconds: int = Field(3600, ge=1, le=3600)
    max_jobs: int = Field(3, ge=1, le=10)
    result_ttl: int = Field(86400, ge=1)
    upload_timeout: int = Field(900, ge=1)
    processing_timeout: int = Field(7200, ge=5)
    decode_timeout: int = Field(300, ge=1)
    cleanup_grace: int = Field(60, ge=5)
    disk_margin_bytes: int = Field(1024**3, ge=0)
    heartbeat_ttl: int = Field(20, ge=5)

    @property
    def queue_timeout(self) -> int:
        return self.max_jobs * (self.processing_timeout + self.cleanup_grace) + self.upload_timeout

    @property
    def reservation_bytes(self) -> int:
        # Multipart spool + saved upload + bounded mono PCM output and headroom.
        return 2 * self.max_upload_bytes + 256 * 1024**2
