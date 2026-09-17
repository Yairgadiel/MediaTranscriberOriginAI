from pathlib import Path
from typing import Protocol

class TranscriptionEngine(Protocol):
    def transcribe(self, audio: Path) -> str: ...
