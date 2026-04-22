from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import httpx

from app.core.config import settings


class YouTubePublishError(RuntimeError):
    pass


def _privacy_status_for_schedule(scheduled_for: datetime | None) -> str:
    return "private" if scheduled_for else "public"


def upload_short(
    *,
    access_token: str,
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    scheduled_for: datetime | None,
) -> dict:
    file_path = Path(video_path)
    if not file_path.exists():
        raise YouTubePublishError("Preview file is missing from storage.")

    metadata = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": _privacy_status_for_schedule(scheduled_for),
            "selfDeclaredMadeForKids": False,
        },
    }
    if scheduled_for:
        metadata["status"]["publishAt"] = scheduled_for.replace(microsecond=0).isoformat() + "Z"

    files = {
        "metadata": ("metadata.json", json.dumps(metadata), "application/json"),
        "media": (file_path.name, file_path.open("rb"), "video/mp4"),
    }
    try:
        response = httpx.post(
            settings.YOUTUBE_UPLOAD_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            files=files,
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        raise YouTubePublishError(f"YouTube upload failed: {detail}") from exc
    except httpx.HTTPError as exc:
        raise YouTubePublishError("YouTube upload request failed.") from exc
    finally:
        media_file = files["media"][1]
        media_file.close()

    video_id = payload.get("id")
    if not video_id:
        raise YouTubePublishError("YouTube upload did not return a video id.")

    return {
        "external_post_id": video_id,
        "external_url": f"https://www.youtube.com/watch?v={video_id}",
        "payload": payload,
    }
