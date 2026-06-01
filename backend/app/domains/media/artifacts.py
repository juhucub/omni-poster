from __future__ import annotations

from urllib.parse import quote


def artifact_url_path(job_id: int, relative_posix: str) -> str:
    return f"/generation-jobs/{job_id}/artifacts/{quote(relative_posix)}"
