from __future__ import annotations

from pathlib import Path
from typing import Protocol


class StorageAdapter(Protocol):
    def ensure_directory(self, path: str | Path) -> Path:
        ...

    def is_file(self, path: str | Path) -> bool:
        ...

    def copy_file(self, source: str | Path, destination: str | Path, *, skip_same: bool = True) -> Path:
        ...

    def delete_file(self, path: str | Path) -> bool:
        ...

    def file_size(self, path: str | Path) -> int:
        ...

    def directory_usage_bytes(self, root: str | Path) -> int:
        ...

    def guess_mime_type(self, path: str | Path) -> str:
        ...
