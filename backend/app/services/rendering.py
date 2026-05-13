from __future__ import annotations

import logging
import math
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import uuid
import wave
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.core.config import settings
from app.services.character_presets import resolve_character_portrait_path, resolve_character_preset_for_speaker
from app.services.render_profiling import RenderProfiler
from app.services.storage import generated_job_artifact_dir, generated_job_artifact_url, generated_job_segment_dir
from app.services.tts import LocalSpeechService, SpeechSegment, TTSProviderError
from app.services.vid_gen import VideoGenerationService

logger = logging.getLogger(__name__)


class ProjectRenderService:
    CANVAS_WIDTH = 1080
    CANVAS_HEIGHT = 1920
    BASE_POSITIONS = ((56, 1080), (584, 1080))
    ACTIVE_POSITIONS = ((4, 930), (472, 930))
    BASE_HEIGHT = 620
    ACTIVE_HEIGHT = 780

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
    ) -> dict:
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
            base_height = int(round(self.BASE_HEIGHT * character_scale))
            active_height = int(round(self.ACTIVE_HEIGHT * character_scale))
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
            self._emit_progress(progress_callback, "tts_ready", 46)

            with profiler.stage("moviepy.background_load", background_video_path=clean_video_path):
                background_clip = VideoFileClip(clean_video_path).without_audio()
            with profiler.stage("moviepy.background_style", style_preset=style_preset):
                background_clip = self.video_service._apply_background_style(background_clip, style_preset)
            with profiler.stage("moviepy.background_fit", output_kind=output_kind):
                background_clip = self._fit_to_canvas(background_clip, output_kind)
            self._emit_progress(progress_callback, "background_ready", 58)

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

            self._emit_progress(progress_callback, "timeline_ready", 68)

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
            self._emit_progress(progress_callback, "encoding", 80)
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
            self._emit_progress(progress_callback, "encoded", 88)
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
            tts_result = {
                "status": "completed",
                "provider_state": (segments[-1].provider_state or {}) if segments else {},
                "segments": segment_metadata,
                "assembly": assembly_metadata,
                "render_settings": {"layout": render_layout},
            }
            selected_profiles = {
                segment.speaker: {
                    "provider_used": segment.provider_used,
                    "voice_profile_id": segment.voice_profile_id,
                    "voice": segment.voice,
                    "fallback_used": segment.fallback_used,
                }
                for segment in segments
            }
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
            render_profile_metadata = {
                "artifact_url": profile_artifact_url,
                "summary": profile_summary,
                "profile_path": str(generated_job_artifact_dir(job_id) / "generation_profile.json") if profile_artifact_url else None,
            }
            tts_result["render_profile"] = render_profile_metadata

            return {
                "output_path": f"file://{output_path.absolute()}",
                "filename": output_filename,
                "size_bytes": output_path.stat().st_size,
                "duration_seconds": total_duration,
                "status": "completed",
                "created_at": datetime.now().isoformat(),
                "processing_time_seconds": None,
                "metadata": {
                    "render_mode": "speaker_dialogue",
                    "voices": {
                        segment.speaker: {
                            "voice": segment.voice,
                            "provider_used": segment.provider_used,
                            "voice_profile_id": segment.voice_profile_id,
                            "fallback_used": segment.fallback_used,
                            "reference_audio_count": segment.reference_audio_count,
                        }
                        for segment in segments
                    },
                    "tts_result": tts_result,
                    "render_settings": {"layout": render_layout},
                    "preview_layout": render_layout,
                    "render_profile": render_profile_metadata,
                    "render_profile_artifact_url": profile_artifact_url,
                    "render_assembly": assembly_metadata,
                    "line_timing_seconds": [
                        {
                            "speaker": item["segment"].speaker,
                            "text": item["segment"].text,
                            "duration_seconds": item["duration_seconds"],
                            "audio_path": item["segment"].audio_path,
                            "audio_path_used_for_final_assembly": item["segment"].audio_path,
                            "artifact_url": segment_metadata[index].get("artifact_url"),
                            "provider_used": item["segment"].provider_used,
                            "voice_profile_id": item["segment"].voice_profile_id,
                            "fallback_used": item["segment"].fallback_used,
                        }
                        for index, item in enumerate(timed_segments)
                    ],
                    "render_fps": render_config["fps"],
                    "render_resolution": {"width": canvas_width, "height": canvas_height},
                    "character_scale": character_scale,
                    "chat_font_size_px": chat_font_size_px,
                    "ffmpeg_threads": render_config["threads"],
                    "encode_preset": render_config["preset"],
                    "portrait_resolution": "backend/storage/characters/<speaker>.png or speaker_<slot>.png",
                },
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

    def _segment_artifact_metadata(
        self,
        *,
        index: int,
        item: dict,
        voice_manifest: dict | None,
        job_id: int | None,
        audio_path_used_for_final_assembly: str | None = None,
    ) -> dict:
        segment: SpeechSegment = item["segment"]
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
        payload = {
            "segment_index": index,
            "segment_id": f"{index:03d}_{self._slugify(segment.speaker)}",
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
            "artifact_url": generated_job_artifact_url(job_id, audio_path) if job_id is not None else None,
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
        return payload

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
        timed_segments: list[dict] = []
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
            file_duration = self._wav_duration_seconds(audio_path)
            timed_segments.append(
                {
                    "segment": segment,
                    "duration_seconds": max(file_duration, segment.duration_seconds, 0.6),
                }
            )
        return timed_segments

    def _wav_duration_seconds(self, audio_path: Path) -> float:
        with wave.open(str(audio_path), "rb") as handle:
            frame_rate = handle.getframerate()
            frame_count = handle.getnframes()
        if frame_rate <= 0:
            return 0.0
        return float(frame_count) / float(frame_rate)

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
        concat_lines: list[str] = []
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
            escaped_audio_path = str(audio_path).replace("'", "'\\''")
            concat_lines.append(f"file '{escaped_audio_path}'")
            audio_paths.append(audio_path)
        concat_list_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
        command = ["ffmpeg", "-y"]
        for audio_path in audio_paths:
            command.extend(["-i", str(audio_path)])
        if len(audio_paths) == 1:
            filter_complex = f"[0:a]aresample={self.audio_export_fps}[a]"
        else:
            filter_complex = (
                "".join(f"[{index}:a]" for index in range(len(audio_paths)))
                + f"concat=n={len(audio_paths)}:v=0:a=1,aresample={self.audio_export_fps}[a]"
            )
        command.extend(
            [
                "-filter_complex",
                filter_complex,
                "-map",
                "[a]",
                "-acodec",
                "pcm_s16le",
                "-ar",
                str(self.audio_export_fps),
                "-ac",
                "2",
                str(composite_audio_path),
            ]
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
        return {
            "job_id": job_id,
            "project_id": project_id,
            "composite_audio_path": str(composite_audio_path),
            "composite_audio_artifact_url": (
                generated_job_artifact_url(job_id, composite_audio_path) if job_id is not None else None
            ),
            "final_mp4_path": str(final_mp4_path),
            "final_video_audio_path": str(final_video_audio_path) if final_video_audio_path else None,
            "final_video_audio_artifact_url": (
                generated_job_artifact_url(job_id, final_video_audio_path)
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
                    "audio_path_used_for_final_assembly": item["segment"].audio_path,
                    "segment_wav_exists": Path(item["segment"].audio_path).exists(),
                }
                for metadata, item in zip(segment_metadata, timed_segments, strict=False)
            ],
        }

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
        payload = dict(render_settings or {})
        layout = dict(payload.get("layout") or payload)
        try:
            character_scale = float(layout.get("character_scale", 1.0))
        except (TypeError, ValueError):
            character_scale = 1.0
        try:
            chat_font_size_px = int(layout.get("chat_font_size_px", 18))
        except (TypeError, ValueError):
            chat_font_size_px = 18
        return {
            "character_scale": min(max(character_scale, 0.75), 1.5),
            "chat_font_size_px": min(max(chat_font_size_px, 12), 32),
        }

    def _emit_progress(self, progress_callback, stage: str, progress: int) -> None:
        if callable(progress_callback):
            progress_callback(stage, progress)

    def _primary_cast(self, segments: list[SpeechSegment]) -> list[SpeechSegment]:
        cast: list[SpeechSegment] = []
        seen: set[str] = set()
        for segment in segments:
            if segment.speaker in seen:
                continue
            cast.append(segment)
            seen.add(segment.speaker)
            if len(cast) == 2:
                break
        return cast

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
        palette = self._speaker_palette(slot_index)
        portrait_path = work_dir / f"portrait_{slot_index}_{self._slugify(speaker)}.png"
        image = Image.new("RGBA", (760, 1100), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        draw.ellipse((180, 60, 580, 460), fill=palette["accent"])
        draw.rounded_rectangle((140, 420, 620, 1060), radius=180, fill=palette["body"])
        draw.rounded_rectangle((120, 780, 640, 1060), radius=140, fill=palette["plate"])

        initials = "".join(part[0] for part in speaker.split()[:2]).upper() or "S"
        name_font = self._load_font(54)
        initials_font = self._load_font(176)
        draw.text((380, 250), initials, anchor="mm", fill=(255, 255, 255, 255), font=initials_font)
        draw.rounded_rectangle((80, 880, 680, 1030), radius=50, fill=(10, 14, 20, 230))
        draw.text((380, 956), speaker, anchor="mm", fill=(243, 248, 255, 255), font=name_font)

        image.save(portrait_path)
        return portrait_path

    def _build_dialogue_card(self, segment: SpeechSegment, work_dir: Path, *, chat_font_size_px: int = 18) -> Path:
        palette = self._speaker_palette(segment.slot_index)
        caption_path = work_dir / f"caption_{uuid.uuid4().hex}.png"
        image = Image.new("RGBA", (900, 380), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, 900, 380), radius=48, fill=(6, 10, 18, 228))
        draw.rounded_rectangle((0, 0, 900, 22), radius=22, fill=palette["accent"])

        label_font = self._load_font(max(24, int(chat_font_size_px * 1.45)))
        body_font = self._load_font(max(28, int(chat_font_size_px * 2)))
        draw.text((70, 74), segment.speaker.upper(), fill=palette["accent"], font=label_font)

        wrapped_lines = textwrap.wrap(segment.text, width=24)[:4]
        y = 138
        for line in wrapped_lines:
            draw.text((70, y), line, fill=(245, 248, 255, 255), font=body_font)
            y += 64

        image.save(caption_path)
        return caption_path

    def _speaker_palette(self, slot_index: int) -> dict[str, tuple[int, int, int, int]]:
        palettes = (
            {
                "accent": (105, 224, 255, 255),
                "body": (19, 84, 122, 238),
                "plate": (35, 155, 208, 228),
            },
            {
                "accent": (255, 196, 87, 255),
                "body": (134, 76, 16, 238),
                "plate": (214, 120, 36, 228),
            },
        )
        return palettes[slot_index % len(palettes)]

    def _slugify(self, value: str) -> str:
        slug = "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")
        return slug or "speaker"

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
