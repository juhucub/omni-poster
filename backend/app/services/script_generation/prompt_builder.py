from __future__ import annotations

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
        speaker_names = [name for name in request.speaker_names if name.strip()]
        target_line_count = max(4, min(10, round(target_duration_sec / 7)))
        dialogue_rule = ""
        if template.id == "character_dialogue":
            dialogue_rule = "Use exactly two speakers and alternate every line."
        return "\n".join(
            [
                "Return ONLY valid JSON. No markdown. No code fences. No explanations.",
                'Shape: {"id":"","idea":"","content_format_id":"","platform":"","target_duration_sec":0,"tone":"","audience":"","speakers":[{"id":"","label":"","role":""}],"lines":[{"id":"","section":"hook|body|payoff|cta","speaker_id":"","speaker_label":"","text":"","caption_text":"","estimated_duration_sec":0,"emotion":"","delivery":"","visual_cue":{"cue_type":"","description":"","asset_slot":null}}],"sections":["hook","body","payoff","cta"],"caption_blocks":[],"metadata_suggestions":{"title":"","description":"","hashtags":[],"cta":""},"total_estimated_duration_sec":0}',
                f"Idea: {request.idea}",
                f"Format: {template.id}",
                f"Platform: {platform_rules.id}",
                f"Duration: {target_duration_sec}s",
                f"Tone: {request.tone or 'engaging'}",
                f"Audience: {request.audience or 'general short-form viewers'}",
                f"Speakers: {', '.join(speaker_names) if speaker_names else ', '.join(template.default_speaker_roles)}",
                f"Line count: {target_line_count} max.",
                f"Words per line: {platform_rules.max_words_per_spoken_line} max.",
                "Sections must be hook, body, payoff, cta.",
                "Every line needs id, section, speaker_id, speaker_label, text, caption_text, estimated_duration_sec.",
                "No stage directions in text. Put visuals only in visual_cue.description.",
                dialogue_rule,
            ]
        )
