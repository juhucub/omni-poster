from __future__ import annotations

import hashlib
import re
from typing import Any

from app.schemas import GeneratedScript, ScriptLine, ScriptSpeaker, ScriptVisualCue
from app.services.script_generation.captions import CaptionBlockBuilder
from app.services.script_generation.formats import ScriptFormatTemplate
from app.services.script_generation.platforms import PlatformPacingRules

CANONICAL_SECTIONS = ("hook", "body", "payoff", "cta")
STAGE_DIRECTION_RE = re.compile(r"\s*(\[[^\]]+\]|\([^)]{1,120}\)|\*[^*]{1,120}\*)\s*")


def stable_slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or fallback


def stable_script_id(idea: str, content_format_id: str, platform: str) -> str:
    digest = hashlib.sha1(f"{content_format_id}|{platform}|{idea}".encode("utf-8")).hexdigest()[:12]
    return f"script_{digest}"


def clean_spoken_text(text: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    cleaned = STAGE_DIRECTION_RE.sub(" ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned != (text or "").strip():
        warnings.append("Removed stage directions from spoken text.")
    return cleaned, warnings


def estimate_duration_seconds(text: str, platform_rules: PlatformPacingRules) -> float:
    words = max(len(text.split()), 1)
    return round(max(words / platform_rules.estimated_words_per_minute * 60, 0.7), 2)


def _section(value: Any, index: int, total: int) -> str:
    raw = str(value or "").strip().lower()
    if raw in CANONICAL_SECTIONS:
        return raw
    if index == 0:
        return "hook"
    if index >= total - 2:
        return "payoff" if index == total - 2 else "cta"
    return "body"


def _split_line_text(text: str, max_words: int) -> list[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text]
    chunks = []
    for index in range(0, len(words), max_words):
        chunks.append(" ".join(words[index : index + max_words]))
    return chunks


class ScriptNormalizer:
    def normalize(
        self,
        payload: dict[str, Any] | GeneratedScript,
        *,
        idea: str,
        content_format_id: str,
        platform: str,
        target_duration_sec: int,
        tone: str | None,
        audience: str | None,
        template: ScriptFormatTemplate,
        platform_rules: PlatformPacingRules,
    ) -> tuple[GeneratedScript, list[str]]:
        warnings: list[str] = []
        data = payload.model_dump() if isinstance(payload, GeneratedScript) else dict(payload or {})
        script_id = str(data.get("id") or stable_script_id(idea, content_format_id, platform))

        speakers = self._normalize_speakers(data.get("speakers"), template)
        speaker_by_label = {speaker.label.lower(): speaker for speaker in speakers}
        speaker_by_id = {speaker.id: speaker for speaker in speakers}

        normalized_lines: list[ScriptLine] = []
        source_lines = [item for item in list(data.get("lines") or []) if isinstance(item, dict)]
        if not source_lines:
            warnings.append("Provider returned no lines.")

        for index, raw_line in enumerate(source_lines):
            raw_label = str(raw_line.get("speaker_label") or raw_line.get("speaker") or "").strip()
            raw_id = str(raw_line.get("speaker_id") or "").strip()
            speaker = speaker_by_id.get(raw_id) or speaker_by_label.get(raw_label.lower()) or speakers[min(index, len(speakers) - 1)]
            text, cleanup_warnings = clean_spoken_text(str(raw_line.get("text") or ""))
            warnings.extend(cleanup_warnings)
            if not text:
                continue
            section = _section(raw_line.get("section"), index, max(len(source_lines), 1))
            visual_cue = raw_line.get("visual_cue")
            cue = ScriptVisualCue(**visual_cue) if isinstance(visual_cue, dict) else None
            for chunk in _split_line_text(text, platform_rules.max_words_per_spoken_line):
                line_id = f"line_{len(normalized_lines) + 1:03d}"
                caption_text = str(raw_line.get("caption_text") or chunk).strip()
                if caption_text == text and chunk != text:
                    caption_text = chunk
                normalized_lines.append(
                    ScriptLine(
                        id=line_id,
                        section=section,  # type: ignore[arg-type]
                        speaker_id=speaker.id,
                        speaker_label=speaker.label,
                        text=chunk,
                        caption_text=caption_text or chunk,
                        estimated_duration_sec=estimate_duration_seconds(chunk, platform_rules),
                        emotion=raw_line.get("emotion"),
                        delivery=raw_line.get("delivery"),
                        visual_cue=cue,
                    )
                )

        if not normalized_lines:
            fallback_text = f"Here's the key thing to know about {idea}."
            speaker = speakers[0]
            normalized_lines.append(
                ScriptLine(
                    id="line_001",
                    section="hook",
                    speaker_id=speaker.id,
                    speaker_label=speaker.label,
                    text=fallback_text,
                    caption_text=fallback_text,
                    estimated_duration_sec=estimate_duration_seconds(fallback_text, platform_rules),
                )
            )

        sections = []
        for name in CANONICAL_SECTIONS:
            if any(line.section == name for line in normalized_lines):
                sections.append(name)

        script = GeneratedScript(
            id=script_id,
            idea=idea,
            content_format_id=content_format_id,
            platform=platform,  # type: ignore[arg-type]
            target_duration_sec=target_duration_sec,
            tone=tone,
            audience=audience,
            speakers=speakers,
            lines=normalized_lines,
            sections=sections,  # type: ignore[arg-type]
            metadata_suggestions=data.get("metadata_suggestions") or {},
            total_estimated_duration_sec=round(sum(line.estimated_duration_sec for line in normalized_lines), 2),
            provider_metadata=dict(data.get("provider_metadata") or {}),
        )
        script.caption_blocks = CaptionBlockBuilder().build(script.lines, platform_rules)
        return script, warnings

    def _normalize_speakers(self, raw_speakers: Any, template: ScriptFormatTemplate) -> list[ScriptSpeaker]:
        speakers: list[ScriptSpeaker] = []
        for index, item in enumerate(raw_speakers or []):
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or item.get("name") or "").strip()
            if not label:
                continue
            speakers.append(
                ScriptSpeaker(
                    id=stable_slug(str(item.get("id") or label), f"speaker_{index + 1}"),
                    label=label,
                    role=str(item.get("role") or template.default_speaker_roles[min(index, len(template.default_speaker_roles) - 1)]),
                    voice_profile_id=item.get("voice_profile_id"),
                    speaker_image_id=item.get("speaker_image_id"),
                )
            )
        while len(speakers) < template.min_speakers:
            role = template.default_speaker_roles[min(len(speakers), len(template.default_speaker_roles) - 1)]
            speakers.append(ScriptSpeaker(id=stable_slug(role, f"speaker_{len(speakers) + 1}"), label=role, role=role))
        return speakers[: template.max_speakers]
