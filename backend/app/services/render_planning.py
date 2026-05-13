from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.render_cache import RENDER_CACHE_SCHEMA_VERSION, stable_hash


@dataclass(frozen=True)
class RenderPreset:
    mode: str
    width: int
    height: int
    fps: int
    x264_preset: str
    crf: int
    debug_audio_extract: bool = False


@dataclass
class RenderPlan:
    job_id: int | None
    project_id: int
    output_kind: str
    preset: RenderPreset
    parsed_lines: list[dict[str, Any]]
    voice_profiles: dict[str, dict[str, Any]]
    background_source_path: str
    background_hash: str
    background_mime_type: str
    style_preset: str
    speaker_pngs: dict[str, str]
    speaker_png_hashes: dict[str, str]
    layout: dict[str, Any]
    caption_settings: dict[str, Any]
    expected_artifacts: dict[str, str]
    cache_keys: dict[str, Any] = field(default_factory=dict)
    segments: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": RENDER_CACHE_SCHEMA_VERSION,
            "job_id": self.job_id,
            "project_id": self.project_id,
            "output_kind": self.output_kind,
            "preset": self.preset.__dict__,
            "parsed_lines": self.parsed_lines,
            "selected_voice_profiles": self.voice_profiles,
            "background_source_path": self.background_source_path,
            "background_hash": self.background_hash,
            "background_mime_type": self.background_mime_type,
            "style_preset": self.style_preset,
            "speaker_pngs": self.speaker_pngs,
            "speaker_png_hashes": self.speaker_png_hashes,
            "layout": self.layout,
            "caption_settings": self.caption_settings,
            "expected_artifact_paths": self.expected_artifacts,
            "cache_keys": self.cache_keys,
            "segments": self.segments,
        }

    def plan_key(self) -> str:
        payload = self.to_dict()
        payload.pop("expected_artifact_paths", None)
        return stable_hash(payload)


def write_render_plan(plan: RenderPlan, destination: Path) -> None:
    import json

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(plan.to_dict(), indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
