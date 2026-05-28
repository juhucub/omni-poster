from __future__ import annotations

import hashlib
import re
from typing import Any

from app.schemas import GeneratedScript, ScriptLine, ScriptSpeaker, ScriptVisualCue
from app.domains.script_generation.captions import CaptionBlockBuilder
from app.domains.script_generation.formats import ScriptFormatTemplate
from app.domains.script_generation.platforms import PlatformPacingRules

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


def _section(value: Any, index: int, total: int, template: ScriptFormatTemplate) -> str:
    raw = str(value or "").strip().lower()
    allowed = set(CANONICAL_SECTIONS) | {section.lower() for section in template.structure}
    if raw in allowed:
        return raw
    if index == 0:
        return template.structure[0] if template.structure else "hook"
    if index >= total - 2:
        if index == total - 1:
            return template.structure[-1] if template.structure else "cta"
        return template.structure[-2] if len(template.structure) >= 2 else "payoff"
    if len(template.structure) > 2:
        midpoint = min(index, len(template.structure) - 2)
        return template.structure[midpoint]
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
        returned_format = str(data.get("content_format_id") or "").strip()
        if returned_format and returned_format != content_format_id:
            warnings.append(f"Model returned content_format_id={returned_format}; normalized to requested {content_format_id}.")
        script_id = str(data.get("id") or stable_script_id(idea, content_format_id, platform))

        speakers = self._normalize_speakers(data.get("speakers"), template)
        speaker_by_label = {speaker.label.lower(): speaker for speaker in speakers}
        speaker_by_id = {speaker.id: speaker for speaker in speakers}

        normalized_lines: list[ScriptLine] = []
        source_lines = [item for item in list(data.get("lines") or []) if isinstance(item, dict)]
        if not source_lines:
            warnings.append("Provider returned no lines.")

        for index, raw_line in enumerate(source_lines):
            raw_label = str(raw_line.get("speaker_label") or raw_line.get("label") or raw_line.get("speaker") or "").strip()
            raw_id = str(raw_line.get("speaker_id") or "").strip()
            speaker = speaker_by_id.get(raw_id) or speaker_by_label.get(raw_label.lower()) or speakers[min(index, len(speakers) - 1)]
            if raw_id and raw_id not in speaker_by_id:
                warnings.append(f"Line {index + 1} referenced unknown speaker_id={raw_id}; remapped to {speaker.id}.")
            text, cleanup_warnings = clean_spoken_text(str(raw_line.get("text") or ""))
            warnings.extend(cleanup_warnings)
            if not text:
                continue
            section = _section(raw_line.get("section"), index, max(len(source_lines), 1), template)
            visual_cue = raw_line.get("visual_cue")
            cue = ScriptVisualCue(**visual_cue) if isinstance(visual_cue, dict) else None
            for chunk in _split_line_text(text, platform_rules.max_words_per_spoken_line):
                line_id = f"line_{len(normalized_lines) + 1:03d}"
                caption_text = str(raw_line.get("caption_text") or "").strip() or chunk
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
                        beat_index=len(normalized_lines),
                        order=len(normalized_lines),
                    )
                )

        self._distribute_sections(normalized_lines, template)

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
                    beat_index=0,
                    order=0,
                )
            )

        sections = []
        for name in list(dict.fromkeys([*template.structure, *CANONICAL_SECTIONS])):
            if any(line.section == name for line in normalized_lines):
                sections.append(name)

        title = str((data.get("metadata_suggestions") or {}).get("title") or "").strip() or _title_from_idea(idea)
        short_summary = str(data.get("short_summary") or "").strip() or _short_summary(idea, content_format_id)

        script = GeneratedScript(
            id=script_id,
            script_id=script_id,
            idea=idea,
            content_format_id=content_format_id,
            format_id=content_format_id,
            platform=platform,  # type: ignore[arg-type]
            platform_targets=[platform],  # type: ignore[list-item]
            target_duration_sec=target_duration_sec,
            tone=tone,
            audience=audience,
            title=title,
            short_summary=short_summary,
            speakers=speakers,
            lines=normalized_lines,
            sections=sections,  # type: ignore[arg-type]
            metadata_suggestions=data.get("metadata_suggestions") or {},
            total_estimated_duration_sec=round(sum(line.estimated_duration_sec for line in normalized_lines), 2),
            estimated_total_duration_sec=round(sum(line.estimated_duration_sec for line in normalized_lines), 2),
            provider_metadata=dict(data.get("provider_metadata") or {}),
        )
        script.caption_blocks = CaptionBlockBuilder().build(script.lines, platform_rules)
        return script, warnings

    def _distribute_sections(self, lines: list[ScriptLine], template: ScriptFormatTemplate) -> None:
        if not lines:
            return
        structure = template.structure or list(CANONICAL_SECTIONS)
        lines[0].section = structure[0]
        for index, line in enumerate(lines):
            line.beat_index = index
            line.order = index
        if len(lines) == 1:
            return
        lines[-1].section = structure[-1]
        if len(lines) >= 3:
            lines[-2].section = structure[-2] if len(structure) >= 2 else "payoff"
        allowed = set(CANONICAL_SECTIONS) | set(structure)
        for index, line in enumerate(lines[1:-2], start=1):
            if line.section not in allowed:
                line.section = structure[min(index, max(len(structure) - 2, 1))]

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
                    point_of_view=item.get("point_of_view"),
                    motivation=item.get("motivation"),
                    stance=item.get("stance"),
                    conversational_style=item.get("conversational_style"),
                    likely_objection=item.get("likely_objection"),
                    relationship_to_others=item.get("relationship_to_others"),
                )
            )
        while len(speakers) < template.min_speakers:
            role = template.default_speaker_roles[min(len(speakers), len(template.default_speaker_roles) - 1)]
            speakers.append(ScriptSpeaker(id=stable_slug(role, f"speaker_{len(speakers) + 1}"), label=role, role=role))
        return speakers[: template.max_speakers]


def _title_from_idea(idea: str) -> str:
    return " ".join(idea.strip().split()[:8]).title() or "Short-Form Script"


def _short_summary(idea: str, content_format_id: str) -> str:
    return f"{content_format_id.replace('_', ' ')} about {idea.strip()[:120]}"
