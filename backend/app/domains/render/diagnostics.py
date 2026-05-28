from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models import GenerationJob


TARGET_DRAFT_SECONDS = 60


def build_render_profile_metadata(
    *,
    artifact_url: str | None,
    summary: dict[str, Any],
    profile_path: Path | str | None,
) -> dict[str, Any]:
    return {
        "artifact_url": artifact_url,
        "summary": summary,
        "profile_path": str(profile_path) if artifact_url and profile_path is not None else None,
    }


def _load_json(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {}
    try:
        path = Path(path_value)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {}


def _stage_seconds(profile: dict[str, Any], predicate) -> float:
    total = 0.0
    for stage in profile.get("stages") or []:
        name = str(stage.get("name") or "")
        if predicate(name):
            total += float(stage.get("duration_seconds") or 0.0)
    return total


def _top_bottleneck(profile: dict[str, Any]) -> str | None:
    stages = list(profile.get("stages") or [])
    if not stages:
        top = ((profile.get("summary") or {}).get("top_stages") or [])
        stages = list(top)
    if not stages:
        return None
    slowest = max(stages, key=lambda item: float(item.get("duration_seconds") or 0.0))
    return str(slowest.get("name") or "") or None


def _hint_for_bottleneck(bottleneck: str | None, cache_summary: dict[str, Any]) -> str:
    by_type = dict(cache_summary.get("by_type") or {})
    tts_misses = int((by_type.get("tts_segment") or {}).get("miss") or 0)
    if bottleneck and bottleneck.startswith("tts"):
        if tts_misses:
            return "Cache or explicitly choose a faster draft voice before expecting a 60-second draft."
        return "TTS dominates even with cache evidence; shorten script segments before rerendering."
    if bottleneck and "final_video" in bottleneck:
        return "Use draft mode for iteration; reserve preview/final settings for review."
    if bottleneck and "background" in bottleneck:
        return "Reuse the same scene or warm the background cache before measuring draft speed."
    return "Inspect the timing profile and cache report before changing concurrency or providers."


def build_performance_summary(job: GenerationJob) -> dict[str, Any]:
    tts_result = dict(job.tts_result_json or {})
    render_profile = dict(tts_result.get("render_profile") or {})
    cache_report = dict(tts_result.get("cache_report") or {})
    profile = _load_json(render_profile.get("profile_path")) or {"summary": render_profile.get("summary") or {}}
    cache_summary = dict(cache_report.get("summary") or {})
    total_seconds = float(
        tts_result.get("generation_job_duration_seconds")
        or (profile.get("summary") or {}).get("total_duration_seconds")
        or 0.0
    )
    if not total_seconds and job.started_at and job.finished_at:
        total_seconds = max((job.finished_at - job.started_at).total_seconds(), 0.0)

    generated_script = dict(job.script_revision.generated_script_json or {}) if job.script_revision else {}
    provider_metadata = dict(generated_script.get("provider_metadata") or {})
    script_generation_ms = provider_metadata.get("generation_duration_ms")
    bottleneck = _top_bottleneck(profile)
    peak_rss = int((profile.get("summary") or {}).get("peak_observed_rss_bytes") or profile.get("peak_observed_rss_bytes") or 0)
    summary = {
        "target_seconds": TARGET_DRAFT_SECONDS,
        "total_seconds": round(total_seconds, 3),
        "script_generation_seconds": round(float(script_generation_ms) / 1000, 3) if script_generation_ms is not None else None,
        "tts_seconds": round(_stage_seconds(profile, lambda name: name.startswith("tts.")), 3),
        "ffmpeg_seconds": round(_stage_seconds(profile, lambda name: name.startswith("ffmpeg.")), 3),
        "overlay_seconds": round(_stage_seconds(profile, lambda name: name.startswith("render.dynamic") or name.startswith("render.static")), 3),
        "background_seconds": round(_stage_seconds(profile, lambda name: "background" in name), 3),
        "cache_hit_summary": {
            "hits": int(cache_summary.get("hits") or 0),
            "misses": int(cache_summary.get("misses") or 0),
            "by_type": dict(cache_summary.get("by_type") or {}),
        },
        "peak_rss_mb": round(peak_rss / 1024 / 1024, 1) if peak_rss else None,
        "exceeded_60s_target": total_seconds > TARGET_DRAFT_SECONDS if total_seconds else None,
        "top_bottleneck": bottleneck,
        "next_optimization_hint": _hint_for_bottleneck(bottleneck, cache_summary),
    }
    hits = int(cache_summary.get("hits") or 0)
    misses = int(cache_summary.get("misses") or 0)
    summary["estimated_time_saved"] = "Cache savings are visible in cache_report.json." if hits and misses else None
    return summary
