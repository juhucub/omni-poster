from __future__ import annotations

import json

from app.schemas import ScriptGenerationRequest
from app.services.script_generation.formats import ScriptFormatTemplate
from app.services.script_generation.platforms import PlatformPacingRules


class ScriptPromptBuilder:
    def build(
        self,
        request: ScriptGenerationRequest,
        *,
        template: ScriptFormatTemplate,
        platform_rules: PlatformPacingRules,
        target_duration_sec: int,
    ) -> str:
        schema_hint = {
            "id": "script_short_stable_id",
            "idea": request.idea,
            "content_format_id": template.id,
            "platform": platform_rules.id,
            "target_duration_sec": target_duration_sec,
            "tone": request.tone,
            "audience": request.audience,
            "speakers": [
                {
                    "id": "speaker_slug",
                    "label": "Speaker label",
                    "role": "narrator/host/guest/moderator/character",
                    "voice_profile_id": None,
                    "speaker_image_id": None,
                }
            ],
            "lines": [
                {
                    "id": "line_001",
                    "section": "hook",
                    "speaker_id": "speaker_slug",
                    "speaker_label": "Speaker label",
                    "text": "TTS-ready spoken words only.",
                    "caption_text": "Caption-ready text.",
                    "estimated_duration_sec": 2.4,
                    "emotion": "curious",
                    "delivery": "fast but clear",
                    "visual_cue": {"cue_type": "text_card", "description": "On-screen visual only.", "asset_slot": None},
                }
            ],
            "sections": ["hook", "body", "payoff", "cta"],
            "caption_blocks": [],
            "metadata_suggestions": {"title": "", "description": "", "hashtags": [], "cta": ""},
            "total_estimated_duration_sec": target_duration_sec,
        }
        speaker_names = [name for name in request.speaker_names if name.strip()]
        return "\n".join(
            [
                "You generate production-ready short-form video scripts for OmniPoster.",
                "Return only valid JSON. Do not include markdown, comments, or explanatory prose.",
                "The JSON must match this shape exactly:",
                json.dumps(schema_hint, indent=2),
                "",
                f"Idea: {request.idea}",
                f"Content format: {template.id} ({template.label})",
                f"Speaker mode: {template.speaker_mode}",
                f"Speaker roles: {', '.join(template.default_speaker_roles)}",
                f"Speaker constraints: min {template.min_speakers}, max {template.max_speakers}, default {template.default_speaker_count}",
                f"Requested speaker names: {', '.join(speaker_names) if speaker_names else 'Use format defaults'}",
                f"Platform: {platform_rules.label}",
                f"Target duration seconds: {target_duration_sec}",
                f"Max duration seconds: {platform_rules.max_duration_sec}",
                f"Hook max seconds: {platform_rules.hook_max_seconds}",
                f"Max words per spoken line: {platform_rules.max_words_per_spoken_line}",
                f"Caption words per block: {platform_rules.caption_words_per_block}",
                f"Pacing style: {platform_rules.pacing_style}",
                f"CTA style: {platform_rules.cta_style}",
                f"Tone: {request.tone or 'engaging'}",
                f"Audience: {request.audience or 'general short-form viewers'}",
                "",
                "Rules:",
                "- Use speaker-separated dialogue only.",
                "- Include hook, body, payoff, and cta sections where natural.",
                "- Keep each line short and TTS-ready.",
                "- No stage directions inside spoken text.",
                "- Put visual instructions only in visual_cue fields.",
                "- caption_text must be caption-ready and never a visual direction.",
                "- Dialogue must alternate speakers when the format requires it.",
                "- Use no markdown and no prose outside JSON.",
            ]
        )
