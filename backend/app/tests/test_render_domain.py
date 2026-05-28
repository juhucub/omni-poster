from __future__ import annotations

import wave
from pathlib import Path
from types import SimpleNamespace

from app.domains.render.audio.timeline import (
    build_timed_segments_from_durations,
    timeline_duration_seconds,
    wav_duration_seconds,
)
from app.domains.render.audio.mixdown import (
    concat_demuxer_audio_command,
    concat_filter_complex,
    ffmpeg_concat_file_contents,
    multi_input_audio_command,
)
from app.domains.render.artifacts import (
    build_debug_audio_extraction_metadata,
    build_line_timing_metadata,
    build_render_result_metadata,
    build_selected_profile_summary,
    build_tts_result_metadata,
    build_voice_summary,
)
from app.domains.render.cache_keys import (
    background_cache_key,
    dynamic_frame_cache_key,
    dynamic_overlay_cache_key,
    final_video_cache_key,
    normalized_audio_cache_key,
    static_overlay_cache_key,
)
from app.domains.render.cache_report import (
    RenderCacheReport as DomainRenderCacheReport,
    build_background_cache_transfer_metadata,
    build_composite_audio_cache_transfer_metadata,
    build_final_render_cache_transfer_metadata,
    build_normalized_audio_cache_transfer_metadata,
    build_overlay_cache_transfer_metadata,
    build_tts_segment_cache_miss_metadata,
    build_tts_segment_cache_transfer_metadata,
)
from app.domains.render.diagnostics import build_render_profile_metadata
from app.domains.render.geometry import (
    ACTIVE_PORTRAIT_HEIGHT,
    BASE_PORTRAIT_HEIGHT,
    CAPTION_CARD_POSITION,
    CAPTION_CARD_SIZE,
    REFERENCE_CANVAS_HEIGHT,
    REFERENCE_CANVAS_WIDTH,
    layout_scaled_height,
    portrait_resize_dimensions,
    scale_box,
)
from app.domains.render.planning import RenderPlan, RenderPreset
from app.domains.render.presets import (
    background_cache_duration_seconds,
    normalize_render_layout,
    render_preset_for_output_kind,
)
from app.domains.render.progress import FFMPEG_PROGRESS_STAGES, MOVIEPY_PROGRESS_STAGES, render_progress_payload
from app.domains.render.video.backgrounds import background_normalization_ffmpeg_command, background_video_filter
from app.domains.render.video.composer import (
    FINAL_VIDEO_OVERLAY_FILTER,
    dynamic_overlay_concat_list_contents,
    dynamic_overlay_ffmpeg_command,
    final_video_ffmpeg_command,
)
from app.domains.render.video.overlays import (
    STATIC_OVERLAY_PORTRAIT_ALPHA,
    dialogue_card_layout_payload,
    dynamic_frame_caption_entry,
    dynamic_frame_composition_payload,
    dynamic_frame_portrait_entry,
    generated_portrait_layout_payload,
    primary_cast_segments,
    speaker_initials,
    speaker_palette,
    speaker_slots_from_lines,
    static_overlay_cast,
    static_overlay_portrait_entries,
)
from app.core.config import settings
from app.services.render_cache import RENDER_CACHE_SCHEMA_VERSION, stable_hash
from app.services.render_cache import RenderCacheReport as ServiceRenderCacheReport
from app.services.render_planning import RenderPlan as ServiceRenderPlan


def _write_test_wav(path: Path, *, seconds: float = 1.0, sample_rate: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frame_count)


def _render_plan(*, expected_artifacts: dict[str, str]) -> RenderPlan:
    return RenderPlan(
        job_id=7,
        project_id=3,
        output_kind="preview",
        preset=RenderPreset(mode="preview", width=1080, height=1920, fps=24, x264_preset="fast", crf=23),
        parsed_lines=[{"speaker": "Host", "text": "Hello."}],
        voice_profiles={"Host": {"id": "vp_host", "provider": "espeak"}},
        background_source_path="/tmp/background.mp4",
        background_hash="background_hash",
        background_mime_type="video/mp4",
        style_preset="clean",
        speaker_pngs={"Host": "/tmp/host.png"},
        speaker_png_hashes={"Host": "host_hash"},
        layout={"character_scale": 1.0, "chat_font_size_px": 24},
        caption_settings={"font_size_px": 24, "card_position": [90, 1320]},
        expected_artifacts=expected_artifacts,
        cache_keys={"final_video": "final_key"},
        segments=[{"segment_index": 0, "speaker": "Host"}],
    )


def test_render_plan_key_ignores_expected_artifact_paths() -> None:
    first = _render_plan(expected_artifacts={"render_plan": "/tmp/job_a/render_plan.json"})
    second = _render_plan(expected_artifacts={"render_plan": "/tmp/job_b/render_plan.json"})

    assert first.plan_key() == second.plan_key()
    assert first.to_dict()["expected_artifact_paths"] != second.to_dict()["expected_artifact_paths"]
    assert ServiceRenderPlan is RenderPlan


def test_render_cache_report_summary_shape_and_service_reexport() -> None:
    report = DomainRenderCacheReport()
    report.record(
        artifact_type="tts_segment",
        cache_key="a" * 64,
        status="hit",
        cache_path=Path("/cache/a.wav"),
        job_path=Path("/job/a.wav"),
        metadata={"method": "hardlink"},
    )
    report.record(artifact_type="final_video", cache_key="b" * 64, status="miss")
    report.record(
        artifact_type="final_video",
        cache_key="b" * 64,
        status="regenerated",
        metadata={"method": "copy"},
    )

    summary = report.summary()

    assert summary["hits"] == 1
    assert summary["misses"] == 2
    assert summary["total_events"] == 3
    assert summary["by_type"] == {
        "tts_segment": {"hit": 1},
        "final_video": {"miss": 1, "regenerated": 1},
    }
    assert summary["transfer_methods"] == {"hardlink": 1, "copy": 1}
    assert summary["events"][0]["cache_key_prefix"] == "a" * 16
    assert ServiceRenderCacheReport is DomainRenderCacheReport


def test_final_render_cache_transfer_metadata_preserves_transfer_payload() -> None:
    transfer = {
        "operation": "store",
        "method": "hardlink",
        "error": None,
    }

    metadata = build_final_render_cache_transfer_metadata(transfer)

    assert metadata == transfer
    assert metadata is not transfer


def test_final_render_cache_transfer_metadata_handles_missing_transfer_payload() -> None:
    assert build_final_render_cache_transfer_metadata(None) == {}


def test_intermediate_cache_transfer_metadata_preserves_transfer_payloads() -> None:
    transfer = {"operation": "materialize", "method": "copy", "error": "cross-device link"}

    assert build_composite_audio_cache_transfer_metadata(transfer) == transfer
    assert build_overlay_cache_transfer_metadata(transfer) == transfer
    assert build_composite_audio_cache_transfer_metadata(transfer) is not transfer
    assert build_overlay_cache_transfer_metadata(transfer) is not transfer


def test_normalized_audio_cache_transfer_metadata_preserves_existing_shape() -> None:
    metadata = build_normalized_audio_cache_transfer_metadata(
        {"operation": "store", "method": "hardlink", "error": None},
        duration_seconds=1.25,
        normalization_skipped=False,
    )

    assert metadata == {
        "operation": "store",
        "method": "hardlink",
        "error": None,
        "duration_seconds": 1.25,
        "normalization_skipped": False,
    }


def test_background_cache_transfer_metadata_preserves_duration_bucket() -> None:
    metadata = build_background_cache_transfer_metadata(
        {"operation": "materialize", "method": "same_path", "error": None},
        cache_duration_seconds=15.0,
    )

    assert metadata == {
        "operation": "materialize",
        "method": "same_path",
        "error": None,
        "cache_duration_seconds": 15.0,
    }


def test_tts_segment_cache_transfer_metadata_preserves_existing_shape() -> None:
    metadata = build_tts_segment_cache_transfer_metadata(
        {"operation": "materialize", "method": "hardlink", "error": None},
        speaker="Host",
        provider_used="xtts",
    )

    assert metadata == {
        "operation": "materialize",
        "method": "hardlink",
        "error": None,
        "speaker": "Host",
        "provider_used": "xtts",
    }


def test_tts_segment_cache_miss_metadata_preserves_existing_shape() -> None:
    assert build_tts_segment_cache_miss_metadata(speaker="Guest") == {"speaker": "Guest"}


def test_render_line_timing_metadata_preserves_segment_summary_shape() -> None:
    segment = SimpleNamespace(
        speaker="Host",
        text="Welcome back.",
        audio_path="/tmp/segments/000_host.wav",
        provider_used="espeak",
        voice_profile_id="vp_host",
        fallback_used=False,
    )

    payload = build_line_timing_metadata(
        timed_segments=[{"segment": segment, "duration_seconds": 0.9}],
        segment_metadata=[{"artifact_url": "/generation-jobs/1/artifacts/segments/000_host.wav"}],
    )

    assert payload == [
        {
            "speaker": "Host",
            "text": "Welcome back.",
            "duration_seconds": 0.9,
            "audio_path": "/tmp/segments/000_host.wav",
            "audio_path_used_for_final_assembly": "/tmp/segments/000_host.wav",
            "artifact_url": "/generation-jobs/1/artifacts/segments/000_host.wav",
            "provider_used": "espeak",
            "voice_profile_id": "vp_host",
            "fallback_used": False,
        }
    ]


def test_render_line_timing_metadata_preserves_normalized_audio_summary_shape() -> None:
    segment = SimpleNamespace(
        speaker="Guest",
        text="A normalized line.",
        audio_path="/tmp/segments/001_guest.wav",
        provider_used="xtts",
        voice_profile_id="vp_guest",
        fallback_used=True,
    )

    payload = build_line_timing_metadata(
        timed_segments=[
            {
                "segment": segment,
                "duration_seconds": 1.2,
                "normalized_audio_path": Path("/tmp/normalized/001_guest.wav"),
            }
        ],
        segment_metadata=[
            {
                "artifact_url": "/generation-jobs/2/artifacts/segments/001_guest.wav",
                "normalized_audio_artifact_url": "/generation-jobs/2/artifacts/normalized/001_guest.wav",
            }
        ],
    )

    assert payload == [
        {
            "speaker": "Guest",
            "text": "A normalized line.",
            "duration_seconds": 1.2,
            "audio_path": "/tmp/segments/001_guest.wav",
            "normalized_audio_path": "/tmp/normalized/001_guest.wav",
            "audio_path_used_for_final_assembly": "/tmp/normalized/001_guest.wav",
            "artifact_url": "/generation-jobs/2/artifacts/segments/001_guest.wav",
            "normalized_audio_artifact_url": "/generation-jobs/2/artifacts/normalized/001_guest.wav",
            "provider_used": "xtts",
            "voice_profile_id": "vp_guest",
            "fallback_used": True,
        }
    ]


def test_render_selected_profile_summary_preserves_profiler_context_shape() -> None:
    host = SimpleNamespace(
        speaker="Host",
        voice="Host Voice",
        provider_used="espeak",
        voice_profile_id="vp_host",
        fallback_used=False,
        reference_audio_count=0,
    )
    guest = SimpleNamespace(
        speaker="Guest",
        voice="Guest Voice",
        provider_used="xtts",
        voice_profile_id="vp_guest",
        fallback_used=True,
        reference_audio_count=2,
    )

    assert build_selected_profile_summary([host, guest]) == {
        "Host": {
            "provider_used": "espeak",
            "voice_profile_id": "vp_host",
            "voice": "Host Voice",
            "fallback_used": False,
        },
        "Guest": {
            "provider_used": "xtts",
            "voice_profile_id": "vp_guest",
            "voice": "Guest Voice",
            "fallback_used": True,
        },
    }


def test_render_voice_summary_preserves_result_metadata_shape() -> None:
    segment = SimpleNamespace(
        speaker="Host",
        voice="Host Voice",
        provider_used="openvoice",
        voice_profile_id="vp_host",
        fallback_used=False,
        reference_audio_count=3,
    )

    assert build_voice_summary([segment]) == {
        "Host": {
            "voice": "Host Voice",
            "provider_used": "openvoice",
            "voice_profile_id": "vp_host",
            "fallback_used": False,
            "reference_audio_count": 3,
        }
    }


def test_render_tts_result_metadata_preserves_base_moviepy_shape() -> None:
    provider_state = {"espeak": {"available": True}}
    segment_metadata = [{"segment_index": 0, "speaker": "Host"}]
    assembly_metadata = {"final_mp4_path": "/tmp/final.mp4"}
    layout = {"character_scale": 1.0, "chat_font_size_px": 18}

    assert build_tts_result_metadata(
        provider_state=provider_state,
        segment_metadata=segment_metadata,
        assembly_metadata=assembly_metadata,
        render_layout=layout,
    ) == {
        "status": "completed",
        "provider_state": provider_state,
        "segments": segment_metadata,
        "assembly": assembly_metadata,
        "render_settings": {"layout": layout},
    }


def test_render_tts_result_metadata_preserves_ffmpeg_plan_and_cache_shape() -> None:
    provider_state = {"xtts": {"available": True}}
    segment_metadata = [{"segment_index": 1, "speaker": "Guest"}]
    assembly_metadata = {"final_mp4_path": "/tmp/final.mp4"}
    layout = {"character_scale": 1.25, "chat_font_size_px": 22}
    render_plan = {
        "path": "/tmp/render_plan.json",
        "artifact_url": "/generation-jobs/5/artifacts/render_plan.json",
        "plan_key": "plan-key",
    }
    cache_report = {
        "path": "/tmp/cache_report.json",
        "artifact_url": "/generation-jobs/5/artifacts/cache_report.json",
        "summary": {"hits": 2},
    }

    assert build_tts_result_metadata(
        provider_state=provider_state,
        segment_metadata=segment_metadata,
        assembly_metadata=assembly_metadata,
        render_layout=layout,
        current_phase="completed",
        render_plan=render_plan,
        cache_report=cache_report,
    ) == {
        "status": "completed",
        "current_phase": "completed",
        "provider_state": provider_state,
        "segments": segment_metadata,
        "assembly": assembly_metadata,
        "render_settings": {"layout": layout},
        "render_plan": render_plan,
        "cache_report": cache_report,
    }


def test_render_debug_audio_extraction_metadata_preserves_preview_shape() -> None:
    assert build_debug_audio_extraction_metadata(enabled=False) == {
        "enabled": False,
        "skipped": True,
    }


def test_render_debug_audio_extraction_metadata_preserves_debug_artifact_shape() -> None:
    assert build_debug_audio_extraction_metadata(
        enabled=True,
        artifact_path=Path("/tmp/job/audio/final_video_audio.wav"),
        include_artifact_path=True,
    ) == {
        "enabled": True,
        "skipped": False,
        "artifact_path": "/tmp/job/audio/final_video_audio.wav",
    }


def test_render_debug_audio_extraction_metadata_preserves_missing_artifact_shape() -> None:
    assert build_debug_audio_extraction_metadata(
        enabled=True,
        artifact_path=None,
        include_artifact_path=True,
    ) == {
        "enabled": True,
        "skipped": False,
        "artifact_path": None,
    }


def test_render_progress_payload_preserves_ffmpeg_stage_percentages() -> None:
    assert FFMPEG_PROGRESS_STAGES == {
        "tts_ready": 46,
        "audio_ready": 55,
        "background_ready": 62,
        "timeline_ready": 70,
        "encoding": 80,
        "encoded": 88,
    }
    assert render_progress_payload("tts_ready") == ("tts_ready", 46)
    assert render_progress_payload("audio_ready") == ("audio_ready", 55)
    assert render_progress_payload("encoded") == ("encoded", 88)


def test_render_progress_payload_preserves_moviepy_stage_percentages() -> None:
    assert MOVIEPY_PROGRESS_STAGES == {
        "tts_ready": 46,
        "background_ready": 58,
        "timeline_ready": 68,
        "encoding": 80,
        "encoded": 88,
    }
    assert render_progress_payload("background_ready", engine="moviepy") == ("background_ready", 58)
    assert render_progress_payload("timeline_ready", engine="moviepy") == ("timeline_ready", 68)


def test_render_result_metadata_preserves_moviepy_envelope_shape() -> None:
    segment = SimpleNamespace(
        speaker="Host",
        text="Welcome back.",
        voice="Host Voice",
        audio_path="/tmp/segments/000_host.wav",
        provider_used="espeak",
        voice_profile_id="vp_host",
        fallback_used=False,
        reference_audio_count=0,
    )

    metadata = build_render_result_metadata(
        render_mode="speaker_dialogue",
        segments=[segment],
        tts_result={"status": "completed"},
        render_layout={"character_scale": 1.0, "chat_font_size_px": 18},
        render_profile_metadata={"artifact_url": None, "summary": {}},
        render_profile_artifact_url=None,
        assembly_metadata={"segments": []},
        timed_segments=[{"segment": segment, "duration_seconds": 0.9}],
        segment_metadata=[{"artifact_url": "/generation-jobs/1/artifacts/segments/000_host.wav"}],
        render_fps=24,
        render_resolution={"width": 1080, "height": 1920},
        character_scale=1.0,
        chat_font_size_px=18,
        ffmpeg_threads=4,
        encode_preset="medium",
        portrait_resolution="backend/storage/characters/<speaker>.png or speaker_<slot>.png",
    )

    assert metadata == {
        "render_mode": "speaker_dialogue",
        "voices": {
            "Host": {
                "voice": "Host Voice",
                "provider_used": "espeak",
                "voice_profile_id": "vp_host",
                "fallback_used": False,
                "reference_audio_count": 0,
            }
        },
        "tts_result": {"status": "completed"},
        "render_settings": {"layout": {"character_scale": 1.0, "chat_font_size_px": 18}},
        "preview_layout": {"character_scale": 1.0, "chat_font_size_px": 18},
        "render_profile": {"artifact_url": None, "summary": {}},
        "render_profile_artifact_url": None,
        "render_assembly": {"segments": []},
        "line_timing_seconds": [
            {
                "speaker": "Host",
                "text": "Welcome back.",
                "duration_seconds": 0.9,
                "audio_path": "/tmp/segments/000_host.wav",
                "audio_path_used_for_final_assembly": "/tmp/segments/000_host.wav",
                "artifact_url": "/generation-jobs/1/artifacts/segments/000_host.wav",
                "provider_used": "espeak",
                "voice_profile_id": "vp_host",
                "fallback_used": False,
            }
        ],
        "render_fps": 24,
        "render_resolution": {"width": 1080, "height": 1920},
        "character_scale": 1.0,
        "chat_font_size_px": 18,
        "ffmpeg_threads": 4,
        "encode_preset": "medium",
        "portrait_resolution": "backend/storage/characters/<speaker>.png or speaker_<slot>.png",
    }


def test_render_result_metadata_preserves_ffmpeg_envelope_additions() -> None:
    segment = SimpleNamespace(
        speaker="Guest",
        text="A normalized line.",
        voice="Guest Voice",
        audio_path="/tmp/segments/001_guest.wav",
        provider_used="xtts",
        voice_profile_id="vp_guest",
        fallback_used=True,
        reference_audio_count=2,
    )
    render_layout = {"character_scale": 1.25, "chat_font_size_px": 22}
    cache_statistics = {"hits": 1, "misses": 0}
    performance = {"fast_preview_enabled": False, "render_preset": {"mode": "final"}, "asset_fingerprints": {}}
    debug_audio_extraction = {"enabled": True}

    metadata = build_render_result_metadata(
        render_mode="speaker_dialogue_ffmpeg",
        render_engine="ffmpeg",
        segments=[segment],
        tts_result={"status": "completed"},
        render_layout=render_layout,
        render_profile_metadata={"artifact_url": "/profile.json", "summary": {"total": 1.0}},
        render_profile_artifact_url="/profile.json",
        render_plan_artifact_url="/render_plan.json",
        cache_report_artifact_url="/cache_report.json",
        cache_statistics=cache_statistics,
        performance=performance,
        assembly_metadata={"segments": []},
        timed_segments=[
            {
                "segment": segment,
                "duration_seconds": 1.2,
                "normalized_audio_path": Path("/tmp/normalized/001_guest.wav"),
            }
        ],
        segment_metadata=[
            {
                "artifact_url": "/generation-jobs/2/artifacts/segments/001_guest.wav",
                "normalized_audio_artifact_url": "/generation-jobs/2/artifacts/normalized/001_guest.wav",
            }
        ],
        render_fps=30,
        render_resolution={"width": 1080, "height": 1920},
        character_scale=1.25,
        chat_font_size_px=22,
        ffmpeg_threads=6,
        encode_preset="fast",
        crf=20,
        debug_audio_extraction=debug_audio_extraction,
    )

    assert metadata["render_mode"] == "speaker_dialogue_ffmpeg"
    assert metadata["render_engine"] == "ffmpeg"
    assert metadata["voices"]["Guest"]["reference_audio_count"] == 2
    assert metadata["performance"] is performance
    assert metadata["cache_statistics"] is cache_statistics
    assert metadata["render_plan_artifact_url"] == "/render_plan.json"
    assert metadata["cache_report_artifact_url"] == "/cache_report.json"
    assert metadata["line_timing_seconds"][0]["normalized_audio_path"] == "/tmp/normalized/001_guest.wav"
    assert metadata["line_timing_seconds"][0]["audio_path_used_for_final_assembly"] == "/tmp/normalized/001_guest.wav"
    assert metadata["crf"] == 20
    assert metadata["debug_audio_extraction"] is debug_audio_extraction


def test_render_profile_metadata_preserves_artifact_url_summary_and_path_shape() -> None:
    summary = {"total_duration_seconds": 4.2, "top_stages": [{"name": "ffmpeg.final_video"}]}

    assert build_render_profile_metadata(
        artifact_url="/generation-jobs/7/artifacts/generation_profile.json",
        summary=summary,
        profile_path=Path("/tmp/job/generation_profile.json"),
    ) == {
        "artifact_url": "/generation-jobs/7/artifacts/generation_profile.json",
        "summary": summary,
        "profile_path": "/tmp/job/generation_profile.json",
    }


def test_render_profile_metadata_keeps_path_empty_without_artifact_url() -> None:
    summary = {"total_duration_seconds": 0.0}

    assert build_render_profile_metadata(
        artifact_url=None,
        summary=summary,
        profile_path=Path("/tmp/job/generation_profile.json"),
    ) == {
        "artifact_url": None,
        "summary": summary,
        "profile_path": None,
    }


def test_normalized_audio_cache_key_matches_legacy_payload_and_tracks_audio_format() -> None:
    expected = stable_hash(
        {
            "version": RENDER_CACHE_SCHEMA_VERSION,
            "type": "normalized_audio",
            "source_identity": "source-a",
            "format": {"codec": "pcm_s16le", "sample_rate": 44100, "channels": 2},
        }
    )

    assert normalized_audio_cache_key("source-a", 44100) == expected
    assert normalized_audio_cache_key("source-b", 44100) != expected
    assert normalized_audio_cache_key("source-a", 48000) != expected


def test_background_cache_key_matches_legacy_payload_and_uses_both_durations() -> None:
    preset = RenderPreset(mode="preview", width=1080, height=1920, fps=24, x264_preset="fast", crf=23)
    expected = stable_hash(
        {
            "version": RENDER_CACHE_SCHEMA_VERSION,
            "type": "background",
            "source_hash": "bg-a",
            "mime_type": "video/mp4",
            "style_preset": "clean",
            "preset": preset.__dict__,
            "duration_seconds": round(15.0, 3),
            "requested_duration_seconds": round(11.2345, 3),
        }
    )

    assert background_cache_key("bg-a", "video/mp4", "clean", preset, 15.0, 11.2345) == expected
    assert background_cache_key("bg-b", "video/mp4", "clean", preset, 15.0, 11.2345) != expected
    assert background_cache_key("bg-a", "video/mp4", "clean", preset, 20.0, 11.2345) != expected
    assert background_cache_key("bg-a", "video/mp4", "clean", preset, 15.0, 12.0) != expected


def test_overlay_and_final_video_cache_keys_only_track_declared_inputs() -> None:
    preset = RenderPreset(mode="preview", width=1080, height=1920, fps=24, x264_preset="fast", crf=23)
    layout = {"character_scale": 1.0, "chat_font_size_px": 24}
    cast = [("Host", 0), ("Guest", 1)]
    portrait_hashes = {"Host": "host-hash", "Guest": "guest-hash"}
    segment = SimpleNamespace(speaker="Host", slot_index=0, text="Hello there")
    frame_entries = [{"key": "frame-a", "duration_seconds": 1.2345}, {"key": "frame-b", "duration_seconds": 2.0}]

    static_key = static_overlay_cache_key(cast, portrait_hashes, layout, preset)
    assert static_key == stable_hash(
        {
            "version": RENDER_CACHE_SCHEMA_VERSION,
            "type": "static_overlay",
            "cast": [
                {"speaker": "Host", "slot": 0, "portrait_hash": "host-hash"},
                {"speaker": "Guest", "slot": 1, "portrait_hash": "guest-hash"},
            ],
            "layout": layout,
            "preset": preset.__dict__,
        }
    )
    assert static_overlay_cache_key(list(reversed(cast)), portrait_hashes, layout, preset) != static_key

    dynamic_frame_key = dynamic_frame_cache_key(segment, "host-hash", layout, preset)
    assert dynamic_frame_cache_key(SimpleNamespace(speaker="Host", slot_index=0, text="Changed"), "host-hash", layout, preset) != dynamic_frame_key

    dynamic_overlay_key = dynamic_overlay_cache_key(frame_entries, preset)
    assert dynamic_overlay_key == stable_hash(
        {
            "version": RENDER_CACHE_SCHEMA_VERSION,
            "type": "dynamic_overlay",
            "frames": [{"key": "frame-a", "duration_seconds": 1.234}, {"key": "frame-b", "duration_seconds": 2.0}],
            "preset": preset.__dict__,
        }
    )
    assert dynamic_overlay_cache_key([{"key": "frame-a", "duration_seconds": 1.2345}], preset) != dynamic_overlay_key

    final_key = final_video_cache_key(
        background_key="background",
        static_overlay_key=static_key,
        dynamic_overlay_key=dynamic_overlay_key,
        composite_audio_key="composite",
        preset=preset,
        duration_seconds=9.8765,
        audio_bitrate="192k",
    )
    assert final_key == stable_hash(
        {
            "version": RENDER_CACHE_SCHEMA_VERSION,
            "type": "final_video",
            "background_key": "background",
            "static_overlay_key": static_key,
            "dynamic_overlay_key": dynamic_overlay_key,
            "composite_audio_key": "composite",
            "preset": preset.__dict__,
            "duration_seconds": 9.877,
            "audio_bitrate": "192k",
        }
    )
    assert final_video_cache_key("changed", static_key, dynamic_overlay_key, "composite", preset, 9.8765, "192k") != final_key


def test_render_preset_for_output_kind_uses_expected_modes() -> None:
    draft = render_preset_for_output_kind("draft")
    preview = render_preset_for_output_kind("preview")
    final = render_preset_for_output_kind("final")
    debug = render_preset_for_output_kind("debug")
    unknown = render_preset_for_output_kind("unexpected")

    assert draft == RenderPreset(
        mode="draft",
        width=settings.RENDER_DRAFT_WIDTH,
        height=settings.RENDER_DRAFT_HEIGHT,
        fps=settings.RENDER_DRAFT_FPS_CAP,
        x264_preset=settings.RENDER_DRAFT_ENCODE_PRESET,
        crf=settings.RENDER_DRAFT_CRF,
    )
    assert preview == RenderPreset(
        mode="preview",
        width=settings.RENDER_PREVIEW_WIDTH,
        height=settings.RENDER_PREVIEW_HEIGHT,
        fps=settings.RENDER_PREVIEW_FPS_CAP,
        x264_preset=settings.RENDER_PREVIEW_ENCODE_PRESET,
        crf=settings.RENDER_PREVIEW_CRF,
    )
    assert final == RenderPreset(
        mode="final",
        width=settings.RENDER_EXPORT_WIDTH,
        height=settings.RENDER_EXPORT_HEIGHT,
        fps=settings.RENDER_EXPORT_FPS_CAP,
        x264_preset=settings.RENDER_EXPORT_ENCODE_PRESET,
        crf=settings.RENDER_EXPORT_CRF,
        debug_audio_extract=False,
    )
    assert debug == RenderPreset(
        mode="debug",
        width=settings.RENDER_EXPORT_WIDTH,
        height=settings.RENDER_EXPORT_HEIGHT,
        fps=settings.RENDER_EXPORT_FPS_CAP,
        x264_preset=settings.RENDER_EXPORT_ENCODE_PRESET,
        crf=settings.RENDER_EXPORT_CRF,
        debug_audio_extract=True,
    )
    assert unknown == preview


def test_background_cache_duration_seconds_buckets_preview_and_draft_only() -> None:
    preview = RenderPreset(mode="preview", width=1080, height=1920, fps=24, x264_preset="fast", crf=23)
    draft = RenderPreset(mode="draft", width=540, height=960, fps=12, x264_preset="ultrafast", crf=30)
    final = RenderPreset(mode="final", width=1080, height=1920, fps=30, x264_preset="faster", crf=22)
    debug = RenderPreset(mode="debug", width=1080, height=1920, fps=30, x264_preset="faster", crf=22)

    assert background_cache_duration_seconds(11.2, preview) == 15.0
    assert background_cache_duration_seconds(11.2, draft) == 15.0
    assert background_cache_duration_seconds(15.0, preview) == 15.0
    assert background_cache_duration_seconds(11.2, final) == 11.2
    assert background_cache_duration_seconds(11.2, debug) == 11.2


def test_normalize_render_layout_defaults_nested_flat_invalid_and_clamps() -> None:
    assert normalize_render_layout(None) == {"character_scale": 1.0, "chat_font_size_px": 18}
    assert normalize_render_layout({"layout": {"character_scale": "1.25", "chat_font_size_px": "24"}}) == {
        "character_scale": 1.25,
        "chat_font_size_px": 24,
    }
    assert normalize_render_layout({"character_scale": 0.5, "chat_font_size_px": 8}) == {
        "character_scale": 0.75,
        "chat_font_size_px": 12,
    }
    assert normalize_render_layout({"layout": {"character_scale": 2.0, "chat_font_size_px": 48}}) == {
        "character_scale": 1.5,
        "chat_font_size_px": 32,
    }
    assert normalize_render_layout({"character_scale": "bad", "chat_font_size_px": None}) == {
        "character_scale": 1.0,
        "chat_font_size_px": 18,
    }
    assert normalize_render_layout(
        {"character_scale": 0.8, "chat_font_size_px": 13, "layout": {"character_scale": 1.4, "chat_font_size_px": 26}}
    ) == {"character_scale": 1.4, "chat_font_size_px": 26}


def test_render_geometry_scales_reference_boxes_to_preset_size() -> None:
    full = RenderPreset(mode="final", width=REFERENCE_CANVAS_WIDTH, height=REFERENCE_CANVAS_HEIGHT, fps=30, x264_preset="fast", crf=22)
    preview = RenderPreset(mode="preview", width=540, height=960, fps=24, x264_preset="fast", crf=23)

    assert scale_box(CAPTION_CARD_POSITION, full) == CAPTION_CARD_POSITION
    assert scale_box(CAPTION_CARD_POSITION, preview) == (45, 660)
    assert scale_box(CAPTION_CARD_SIZE, preview) == (450, 190)


def test_render_geometry_layout_scaled_height_preserves_legacy_and_preset_scaled_math() -> None:
    assert layout_scaled_height(BASE_PORTRAIT_HEIGHT, 1.25) == 775
    assert layout_scaled_height(ACTIVE_PORTRAIT_HEIGHT, 1.25) == 975
    assert layout_scaled_height(
        BASE_PORTRAIT_HEIGHT,
        1.25,
        preset_height=960,
        canvas_height=REFERENCE_CANVAS_HEIGHT,
    ) == 388
    assert layout_scaled_height(
        ACTIVE_PORTRAIT_HEIGHT,
        1.25,
        preset_height=960,
        canvas_height=REFERENCE_CANVAS_HEIGHT,
    ) == 488


def test_render_geometry_portrait_resize_dimensions_preserve_ratio_and_minimum_width() -> None:
    assert portrait_resize_dimensions(400, 800, 200) == (100, 200)
    assert portrait_resize_dimensions(0, 0, 200) == (1, 200)
    assert portrait_resize_dimensions(1, 10_000, 1) == (1, 1)


def test_render_video_static_overlay_cast_preserves_first_two_speaker_slots() -> None:
    assert static_overlay_cast({"Host": 0, "Guest": 1, "Caller": 2}) == [("Host", 0), ("Guest", 1)]


def test_render_video_speaker_slots_from_lines_preserves_first_text_speakers() -> None:
    parsed_lines = [
        {"speaker": " Host ", "text": "Welcome."},
        {"speaker": "Guest", "text": ""},
        {"speaker": "Host", "text": "Again."},
        {"speaker": None, "text": "Default speaker."},
        {"text": "Next default."},
        {"speaker": "Caller", "text": "Question."},
    ]

    assert speaker_slots_from_lines(parsed_lines) == {
        "Host": 0,
        "Speaker 4": 1,
        "Speaker 5": 2,
        "Caller": 3,
    }


def test_render_video_primary_cast_segments_preserves_first_two_unique_speakers() -> None:
    host = SimpleNamespace(speaker="Host", slot_index=0)
    host_again = SimpleNamespace(speaker="Host", slot_index=0)
    guest = SimpleNamespace(speaker="Guest", slot_index=1)
    caller = SimpleNamespace(speaker="Caller", slot_index=2)

    assert primary_cast_segments([host, host_again, guest, caller]) == [host, guest]


def test_render_video_static_overlay_portrait_entries_preserve_scaled_payloads() -> None:
    full = RenderPreset(mode="final", width=1080, height=1920, fps=30, x264_preset="fast", crf=20)
    preview = RenderPreset(mode="preview", width=540, height=960, fps=12, x264_preset="ultrafast", crf=30)
    cast = [("Host", 0), ("Guest", 1)]
    layout = {"character_scale": 1.25, "chat_font_size_px": 18}

    assert static_overlay_portrait_entries(cast, layout, full) == [
        {
            "speaker": "Host",
            "slot_index": 0,
            "height": 775,
            "position": (56, 1080),
            "alpha": STATIC_OVERLAY_PORTRAIT_ALPHA,
        },
        {
            "speaker": "Guest",
            "slot_index": 1,
            "height": 775,
            "position": (584, 1080),
            "alpha": STATIC_OVERLAY_PORTRAIT_ALPHA,
        },
    ]
    assert static_overlay_portrait_entries(cast, layout, preview) == [
        {
            "speaker": "Host",
            "slot_index": 0,
            "height": 388,
            "position": (28, 540),
            "alpha": STATIC_OVERLAY_PORTRAIT_ALPHA,
        },
        {
            "speaker": "Guest",
            "slot_index": 1,
            "height": 388,
            "position": (292, 540),
            "alpha": STATIC_OVERLAY_PORTRAIT_ALPHA,
        },
    ]
    assert STATIC_OVERLAY_PORTRAIT_ALPHA == 0.26


def test_render_video_dynamic_frame_portrait_entry_preserves_scaled_payloads() -> None:
    full = RenderPreset(mode="final", width=1080, height=1920, fps=30, x264_preset="fast", crf=20)
    preview = RenderPreset(mode="preview", width=540, height=960, fps=12, x264_preset="ultrafast", crf=30)
    layout = {"character_scale": 1.25, "chat_font_size_px": 18}

    assert dynamic_frame_portrait_entry(0, layout, full) == {"height": 975, "position": (4, 930)}
    assert dynamic_frame_portrait_entry(1, layout, full) == {"height": 975, "position": (472, 930)}
    assert dynamic_frame_portrait_entry(2, layout, preview) == {"height": 488, "position": (236, 465)}


def test_render_video_dynamic_frame_caption_entry_preserves_scaled_payloads() -> None:
    full = RenderPreset(mode="final", width=1080, height=1920, fps=30, x264_preset="fast", crf=20)
    preview = RenderPreset(mode="preview", width=540, height=960, fps=12, x264_preset="ultrafast", crf=30)
    layout = {"character_scale": 1.25, "chat_font_size_px": 26}

    assert dynamic_frame_caption_entry(layout, full) == {
        "font_size_px": 26,
        "size": (900, 380),
        "position": (90, 1320),
    }
    assert dynamic_frame_caption_entry(layout, preview) == {
        "font_size_px": 26,
        "size": (450, 190),
        "position": (45, 660),
    }
    assert dynamic_frame_composition_payload(1, layout, preview) == {
        "portrait": {"height": 488, "position": (236, 465)},
        "caption": {"font_size_px": 26, "size": (450, 190), "position": (45, 660)},
    }


def test_render_video_dialogue_card_layout_preserves_card_and_font_payloads() -> None:
    layout = dialogue_card_layout_payload(
        speaker="Host",
        text="A short line for the render dialogue card.",
        chat_font_size_px=18,
    )

    assert layout["size"] == (900, 380)
    assert layout["background"] == {"box": (0, 0, 900, 380), "radius": 48, "fill": (6, 10, 18, 228)}
    assert layout["accent_bar"] == {"box": (0, 0, 900, 22), "radius": 22}
    assert layout["label"] == {"text": "HOST", "position": (70, 74), "font_size": 26}
    assert layout["body"]["font_size"] == 36
    assert layout["body"]["fill"] == (245, 248, 255, 255)
    assert layout["body"]["lines"] == [
        {"text": "A short line for the", "position": (70, 138)},
        {"text": "render dialogue card.", "position": (70, 202)},
    ]


def test_render_video_dialogue_card_layout_clamps_fonts_and_limits_wrapped_lines() -> None:
    layout = dialogue_card_layout_payload(
        speaker="guest",
        text=" ".join(f"word{index}" for index in range(30)),
        chat_font_size_px=8,
    )

    assert layout["label"]["text"] == "GUEST"
    assert layout["label"]["font_size"] == 24
    assert layout["body"]["font_size"] == 28
    assert len(layout["body"]["lines"]) == 4
    assert [line["position"] for line in layout["body"]["lines"]] == [(70, 138), (70, 202), (70, 266), (70, 330)]


def test_render_video_speaker_palette_preserves_values_and_modulo_slots() -> None:
    first = {
        "accent": (105, 224, 255, 255),
        "body": (19, 84, 122, 238),
        "plate": (35, 155, 208, 228),
    }
    second = {
        "accent": (255, 196, 87, 255),
        "body": (134, 76, 16, 238),
        "plate": (214, 120, 36, 228),
    }

    assert speaker_palette(0) == first
    assert speaker_palette(1) == second
    assert speaker_palette(2) == first


def test_render_video_speaker_initials_preserve_existing_extraction() -> None:
    assert speaker_initials("Ada Lovelace") == "AL"
    assert speaker_initials("Prince") == "P"
    assert speaker_initials("  ") == "S"
    assert speaker_initials("") == "S"


def test_render_video_generated_portrait_layout_preserves_payload_shape() -> None:
    layout = generated_portrait_layout_payload("Ada Lovelace", 1)

    assert layout["size"] == (760, 1100)
    assert layout["palette"] == speaker_palette(1)
    assert layout["head"] == {"box": (180, 60, 580, 460), "fill": (255, 196, 87, 255)}
    assert layout["body"] == {"box": (140, 420, 620, 1060), "radius": 180, "fill": (134, 76, 16, 238)}
    assert layout["plate"] == {"box": (120, 780, 640, 1060), "radius": 140, "fill": (214, 120, 36, 228)}
    assert layout["initials"] == {
        "text": "AL",
        "position": (380, 250),
        "anchor": "mm",
        "fill": (255, 255, 255, 255),
        "font_size": 176,
    }
    assert layout["name_plate"] == {"box": (80, 880, 680, 1030), "radius": 50, "fill": (10, 14, 20, 230)}
    assert layout["name"] == {
        "text": "Ada Lovelace",
        "position": (380, 956),
        "anchor": "mm",
        "fill": (243, 248, 255, 255),
        "font_size": 54,
    }


def test_render_audio_timeline_wav_duration_reads_actual_file_duration(tmp_path: Path) -> None:
    audio_path = tmp_path / "segment.wav"
    _write_test_wav(audio_path, seconds=1.25, sample_rate=8000)

    assert abs(wav_duration_seconds(audio_path) - 1.25) < 0.01


def test_render_audio_timeline_duration_prefers_file_then_segment_then_minimum() -> None:
    assert timeline_duration_seconds(1.4, 0.8) == 1.4
    assert timeline_duration_seconds(0.0, 1.1) == 1.1
    assert timeline_duration_seconds(0.1, 0.2) == 0.6


def test_render_audio_timeline_builds_ordered_entries_with_normalized_paths() -> None:
    first = SimpleNamespace(speaker="Host", duration_seconds=0.5)
    second = SimpleNamespace(speaker="Guest", duration_seconds=0.9)
    normalized_paths = [Path("/tmp/normalized_host.wav"), Path("/tmp/normalized_guest.wav")]

    timed_segments = build_timed_segments_from_durations(
        [first, second],
        [0.7, 0.4],
        normalized_paths,
    )

    assert [item["segment"].speaker for item in timed_segments] == ["Host", "Guest"]
    assert [item["duration_seconds"] for item in timed_segments] == [0.7, 0.9]
    assert [item["normalized_audio_path"] for item in timed_segments] == normalized_paths


def test_render_audio_mixdown_concat_file_contents_preserve_existing_escaping() -> None:
    contents = ffmpeg_concat_file_contents(
        [
            Path("/tmp/host.wav"),
            Path("/tmp/guest's line.wav"),
        ]
    )

    assert contents == "file '/tmp/host.wav'\nfile '/tmp/guest'\\''s line.wav'\n"


def test_render_audio_mixdown_concat_demuxer_command_matches_renderer_payload() -> None:
    assert concat_demuxer_audio_command(
        concat_list_path=Path("/tmp/dialogue_segments.txt"),
        output_path=Path("/tmp/dialogue_composite.wav"),
        sample_rate=44100,
    ) == [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        "/tmp/dialogue_segments.txt",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "44100",
        "-ac",
        "2",
        "/tmp/dialogue_composite.wav",
    ]


def test_render_audio_mixdown_multi_input_command_matches_single_and_multi_segment_payloads() -> None:
    assert concat_filter_complex(1, 44100) == "[0:a]aresample=44100[a]"
    assert concat_filter_complex(2, 44100) == "[0:a][1:a]concat=n=2:v=0:a=1,aresample=44100[a]"

    command = multi_input_audio_command(
        audio_paths=[Path("/tmp/one.wav"), Path("/tmp/two.wav")],
        output_path=Path("/tmp/dialogue_composite.wav"),
        sample_rate=44100,
    )

    assert command == [
        "ffmpeg",
        "-y",
        "-i",
        "/tmp/one.wav",
        "-i",
        "/tmp/two.wav",
        "-filter_complex",
        "[0:a][1:a]concat=n=2:v=0:a=1,aresample=44100[a]",
        "-map",
        "[a]",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "44100",
        "-ac",
        "2",
        "/tmp/dialogue_composite.wav",
    ]


def test_render_video_composer_final_video_command_matches_renderer_payload() -> None:
    preset = RenderPreset(mode="preview", width=1080, height=1920, fps=24, x264_preset="fast", crf=23)

    assert final_video_ffmpeg_command(
        background_path=Path("/tmp/background.mp4"),
        static_overlay_path=Path("/tmp/static_overlay.png"),
        dynamic_overlay_path=Path("/tmp/dynamic_overlay.mov"),
        audio_path=Path("/tmp/dialogue_composite.wav"),
        output_path=Path("/tmp/final.mp4"),
        preset=preset,
        duration_seconds=9.8765,
        audio_bitrate="192k",
        ffmpeg_threads=4,
    ) == [
        "ffmpeg",
        "-y",
        "-i",
        "/tmp/background.mp4",
        "-loop",
        "1",
        "-i",
        "/tmp/static_overlay.png",
        "-i",
        "/tmp/dynamic_overlay.mov",
        "-i",
        "/tmp/dialogue_composite.wav",
        "-filter_complex",
        FINAL_VIDEO_OVERLAY_FILTER,
        "-map",
        "[v]",
        "-map",
        "3:a",
        "-t",
        "9.877",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        "-threads",
        "4",
        "-shortest",
        "/tmp/final.mp4",
    ]


def test_render_video_composer_dynamic_overlay_concat_list_preserves_payload_shape(tmp_path: Path) -> None:
    first = tmp_path / "frame_one.png"
    second = tmp_path / "frame's two.png"
    expected_first = str(first.resolve())
    expected_second = str(second.resolve()).replace("'", "'\\''")

    assert dynamic_overlay_concat_list_contents(
        [
            {"path": first, "duration_seconds": 1.2345},
            {"path": second, "duration_seconds": 2.0},
        ]
    ) == (
        f"file '{expected_first}'\n"
        "duration 1.234\n"
        f"file '{expected_second}'\n"
        "duration 2.000\n"
        f"file '{expected_second}'\n"
    )


def test_render_video_composer_dynamic_overlay_command_matches_renderer_payload() -> None:
    preset = RenderPreset(mode="preview", width=540, height=960, fps=12, x264_preset="fast", crf=23)

    assert dynamic_overlay_ffmpeg_command(
        concat_list_path=Path("/tmp/dynamic_frames.txt"),
        output_path=Path("/tmp/dynamic_overlay.mov"),
        preset=preset,
    ) == [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        "/tmp/dynamic_frames.txt",
        "-vf",
        "fps=12,format=rgba",
        "-c:v",
        "qtrle",
        "/tmp/dynamic_overlay.mov",
    ]


def test_render_video_backgrounds_filter_preserves_style_payloads() -> None:
    preset = RenderPreset(mode="preview", width=540, height=960, fps=12, x264_preset="fast", crf=23)

    assert background_video_filter(style_preset="none", preset=preset) == (
        "scale=540:960:force_original_aspect_ratio=increase,crop=540:960,fps=12,format=yuv420p"
    )
    assert background_video_filter(style_preset="blur", preset=preset) == (
        "scale=540:960:force_original_aspect_ratio=increase,crop=540:960,fps=12,boxblur=20:1,format=yuv420p"
    )
    assert background_video_filter(style_preset="grayscale", preset=preset) == (
        "scale=540:960:force_original_aspect_ratio=increase,crop=540:960,fps=12,hue=s=0,format=yuv420p"
    )


def test_render_video_backgrounds_command_preserves_image_and_video_inputs() -> None:
    preset = RenderPreset(mode="preview", width=540, height=960, fps=12, x264_preset="ultrafast", crf=30)
    image_command = background_normalization_ffmpeg_command(
        background_path=Path("/tmp/background.png"),
        output_path=Path("/tmp/background_normalized.mp4"),
        style_preset="none",
        preset=preset,
        duration_seconds=11.2345,
        is_image_background=True,
        ffmpeg_threads=2,
    )
    video_command = background_normalization_ffmpeg_command(
        background_path=Path("/tmp/background.mp4"),
        output_path=Path("/tmp/background_normalized.mp4"),
        style_preset="none",
        preset=preset,
        duration_seconds=11.2345,
        is_image_background=False,
        ffmpeg_threads=2,
    )

    assert image_command[:8] == ["ffmpeg", "-y", "-loop", "1", "-i", "/tmp/background.png", "-t", "11.235"]
    assert video_command[:7] == ["ffmpeg", "-y", "-stream_loop", "-1", "-i", "/tmp/background.mp4", "-t"]
    assert video_command[7] == "11.235"
    assert image_command[-12:] == [
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "30",
        "-pix_fmt",
        "yuv420p",
        "-threads",
        "2",
        "/tmp/background_normalized.mp4",
    ]
