from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


ArtifactUrlBuilder = Callable[[int, Path], str]
SlugBuilder = Callable[[str], str]


def build_segment_artifact_metadata(
    *,
    index: int,
    item: dict[str, Any],
    voice_manifest: dict[str, Any] | None,
    job_id: int | None,
    slugify: SlugBuilder,
    artifact_url_for_path: ArtifactUrlBuilder,
    audio_path_used_for_final_assembly: str | None = None,
) -> dict[str, Any]:
    segment = item["segment"]
    audio_path = Path(segment.audio_path)
    manifest_entry = dict(((voice_manifest or {}).get("speakers") or {}).get(segment.speaker) or {})
    voice_profile = dict(manifest_entry.get("voice_profile") or {})
    provider_metadata = dict(voice_profile.get("provider_metadata") or {})
    reference_artifacts = []
    for reference in voice_profile.get("reference_audios") or []:
        if not isinstance(reference, dict):
            continue
        reference_artifacts.append(
            {
                "id": reference.get("id"),
                "original_storage_path": reference.get("original_storage_path"),
                "processed_storage_path": reference.get("processed_storage_path") or reference.get("storage_path"),
                "processed_sha256": reference.get("processed_sha256"),
                "validation_status": reference.get("validation_status"),
            }
        )
    final_audio_path = audio_path_used_for_final_assembly or str(audio_path)
    return {
        "segment_index": index,
        "segment_id": f"{index:03d}_{slugify(segment.speaker)}",
        "line_id": segment.line_id,
        "speaker": segment.speaker,
        "text": segment.text,
        "voice_profile_id": segment.voice_profile_id,
        "voice_profile_name": voice_profile.get("display_name") or manifest_entry.get("character_display_name"),
        "tts_provider": segment.provider_used,
        "provider_used": segment.provider_used,
        "fallback_used": segment.fallback_used,
        "fallback_reason": segment.fallback_reason,
        "provider_failures": segment.provider_failures or {},
        "local_file_path": str(audio_path),
        "audio_path": str(audio_path),
        "audio_path_used_for_final_assembly": final_audio_path,
        "used_for_final_assembly": final_audio_path == str(audio_path),
        "artifact_url": artifact_url_for_path(job_id, audio_path) if job_id is not None else None,
        "duration_seconds": item["duration_seconds"],
        "reference_audio_count": segment.reference_audio_count,
        "voice_profile_settings": {
            "provider": voice_profile.get("provider"),
            "model_checkpoint_path": voice_profile.get("model_checkpoint_path"),
            "reference_dataset_id": voice_profile.get("reference_dataset_id"),
            "selected_recipe": dict(segment.recipe_used or voice_profile.get("selected_recipe") or {}),
            "calibration_score": voice_profile.get("calibration_score"),
            "last_verified_render_job_id": voice_profile.get("last_verified_render_job_id"),
            "base_speaker": voice_profile.get("base_speaker") or dict(voice_profile.get("style") or {}).get("base_speaker"),
            "style_preset": dict(voice_profile.get("style") or {}).get("style_preset"),
            "controls": dict(voice_profile.get("controls") or {}),
            "style": dict(voice_profile.get("style") or {}),
            "embedding_path": voice_profile.get("embedding_path") or provider_metadata.get("embedding_artifact_path"),
            "reference_audio_sha256": provider_metadata.get("reference_audio_sha256"),
            "target_embedding_hash": provider_metadata.get("target_embedding_hash"),
            "reference_validation_status": provider_metadata.get("reference_validation_status"),
        },
        "reference_artifacts": reference_artifacts,
        "selected_recipe": dict(segment.recipe_used or voice_profile.get("selected_recipe") or {}),
        "recipe_used": dict(segment.recipe_used or voice_profile.get("selected_recipe") or {}),
        "golden_preview_wav": segment.golden_preview_wav,
        "model_checkpoint_path": voice_profile.get("model_checkpoint_path"),
        "reference_dataset_id": voice_profile.get("reference_dataset_id"),
    }


def build_assembly_metadata(
    *,
    job_id: int | None,
    project_id: int,
    timed_segments: list[dict[str, Any]],
    segment_metadata: list[dict[str, Any]],
    composite_audio_path: Path,
    final_mp4_path: Path,
    artifact_url_for_path: ArtifactUrlBuilder,
    final_video_audio_path: Path | None = None,
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "project_id": project_id,
        "composite_audio_path": str(composite_audio_path),
        "composite_audio_artifact_url": (
            artifact_url_for_path(job_id, composite_audio_path) if job_id is not None else None
        ),
        "final_mp4_path": str(final_mp4_path),
        "final_video_audio_path": str(final_video_audio_path) if final_video_audio_path else None,
        "final_video_audio_artifact_url": (
            artifact_url_for_path(job_id, final_video_audio_path)
            if job_id is not None and final_video_audio_path is not None
            else None
        ),
        "segments": [
            {
                "segment_index": metadata["segment_index"],
                "speaker": metadata["speaker"],
                "provider_used": metadata["provider_used"],
                "fallback_used": metadata["fallback_used"],
                "artifact_url": metadata.get("artifact_url"),
                "segment_audio_path": metadata["audio_path"],
                "normalized_audio_path": metadata.get("normalized_audio_path"),
                "normalized_audio_artifact_url": metadata.get("normalized_audio_artifact_url"),
                "audio_path_used_for_final_assembly": str(item.get("normalized_audio_path") or item["segment"].audio_path),
                "segment_wav_exists": Path(item["segment"].audio_path).exists(),
            }
            for metadata, item in zip(segment_metadata, timed_segments, strict=False)
        ],
    }


def build_line_timing_metadata(
    *,
    timed_segments: list[dict[str, Any]],
    segment_metadata: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for metadata, item in zip(segment_metadata, timed_segments, strict=False):
        segment = item["segment"]
        audio_path_used_for_final_assembly = segment.audio_path
        entry = {
            "speaker": segment.speaker,
            "text": segment.text,
            "duration_seconds": item["duration_seconds"],
            "audio_path": segment.audio_path,
            "audio_path_used_for_final_assembly": audio_path_used_for_final_assembly,
            "artifact_url": metadata.get("artifact_url"),
            "provider_used": segment.provider_used,
            "voice_profile_id": segment.voice_profile_id,
            "fallback_used": segment.fallback_used,
        }
        normalized_audio_path = item.get("normalized_audio_path")
        if normalized_audio_path is not None:
            normalized_audio_path_text = str(normalized_audio_path)
            entry["normalized_audio_path"] = normalized_audio_path_text
            entry["audio_path_used_for_final_assembly"] = normalized_audio_path_text
            entry["normalized_audio_artifact_url"] = metadata.get("normalized_audio_artifact_url")
        payload.append(entry)
    return payload


def build_selected_profile_summary(segments: list[Any]) -> dict[str, dict[str, Any]]:
    return {
        segment.speaker: {
            "provider_used": segment.provider_used,
            "voice_profile_id": segment.voice_profile_id,
            "voice": segment.voice,
            "fallback_used": segment.fallback_used,
        }
        for segment in segments
    }


def build_voice_summary(segments: list[Any]) -> dict[str, dict[str, Any]]:
    return {
        segment.speaker: {
            "voice": segment.voice,
            "provider_used": segment.provider_used,
            "voice_profile_id": segment.voice_profile_id,
            "fallback_used": segment.fallback_used,
            "reference_audio_count": segment.reference_audio_count,
        }
        for segment in segments
    }


def build_tts_result_metadata(
    *,
    provider_state: dict[str, Any],
    segment_metadata: list[dict[str, Any]],
    assembly_metadata: dict[str, Any],
    render_layout: dict[str, Any],
    status: str = "completed",
    current_phase: str | None = None,
    render_plan: dict[str, Any] | None = None,
    cache_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "provider_state": provider_state,
        "segments": segment_metadata,
        "assembly": assembly_metadata,
        "render_settings": {"layout": render_layout},
    }
    if current_phase is not None:
        payload["current_phase"] = current_phase
    if render_plan is not None:
        payload["render_plan"] = render_plan
    if cache_report is not None:
        payload["cache_report"] = cache_report
    return payload


def build_debug_audio_extraction_metadata(
    *,
    enabled: bool,
    artifact_path: Path | str | None = None,
    include_artifact_path: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "enabled": enabled,
        "skipped": not enabled,
    }
    if include_artifact_path:
        payload["artifact_path"] = str(artifact_path) if artifact_path else None
    return payload


def build_render_result_metadata(
    *,
    render_mode: str,
    segments: list[Any],
    tts_result: dict[str, Any],
    render_layout: dict[str, Any],
    render_profile_metadata: dict[str, Any],
    render_profile_artifact_url: str | None,
    assembly_metadata: dict[str, Any],
    timed_segments: list[dict[str, Any]],
    segment_metadata: list[dict[str, Any]],
    render_fps: int,
    render_resolution: dict[str, int],
    character_scale: float | int,
    chat_font_size_px: float | int,
    ffmpeg_threads: int,
    encode_preset: str,
    render_engine: str | None = None,
    render_plan_artifact_url: str | None = None,
    cache_report_artifact_url: str | None = None,
    cache_statistics: dict[str, Any] | None = None,
    performance: dict[str, Any] | None = None,
    crf: int | None = None,
    debug_audio_extraction: dict[str, Any] | None = None,
    portrait_resolution: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "render_mode": render_mode,
    }
    if render_engine is not None:
        payload["render_engine"] = render_engine
    payload.update(
        {
            "voices": build_voice_summary(segments),
            "tts_result": tts_result,
            "render_settings": {"layout": render_layout},
        }
    )
    if performance is not None:
        payload["performance"] = performance
    payload.update(
        {
            "preview_layout": render_layout,
            "render_profile": render_profile_metadata,
            "render_profile_artifact_url": render_profile_artifact_url,
        }
    )
    if render_plan_artifact_url is not None:
        payload["render_plan_artifact_url"] = render_plan_artifact_url
    if cache_report_artifact_url is not None:
        payload["cache_report_artifact_url"] = cache_report_artifact_url
    if cache_statistics is not None:
        payload["cache_statistics"] = cache_statistics
    payload.update(
        {
            "render_assembly": assembly_metadata,
            "line_timing_seconds": build_line_timing_metadata(
                timed_segments=timed_segments,
                segment_metadata=segment_metadata,
            ),
            "render_fps": render_fps,
            "render_resolution": render_resolution,
            "character_scale": character_scale,
            "chat_font_size_px": chat_font_size_px,
            "ffmpeg_threads": ffmpeg_threads,
            "encode_preset": encode_preset,
        }
    )
    if crf is not None:
        payload["crf"] = crf
    if debug_audio_extraction is not None:
        payload["debug_audio_extraction"] = debug_audio_extraction
    if portrait_resolution is not None:
        payload["portrait_resolution"] = portrait_resolution
    return payload
