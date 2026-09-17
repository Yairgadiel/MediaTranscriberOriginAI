from pathlib import Path
from typing import Protocol

class MediaProcessor(Protocol):
    def normalize(self, source: Path, destination: Path) -> float: ...
