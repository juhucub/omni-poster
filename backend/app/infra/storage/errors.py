from __future__ import annotations


class StorageInfraError(RuntimeError):
    """Base error for low-level storage infrastructure failures."""


class StoragePathTraversalError(StorageInfraError):
    """Raised when a relative storage path escapes its expected root."""


class StorageFileNotFoundError(StorageInfraError):
    """Raised when a local storage file is expected but missing."""
