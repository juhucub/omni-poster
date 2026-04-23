from __future__ import annotations

import logging
import math
import os
import shutil
import tempfile
import textwrap
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.core.config import settings
from app.services.character_presets import resolve_character_portrait_path, resolve_character_preset_for_speaker
from app.services.tts import LocalSpeechService, SpeechSegment
from app.services.vid_gen import VideoGenerationService

logger = logging.getLogger(__name__)


class ProjectRenderService:
    CANVAS_WIDTH = 1080
    CANVAS_HEIGHT = 1920
    BASE_POSITIONS = ((56, 1080), (584, 1080))
    ACTIVE_POSITIONS = ((4, 930), (472, 930))
    BASE_HEIGHT = 620
    ACTIVE_HEIGHT = 780

    def __init__(self) -> None:
        self.video_service = VideoGenerationService(output_dir="./generated_videos")
        self.speech_service = LocalSpeechService()
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
    ) -> dict:
        try:
            return self._render_speaker_video(
                project_id=project_id,
                background_video_path=background_video_path,
                parsed_lines=parsed_lines,
                style_preset=style_preset,
                output_kind=output_kind,
                progress_callback=progress_callback,
            )
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
    ) -> dict:
        from moviepy import (
            CompositeVideoClip,
            ImageClip,
            VideoFileClip,
            concatenate_audioclips,
        )

        clean_video_path = self.video_service._clean_file_path(background_video_path)
        if not Path(clean_video_path).exists():
            raise RuntimeError(f"Background video not found: {clean_video_path}")

        work_dir = Path(tempfile.mkdtemp(prefix=f"render_{project_id}_", dir=self.output_dir))
        clips_to_close: list = []
        audio_clips: list = []
        try:
            segments = self.speech_service.synthesize_dialogue(parsed_lines, work_dir / "speech")
            self._emit_progress(progress_callback, "tts_ready", 46)

            background_clip = VideoFileClip(clean_video_path).without_audio()
            background_clip = self.video_service._apply_background_style(background_clip, style_preset)
            background_clip = self._fit_to_canvas(background_clip)
            self._emit_progress(progress_callback, "background_ready", 58)

            timed_segments = self._build_timed_segments(segments)
            audio_clips.extend(item["audio_clip"] for item in timed_segments)

            total_duration = sum(item["duration_seconds"] for item in timed_segments)
            if total_duration <= 0:
                raise RuntimeError("Generated speech audio has no duration.")

            background_clip = self._extend_background(background_clip, total_duration)
            clips_to_close.append(background_clip)

            cast = self._primary_cast(segments)
            timeline_layers = [background_clip]

            for cast_member in cast:
                portrait_path = self._resolve_character_portrait(cast_member.speaker, cast_member.slot_index, work_dir)
                base_clip = (
                    ImageClip(str(portrait_path))
                    .resized(height=self.BASE_HEIGHT)
                    .with_opacity(0.26)
                    .with_position(self.BASE_POSITIONS[min(cast_member.slot_index, 1)])
                    .with_duration(total_duration)
                )
                timeline_layers.append(base_clip)
                clips_to_close.append(base_clip)

            cursor = 0.0
            for item in timed_segments:
                segment = item["segment"]
                portrait_path = self._resolve_character_portrait(segment.speaker, segment.slot_index, work_dir)
                speaker_slot = min(segment.slot_index, 1)
                active_clip = (
                    ImageClip(str(portrait_path))
                    .resized(height=self.ACTIVE_HEIGHT)
                    .with_position(self.ACTIVE_POSITIONS[speaker_slot])
                    .with_start(cursor)
                    .with_duration(item["duration_seconds"])
                )
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

            composite_audio = concatenate_audioclips(audio_clips)
            composite = (
                CompositeVideoClip(
                    timeline_layers,
                    size=(self.CANVAS_WIDTH, self.CANVAS_HEIGHT),
                )
                .with_audio(composite_audio)
                .with_duration(total_duration)
            )
            clips_to_close.append(composite)
            clips_to_close.append(composite_audio)

            render_config = self._render_config(background_clip, output_kind)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{project_id}_{output_kind}_{timestamp}.mp4"
            output_path = self.output_dir / output_filename
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
                    "voices": {segment.speaker: segment.voice for segment in segments},
                    "line_timing_seconds": [
                        {
                            "speaker": item["segment"].speaker,
                            "text": item["segment"].text,
                            "duration_seconds": item["duration_seconds"],
                        }
                        for item in timed_segments
                    ],
                    "render_fps": render_config["fps"],
                    "encode_preset": render_config["preset"],
                    "portrait_resolution": "backend/storage/characters/<speaker>.png or speaker_<slot>.png",
                },
            }
        finally:
            for clip in reversed(clips_to_close):
                close = getattr(clip, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        logger.debug("Failed to close clip cleanly", exc_info=True)
            shutil.rmtree(work_dir, ignore_errors=True)

    def _fit_to_canvas(self, clip):
        scale = max(self.CANVAS_WIDTH / clip.w, self.CANVAS_HEIGHT / clip.h)
        resized = clip.resized(new_size=(math.ceil(clip.w * scale), math.ceil(clip.h * scale)))
        return resized.cropped(
            x_center=int(resized.w / 2),
            y_center=int(resized.h / 2),
            width=self.CANVAS_WIDTH,
            height=self.CANVAS_HEIGHT,
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
            audio_clip = self.speech_service.build_audio_clip(segment.audio_path)
            timed_segments.append(
                {
                    "segment": segment,
                    "audio_clip": audio_clip,
                    "duration_seconds": max(float(getattr(audio_clip, "duration", 0) or 0), segment.duration_seconds, 0.6),
                }
            )
        return timed_segments

    def _render_config(self, background_clip, output_kind: str) -> dict[str, int | str]:
        source_fps = float(getattr(background_clip, "fps", 24) or 24)
        fps_cap = 24 if output_kind == "preview" else 30
        target_fps = max(24, min(int(round(source_fps)), fps_cap))
        return {
            "fps": target_fps,
            "preset": "veryfast" if output_kind == "preview" else "faster",
            "crf": 24 if output_kind == "preview" else 22,
            "threads": max(2, min(os.cpu_count() or 4, 8)),
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
        preset = resolve_character_preset_for_speaker(speaker)
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

    def _build_dialogue_card(self, segment: SpeechSegment, work_dir: Path) -> Path:
        palette = self._speaker_palette(segment.slot_index)
        caption_path = work_dir / f"caption_{uuid.uuid4().hex}.png"
        image = Image.new("RGBA", (900, 380), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, 900, 380), radius=48, fill=(6, 10, 18, 228))
        draw.rounded_rectangle((0, 0, 900, 22), radius=22, fill=palette["accent"])

        label_font = self._load_font(40)
        body_font = self._load_font(56)
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
