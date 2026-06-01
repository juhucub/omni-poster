from __future__ import annotations

from pathlib import Path


def asset_file_exists(storage_key: str) -> bool:
    return Path(storage_key).exists()


def asset_file_missing(storage_key: str) -> bool:
    return not asset_file_exists(storage_key)
