from __future__ import annotations


MOVIEPY_PROGRESS_STAGES: dict[str, int] = {
    "tts_ready": 46,
    "background_ready": 58,
    "timeline_ready": 68,
    "encoding": 80,
    "encoded": 88,
}

FFMPEG_PROGRESS_STAGES: dict[str, int] = {
    "tts_ready": 46,
    "audio_ready": 55,
    "background_ready": 62,
    "timeline_ready": 70,
    "encoding": 80,
    "encoded": 88,
}


def render_progress_payload(stage: str, *, engine: str = "ffmpeg") -> tuple[str, int]:
    stages = MOVIEPY_PROGRESS_STAGES if engine == "moviepy" else FFMPEG_PROGRESS_STAGES
    return stage, stages[stage]
