from __future__ import annotations

import re

from app.schemas import GeneratedScript
from app.domains.script_generation.topic_parsers.debate_topics import is_sentence_complete, keyword_terms, normalize_debate_topic
from app.domains.script_generation.formats import ScriptFormatTemplate
from app.domains.script_generation.normalizer import STAGE_DIRECTION_RE
from app.domains.script_generation.platforms import PlatformPacingRules

HARD_PREFIX = "Hard quality failure:"


class ScriptValidator:
    def validate(
        self,
        script: GeneratedScript,
        *,
        template: ScriptFormatTemplate,
        platform_rules: PlatformPacingRules,
        idea: str,
    ) -> list[str]:
        warnings: list[str] = []
        budget = dict(template.generation_budget or {})
        max_lines = int(budget.get("max_lines_for_60s_draft") or 999)
        max_draft_speakers = int(budget.get("max_speakers_for_draft") or template.max_speakers)
        max_words_per_line = int(budget.get("max_words_per_line") or platform_rules.max_words_per_spoken_line)
        max_total_words = int(budget.get("max_total_words") or 999)
        speaker_ids = {speaker.id for speaker in script.speakers}
        if len(script.speakers) < template.min_speakers or len(script.speakers) > template.max_speakers:
            warnings.append(
                f"Speaker count {len(script.speakers)} does not match {template.id} constraints "
                f"({template.min_speakers}-{template.max_speakers})."
            )
        if script.target_duration_sec <= 60 and len(script.speakers) > max_draft_speakers:
            warnings.append(f"Reduce to {max_draft_speakers} speakers for 60-second draft.")

        if not script.lines:
            warnings.append(f"{HARD_PREFIX} Script has no spoken lines.")
            return warnings
        if script.target_duration_sec <= 60 and len(script.lines) > max_lines:
            warnings.append(f"{HARD_PREFIX} Reduce to {max_lines} lines for 60-second draft.")

        for line in script.lines:
            if line.speaker_id not in speaker_ids:
                warnings.append(f"{HARD_PREFIX} Line {line.id} references missing speaker {line.speaker_id}.")
            if not line.text.strip():
                warnings.append(f"{HARD_PREFIX} Line {line.id} has no spoken text.")
            if not line.caption_text.strip():
                warnings.append(f"{HARD_PREFIX} Line {line.id} has no caption text.")
            if line.section not in set(template.structure) | {"hook", "body", "payoff", "cta"}:
                warnings.append(f"Line {line.id} uses unsupported section {line.section} for {template.id}.")
            if len(line.text.split()) > platform_rules.max_words_per_spoken_line:
                warnings.append(f"Split this line or shorten it: {line.id} exceeds platform line word pacing.")
            if len(line.text.split()) > max_words_per_line:
                warnings.append(f"Split this line or shorten it: {line.id} exceeds {max_words_per_line} words for the selected preset.")
            if len(line.caption_text.split()) > max_words_per_line + 2:
                warnings.append(f"Shorten caption_text for {line.id}; captions are too long for fast draft pacing.")
            if STAGE_DIRECTION_RE.search(line.text):
                warnings.append(f"Line {line.id} still contains stage directions.")

        expected_first = template.structure[0] if template.structure else "hook"
        if script.lines[0].section != expected_first:
            warnings.append(f"{expected_first} does not appear at the beginning.")
        expected_terminal = set(template.structure[-2:]) if len(template.structure) >= 2 else set(template.structure)
        if expected_terminal and not any(line.section in expected_terminal for line in script.lines[-3:]):
            warnings.append(f"Ending sections do not match {template.id} structure.")
        if not script.caption_blocks:
            warnings.append("No caption blocks were generated.")

        missing_sections = [
            section
            for section in template.structure
            if section not in {"cta"} and not any(line.section == section for line in script.lines)
        ]
        if missing_sections:
            warnings.append(f"Script is missing expected {template.id} sections: {', '.join(missing_sections[:4])}.")

        total_words = sum(len(line.text.split()) for line in script.lines)
        if script.target_duration_sec <= 60 and total_words > max_total_words:
            warnings.append(f"{HARD_PREFIX} Ollama output exceeded preset budget; fallback used if repair cannot reduce below {max_total_words} words.")

        duration_delta = abs(script.total_estimated_duration_sec - script.target_duration_sec)
        if duration_delta > max(12, script.target_duration_sec * 0.45):
            warnings.append("Estimated duration is not close to target duration.")

        if template.dialogue_must_alternate and len(script.speakers) > 1:
            repeated = 0
            previous = None
            for line in script.lines:
                if previous == line.speaker_id:
                    repeated += 1
                previous = line.speaker_id
            if repeated > max(1, len(script.lines) // 3):
                warnings.append(f"{HARD_PREFIX} Dialogue does not alternate speakers enough for the selected format.")

        if template.min_speakers >= 2 and len({line.speaker_id for line in script.lines}) < 2:
            warnings.append(f"{HARD_PREFIX} Dialogue uses fewer than two speakers.")
        if template.id == "debate_format":
            speaker_line_sets = {speaker_id: 0 for speaker_id in speaker_ids}
            for line in script.lines:
                speaker_line_sets[line.speaker_id] = speaker_line_sets.get(line.speaker_id, 0) + 1
            if len(script.speakers) != 3:
                warnings.append(f"{HARD_PREFIX} This format expects 3 speakers.")
            if sum(1 for count in speaker_line_sets.values() if count > 0) < 3:
                warnings.append("Debate format lacks opposing viewpoints.")
            warnings.extend(_debate_quality_warnings(script, idea))
        if template.id == "educational_short":
            required = {"misconception", "example", "takeaway"}
            present = {line.section for line in script.lines}
            if not required.issubset(present):
                warnings.append("Educational format lacks misconception/example/takeaway.")
        if template.id == "meme_news_reaction":
            required = {"reaction", "implication"} & set(template.structure)
            present = {line.section for line in script.lines}
            if not required.issubset(present) or not any(line.section in {"payoff", "punchline"} for line in script.lines):
                warnings.append("Meme/news reaction lacks reaction/implication/punchline.")
        if template.speaker_mode in {"dialogue", "ensemble", "moderated_debate"}:
            present_sections = {line.section for line in script.lines}
            if not any(section in present_sections for section in {"conflict", "claim", "rebuttal", "escalation", "punchline", "payoff"}):
                warnings.append("Missing conflict/escalation/payoff for dialogue format.")

        combined_text = " ".join(line.text for line in script.lines)
        topic_terms = _topic_terms(idea)
        if topic_terms and not any(term in combined_text.lower() for term in topic_terms):
            warnings.append(f"{HARD_PREFIX} Script does not include a topic-specific reference.")
        if _looks_generic(combined_text, idea):
            warnings.append(f"{HARD_PREFIX} Script looks generic or fallback-like.")

        return warnings


def _topic_terms(idea: str) -> list[str]:
    terms = []
    for token in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]+", idea.lower()):
        if len(token) >= 4 and token not in {"this", "that", "with", "about", "from", "into", "video", "script", "test"}:
            terms.append(token)
    return terms[:8]


def _looks_generic(text: str, idea: str) -> bool:
    lowered = text.lower()
    generic_markers = (
        "worth the hype",
        "hidden cost",
        "the strongest point",
        "people keep ignoring",
        "here is the fastest way",
        "the one mechanism",
    )
    marker_count = sum(1 for marker in generic_markers if marker in lowered)
    if marker_count >= 2:
        return True
    topic_terms = _topic_terms(idea)
    return bool(topic_terms) and len(text.split()) >= 24 and not any(term in lowered for term in topic_terms)


def _debate_quality_warnings(script: GeneratedScript, idea: str) -> list[str]:
    warnings: list[str] = []
    topic = normalize_debate_topic(idea)
    combined_text = " ".join(line.text for line in script.lines)
    lowered = combined_text.lower()
    idea_lower = idea.lower()
    idea_terms = set(keyword_terms(idea))

    placeholder_phrases = (
        "two characters debate",
        "example debate",
        "placeholder debate",
        "speaker a argues",
        "speaker b argues",
    )
    for phrase in placeholder_phrases:
        if phrase in lowered:
            warnings.append(f"{HARD_PREFIX} Debate output leaked placeholder/example language: {phrase}.")

    canned_topic_patterns = (
        r"\bcats?\s+or\s+dogs?\b",
        r"\bdogs?\s+or\s+cats?\b",
        r"\bcats?\s+versus\s+dogs?\b",
        r"\bdogs?\s+versus\s+cats?\b",
    )
    if "cat" not in idea_terms and any(re.search(pattern, lowered) for pattern in canned_topic_patterns):
        warnings.append(f"{HARD_PREFIX} Debate output leaked an unrelated cats-or-dogs canned topic.")

    generic_terms = ("workflow", "speed", "review", "publishing", "publish", "repeatable", "creator", "short-form")
    leaked_terms = [
        term
        for term in generic_terms
        if term not in idea_lower and re.search(rf"\b{re.escape(term)}\b", lowered)
    ]
    if leaked_terms:
        warnings.append(
            f"{HARD_PREFIX} Debate output contains generic fallback language: {', '.join(leaked_terms[:4])}."
        )

    for line in script.lines:
        if not is_sentence_complete(line.text):
            warnings.append(f"{HARD_PREFIX} Line {line.id} ends as an incomplete sentence fragment.")

    speaker_a = _speaker_by_role(script, "speaker a")
    speaker_b = _speaker_by_role(script, "speaker b")
    if not speaker_a or not speaker_b:
        warnings.append(f"{HARD_PREFIX} Debate format requires Speaker A and Speaker B.")
        return warnings

    side_a_terms = _distinct_terms(topic.side_a_keywords, topic.side_b_keywords)
    side_b_terms = _distinct_terms(topic.side_b_keywords, topic.side_a_keywords)
    speaker_a_text = " ".join(line.text for line in script.lines if line.speaker_id == speaker_a.id)
    speaker_b_text = " ".join(line.text for line in script.lines if line.speaker_id == speaker_b.id)
    if side_a_terms and not _contains_any_term(speaker_a_text, side_a_terms):
        warnings.append(f"{HARD_PREFIX} Speaker A does not argue the normalized side: {topic.side_a}.")
    if side_b_terms and not _contains_any_term(speaker_b_text, side_b_terms):
        warnings.append(f"{HARD_PREFIX} Speaker B does not argue the normalized side: {topic.side_b}.")

    return warnings


def _speaker_by_role(script: GeneratedScript, expected_role: str):
    expected = expected_role.lower()
    for speaker in script.speakers:
        if speaker.role.lower() == expected or speaker.label.lower() == expected:
            return speaker
    return None


def _distinct_terms(primary: tuple[str, ...], opposing: tuple[str, ...]) -> tuple[str, ...]:
    opposing_set = set(opposing)
    distinct = tuple(term for term in primary if term not in opposing_set)
    return distinct or primary


def _contains_any_term(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(term)}\b", lowered) for term in terms)
