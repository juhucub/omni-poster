from __future__ import annotations

import logging
import math
import os
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import uuid
import wave
from functools import lru_cache
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.core.config import settings
from app.domains.render.artifacts import (
    build_assembly_metadata,
    build_debug_audio_extraction_metadata,
    build_render_result_metadata,
    build_segment_artifact_metadata,
    build_selected_profile_summary,
    build_tts_result_metadata,
)
from app.domains.render.audio.mixdown import (
    concat_demuxer_audio_command,
    ffmpeg_concat_file_contents,
    multi_input_audio_command,
)
from app.domains.render.audio.timeline import build_timed_segments_from_durations, wav_duration_seconds
from app.domains.render.cache_keys import (
    background_cache_key,
    composite_audio_cache_key,
    dynamic_frame_cache_key,
    dynamic_overlay_cache_key,
    final_video_cache_key,
    normalized_audio_cache_key,
    static_overlay_cache_key,
    tts_segment_cache_key,
    voice_profile_cache_payload,
)
from app.domains.render.cache_report import (
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
    ACTIVE_POSITIONS as RENDER_ACTIVE_POSITIONS,
    BASE_PORTRAIT_HEIGHT,
    BASE_POSITIONS as RENDER_BASE_POSITIONS,
    CAPTION_CARD_POSITION,
    CAPTION_CARD_SIZE,
    REFERENCE_CANVAS_HEIGHT,
    REFERENCE_CANVAS_WIDTH,
    layout_scaled_height,
    portrait_resize_dimensions,
    scale_box,
)
from app.domains.render.planning import RenderPlan, RenderPreset, write_render_plan
from app.domains.render.presets import (
    background_cache_duration_seconds,
    normalize_render_layout,
    render_preset_for_output_kind,
)
from app.domains.render.progress import render_progress_payload
from app.domains.render.video.backgrounds import background_normalization_ffmpeg_command
from app.domains.render.video.composer import (
    dynamic_overlay_concat_list_contents,
    dynamic_overlay_ffmpeg_command,
    final_video_ffmpeg_command,
)
from app.domains.render.video.overlays import (
    dialogue_card_layout_payload,
    dynamic_frame_composition_payload,
    generated_portrait_layout_payload,
    primary_cast_segments,
    speaker_palette as render_speaker_palette,
    speaker_slots_from_lines,
    static_overlay_cast,
    static_overlay_portrait_entries,
)
from app.services.character_presets import resolve_character_portrait_path, resolve_character_preset_for_speaker
from app.services.render_cache import (
    RENDER_CACHE_SCHEMA_VERSION,
    RenderCache,
    RenderCacheReport,
    cached_file_sha256,
    file_sha256,
)
from app.services.render_profiling import RenderProfiler
from app.services.storage import generated_job_artifact_dir, generated_job_artifact_url, generated_job_segment_dir
from app.services.tts import LocalSpeechService, SpeechSegment, TTSProviderError
from app.services.vid_gen import VideoGenerationService

logger = logging.getLogger(__name__)


class ProjectRenderService:
    CANVAS_WIDTH = REFERENCE_CANVAS_WIDTH
    CANVAS_HEIGHT = REFERENCE_CANVAS_HEIGHT
    BASE_POSITIONS = RENDER_BASE_POSITIONS
    ACTIVE_POSITIONS = RENDER_ACTIVE_POSITIONS
    BASE_HEIGHT = BASE_PORTRAIT_HEIGHT
    ACTIVE_HEIGHT = ACTIVE_PORTRAIT_HEIGHT

    def __init__(self, *, db=None, project_id: int | None = None) -> None:
        self.db = db
        self.project_id = project_id
        self.video_service = VideoGenerationService(output_dir="./generated_videos")
        self.speech_service = LocalSpeechService(db=db, project_id=project_id)
        self.output_dir = Path("./generated_videos")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.audio_export_fps = settings.TTS_AUDIO_EXPORT_FPS
        self.audio_export_bitrate = settings.TTS_AUDIO_EXPORT_BITRATE

    def render_preview(
        self,
        project_id: int,
        background_video_path: str,
        parsed_lines: list[dict],
        style_preset: str,
        output_kind: str = "preview",
        progress_callback=None,
        voice_manifest: dict | None = None,
        render_settings: dict | None = None,
        job_id: int | None = None,
        output_path: str | Path | None = None,
    ) -> dict:
        try:
            return self._render_speaker_video(
                project_id=project_id,
                background_video_path=background_video_path,
                parsed_lines=parsed_lines,
                style_preset=style_preset,
                output_kind=output_kind,
                progress_callback=progress_callback,
                voice_manifest=voice_manifest,
                render_settings=render_settings,
                job_id=job_id,
                output_path=output_path,
            )
        except TTSProviderError:
            # Provider selection failures are product-visible and must not be hidden by the visual fallback.
            logger.warning("Speaker render failed during TTS for project %s", project_id, exc_info=True)
            raise
        except RuntimeError as exc:
            logger.warning("Falling back to overlay-only render for project %s: %s", project_id, exc)
            return self.video_service.generate_video(
                video_path=background_video_path,
                audio_path=None,
                thumbnail_path=self._make_script_overlay(parsed_lines, style_preset),
                project_id=str(project_id),
                background_style=style_preset,
                output_kind=output_kind,
            )

    def _render_speaker_video(
        self,
        *,
        project_id: int,
        background_video_path: str,
        parsed_lines: list[dict],
        style_preset: str,
        output_kind: str,
        progress_callback,
        voice_manifest: dict | None,
        render_settings: dict | None,
        job_id: int | None,
        output_path: str | Path | None = None,
    ) -> dict:
        return self._render_speaker_video_ffmpeg(
            project_id=project_id,
            background_video_path=background_video_path,
            parsed_lines=parsed_lines,
            style_preset=style_preset,
            output_kind=output_kind,
            progress_callback=progress_callback,
            voice_manifest=voice_manifest,
            render_settings=render_settings,
            job_id=job_id,
            output_path=output_path,
        )

        from moviepy import (
            AudioFileClip,
            CompositeVideoClip,
            ImageClip,
            VideoFileClip,
        )

        clean_video_path = self.video_service._clean_file_path(background_video_path)
        if not Path(clean_video_path).exists():
            raise RuntimeError(f"Background video not found: {clean_video_path}")

        work_dir = Path(tempfile.mkdtemp(prefix=f"render_{project_id}_", dir=self.output_dir))
        clips_to_close: list = []
        profiler = RenderProfiler(
            enabled=settings.RENDER_PROFILING_ENABLED,
            job_id=job_id,
            project_id=project_id,
            output_kind=output_kind,
        )
        full_profile_stage = profiler.stage("render.full_generation_path")
        full_profile_stage.__enter__()
        full_profile_stage_closed = False
        try:
            render_layout = self._render_layout(render_settings)
            character_scale = render_layout["character_scale"]
            base_height = layout_scaled_height(self.BASE_HEIGHT, character_scale)
            active_height = layout_scaled_height(self.ACTIVE_HEIGHT, character_scale)
            chat_font_size_px = render_layout["chat_font_size_px"]
            profiler.add_context(
                background_video_path=clean_video_path,
                style_preset=style_preset,
                parsed_line_count=len(parsed_lines),
                preview_layout=render_layout,
            )
            self.speech_service = LocalSpeechService(
                db=self.db,
                project_id=project_id,
                voice_manifest=voice_manifest,
                profiler=profiler,
                output_kind=output_kind,
            )
            # Job-backed renders persist segment WAVs so the final MP4 audio can be audited later.
            speech_dir = self._speech_output_dir(job_id, work_dir)
            with profiler.stage("tts.dialogue_synthesis", segment_count=len(parsed_lines), speech_dir=speech_dir):
                segments = self.speech_service.synthesize_dialogue(parsed_lines, speech_dir)
            self._emit_progress(progress_callback, *render_progress_payload("tts_ready", engine="moviepy"))

            with profiler.stage("moviepy.background_load", background_video_path=clean_video_path):
                background_clip = VideoFileClip(clean_video_path).without_audio()
            with profiler.stage("moviepy.background_style", style_preset=style_preset):
                background_clip = self.video_service._apply_background_style(background_clip, style_preset)
            with profiler.stage("moviepy.background_fit", output_kind=output_kind):
                background_clip = self._fit_to_canvas(background_clip, output_kind)
            self._emit_progress(progress_callback, *render_progress_payload("background_ready", engine="moviepy"))

            with profiler.stage("render.segment_wav_validation", segment_count=len(segments)):
                timed_segments = self._build_timed_segments(segments)

            total_duration = sum(item["duration_seconds"] for item in timed_segments)
            if total_duration <= 0:
                raise RuntimeError("Generated speech audio has no duration.")
            with profiler.stage("ffmpeg.composite_audio_build", segment_count=len(timed_segments)):
                composite_audio_path = self._build_composite_audio_track(
                    timed_segments=timed_segments,
                    job_id=job_id,
                    project_id=project_id,
                    work_dir=work_dir,
                )

            with profiler.stage("moviepy.background_extend", duration_seconds=total_duration):
                background_clip = self._extend_background(background_clip, total_duration)
            clips_to_close.append(background_clip)

            portrait_path_cache: dict[tuple[str, int], Path] = {}

            def resolve_portrait_once(speaker: str, slot_index: int) -> Path:
                cache_key = (speaker, slot_index)
                cached = portrait_path_cache.get(cache_key)
                if cached is not None:
                    return cached
                resolved = self._resolve_character_portrait(speaker, slot_index, work_dir)
                portrait_path_cache[cache_key] = resolved
                return resolved

            cast = self._primary_cast(segments)
            timeline_layers = [background_clip]

            with profiler.stage("moviepy.portrait_layers_build", cast_count=len(cast)):
                for cast_member in cast:
                    portrait_path = resolve_portrait_once(cast_member.speaker, cast_member.slot_index)
                    base_clip = (
                        ImageClip(str(portrait_path))
                        .resized(height=base_height)
                        .with_opacity(0.26)
                        .with_position(self.BASE_POSITIONS[min(cast_member.slot_index, 1)])
                        .with_duration(total_duration)
                    )
                    timeline_layers.append(base_clip)
                    clips_to_close.append(base_clip)

            with profiler.stage("moviepy.caption_active_layers_build", segment_count=len(timed_segments)):
                cursor = 0.0
                for item in timed_segments:
                    # Segment order is the canonical timeline for active portraits, captions, and audio.
                    segment = item["segment"]
                    portrait_path = resolve_portrait_once(segment.speaker, segment.slot_index)
                    speaker_slot = min(segment.slot_index, 1)
                    active_clip = (
                        ImageClip(str(portrait_path))
                        .resized(height=active_height)
                        .with_position(self.ACTIVE_POSITIONS[speaker_slot])
                        .with_start(cursor)
                        .with_duration(item["duration_seconds"])
                    )
                    try:
                        caption_path = self._build_dialogue_card(
                            segment,
                            work_dir,
                            chat_font_size_px=chat_font_size_px,
                        )
                    except TypeError:
                        caption_path = self._build_dialogue_card(segment, work_dir)
                    caption_clip = (
                        ImageClip(str(caption_path))
                        .with_position((90, 1320))
                        .with_start(cursor)
                        .with_duration(item["duration_seconds"])
                    )
                    timeline_layers.extend([active_clip, caption_clip])
                    clips_to_close.extend([active_clip, caption_clip])
                    cursor += item["duration_seconds"]

            self._emit_progress(progress_callback, *render_progress_payload("timeline_ready", engine="moviepy"))

            with profiler.stage("moviepy.composite_audio_load", composite_audio_path=composite_audio_path):
                composite_audio = AudioFileClip(str(composite_audio_path))
            render_config = self._render_config(background_clip, output_kind)
            canvas_width = int(render_config["width"])
            canvas_height = int(render_config["height"])
            with profiler.stage(
                "moviepy.composite_video_build",
                layer_count=len(timeline_layers),
                width=canvas_width,
                height=canvas_height,
            ):
                composite = (
                    CompositeVideoClip(
                        timeline_layers,
                        size=(canvas_width, canvas_height),
                    )
                    .with_audio(composite_audio)
                    .with_duration(total_duration)
                )
            clips_to_close.append(composite)
            clips_to_close.append(composite_audio)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{project_id}_{output_kind}_{timestamp}.mp4"
            output_path = self.output_dir / output_filename
            self._log_final_assembly_inputs(
                job_id=job_id,
                project_id=project_id,
                timed_segments=timed_segments,
                composite_audio_path=composite_audio_path,
                final_mp4_path=output_path,
            )
            logger.info(
                "Writing composite video project=%s output=%s audio_fps=%s audio_bitrate=%s render_fps=%s preset=%s crf=%s segment_count=%s duration=%.2fs",
                project_id,
                output_path,
                self.audio_export_fps,
                self.audio_export_bitrate,
                render_config["fps"],
                render_config["preset"],
                render_config["crf"],
                len(segments),
                total_duration,
            )
            self._emit_progress(progress_callback, *render_progress_payload("encoding", engine="moviepy"))
            with profiler.stage(
                "moviepy.ffmpeg_encode_and_mp4_write",
                output_path=output_path,
                fps=render_config["fps"],
                threads=render_config["threads"],
                preset=render_config["preset"],
                crf=render_config["crf"],
            ):
                composite.write_videofile(
                    str(output_path),
                    fps=render_config["fps"],
                    codec="libx264",
                    audio_codec="aac",
                    audio_fps=self.audio_export_fps,
                    audio_bitrate=self.audio_export_bitrate,
                    temp_audiofile=str(work_dir / "temp_audio.m4a"),
                    remove_temp=True,
                    preset=render_config["preset"],
                    ffmpeg_params=[
                        "-crf",
                        str(render_config["crf"]),
                        "-movflags",
                        "+faststart",
                        "-pix_fmt",
                        "yuv420p",
                    ],
                    threads=render_config["threads"],
                    logger=None,
                )
            self._emit_progress(progress_callback, *render_progress_payload("encoded", engine="moviepy"))
            with profiler.stage("ffmpeg.final_audio_extract", final_mp4_path=output_path):
                final_video_audio_path = self._extract_final_video_audio(
                    final_mp4_path=output_path,
                    job_id=job_id,
                    work_dir=work_dir,
                )

            segment_metadata = [
                self._segment_artifact_metadata(
                    index=index,
                    item=item,
                    voice_manifest=voice_manifest,
                    job_id=job_id,
                    audio_path_used_for_final_assembly=str(item["segment"].audio_path),
                )
                for index, item in enumerate(timed_segments)
            ]
            assembly_metadata = self._assembly_metadata(
                job_id=job_id,
                project_id=project_id,
                timed_segments=timed_segments,
                segment_metadata=segment_metadata,
                composite_audio_path=composite_audio_path,
                final_mp4_path=output_path,
                final_video_audio_path=final_video_audio_path,
            )
            tts_result = build_tts_result_metadata(
                provider_state=(segments[-1].provider_state or {}) if segments else {},
                segment_metadata=segment_metadata,
                assembly_metadata=assembly_metadata,
                render_layout=render_layout,
            )
            selected_profiles = build_selected_profile_summary(segments)
            profiler.add_context(
                segment_count=len(segments),
                video_duration_seconds=total_duration,
                resolution={"width": canvas_width, "height": canvas_height},
                fps=render_config["fps"],
                ffmpeg_thread_cap=settings.RENDER_FFMPEG_THREAD_CAP,
                ffmpeg_threads=render_config["threads"],
                encode_preset=render_config["preset"],
                crf=render_config["crf"],
                preview_layout=render_layout,
                tts_provider_state=tts_result["provider_state"],
                selected_profiles=selected_profiles,
            )
            full_profile_stage.__exit__(None, None, None)
            full_profile_stage_closed = True
            profile_artifact_url = None
            profile_summary = profiler.summary()
            if profiler.enabled and job_id is not None:
                profile_path = generated_job_artifact_dir(job_id) / "generation_profile.json"
                with profiler.stage("profile.write_artifact", profile_path=profile_path):
                    profiler.write_json(profile_path)
                profile_artifact_url = generated_job_artifact_url(job_id, profile_path)
                profile_summary = profiler.summary()
                logger.info(
                    "Render profile job_id=%s total=%.3fs peak_rss=%s top_stages=%s artifact=%s",
                    job_id,
                    profile_summary.get("total_duration_seconds") or 0,
                    profile_summary.get("peak_observed_rss_bytes"),
                    profile_summary.get("top_stages"),
                    profile_artifact_url,
                )
            render_profile_metadata = build_render_profile_metadata(
                artifact_url=profile_artifact_url,
                summary=profile_summary,
                profile_path=generated_job_artifact_dir(job_id) / "generation_profile.json" if job_id is not None else None,
            )
            tts_result["render_profile"] = render_profile_metadata

            return {
                "output_path": f"file://{output_path.absolute()}",
                "filename": output_filename,
                "size_bytes": output_path.stat().st_size,
                "duration_seconds": total_duration,
                "status": "completed",
                "created_at": datetime.now().isoformat(),
                "processing_time_seconds": None,
                "metadata": build_render_result_metadata(
                    render_mode="speaker_dialogue",
                    segments=segments,
                    tts_result=tts_result,
                    render_layout=render_layout,
                    render_profile_metadata=render_profile_metadata,
                    render_profile_artifact_url=profile_artifact_url,
                    assembly_metadata=assembly_metadata,
                    timed_segments=timed_segments,
                    segment_metadata=segment_metadata,
                    render_fps=render_config["fps"],
                    render_resolution={"width": canvas_width, "height": canvas_height},
                    character_scale=character_scale,
                    chat_font_size_px=chat_font_size_px,
                    ffmpeg_threads=render_config["threads"],
                    encode_preset=render_config["preset"],
                    portrait_resolution="backend/storage/characters/<speaker>.png or speaker_<slot>.png",
                ),
            }
        finally:
            if not full_profile_stage_closed:
                full_profile_stage.__exit__(*sys.exc_info())
            for clip in reversed(clips_to_close):
                close = getattr(clip, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        logger.debug("Failed to close clip cleanly", exc_info=True)
            shutil.rmtree(work_dir, ignore_errors=True)

    def _render_speaker_video_ffmpeg(
        self,
        *,
        project_id: int,
        background_video_path: str,
        parsed_lines: list[dict],
        style_preset: str,
        output_kind: str,
        progress_callback,
        voice_manifest: dict | None,
        render_settings: dict | None,
        job_id: int | None,
        output_path: str | Path | None = None,
    ) -> dict:
        clean_video_path = self.video_service._clean_file_path(background_video_path)
        background_path = Path(clean_video_path)
        if not background_path.exists():
            raise RuntimeError(f"Background video not found: {clean_video_path}")

        work_dir = Path(tempfile.mkdtemp(prefix=f"render_{project_id}_", dir=self.output_dir))
        cache = RenderCache()
        cache_report = RenderCacheReport()
        profiler = RenderProfiler(
            enabled=settings.RENDER_PROFILING_ENABLED,
            job_id=job_id,
            project_id=project_id,
            output_kind=output_kind,
        )
        full_profile_stage = profiler.stage("render.full_generation_path")
        full_profile_stage.__enter__()
        full_profile_stage_closed = False
        try:
            render_layout = self._render_layout(render_settings)
            preset = self._render_preset(output_kind)
            visual_dir = generated_job_artifact_dir(job_id) / "visual" if job_id is not None else work_dir / "visual"
            visual_dir.mkdir(parents=True, exist_ok=True)
            audio_dir = generated_job_artifact_dir(job_id) / "audio" if job_id is not None else work_dir / "audio"
            audio_dir.mkdir(parents=True, exist_ok=True)
            speech_dir = self._speech_output_dir(job_id, work_dir)
            final_output_path = Path(output_path) if output_path is not None else self.output_dir / f"{project_id}_{output_kind}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            final_output_path.parent.mkdir(parents=True, exist_ok=True)

            self.speech_service = LocalSpeechService(
                db=self.db,
                project_id=project_id,
                voice_manifest=voice_manifest,
                profiler=profiler,
                output_kind=output_kind,
            )
            with profiler.stage("tts.resolve_voice_profiles", line_count=len(parsed_lines)):
                voice_profile_map = self.speech_service.resolve_voice_profile_map(parsed_lines)

            speaker_slots = self._speaker_slots(parsed_lines)
            portrait_paths: dict[str, Path] = {}
            portrait_hashes: dict[str, str] = {}
            fingerprint_metadata: dict[str, Any] = {}
            for speaker, slot_index in speaker_slots.items():
                portrait = self._resolve_character_portrait(speaker, slot_index, work_dir)
                portrait_paths[speaker] = portrait
                if portrait.exists():
                    portrait_hashes[speaker], fingerprint_metadata[f"portrait:{speaker}"] = cached_file_sha256(portrait)
                else:
                    portrait_hashes[speaker] = ""

            background_hash, background_fingerprint_metadata = cached_file_sha256(background_path)
            fingerprint_metadata["background"] = background_fingerprint_metadata
            background_mime_type = self._guess_mime_type(background_path)
            expected_artifacts = {
                "render_plan": str(generated_job_artifact_dir(job_id) / "render_plan.json") if job_id is not None else str(work_dir / "render_plan.json"),
                "cache_report": str(generated_job_artifact_dir(job_id) / "cache_report.json") if job_id is not None else str(work_dir / "cache_report.json"),
                "composite_audio": str(audio_dir / "dialogue_composite.wav"),
                "normalized_background": str(visual_dir / "background_normalized.mp4"),
                "static_overlay": str(visual_dir / "static_overlay.png"),
                "dynamic_overlay": str(visual_dir / "dynamic_overlay.mov"),
                "final_video": str(final_output_path),
            }
            plan = RenderPlan(
                job_id=job_id,
                project_id=project_id,
                output_kind=output_kind,
                preset=preset,
                parsed_lines=parsed_lines,
                voice_profiles=voice_profile_map,
                background_source_path=str(background_path),
                background_hash=background_hash,
                background_mime_type=background_mime_type,
                style_preset=style_preset,
                speaker_pngs={speaker: str(path) for speaker, path in portrait_paths.items()},
                speaker_png_hashes=portrait_hashes,
                layout=render_layout,
                caption_settings={"font_size_px": render_layout["chat_font_size_px"], "card_position": [90, 1320]},
                expected_artifacts=expected_artifacts,
            )
            profiler.add_context(
                background_video_path=clean_video_path,
                background_hash=background_hash,
                background_mime_type=background_mime_type,
                style_preset=style_preset,
                parsed_line_count=len(parsed_lines),
                preview_layout=render_layout,
                render_engine="ffmpeg",
                render_cache_schema_version=RENDER_CACHE_SCHEMA_VERSION,
                asset_fingerprints=fingerprint_metadata,
            )

            with profiler.stage("tts.dialogue_synthesis_or_cache", segment_count=len(parsed_lines), speech_dir=speech_dir):
                segments = self._synthesize_segments_with_render_cache(
                    parsed_lines=parsed_lines,
                    voice_profile_map=voice_profile_map,
                    output_dir=speech_dir,
                    cache=cache,
                    cache_report=cache_report,
                    profiler=profiler,
                    output_kind=output_kind,
                )
            self._emit_progress(progress_callback, *render_progress_payload("tts_ready"))

            with profiler.stage("ffmpeg.wav_normalization", segment_count=len(segments)):
                normalized_paths, normalized_keys = self._normalize_segment_wavs(
                    segments=segments,
                    cache=cache,
                    cache_report=cache_report,
                    audio_dir=audio_dir,
                )
            timed_segments = self._build_timed_segments_with_normalized_audio(segments, normalized_paths)
            total_duration = sum(item["duration_seconds"] for item in timed_segments)
            if total_duration <= 0:
                raise RuntimeError("Generated speech audio has no duration.")

            with profiler.stage("ffmpeg.composite_audio_build", segment_count=len(timed_segments)):
                composite_audio_path, composite_audio_key = self._build_composite_audio_track_cached(
                    timed_segments=timed_segments,
                    normalized_keys=normalized_keys,
                    cache=cache,
                    cache_report=cache_report,
                    audio_dir=audio_dir,
                    job_id=job_id,
                    project_id=project_id,
                )
            self._emit_progress(progress_callback, *render_progress_payload("audio_ready"))

            with profiler.stage("ffmpeg.background_normalization", duration_seconds=total_duration):
                normalized_background_path, background_key = self._normalize_background_layer(
                    background_path=background_path,
                    background_hash=background_hash,
                    background_mime_type=background_mime_type,
                    style_preset=style_preset,
                    preset=preset,
                    duration_seconds=total_duration,
                    cache=cache,
                    cache_report=cache_report,
                    visual_dir=visual_dir,
                )
            self._emit_progress(progress_callback, *render_progress_payload("background_ready"))

            with profiler.stage("render.static_overlay_build", speaker_count=len(portrait_paths)):
                static_overlay_path, static_overlay_key = self._build_static_overlay_layer(
                    portrait_paths=portrait_paths,
                    portrait_hashes=portrait_hashes,
                    speaker_slots=speaker_slots,
                    render_layout=render_layout,
                    preset=preset,
                    cache=cache,
                    cache_report=cache_report,
                    visual_dir=visual_dir,
                )
            with profiler.stage("render.dynamic_overlay_build", segment_count=len(timed_segments)):
                dynamic_overlay_path, dynamic_overlay_key = self._build_dynamic_overlay_layer(
                    timed_segments=timed_segments,
                    portrait_paths=portrait_paths,
                    portrait_hashes=portrait_hashes,
                    render_layout=render_layout,
                    preset=preset,
                    cache=cache,
                    cache_report=cache_report,
                    visual_dir=visual_dir,
                )
            self._emit_progress(progress_callback, *render_progress_payload("timeline_ready"))

            final_video_key = final_video_cache_key(
                background_key=background_key,
                static_overlay_key=static_overlay_key,
                dynamic_overlay_key=dynamic_overlay_key,
                composite_audio_key=composite_audio_key,
                preset=preset,
                duration_seconds=total_duration,
                audio_bitrate=self.audio_export_bitrate,
            )
            final_cache_path = cache.path("final_videos", final_video_key, ".mp4")
            elapsed = cache_report.timed()
            if cache.materialize(final_cache_path, final_output_path):
                cache_report.record(
                    artifact_type="final_video",
                    cache_key=final_video_key,
                    status="materialized_from_cache",
                    cache_path=final_cache_path,
                    job_path=final_output_path,
                    duration_seconds=elapsed(),
                    metadata=build_final_render_cache_transfer_metadata(cache.last_transfer),
                )
            else:
                cache_report.record(
                    artifact_type="final_video",
                    cache_key=final_video_key,
                    status="miss",
                    cache_path=final_cache_path,
                    job_path=final_output_path,
                    duration_seconds=elapsed(),
                )
                self._emit_progress(progress_callback, *render_progress_payload("encoding"))
                with profiler.stage(
                    "ffmpeg.final_video_render",
                    output_path=final_output_path,
                    fps=preset.fps,
                    threads=self._ffmpeg_threads(),
                    preset=preset.x264_preset,
                    crf=preset.crf,
                ):
                    self._build_final_video_ffmpeg(
                        background_path=normalized_background_path,
                        static_overlay_path=static_overlay_path,
                        dynamic_overlay_path=dynamic_overlay_path,
                        audio_path=composite_audio_path,
                        output_path=final_output_path,
                        preset=preset,
                        duration_seconds=total_duration,
                    )
                cache.store(final_output_path, final_cache_path, {"cache_key": final_video_key, "created_at": datetime.utcnow().isoformat()})
                cache_report.record(
                    artifact_type="final_video",
                    cache_key=final_video_key,
                    status="regenerated",
                    cache_path=final_cache_path,
                    job_path=final_output_path,
                    metadata=build_final_render_cache_transfer_metadata(cache.last_transfer),
                )
            self._emit_progress(progress_callback, *render_progress_payload("encoded"))

            final_video_audio_path: Path | None = None
            debug_extraction = build_debug_audio_extraction_metadata(enabled=preset.debug_audio_extract)
            if preset.debug_audio_extract:
                with profiler.stage("ffmpeg.final_audio_extract", final_mp4_path=final_output_path):
                    final_video_audio_path = self._extract_final_video_audio(
                        final_mp4_path=final_output_path,
                        job_id=job_id,
                        work_dir=work_dir,
                    )
                    debug_extraction = build_debug_audio_extraction_metadata(
                        enabled=preset.debug_audio_extract,
                        artifact_path=final_video_audio_path,
                        include_artifact_path=True,
                    )

            segment_metadata = [
                self._segment_artifact_metadata(
                    index=index,
                    item=item,
                    voice_manifest=voice_manifest,
                    job_id=job_id,
                    audio_path_used_for_final_assembly=str(item["normalized_audio_path"]),
                )
                for index, item in enumerate(timed_segments)
            ]
            for index, metadata in enumerate(segment_metadata):
                metadata["normalized_audio_path"] = str(normalized_paths[index])
                metadata["normalized_audio_artifact_url"] = (
                    generated_job_artifact_url(job_id, normalized_paths[index]) if job_id is not None else None
                )
                metadata["normalized_cache_key"] = normalized_keys[index]
                metadata["normalized_cache_hit"] = timed_segments[index]["segment"].normalized_cache_hit
                metadata["tts_cache_key"] = timed_segments[index]["segment"].cache_key
                metadata["tts_cache_hit"] = timed_segments[index]["segment"].cache_hit
                metadata["tts_cache_source_path"] = timed_segments[index]["segment"].cache_source_path

            assembly_metadata = self._assembly_metadata(
                job_id=job_id,
                project_id=project_id,
                timed_segments=timed_segments,
                segment_metadata=segment_metadata,
                composite_audio_path=composite_audio_path,
                final_mp4_path=final_output_path,
                final_video_audio_path=final_video_audio_path,
            )
            assembly_metadata["debug_audio_extraction"] = debug_extraction
            assembly_metadata["normalized_background_path"] = str(normalized_background_path)
            assembly_metadata["static_overlay_path"] = str(static_overlay_path)
            assembly_metadata["dynamic_overlay_path"] = str(dynamic_overlay_path)

            plan.cache_keys = {
                "background": background_key,
                "static_overlay": static_overlay_key,
                "dynamic_overlay": dynamic_overlay_key,
                "composite_audio": composite_audio_key,
                "final_video": final_video_key,
            }
            plan.segments = segment_metadata
            plan_path = Path(expected_artifacts["render_plan"])
            cache_report_path = Path(expected_artifacts["cache_report"])
            with profiler.stage("render_plan.write_artifact", profile_path=plan_path):
                write_render_plan(plan, plan_path)
            cache_report_payload = cache_report.summary()
            cache_report_path.write_text(json.dumps(cache_report_payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

            render_plan_metadata = {
                "path": str(plan_path),
                "artifact_url": generated_job_artifact_url(job_id, plan_path) if job_id is not None else None,
                "plan_key": plan.plan_key(),
            }
            cache_report_metadata = {
                "path": str(cache_report_path),
                "artifact_url": generated_job_artifact_url(job_id, cache_report_path) if job_id is not None else None,
                "summary": cache_report_payload,
            }
            tts_result = build_tts_result_metadata(
                provider_state=(segments[-1].provider_state or {}) if segments else {},
                segment_metadata=segment_metadata,
                assembly_metadata=assembly_metadata,
                render_layout=render_layout,
                current_phase="completed",
                render_plan=render_plan_metadata,
                cache_report=cache_report_metadata,
            )
            selected_profiles = build_selected_profile_summary(segments)
            profiler.add_context(
                segment_count=len(segments),
                video_duration_seconds=total_duration,
                resolution={"width": preset.width, "height": preset.height},
                fps=preset.fps,
                ffmpeg_thread_cap=settings.RENDER_FFMPEG_THREAD_CAP,
                ffmpeg_threads=self._ffmpeg_threads(),
                encode_preset=preset.x264_preset,
                crf=preset.crf,
                preview_layout=render_layout,
                tts_provider_state=tts_result["provider_state"],
                selected_profiles=selected_profiles,
                cache_statistics=cache_report_payload,
                fast_preview_enabled=preset.mode == "draft",
            )
            full_profile_stage.__exit__(None, None, None)
            full_profile_stage_closed = True
            profile_artifact_url = None
            profile_summary = profiler.summary()
            if profiler.enabled and job_id is not None:
                profile_path = generated_job_artifact_dir(job_id) / "generation_profile.json"
                with profiler.stage("profile.write_artifact", profile_path=profile_path):
                    profiler.write_json(profile_path)
                profile_artifact_url = generated_job_artifact_url(job_id, profile_path)
                profile_summary = profiler.summary()
            render_profile_metadata = build_render_profile_metadata(
                artifact_url=profile_artifact_url,
                summary=profile_summary,
                profile_path=generated_job_artifact_dir(job_id) / "generation_profile.json" if job_id is not None else None,
            )
            tts_result["render_profile"] = render_profile_metadata

            return {
                "output_path": f"file://{final_output_path.absolute()}",
                "filename": final_output_path.name,
                "size_bytes": final_output_path.stat().st_size,
                "duration_seconds": total_duration,
                "status": "completed",
                "created_at": datetime.now().isoformat(),
                "processing_time_seconds": None,
                "metadata": build_render_result_metadata(
                    render_mode="speaker_dialogue_ffmpeg",
                    render_engine="ffmpeg",
                    segments=segments,
                    tts_result=tts_result,
                    render_layout=render_layout,
                    performance={
                        "fast_preview_enabled": preset.mode == "draft",
                        "render_preset": preset.__dict__,
                        "asset_fingerprints": fingerprint_metadata,
                    },
                    render_profile_metadata=render_profile_metadata,
                    render_profile_artifact_url=profile_artifact_url,
                    render_plan_artifact_url=tts_result["render_plan"]["artifact_url"],
                    cache_report_artifact_url=tts_result["cache_report"]["artifact_url"],
                    cache_statistics=cache_report_payload,
                    assembly_metadata=assembly_metadata,
                    timed_segments=timed_segments,
                    segment_metadata=segment_metadata,
                    render_fps=preset.fps,
                    render_resolution={"width": preset.width, "height": preset.height},
                    character_scale=render_layout["character_scale"],
                    chat_font_size_px=render_layout["chat_font_size_px"],
                    ffmpeg_threads=self._ffmpeg_threads(),
                    encode_preset=preset.x264_preset,
                    crf=preset.crf,
                    debug_audio_extraction=debug_extraction,
                ),
            }
        finally:
            if not full_profile_stage_closed:
                full_profile_stage.__exit__(*sys.exc_info())
            shutil.rmtree(work_dir, ignore_errors=True)

    def _render_preset(self, output_kind: str) -> RenderPreset:
        return render_preset_for_output_kind(output_kind)

    def _speaker_slots(self, parsed_lines: list[dict]) -> dict[str, int]:
        return speaker_slots_from_lines(parsed_lines)

    def _guess_mime_type(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in {".png"}:
            return "image/png"
        if suffix in {".jpg", ".jpeg"}:
            return "image/jpeg"
        if suffix in {".webp"}:
            return "image/webp"
        if suffix in {".webm"}:
            return "video/webm"
        if suffix in {".mpeg", ".mpg"}:
            return "video/mpeg"
        return "video/mp4"

    def _is_image_background(self, mime_type: str, path: Path) -> bool:
        return mime_type.startswith("image/") or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}

    def _ffmpeg_threads(self) -> int:
        return max(1, min(os.cpu_count() or 4, max(1, settings.RENDER_FFMPEG_THREAD_CAP)))

    def _run_ffmpeg(self, command: list[str]) -> None:
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise RuntimeError("ffmpeg is required for FFmpeg-first rendering.") from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(exc.stderr or str(exc)) from exc

    def _voice_profile_cache_payload(self, voice_profile: dict[str, Any]) -> dict[str, Any]:
        return voice_profile_cache_payload(voice_profile)

    def _synthesize_segments_with_render_cache(
        self,
        *,
        parsed_lines: list[dict],
        voice_profile_map: dict[str, dict[str, Any]],
        output_dir: Path,
        cache: RenderCache,
        cache_report: RenderCacheReport,
        profiler: RenderProfiler,
        output_kind: str,
    ) -> list[SpeechSegment]:
        output_dir.mkdir(parents=True, exist_ok=True)
        segments: list[SpeechSegment] = []
        slot_map: dict[str, int] = {}
        provider_state = self.speech_service.orchestrator.provider_state()
        for index, line in enumerate(parsed_lines):
            speaker = str(line.get("speaker") or f"Speaker {index + 1}").strip()
            text = str(line.get("text") or "").strip()
            caption_text = str(line.get("caption_text") or text).strip()
            line_id = str(line.get("line_id") or "").strip() or None
            if not text:
                continue
            slot_index = slot_map.setdefault(speaker, len(slot_map))
            voice_profile = voice_profile_map[speaker]
            requested_provider = voice_profile.get("requested_provider") or voice_profile.get("provider")
            fallback_allowed = bool(voice_profile.get("fallback_allowed", True))
            cache_key = tts_segment_cache_key(
                speaker=speaker,
                text=text,
                voice_profile=voice_profile,
                requested_provider=requested_provider,
                fallback_allowed=fallback_allowed,
                output_kind=output_kind,
            )
            output_path = output_dir / f"{index:03d}_{self._slugify(speaker)}_{cache_key[:12]}.wav"
            cache_path = cache.path("tts_segments", cache_key, ".wav")
            elapsed = cache_report.timed()
            metadata = cache.read_metadata(cache_path)
            if cache.materialize(cache_path, output_path) and metadata:
                cache_report.record(
                    artifact_type="tts_segment",
                    cache_key=cache_key,
                    status="materialized_from_cache",
                    cache_path=cache_path,
                    job_path=output_path,
                    duration_seconds=elapsed(),
                    metadata=build_tts_segment_cache_transfer_metadata(
                        cache.last_transfer,
                        speaker=speaker,
                        provider_used=metadata.get("provider_used"),
                    ),
                )
                segments.append(
                    SpeechSegment(
                        speaker=speaker,
                        text=text,
                        voice=str(metadata.get("voice") or voice_profile.get("display_name") or speaker),
                        slot_index=slot_index,
                        audio_path=str(output_path),
                        duration_seconds=float(metadata.get("duration_seconds") or self._wav_duration_seconds(output_path)),
                        caption_text=caption_text,
                        line_id=line_id,
                        voice_profile_id=str(metadata.get("voice_profile_id") or voice_profile.get("id") or ""),
                        provider_used=str(metadata.get("provider_used") or requested_provider or "espeak"),
                        fallback_used=bool(metadata.get("fallback_used", False)),
                        controls_applied=dict(metadata.get("controls_applied") or {}),
                        reference_audio_count=int(metadata.get("reference_audio_count") or len(voice_profile.get("reference_audios") or [])),
                        provider_state=dict(metadata.get("provider_state") or provider_state),
                        provider_failures=dict(metadata.get("provider_failures") or {}),
                        fallback_reason=metadata.get("fallback_reason"),
                        recipe_used=dict(metadata.get("recipe_used") or voice_profile.get("selected_recipe") or {}),
                        golden_preview_wav=metadata.get("golden_preview_wav"),
                        cache_hit=True,
                        cache_key=cache_key,
                        cache_source_path=str(cache_path),
                    )
                )
                continue

            cache_report.record(
                artifact_type="tts_segment",
                cache_key=cache_key,
                status="miss",
                cache_path=cache_path,
                job_path=output_path,
                duration_seconds=elapsed(),
                metadata=build_tts_segment_cache_miss_metadata(speaker=speaker),
            )
            with profiler.stage(
                "tts.segment_synthesis",
                provider=requested_provider,
                voice_profile_id=voice_profile.get("id"),
                output_path=output_path,
                text_length=len(text),
            ):
                result = self.speech_service.orchestrator.synthesize_line(
                    text=text,
                    voice_profile=voice_profile,
                    output_path=output_path,
                    requested_provider=requested_provider,
                    fallback_allowed=fallback_allowed,
                    options={"profiler": profiler, "output_kind": output_kind, "provider_state": provider_state},
                )
            metadata = {
                "cache_key": cache_key,
                "voice": result.voice,
                "duration_seconds": result.duration_seconds,
                "provider_used": result.provider_used,
                "fallback_used": result.fallback_used,
                "controls_applied": result.controls_applied,
                "reference_audio_count": result.reference_audio_count,
                "provider_state": result.provider_state,
                "voice_profile_id": result.voice_profile_id,
                "provider_failures": result.provider_failures or {},
                "fallback_reason": result.fallback_reason,
                "recipe_used": result.recipe_used or {},
                "golden_preview_wav": result.golden_preview_wav,
                "caption_text": caption_text,
                "line_id": line_id,
                "created_at": datetime.utcnow().isoformat(),
            }
            cache.store(output_path, cache_path, metadata)
            cache_report.record(
                artifact_type="tts_segment",
                cache_key=cache_key,
                status="regenerated",
                cache_path=cache_path,
                job_path=output_path,
                metadata=build_tts_segment_cache_transfer_metadata(
                    cache.last_transfer,
                    speaker=speaker,
                    provider_used=result.provider_used,
                ),
            )
            segments.append(
                SpeechSegment(
                    speaker=speaker,
                    text=text,
                    voice=result.voice,
                    slot_index=slot_index,
                    audio_path=str(output_path),
                    duration_seconds=result.duration_seconds,
                    caption_text=caption_text,
                    line_id=line_id,
                    voice_profile_id=result.voice_profile_id,
                    provider_used=result.provider_used,
                    fallback_used=result.fallback_used,
                    controls_applied=result.controls_applied,
                    reference_audio_count=result.reference_audio_count,
                    provider_state=result.provider_state,
                    provider_failures=result.provider_failures,
                    fallback_reason=result.fallback_reason,
                    recipe_used=result.recipe_used,
                    golden_preview_wav=result.golden_preview_wav,
                    cache_hit=False,
                    cache_key=cache_key,
                )
            )
        if not segments:
            raise TTSProviderError(
                code="no_spoken_lines",
                message="Cannot render a dialogue video without spoken lines.",
                provider_state=provider_state,
                suggested_action="Add at least one spoken script line before rendering.",
            )
        return segments

    def _normalize_segment_wavs(
        self,
        *,
        segments: list[SpeechSegment],
        cache: RenderCache,
        cache_report: RenderCacheReport,
        audio_dir: Path,
    ) -> tuple[list[Path], list[str]]:
        normalized_dir = generated_job_artifact_dir(int(audio_dir.parent.name)) / "normalized_segments" if audio_dir.parent.name.isdigit() else audio_dir / "normalized_segments"
        normalized_dir.mkdir(parents=True, exist_ok=True)
        normalized_paths: list[Path] = []
        normalized_keys: list[str] = []
        for index, segment in enumerate(segments):
            source_path = Path(segment.audio_path)
            source_identity = segment.cache_key or file_sha256(source_path)
            cache_key = normalized_audio_cache_key(source_identity, self.audio_export_fps)
            cache_path = cache.path("normalized_audio", cache_key, ".wav")
            output_path = normalized_dir / f"{index:03d}_{self._slugify(segment.speaker)}_{cache_key[:12]}.wav"
            elapsed = cache_report.timed()
            metadata = cache.read_metadata(cache_path)
            if cache.materialize(cache_path, output_path):
                cache_report.record(
                    artifact_type="normalized_audio",
                    cache_key=cache_key,
                    status="materialized_from_cache",
                    cache_path=cache_path,
                    job_path=output_path,
                    duration_seconds=elapsed(),
                    metadata=build_normalized_audio_cache_transfer_metadata(
                        cache.last_transfer,
                        duration_seconds=metadata.get("duration_seconds"),
                        normalization_skipped=metadata.get("normalization_skipped", False),
                    ),
                )
                object.__setattr__(segment, "normalized_cache_hit", True)
                duration_seconds = float(metadata.get("duration_seconds") or self._wav_duration_seconds(output_path))
            else:
                cache_report.record(
                    artifact_type="normalized_audio",
                    cache_key=cache_key,
                    status="miss",
                    cache_path=cache_path,
                    job_path=output_path,
                    duration_seconds=elapsed(),
                )
                normalization_skipped = self._wav_matches_render_format(source_path)
                if normalization_skipped:
                    duration_seconds = self._wav_duration_seconds(source_path)
                    cache.store(
                        source_path,
                        cache_path,
                        {
                            "cache_key": cache_key,
                            "source_path": str(source_path),
                            "duration_seconds": duration_seconds,
                            "normalization_skipped": True,
                        },
                    )
                    cache.materialize(cache_path, output_path)
                else:
                    command = [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(source_path),
                        "-acodec",
                        "pcm_s16le",
                        "-ar",
                        str(self.audio_export_fps),
                        "-ac",
                        "2",
                        str(output_path),
                    ]
                    self._run_ffmpeg(command)
                    duration_seconds = self._wav_duration_seconds(output_path)
                    cache.store(
                        output_path,
                        cache_path,
                        {
                            "cache_key": cache_key,
                            "source_path": str(source_path),
                            "duration_seconds": duration_seconds,
                            "normalization_skipped": False,
                        },
                    )
                cache_report.record(
                    artifact_type="normalized_audio",
                    cache_key=cache_key,
                    status="regenerated",
                    cache_path=cache_path,
                    job_path=output_path,
                    metadata=build_normalized_audio_cache_transfer_metadata(
                        cache.last_transfer,
                        duration_seconds=duration_seconds,
                        normalization_skipped=normalization_skipped,
                    ),
                )
                object.__setattr__(segment, "normalized_cache_hit", False)
            object.__setattr__(segment, "normalized_audio_path", str(output_path))
            object.__setattr__(segment, "normalized_cache_key", cache_key)
            object.__setattr__(segment, "normalized_duration_seconds", duration_seconds)
            normalized_paths.append(output_path)
            normalized_keys.append(cache_key)
        return normalized_paths, normalized_keys

    def _build_timed_segments_with_normalized_audio(self, segments: list[SpeechSegment], normalized_paths: list[Path]) -> list[dict]:
        validated_segments: list[SpeechSegment] = []
        validated_paths: list[Path] = []
        durations: list[float] = []
        for segment, normalized_path in zip(segments, normalized_paths, strict=False):
            if not normalized_path.exists():
                raise TTSProviderError(
                    code="missing_normalized_render_segment_audio",
                    message=f"Normalized render segment audio is missing before final assembly: {normalized_path}",
                    provider_state=segment.provider_state or {},
                    provider_failures=segment.provider_failures or {},
                    suggested_action="Regenerate the video and inspect normalized segment artifact storage.",
                )
            validated_segments.append(segment)
            validated_paths.append(normalized_path)
            durations.append(float(getattr(segment, "normalized_duration_seconds", 0.0) or 0.0))
        return build_timed_segments_from_durations(validated_segments, durations, validated_paths)

    def _build_composite_audio_track_cached(
        self,
        *,
        timed_segments: list[dict],
        normalized_keys: list[str],
        cache: RenderCache,
        cache_report: RenderCacheReport,
        audio_dir: Path,
        job_id: int | None,
        project_id: int,
    ) -> tuple[Path, str]:
        audio_dir.mkdir(parents=True, exist_ok=True)
        composite_audio_path = audio_dir / "dialogue_composite.wav"
        cache_key = composite_audio_cache_key(normalized_keys, timed_segments, self.audio_export_fps)
        cache_path = cache.path("composite_audio", cache_key, ".wav")
        elapsed = cache_report.timed()
        if cache.materialize(cache_path, composite_audio_path):
            cache_report.record(
                artifact_type="composite_audio",
                cache_key=cache_key,
                status="materialized_from_cache",
                cache_path=cache_path,
                job_path=composite_audio_path,
                duration_seconds=elapsed(),
                metadata=build_composite_audio_cache_transfer_metadata(cache.last_transfer),
            )
            return composite_audio_path, cache_key

        concat_list_path = audio_dir / "dialogue_segments.txt"
        audio_paths: list[Path] = []
        for item in timed_segments:
            audio_path = Path(item["normalized_audio_path"]).resolve()
            audio_paths.append(audio_path)
        concat_list_path.write_text(ffmpeg_concat_file_contents(audio_paths), encoding="utf-8")
        cache_report.record(
            artifact_type="composite_audio",
            cache_key=cache_key,
            status="miss",
            cache_path=cache_path,
            job_path=composite_audio_path,
            duration_seconds=elapsed(),
        )
        logger.info(
            "Building final dialogue composite audio job_id=%s project_id=%s segment_count=%s composite_audio_path=%s",
            job_id,
            project_id,
            len(timed_segments),
            composite_audio_path,
        )
        self._run_ffmpeg(
            concat_demuxer_audio_command(
                concat_list_path=concat_list_path,
                output_path=composite_audio_path,
                sample_rate=self.audio_export_fps,
            )
        )
        cache.store(composite_audio_path, cache_path, {"cache_key": cache_key, "segment_count": len(timed_segments)})
        cache_report.record(
            artifact_type="composite_audio",
            cache_key=cache_key,
            status="regenerated",
            cache_path=cache_path,
            job_path=composite_audio_path,
            metadata=build_composite_audio_cache_transfer_metadata(cache.last_transfer),
        )
        return composite_audio_path, cache_key

    def _normalize_background_layer(
        self,
        *,
        background_path: Path,
        background_hash: str,
        background_mime_type: str,
        style_preset: str,
        preset: RenderPreset,
        duration_seconds: float,
        cache: RenderCache,
        cache_report: RenderCacheReport,
        visual_dir: Path,
    ) -> tuple[Path, str]:
        cache_duration_seconds = self._background_cache_duration_seconds(duration_seconds, preset)
        cache_key = background_cache_key(
            background_hash=background_hash,
            background_mime_type=background_mime_type,
            style_preset=style_preset,
            preset=preset,
            cache_duration_seconds=cache_duration_seconds,
            requested_duration_seconds=duration_seconds,
        )
        cache_path = cache.path("backgrounds", cache_key, ".mp4")
        output_path = visual_dir / "background_normalized.mp4"
        elapsed = cache_report.timed()
        if cache.materialize(cache_path, output_path):
            cache_report.record(
                artifact_type="background",
                cache_key=cache_key,
                status="materialized_from_cache",
                cache_path=cache_path,
                job_path=output_path,
                duration_seconds=elapsed(),
                metadata=build_background_cache_transfer_metadata(
                    cache.last_transfer,
                    cache_duration_seconds=cache_duration_seconds,
                ),
            )
            return output_path, cache_key

        command = background_normalization_ffmpeg_command(
            background_path=background_path,
            output_path=output_path,
            style_preset=style_preset,
            preset=preset,
            duration_seconds=cache_duration_seconds,
            is_image_background=self._is_image_background(background_mime_type, background_path),
            ffmpeg_threads=self._ffmpeg_threads(),
        )
        cache_report.record(
            artifact_type="background",
            cache_key=cache_key,
            status="miss",
            cache_path=cache_path,
            job_path=output_path,
            metadata={
                "requested_duration_seconds": duration_seconds,
                "cache_duration_seconds": cache_duration_seconds,
                "duration_bucketed": cache_duration_seconds != duration_seconds,
            },
        )
        self._run_ffmpeg(command)
        cache.store(
            output_path,
            cache_path,
            {
                "cache_key": cache_key,
                "source_path": str(background_path),
                "requested_duration_seconds": duration_seconds,
                "cache_duration_seconds": cache_duration_seconds,
            },
        )
        cache_report.record(
            artifact_type="background",
            cache_key=cache_key,
            status="regenerated",
            cache_path=cache_path,
            job_path=output_path,
            metadata=build_background_cache_transfer_metadata(
                cache.last_transfer,
                cache_duration_seconds=cache_duration_seconds,
            ),
        )
        return output_path, cache_key

    def _background_cache_duration_seconds(self, duration_seconds: float, preset: RenderPreset) -> float:
        return background_cache_duration_seconds(duration_seconds, preset)

    def _scaled_box(self, box: tuple[int, int], preset: RenderPreset) -> tuple[int, int]:
        return scale_box(box, preset, canvas_width=self.CANVAS_WIDTH, canvas_height=self.CANVAS_HEIGHT)

    def _build_static_overlay_layer(
        self,
        *,
        portrait_paths: dict[str, Path],
        portrait_hashes: dict[str, str],
        speaker_slots: dict[str, int],
        render_layout: dict[str, Any],
        preset: RenderPreset,
        cache: RenderCache,
        cache_report: RenderCacheReport,
        visual_dir: Path,
    ) -> tuple[Path, str]:
        cast = static_overlay_cast(speaker_slots)
        cache_key = static_overlay_cache_key(cast, portrait_hashes, render_layout, preset)
        cache_path = cache.path("overlays", cache_key, ".png")
        output_path = visual_dir / "static_overlay.png"
        elapsed = cache_report.timed()
        if cache.materialize(cache_path, output_path):
            cache_report.record(
                artifact_type="static_overlay",
                cache_key=cache_key,
                status="materialized_from_cache",
                cache_path=cache_path,
                job_path=output_path,
                duration_seconds=elapsed(),
                metadata=build_overlay_cache_transfer_metadata(cache.last_transfer),
            )
            return output_path, cache_key
        image = Image.new("RGBA", (preset.width, preset.height), (0, 0, 0, 0))
        portrait_image_cache: dict[tuple[str, str, int], Image.Image] = {}
        for entry in static_overlay_portrait_entries(cast, render_layout, preset):
            speaker = str(entry["speaker"])
            slot_index = int(entry["slot_index"])
            portrait = self._resized_portrait_image(
                portrait_paths[speaker],
                speaker,
                slot_index,
                portrait_hashes.get(speaker, ""),
                int(entry["height"]),
                portrait_image_cache,
            )
            alpha = portrait.getchannel("A").point(lambda value: int(value * float(entry["alpha"])))
            portrait.putalpha(alpha)
            image.alpha_composite(portrait, entry["position"])
        image.save(output_path)
        cache.store(output_path, cache_path, {"cache_key": cache_key})
        cache_report.record(
            artifact_type="static_overlay",
            cache_key=cache_key,
            status="regenerated",
            cache_path=cache_path,
            job_path=output_path,
            metadata=build_overlay_cache_transfer_metadata(cache.last_transfer),
        )
        return output_path, cache_key

    def _build_dynamic_frame(
        self,
        *,
        segment: SpeechSegment,
        portrait_path: Path,
        portrait_hash: str,
        render_layout: dict[str, Any],
        preset: RenderPreset,
        cache: RenderCache,
        cache_report: RenderCacheReport,
        visual_dir: Path,
        portrait_image_cache: dict[tuple[str, str, int], Image.Image] | None = None,
    ) -> tuple[Path, str]:
        cache_key = dynamic_frame_cache_key(segment, portrait_hash, render_layout, preset)
        cache_path = cache.path("overlays", cache_key, ".png")
        output_path = visual_dir / f"frame_{cache_key[:16]}.png"
        if cache.materialize(cache_path, output_path):
            cache_report.record(
                artifact_type="dynamic_frame",
                cache_key=cache_key,
                status="materialized_from_cache",
                cache_path=cache_path,
                job_path=output_path,
                metadata=build_overlay_cache_transfer_metadata(cache.last_transfer),
            )
            return output_path, cache_key
        image = Image.new("RGBA", (preset.width, preset.height), (0, 0, 0, 0))
        composition = dynamic_frame_composition_payload(segment.slot_index, render_layout, preset)
        portrait_payload = composition["portrait"]
        portrait = self._resized_portrait_image(
            portrait_path,
            segment.speaker,
            segment.slot_index,
            portrait_hash,
            int(portrait_payload["height"]),
            portrait_image_cache,
        )
        image.alpha_composite(portrait, portrait_payload["position"])

        caption_payload = composition["caption"]
        caption = self._dialogue_card_image(segment, chat_font_size_px=int(caption_payload["font_size_px"]))
        caption = caption.resize(caption_payload["size"])
        image.alpha_composite(caption, caption_payload["position"])
        image.save(output_path)
        cache.store(output_path, cache_path, {"cache_key": cache_key})
        cache_report.record(
            artifact_type="dynamic_frame",
            cache_key=cache_key,
            status="regenerated",
            cache_path=cache_path,
            job_path=output_path,
            metadata=build_overlay_cache_transfer_metadata(cache.last_transfer),
        )
        return output_path, cache_key

    def _build_dynamic_overlay_layer(
        self,
        *,
        timed_segments: list[dict],
        portrait_paths: dict[str, Path],
        portrait_hashes: dict[str, str],
        render_layout: dict[str, Any],
        preset: RenderPreset,
        cache: RenderCache,
        cache_report: RenderCacheReport,
        visual_dir: Path,
    ) -> tuple[Path, str]:
        frame_entries = []
        portrait_image_cache: dict[tuple[str, str, int], Image.Image] = {}
        for item in timed_segments:
            segment: SpeechSegment = item["segment"]
            frame_path, frame_key = self._build_dynamic_frame(
                segment=segment,
                portrait_path=portrait_paths[segment.speaker],
                portrait_hash=portrait_hashes.get(segment.speaker, ""),
                render_layout=render_layout,
                preset=preset,
                cache=cache,
                cache_report=cache_report,
                visual_dir=visual_dir,
                portrait_image_cache=portrait_image_cache,
            )
            frame_entries.append({"path": frame_path, "key": frame_key, "duration_seconds": item["duration_seconds"]})
        cache_key = dynamic_overlay_cache_key(frame_entries, preset)
        cache_path = cache.path("overlays", cache_key, ".mov")
        output_path = visual_dir / "dynamic_overlay.mov"
        elapsed = cache_report.timed()
        if cache.materialize(cache_path, output_path):
            cache_report.record(
                artifact_type="dynamic_overlay",
                cache_key=cache_key,
                status="materialized_from_cache",
                cache_path=cache_path,
                job_path=output_path,
                duration_seconds=elapsed(),
                metadata=build_overlay_cache_transfer_metadata(cache.last_transfer),
            )
            return output_path, cache_key
        concat_list = visual_dir / "dynamic_frames.txt"
        concat_list.write_text(dynamic_overlay_concat_list_contents(frame_entries), encoding="utf-8")
        self._run_ffmpeg(
            dynamic_overlay_ffmpeg_command(
                concat_list_path=concat_list,
                output_path=output_path,
                preset=preset,
            )
        )
        cache.store(output_path, cache_path, {"cache_key": cache_key, "frame_count": len(frame_entries)})
        cache_report.record(
            artifact_type="dynamic_overlay",
            cache_key=cache_key,
            status="regenerated",
            cache_path=cache_path,
            job_path=output_path,
            metadata=build_overlay_cache_transfer_metadata(cache.last_transfer),
        )
        return output_path, cache_key

    def _build_final_video_ffmpeg(
        self,
        *,
        background_path: Path,
        static_overlay_path: Path,
        dynamic_overlay_path: Path,
        audio_path: Path,
        output_path: Path,
        preset: RenderPreset,
        duration_seconds: float,
    ) -> None:
        command = final_video_ffmpeg_command(
            background_path=background_path,
            static_overlay_path=static_overlay_path,
            dynamic_overlay_path=dynamic_overlay_path,
            audio_path=audio_path,
            output_path=output_path,
            preset=preset,
            duration_seconds=duration_seconds,
            audio_bitrate=self.audio_export_bitrate,
            ffmpeg_threads=self._ffmpeg_threads(),
        )
        self._run_ffmpeg(command)

    def _open_portrait_image(self, portrait_path: Path, speaker: str, slot_index: int) -> Image.Image:
        try:
            return Image.open(portrait_path).convert("RGBA")
        except Exception:
            logger.warning("Could not open portrait image %s; using generated fallback for %s", portrait_path, speaker)
            return Image.open(self._build_generated_portrait(speaker, slot_index, portrait_path.parent)).convert("RGBA")

    def _resized_portrait_image(
        self,
        portrait_path: Path,
        speaker: str,
        slot_index: int,
        portrait_hash: str,
        target_height: int,
        cache: dict[tuple[str, str, int], Image.Image] | None,
    ) -> Image.Image:
        cache_key = (str(portrait_path), portrait_hash, target_height)
        if cache is not None and cache_key in cache:
            return cache[cache_key].copy()
        portrait = self._open_portrait_image(portrait_path, speaker, slot_index)
        resized = portrait.resize(portrait_resize_dimensions(portrait.width, portrait.height, target_height))
        if cache is not None:
            cache[cache_key] = resized.copy()
        return resized

    def _dialogue_card_image(self, segment: SpeechSegment, *, chat_font_size_px: int = 18) -> Image.Image:
        palette = self._speaker_palette(segment.slot_index)
        layout = dialogue_card_layout_payload(
            speaker=segment.speaker,
            text=segment.caption_text or segment.text,
            chat_font_size_px=chat_font_size_px,
        )
        image = Image.new("RGBA", layout["size"], (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(layout["background"]["box"], radius=layout["background"]["radius"], fill=layout["background"]["fill"])
        draw.rounded_rectangle(layout["accent_bar"]["box"], radius=layout["accent_bar"]["radius"], fill=palette["accent"])
        label_font = self._load_font(layout["label"]["font_size"])
        body_font = self._load_font(layout["body"]["font_size"])
        draw.text(layout["label"]["position"], layout["label"]["text"], fill=palette["accent"], font=label_font)
        for line in layout["body"]["lines"]:
            draw.text(line["position"], line["text"], fill=layout["body"]["fill"], font=body_font)
        return image

    def _segment_artifact_metadata(
        self,
        *,
        index: int,
        item: dict,
        voice_manifest: dict | None,
        job_id: int | None,
        audio_path_used_for_final_assembly: str | None = None,
    ) -> dict:
        return build_segment_artifact_metadata(
            index=index,
            item=item,
            voice_manifest=voice_manifest,
            job_id=job_id,
            slugify=self._slugify,
            artifact_url_for_path=generated_job_artifact_url,
            audio_path_used_for_final_assembly=audio_path_used_for_final_assembly,
        )

    def _speech_output_dir(self, job_id: int | None, work_dir: Path) -> Path:
        return generated_job_segment_dir(job_id) if job_id is not None else work_dir / "speech"

    def _canvas_size(self, output_kind: str) -> tuple[int, int]:
        if output_kind == "preview":
            return settings.RENDER_PREVIEW_WIDTH, settings.RENDER_PREVIEW_HEIGHT
        return settings.RENDER_EXPORT_WIDTH, settings.RENDER_EXPORT_HEIGHT

    def _fit_to_canvas(self, clip, output_kind: str = "preview"):
        canvas_width, canvas_height = self._canvas_size(output_kind)
        scale = max(canvas_width / clip.w, canvas_height / clip.h)
        resized = clip.resized(new_size=(math.ceil(clip.w * scale), math.ceil(clip.h * scale)))
        return resized.cropped(
            x_center=int(resized.w / 2),
            y_center=int(resized.h / 2),
            width=canvas_width,
            height=canvas_height,
        )

    def _extend_background(self, clip, duration_seconds: float):
        from moviepy import ImageClip, concatenate_videoclips

        if not getattr(clip, "duration", None) or clip.duration >= duration_seconds:
            return clip.subclipped(0, duration_seconds)

        frozen_frame = clip.get_frame(max(clip.duration - 0.05, 0))
        remaining = duration_seconds - clip.duration
        still = ImageClip(frozen_frame).with_duration(remaining)
        return concatenate_videoclips([clip, still])

    def _build_timed_segments(self, segments: list[SpeechSegment]) -> list[dict]:
        durations: list[float] = []
        for segment in segments:
            audio_path = Path(segment.audio_path)
            if not audio_path.exists():
                raise TTSProviderError(
                    code="missing_render_segment_audio",
                    message=f"Render segment audio is missing before final assembly: {audio_path}",
                    provider_state=segment.provider_state or {},
                    provider_failures=segment.provider_failures or {},
                    suggested_action="Regenerate the video and inspect render segment artifact storage.",
                )
            durations.append(self._wav_duration_seconds(audio_path))
        return build_timed_segments_from_durations(segments, durations)

    def _wav_duration_seconds(self, audio_path: Path) -> float:
        return wav_duration_seconds(audio_path)

    def _wav_matches_render_format(self, audio_path: Path) -> bool:
        try:
            with wave.open(str(audio_path), "rb") as handle:
                return (
                    handle.getframerate() == self.audio_export_fps
                    and handle.getnchannels() == 2
                    and handle.getsampwidth() == 2
                    and handle.getcomptype() == "NONE"
                )
        except Exception:
            return False

    def _build_composite_audio_track(
        self,
        *,
        timed_segments: list[dict],
        job_id: int | None,
        project_id: int,
        work_dir: Path,
    ) -> Path:
        audio_dir = generated_job_artifact_dir(job_id) / "audio" if job_id is not None else work_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        composite_audio_path = audio_dir / "dialogue_composite.wav"
        concat_list_path = audio_dir / "dialogue_segments.txt"
        # Build the MP4 audio from persisted segment WAVs, never from a hidden temp copy.
        audio_paths: list[Path] = []
        for item in timed_segments:
            segment: SpeechSegment = item["segment"]
            audio_path = Path(segment.audio_path).resolve()
            if not audio_path.exists():
                raise TTSProviderError(
                    code="missing_render_segment_audio",
                    message=f"Render segment audio is missing before final audio assembly: {audio_path}",
                    provider_state=segment.provider_state or {},
                    provider_failures=segment.provider_failures or {},
                    suggested_action="Regenerate the video and inspect render segment artifact storage.",
                )
            audio_paths.append(audio_path)
        concat_list_path.write_text(ffmpeg_concat_file_contents(audio_paths), encoding="utf-8")
        command = multi_input_audio_command(
            audio_paths=audio_paths,
            output_path=composite_audio_path,
            sample_rate=self.audio_export_fps,
        )
        logger.info(
            "Building final dialogue composite audio job_id=%s project_id=%s segment_count=%s composite_audio_path=%s",
            job_id,
            project_id,
            len(timed_segments),
            composite_audio_path,
        )
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise TTSProviderError(
                code="ffmpeg_missing",
                message="ffmpeg is required to build the final dialogue composite audio track.",
                suggested_action="Install ffmpeg in the runtime image before rendering video.",
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise TTSProviderError(
                code="composite_audio_failed",
                message=f"Failed to build final dialogue composite audio: {exc.stderr or exc}",
                suggested_action="Inspect render segment WAV files and ffmpeg logs.",
            ) from exc
        if not composite_audio_path.exists():
            raise TTSProviderError(
                code="missing_composite_audio",
                message=f"Final dialogue composite audio was not created: {composite_audio_path}",
                suggested_action="Inspect ffmpeg logs and generated job artifact storage.",
            )
        return composite_audio_path

    def _log_final_assembly_inputs(
        self,
        *,
        job_id: int | None,
        project_id: int,
        timed_segments: list[dict],
        composite_audio_path: Path,
        final_mp4_path: Path,
    ) -> None:
        for index, item in enumerate(timed_segments):
            segment: SpeechSegment = item["segment"]
            audio_path = Path(segment.audio_path)
            logger.info(
                "Final assembly segment job_id=%s project_id=%s segment_index=%s speaker=%s provider_used=%s fallback_used=%s segment_wav_path=%s segment_wav_exists=%s composite_audio_path=%s final_mp4_path=%s",
                job_id,
                project_id,
                index,
                segment.speaker,
                segment.provider_used,
                segment.fallback_used,
                audio_path,
                audio_path.exists(),
                composite_audio_path,
                final_mp4_path,
            )
        logger.info(
            "Final assembly inputs job_id=%s project_id=%s composite_audio_path=%s composite_audio_exists=%s final_mp4_path=%s",
            job_id,
            project_id,
            composite_audio_path,
            composite_audio_path.exists(),
            final_mp4_path,
        )

    def _assembly_metadata(
        self,
        *,
        job_id: int | None,
        project_id: int,
        timed_segments: list[dict],
        segment_metadata: list[dict],
        composite_audio_path: Path,
        final_mp4_path: Path,
        final_video_audio_path: Path | None = None,
    ) -> dict:
        return build_assembly_metadata(
            job_id=job_id,
            project_id=project_id,
            timed_segments=timed_segments,
            segment_metadata=segment_metadata,
            composite_audio_path=composite_audio_path,
            final_mp4_path=final_mp4_path,
            artifact_url_for_path=generated_job_artifact_url,
            final_video_audio_path=final_video_audio_path,
        )

    def _extract_final_video_audio(self, *, final_mp4_path: Path, job_id: int | None, work_dir: Path) -> Path | None:
        audio_dir = generated_job_artifact_dir(job_id) / "audio" if job_id is not None else work_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        output_path = audio_dir / "final_video_audio.wav"
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(final_mp4_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            str(self.audio_export_fps),
            "-ac",
            "2",
            str(output_path),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            logger.warning(
                "Could not extract final MP4 audio for comparison final_mp4_path=%s error=%s",
                final_mp4_path,
                exc,
            )
            return None
        return output_path if output_path.exists() else None

    def _render_config(self, background_clip, output_kind: str) -> dict[str, int | str]:
        source_fps = float(getattr(background_clip, "fps", 24) or 24)
        # Preview and export knobs are separate so faster previews do not redefine final-render quality.
        fps_cap = settings.RENDER_PREVIEW_FPS_CAP if output_kind == "preview" else settings.RENDER_EXPORT_FPS_CAP
        target_fps = max(1, min(int(round(source_fps)), max(1, fps_cap)))
        canvas_width, canvas_height = self._canvas_size(output_kind)
        thread_cap = max(1, settings.RENDER_FFMPEG_THREAD_CAP)
        return {
            "fps": target_fps,
            "width": canvas_width,
            "height": canvas_height,
            "preset": settings.RENDER_PREVIEW_ENCODE_PRESET if output_kind == "preview" else settings.RENDER_EXPORT_ENCODE_PRESET,
            "crf": settings.RENDER_PREVIEW_CRF if output_kind == "preview" else settings.RENDER_EXPORT_CRF,
            "threads": max(1, min(os.cpu_count() or 4, thread_cap)),
        }

    def _render_layout(self, render_settings: dict | None) -> dict[str, float | int]:
        return normalize_render_layout(render_settings)

    def _emit_progress(self, progress_callback, stage: str, progress: int) -> None:
        if callable(progress_callback):
            progress_callback(stage, progress)

    def _primary_cast(self, segments: list[SpeechSegment]) -> list[SpeechSegment]:
        return primary_cast_segments(segments)

    def _resolve_character_portrait(self, speaker: str, slot_index: int, work_dir: Path) -> Path:
        slug = self._slugify(speaker)
        preset = resolve_character_preset_for_speaker(speaker, self.db) if self.db is not None else resolve_character_preset_for_speaker(speaker)
        preset_portrait = resolve_character_portrait_path(preset)
        if preset_portrait:
            logger.info(
                "Resolved portrait for speaker=%s slot=%s from preset=%s path=%s",
                speaker,
                slot_index + 1,
                preset["id"],
                preset_portrait,
            )
            return preset_portrait
        bundled_character_dir = Path(settings.BUNDLED_MEDIA_DIR) / "characters"
        runtime_character_dir = Path(settings.MEDIA_DIR) / "characters"
        runtime_character_dir.mkdir(parents=True, exist_ok=True)

        lookup_groups = [
            (
                "bundled",
                [
                    bundled_character_dir / f"{slug}.png",
                    bundled_character_dir / f"speaker_{slot_index + 1}.png",
                ],
            ),
            (
                "runtime",
                [
                    runtime_character_dir / f"{slug}.png",
                    runtime_character_dir / f"{slug}_{slot_index + 1}.png",
                    runtime_character_dir / f"speaker_{slot_index + 1}.png",
                ],
            ),
        ]

        for source, candidates in lookup_groups:
            for candidate in candidates:
                if candidate.exists():
                    logger.info(
                        "Resolved portrait for speaker=%s slot=%s from %s path=%s",
                        speaker,
                        slot_index + 1,
                        source,
                        candidate,
                    )
                    return candidate

        logger.info(
            "No portrait asset found for speaker=%s slot=%s in bundled=%s or runtime=%s; generating fallback portrait",
            speaker,
            slot_index + 1,
            bundled_character_dir,
            runtime_character_dir,
        )
        return self._build_generated_portrait(speaker, slot_index, work_dir)

    def _build_generated_portrait(self, speaker: str, slot_index: int, work_dir: Path) -> Path:
        portrait_path = work_dir / f"portrait_{slot_index}_{self._slugify(speaker)}.png"
        layout = generated_portrait_layout_payload(speaker, slot_index)
        image = Image.new("RGBA", layout["size"], (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        draw.ellipse(layout["head"]["box"], fill=layout["head"]["fill"])
        draw.rounded_rectangle(layout["body"]["box"], radius=layout["body"]["radius"], fill=layout["body"]["fill"])
        draw.rounded_rectangle(layout["plate"]["box"], radius=layout["plate"]["radius"], fill=layout["plate"]["fill"])

        name_font = self._load_font(layout["name"]["font_size"])
        initials_font = self._load_font(layout["initials"]["font_size"])
        draw.text(
            layout["initials"]["position"],
            layout["initials"]["text"],
            anchor=layout["initials"]["anchor"],
            fill=layout["initials"]["fill"],
            font=initials_font,
        )
        draw.rounded_rectangle(
            layout["name_plate"]["box"],
            radius=layout["name_plate"]["radius"],
            fill=layout["name_plate"]["fill"],
        )
        draw.text(
            layout["name"]["position"],
            layout["name"]["text"],
            anchor=layout["name"]["anchor"],
            fill=layout["name"]["fill"],
            font=name_font,
        )

        image.save(portrait_path)
        return portrait_path

    def _build_dialogue_card(self, segment: SpeechSegment, work_dir: Path, *, chat_font_size_px: int = 18) -> Path:
        palette = self._speaker_palette(segment.slot_index)
        caption_path = work_dir / f"caption_{uuid.uuid4().hex}.png"
        layout = dialogue_card_layout_payload(
            speaker=segment.speaker,
            text=segment.text,
            chat_font_size_px=chat_font_size_px,
        )
        image = Image.new("RGBA", layout["size"], (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(layout["background"]["box"], radius=layout["background"]["radius"], fill=layout["background"]["fill"])
        draw.rounded_rectangle(layout["accent_bar"]["box"], radius=layout["accent_bar"]["radius"], fill=palette["accent"])

        label_font = self._load_font(layout["label"]["font_size"])
        body_font = self._load_font(layout["body"]["font_size"])
        draw.text(layout["label"]["position"], layout["label"]["text"], fill=palette["accent"], font=label_font)

        for line in layout["body"]["lines"]:
            draw.text(line["position"], line["text"], fill=layout["body"]["fill"], font=body_font)

        image.save(caption_path)
        return caption_path

    def _speaker_palette(self, slot_index: int) -> dict[str, tuple[int, int, int, int]]:
        return render_speaker_palette(slot_index)

    def _slugify(self, value: str) -> str:
        slug = "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")
        return slug or "speaker"

    @lru_cache(maxsize=24)
    def _load_font(self, size: int):
        try:
            return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
        except Exception:
            return ImageFont.load_default()

    def _make_script_overlay(self, parsed_lines: list[dict], style_preset: str) -> str:
        overlay_dir = Path("./generated_videos") / "overlays"
        overlay_dir.mkdir(parents=True, exist_ok=True)

        image = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        box_color = {
            "none": (20, 20, 20, 170),
            "blur": (30, 30, 30, 210),
            "grayscale": (80, 80, 80, 210),
        }.get(style_preset, (20, 20, 20, 170))
        draw.rounded_rectangle((80, 1260, 1000, 1780), radius=36, fill=box_color)

        font = ImageFont.load_default()
        y = 1320
        preview_lines = parsed_lines[:4]
        for line in preview_lines:
            speaker = f"{line['speaker']}:"
            dialogue = line["text"]
            for chunk in textwrap.wrap(f"{speaker} {dialogue}", width=30):
                draw.text((120, y), chunk, fill=(255, 255, 255, 255), font=font)
                y += 56
            y += 24

        overlay_path = overlay_dir / f"{uuid.uuid4().hex}.png"
        image.save(overlay_path)
        return str(overlay_path)
