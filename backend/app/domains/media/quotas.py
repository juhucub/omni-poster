from __future__ import annotations


def upload_exceeds_size_limit(size_bytes: int, max_bytes: int) -> bool:
    return max_bytes > 0 and size_bytes > max_bytes


def project_storage_quota_exceeded(existing_usage: int, new_size: int, quota_bytes: int) -> bool:
    return quota_bytes > 0 and existing_usage + new_size > quota_bytes
