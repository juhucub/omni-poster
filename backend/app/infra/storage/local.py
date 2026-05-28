from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path


class LocalStorageAdapter:
    def ensure_directory(self, path: str | Path) -> Path:
        directory = Path(path)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def is_file(self, path: str | Path) -> bool:
        candidate = Path(path)
        return candidate.exists() and candidate.is_file()

    def copy_file(self, source: str | Path, destination: str | Path, *, skip_same: bool = True) -> Path:
        source_path = Path(source)
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if skip_same and source_path.resolve() == destination_path.resolve():
            return destination_path
        shutil.copy2(source_path, destination_path)
        return destination_path

    def delete_file(self, path: str | Path) -> bool:
        candidate = Path(path)
        if not candidate.exists() or not candidate.is_file():
            return False
        candidate.unlink()
        return True

    def file_size(self, path: str | Path) -> int:
        return Path(path).stat().st_size

    def directory_usage_bytes(self, root: str | Path) -> int:
        total = 0
        for path in Path(root).rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        return total

    def guess_mime_type(self, path: str | Path) -> str:
        return mimetypes.guess_type(str(path))[0] or "application/octet-stream"
