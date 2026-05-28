from __future__ import annotations

import re
from typing import Any

from app.schemas import ScriptGenerationRequest
from app.domains.script_generation.topic_parsers.debate_topics import TERMINAL_FRAGMENT_WORDS, is_sentence_complete, normalize_debate_topic
from app.domains.script_generation.formats import ScriptFormatTemplate
from app.domains.script_generation.normalizer import stable_slug
from app.domains.script_generation.platforms import PlatformPacingRules
from app.domains.script_generation.providers.base import ProviderResult, ScriptGenerationProvider


class DeterministicFallbackScriptGenerationProvider(ScriptGenerationProvider):
    provider_name = "deterministic_fallback"

    def _infer_character_names_from_idea(self, idea: str) -> list[str]:
        patterns = [
            r"\b([A-Z][a-zA-Z]+)\s+and\s+([A-Z][a-zA-Z]+)\b",
            r"\b([A-Z][a-zA-Z]+)\s+&\s+([A-Z][a-zA-Z]+)\b",
            r"\bbetween\s+([A-Z][a-zA-Z]+)\s+and\s+([A-Z][a-zA-Z]+)\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, idea)
            if match:
                return [match.group(1), match.group(2)]

        return []
    
    def generate(
        self,
        request: ScriptGenerationRequest,
        *,
        prompt: str,
        template: ScriptFormatTemplate,
        platform_rules: PlatformPacingRules,
        target_duration_sec: int,
    ) -> ProviderResult:
        speakers = self._speakers(request, template)
        lines = self._lines(request, template, speakers)
        payload = {
            "idea": request.idea,
            "content_format_id": template.id,
            "platform": platform_rules.id,
            "target_duration_sec": target_duration_sec,
            "tone": request.tone,
            "audience": request.audience,
            "short_summary": f"{template.label} about {request.idea.strip()[:120]}",
            "speakers": speakers,
            "lines": lines,
            "sections": template.structure,
            "metadata_suggestions": {
                "title": (request.metadata_hints.title_style if request.metadata_hints and request.metadata_hints.title_style else self._title(request.idea)),
                "description": f"A short-form {template.label.lower()} about {request.idea}.",
                "hashtags": list(dict.fromkeys([*template.default_metadata_hints.get("hashtags", []), "#shorts", f"#{stable_slug(template.id, 'format')}"])),
                "cta": template.default_metadata_hints.get("cta") or self._cta(platform_rules),
            },
        }
        return ProviderResult(
            payload=payload,
            provider_name=self.provider_name,
            fallback_used=True,
            fallback_reason="deterministic_template",
        )

    def _speakers(self, request: ScriptGenerationRequest, template: ScriptFormatTemplate) -> list[dict[str, Any]]:
        names = [name.strip() for name in request.speaker_names if name.strip()]
        context_by_label = {context.label.strip().lower(): context for context in request.speaker_contexts if context.label}
        required = template.default_speaker_count

        if template.id == "reddit_story":
            names = names[:1] or template.default_speaker_roles[:1]
        if template.id == "character_dialogue" and len(names) < 2:
            inferred = self._infer_character_names_from_idea(request.idea)
            if len(inferred) >= 2:
                names = inferred
        if template.id == "debate_format":
            names = names[:3] or ["Moderator", "Speaker A", "Speaker B"]
        elif template.id in {"character_dialogue", "podcast_clip"} and len(names) < 2:
            names = names + template.default_speaker_roles[len(names) :]
        elif template.id == "multi_speaker_skit" and len(names) < 3:
            names = names + template.default_speaker_roles[len(names) :]
        elif not names:
            names = template.default_speaker_roles[:required]
        names = names[: template.max_speakers]
        while len(names) < template.min_speakers:
            names.append(template.default_speaker_roles[min(len(names), len(template.default_speaker_roles) - 1)])
        speakers = []
        for index, name in enumerate(names):
            context = context_by_label.get(name.lower())
            role = template.default_speaker_roles[min(index, len(template.default_speaker_roles) - 1)]
            speakers.append({
                "id": stable_slug(name, f"speaker_{index + 1}"),
                "label": name,
                "role": context.role if context and context.role else role,
                "point_of_view": context.point_of_view if context else None,
                "motivation": context.motivation if context else None,
                "stance": context.stance if context else None,
                "conversational_style": context.conversational_style if context else None,
                "likely_objection": context.likely_objection if context else None,
                "relationship_to_others": context.relationship_to_others if context else None,
            })
        return speakers

    def _line(self, speakers: list[dict[str, Any]], index: int, section: str, text: str, visual: str | None = None) -> dict[str, Any]:
        speaker = speakers[index % len(speakers)]
        return {
            "section": section,
            "speaker_id": speaker["id"],
            "speaker_label": speaker["label"],
            "text": text,
            "caption_text": text,
            "visual_cue": {"cue_type": "beat", "description": visual or "", "asset_slot": None} if visual else None,
        }

    def _trim_line_to_budget(self, text: str, max_words: int) -> str:
        normalized = re.sub(r"\s+", " ", text or "").strip()
        if not normalized:
            return ""
        words = normalized.split()
        if len(words) <= max_words:
            return self._ensure_sentence(normalized)

        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", normalized) if sentence.strip()]
        best = ""
        for sentence in sentences:
            candidate = f"{best} {sentence}".strip() if best else sentence
            if len(candidate.split()) <= max_words and is_sentence_complete(candidate):
                best = candidate
        if best:
            return best

        kept = words[:max_words]
        while kept and self._terminal_word(kept[-1]) in TERMINAL_FRAGMENT_WORDS:
            kept.pop()
        if len(kept) < 3:
            kept = words[: min(len(words), max(3, max_words))]
        trimmed = " ".join(kept).rstrip(" ,;:")
        return self._ensure_sentence(trimmed)

    def _ensure_sentence(self, text: str) -> str:
        stripped = text.strip()
        if not stripped:
            return stripped
        while self._terminal_word(stripped) in TERMINAL_FRAGMENT_WORDS and len(stripped.split()) > 3:
            stripped = " ".join(stripped.split()[:-1]).rstrip(" ,;:")
        if stripped[-1] not in ".?!":
            stripped = f"{stripped.rstrip(' ,;:')}."
        return stripped

    def _terminal_word(self, text: str) -> str:
        words = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", text.lower())
        return words[-1] if words else ""

    def _lines(self, request: ScriptGenerationRequest, template: ScriptFormatTemplate, speakers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        idea = request.idea.strip().rstrip(".")
        if template.id == "reddit_story":
            return self._fit_duration(request, template, speakers, [
                self._line(speakers, 0, "hook", f"I thought {idea} was going to be simple, until the smallest detail gave it away.", "Open on a story title card."),
                self._line(speakers, 0, "setup", "At first, everybody acted like it was just a normal day."),
                self._line(speakers, 0, "escalation", f"Then {idea} became the thing nobody in the room wanted to explain."),
                self._line(speakers, 0, "twist", "The person who looked the calmest had been holding the worst clue the entire time."),
                self._line(speakers, 0, "aftermath", "After that, nobody trusted the original story anymore."),
                self._line(speakers, 0, "cta", "Would you have said something, or waited for proof?"),
            ])
        if template.id == "debate_format":
            debate_topic = normalize_debate_topic(request.idea)
            side_a = self._sentence_start(debate_topic.side_a)
            side_b = self._sentence_start(debate_topic.side_b)
            return self._fit_duration(request, template, speakers, [
                self._line(speakers, 0, "hook", f"Quick debate: {debate_topic.topic}. Which side wins?"),
                self._line(speakers, 1, "claim", f"{side_a}: the benefit is concrete and easy to judge."),
                self._line(speakers, 2, "rebuttal", f"{side_b}: the comparison needs a broader standard."),
                self._line(speakers, 1, "counterexample", f"{side_a}: daily impact keeps that side competitive."),
                self._line(speakers, 2, "tension", f"{side_b}: tradeoffs matter more."),
                self._line(speakers, 0, "verdict", "Verdict: both sides define better with different standards."),
                self._line(speakers, 0, "cta", "Which side has the better argument?"),
            ])
        if template.id == "podcast_clip":
            return self._fit_duration(request, template, speakers, [
                self._line(speakers, 1, "hook", f"The overlooked part of {idea} is not the output. It is the repeatable setup."),
                self._line(speakers, 0, "question", "What do you mean by setup?"),
                self._line(speakers, 1, "insight", "The same idea can perform completely differently depending on timing, speaker mapping, and the hook."),
                self._line(speakers, 0, "example", "So a clip fails when it treats every production like a blank page."),
                self._line(speakers, 1, "takeaway", "Exactly. Repeat the structure, then customize the idea."),
                self._line(speakers, 0, "cta", "Save that before your next recording session."),
            ])
        if template.id == "meme_news_reaction":
            return self._fit_duration(request, template, speakers, [
                self._line(speakers, 0, "headline", f"Breaking: {idea} just turned into the weirdest group project on the internet."),
                self._line(speakers, 0, "reaction", "At first, that sounds fine. Then you read the second sentence."),
                self._line(speakers, 0, "implication", "Now everyone involved has accidentally volunteered for a sequel."),
                self._line(speakers, 0, "payoff", "The funniest part is that the obvious fix was sitting there the entire time."),
                self._line(speakers, 0, "cta", "Send this to the friend who always predicts the chaos."),
            ])
        if template.id == "multi_speaker_skit":
            return self._fit_duration(request, template, speakers, [
                self._line(speakers, 0, "premise", f"We need a plan for {idea}, and nobody is allowed to make it worse."),
                self._line(speakers, 1, "role_setup", "Perfect. I have already made it worse, but efficiently."),
                self._line(speakers, 2, "exchange", "That is not efficiency. That is panic wearing a calendar invite."),
                self._line(speakers, 0, "exchange", "Can one person explain the actual problem in one sentence?"),
                self._line(speakers, 1, "punchline", "Yes, but I used that sentence as the title of a new problem."),
                self._line(speakers, 2, "tag", "Follow for the meeting where this becomes policy."),
            ])
        if template.id == "character_dialogue":
            a = speakers[0]["label"] if speakers else "Speaker A"
            b = speakers[1]["label"] if len(speakers) > 1 else "Speaker B"

            return self._fit_duration(request, template, speakers, [
                self._line(speakers, 0, "hook", f"{b}, why does {idea} feel urgent?"),
                self._line(speakers, 1, "conflict", f"Because {a}, everyone is praising the easy part."),
                self._line(speakers, 0, "escalation", "So we are confidently missing the point."),
                self._line(speakers, 1, "escalation", "The weird part is doing all the work."),
                self._line(speakers, 0, "payoff", "That sounds like a trap with branding."),
                self._line(speakers, 1, "payoff", "Exactly. The warning label is tiny."),
                self._line(speakers, 0, "cta", "Follow before this becomes the normal version."),
            ])
        return self._fit_duration(request, template, speakers, [
            self._line(speakers, 0, "hook", f"The mistake with {idea} is starting with the answer."),
            self._line(speakers, 0, "misconception", "Most people explain the feature before the viewer feels the problem."),
            self._line(speakers, 0, "explanation", "Start with the friction, then show the one mechanism that changes the outcome."),
            self._line(speakers, 0, "example", f"For {idea}, that means the reusable step matters as much as the final clip."),
            self._line(speakers, 0, "takeaway", "Make the structure repeatable, then make the idea specific."),
            self._line(speakers, 0, "cta", "Save this for your next short."),
        ])

    def _sentence_start(self, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            return stripped
        return f"{stripped[:1].upper()}{stripped[1:]}"

    def _fit_duration(
        self,
        request: ScriptGenerationRequest,
        template: ScriptFormatTemplate,
        speakers: list[dict[str, Any]],
        lines: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        target_duration_sec = request.target_duration_sec or 45
        budget = dict(template.generation_budget or {})
        max_lines = int(budget.get("max_lines_for_60s_draft") or len(lines))
        max_words = int(budget.get("max_words_per_line") or 14)
        if target_duration_sec <= 18:
            limited = lines[: max(4, template.min_speakers + 2)]
            return [{**line, "text": self._trim_line_to_budget(str(line["text"]), max_words), "caption_text": self._trim_line_to_budget(str(line["caption_text"]), max_words)} for line in limited]

        target_line_count = max(len(lines), min(14, round(target_duration_sec / 4.4)))
        if target_duration_sec <= 60:
            target_line_count = min(target_line_count, max_lines)
        idea = request.idea.strip().rstrip(".")
        if template.id == "debate_format":
            debate_topic = normalize_debate_topic(request.idea)
            side_a = self._sentence_start(debate_topic.side_a)
            side_b = self._sentence_start(debate_topic.side_b)
            inserts = [
                f"{side_a}: real outcomes should judge the debate.",
                f"{side_b}: the first standard may be too narrow.",
                f"{side_a}: the clearest benefit stays visible.",
                f"{side_b}: the opposing tradeoff stays visible.",
            ]
        else:
            inserts = [
                f"That matters for {idea} because the repeatable step changes the result.",
                "The next detail gives the viewer a reason to keep watching.",
                "Without that detail, the conflict feels random instead of earned.",
                "The sharper question is what changes when the workflow repeats.",
                f"That is why {idea} needs a specific example instead of generic advice.",
                "Now the callback lands because the setup was visible from the first beat.",
            ]
        insert_at = max(1, len(lines) - 2)
        while len(lines) < target_line_count:
            text = inserts[(len(lines) - insert_at) % len(inserts)]
            section = template.structure[min(insert_at, max(len(template.structure) - 2, 1))] if template.structure else "body"
            lines.insert(insert_at, self._line(speakers, insert_at, section, text))
            insert_at += 1
        if target_duration_sec <= 60 and len(lines) > max_lines:
            cta = [line for line in lines if line.get("section") in {"cta", "tag"}]
            lines = lines[:max_lines]
            if cta and not any(line.get("section") in {"cta", "tag"} for line in lines):
                lines[-1] = cta[-1]
        if template.id == "debate_format" and len(speakers) >= 3:
            self._assign_debate_speakers(lines, speakers)
        elif template.dialogue_must_alternate and len(speakers) > 1:
            for index, line in enumerate(lines):
                speaker = speakers[index % len(speakers)]
                line["speaker_id"] = speaker["id"]
                line["speaker_label"] = speaker["label"]
        for line in lines:
            line["text"] = self._trim_line_to_budget(str(line["text"]), max_words)
            line["caption_text"] = self._trim_line_to_budget(str(line["caption_text"]), max_words)
        return lines

    def _assign_debate_speakers(self, lines: list[dict[str, Any]], speakers: list[dict[str, Any]]) -> None:
        section_speakers = {
            "hook": 0,
            "claim": 1,
            "counterexample": 1,
            "rebuttal": 2,
            "tension": 2,
            "verdict": 0,
            "cta": 0,
        }
        for index, line in enumerate(lines):
            speaker_index = section_speakers.get(str(line.get("section") or ""), index % len(speakers))
            speaker = speakers[min(speaker_index, len(speakers) - 1)]
            line["speaker_id"] = speaker["id"]
            line["speaker_label"] = speaker["label"]

    def _title(self, idea: str) -> str:
        words = idea.strip().split()
        return " ".join(words[:8]).title() or "Short-Form Script"

    def _cta(self, platform_rules: PlatformPacingRules) -> str:
        return platform_rules.cta_style
