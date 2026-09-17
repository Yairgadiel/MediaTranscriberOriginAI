import re
import shutil
import time
from pathlib import Path
from transcriber.domain.models.transcription_job import JobError

ID = re.compile(r"^[a-f0-9]{32}$")

class LocalMediaStorage:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def directory(self, job_id):
        if not ID.fullmatch(job_id):
            raise ValueError("Invalid storage ID")
        path = self.root / job_id
        if path.is_symlink():
            raise ValueError("Symlink storage directory")
        return path

    def save(self, job_id, source, max_bytes):
        directory = self.directory(job_id)
        directory.mkdir(exist_ok=False)
        part = directory / 'upload.part'
        count = 0
        try:
            with part.open('xb') as output:
                while chunk := source.read(1024 * 1024):
                    count += len(chunk)
                    if count > max_bytes:
                        raise JobError('upload_too_large', 'The file exceeds the upload limit.')
                    output.write(chunk)
            if not count:
                raise JobError('empty_upload', 'Choose a nonempty media file.')
            part.rename(self.input_path(job_id))
        except BaseException:
            self.delete(job_id)
            raise

    def input_path(self, job_id):
        return self.directory(job_id) / 'input'

    def audio_path(self, job_id):
        return self.directory(job_id) / 'audio.wav'

    def delete(self, job_id):
        path = self.directory(job_id)
        if path.exists():
            shutil.rmtree(path)

    def free_bytes(self):
        return shutil.disk_usage(self.root).free

    def healthy(self):
        import tempfile
        with tempfile.TemporaryFile(dir=self.root) as probe:
            probe.write(b'ok')
        return True

    def old_directories(self, before):
        return [p.name for p in self.root.iterdir()
                if ID.fullmatch(p.name) and p.is_dir() and not p.is_symlink() and p.stat().st_mtime < before]
