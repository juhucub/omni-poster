from __future__ import annotations

import json
from typing import Any

from app.schemas import ScriptGenerationRequest
from app.domains.script_generation.topic_parsers.debate_topics import normalize_debate_topic
from app.domains.script_generation.formats import ScriptFormatTemplate
from app.domains.script_generation.planner import ScriptDurationPlan
from app.domains.script_generation.platforms import PlatformPacingRules


PRESET_CONTRACTS: dict[str, list[str]] = {
    "reddit_story": [
        "first-person narrator unless user asks otherwise",
        "include setup, escalation, twist, aftermath",
        "make the hook concrete; avoid vague drama",
    ],
    "character_dialogue": [
        "two-character clash with alternating replies",
        "every line responds to the prior line",
        "end on payoff or reversal, not agreement",
    ],
    "podcast_clip": [
        "host asks concise prompts; guest gives specifics",
        "include one example and one takeaway",
        "sound clipped from conversation, not essay narration",
    ],
    "debate_format": [
        "exactly moderator, speaker A, speaker B",
        "speaker A and speaker B must oppose each other",
        "include claim, rebuttal, counterexample, verdict/open question",
    ],
    "meme_news_reaction": [
        "headline, reaction, implication, payoff",
        "name the concrete topic immediately",
        "do not invent real-world facts beyond the prompt",
    ],
    "educational_short": [
        "include misconception, explanation, example, takeaway",
        "teach one mechanism only",
        "make the takeaway actionable",
    ],
    "multi_speaker_skit": [
        "three-speaker scene with short exchanges",
        "each speaker has a distinct job in the scene",
        "include punchline and short tag",
    ],
}


class ScriptPromptBuilder:
    def build(
        self,
        request: ScriptGenerationRequest,
        *,
        template: ScriptFormatTemplate,
        platform_rules: PlatformPacingRules,
        target_duration_sec: int,
        plan: ScriptDurationPlan,
    ) -> str:
        speaker_json = json.dumps(
            [
                {
                    "id": speaker.id,
                    "label": speaker.label,
                    "role": speaker.role,
                    "pov": speaker.point_of_view,
                    "stance": speaker.stance,
                }
                for speaker in plan.speakers
            ],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        beat_json = json.dumps([{"s": beat.section, "n": beat.target_lines} for beat in plan.beats], ensure_ascii=True, separators=(",", ":"))
        budget = dict(template.generation_budget or {})
        compact_budget = {
            key: budget.get(key)
            for key in (
                "max_speakers_for_draft",
                "max_lines_for_60s_draft",
                "max_words_per_line",
                "max_total_words",
                "section_line_counts",
            )
            if key in budget
        }
        budget_json = json.dumps(compact_budget, ensure_ascii=True, separators=(",", ":"))
        contract_json = json.dumps(PRESET_CONTRACTS.get(template.id, template.prompt_guidance), ensure_ascii=True, separators=(",", ":"))
        platform_targets = request.platform_targets or [request.platform]
        quality_hints = request.quality_hints.model_dump(exclude_none=True) if request.quality_hints else {}
        metadata_hints = request.metadata_hints.model_dump(exclude_none=True) if request.metadata_hints else {}
        dialogue_rule = "Dialogue: disagreement, response, escalation, payoff."
        if template.dialogue_must_alternate:
            dialogue_rule += " Alternate naturally."
        debate_lines: list[str] = []
        if template.id == "debate_format":
            debate_topic = normalize_debate_topic(request.idea)
            debate_json = json.dumps(
                {
                    "side_a": debate_topic.side_a,
                    "side_b": debate_topic.side_b,
                    "topic": debate_topic.topic,
                },
                ensure_ascii=True,
                separators=(",", ":"),
            )
            debate_lines.append(
                f"Debate topic: {debate_json}; Speaker A=side_a; Speaker B=side_b; moderator neutral."
            )

        return "\n".join(
            [
                "System: Generate OmniPoster short-form scripts. Strict JSON only.",
                "Schema: short_summary; speakers[id,label,role,stance]; lines[section,speaker_id,speaker_label,text,caption_text,estimated_duration_sec,beat_index,order]; metadata_suggestions.",
                f"Topic: {request.idea}",
                *debate_lines,
                f"Format/platform: {template.id} for {platform_rules.id}; targets={platform_targets}.",
                f"Tone/audience: {request.tone or 'engaging'} / {request.audience or 'general'}.",
                f"Target: {target_duration_sec}s, about {plan.target_word_count} words, {plan.target_line_count} lines.",
                f"Line words: {plan.words_per_line_min}-{plan.words_per_line_max}, hard max {platform_rules.max_words_per_spoken_line}.",
                f"Preset: sections={template.structure}; speaker_model={template.speaker_mode}.",
                f"Preset budget: {budget_json}",
                f"Preset contract: {contract_json}",
                f"Speakers: {speaker_json}",
                f"Beat plan: {beat_json}",
                f"Hints: quality={json.dumps(quality_hints, ensure_ascii=True, separators=(',', ':'))}; metadata={json.dumps(metadata_hints, ensure_ascii=True, separators=(',', ':'))}; previous={(request.previous_context or '')[:240]}",
                "Quality: topic-specific, one concrete topic reference, no filler.",
                "Character: preserve distinct point of view, stance, motivation, and style.",
                dialogue_rule,
                "Timing/budget: hit target; stay within max lines, speakers, words/line, total words, section counts.",
                "Render-ready lines need known speaker_id/speaker_label, text, caption_text, section, beat_index, order.",
                "No markdown, explanations, copied dialogue, slogans, catchphrases.",
            ]
        )

    def build_repair_prompt(
        self,
        *,
        original_prompt: str,
        bad_output: str | dict[str, Any],
        issues: list[str],
        plan: ScriptDurationPlan,
    ) -> str:
        bad_text = bad_output if isinstance(bad_output, str) else json.dumps(bad_output, ensure_ascii=True)
        return "\n".join(
            [
                "Return strict JSON only. Repair the script for OmniPoster.",
                "Keep the same topic, speaker IDs, and render-ready speaker-separated lines.",
                f"Fix these issues: {'; '.join(issues[:8])}",
                f"Target: {plan.target_duration_sec}s, {plan.target_line_count} lines, {plan.target_word_count} words.",
                "Required keys: short_summary, speakers, lines, metadata_suggestions. Lines need section, speaker_id, speaker_label, text, caption_text, estimated_duration_sec, beat_index, order.",
                "No markdown. No explanation. No generic filler.",
                f"Original instructions: {original_prompt[:1600]}",
                f"Bad output: {bad_text[:2500]}",
            ]
        )
