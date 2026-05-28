from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.schemas import ScriptGenerationRequest
from app.domains.script_generation.formats import ScriptFormatTemplate
from app.domains.script_generation.normalizer import stable_slug
from app.domains.script_generation.platforms import PlatformPacingRules


@dataclass(frozen=True)
class SpeakerPlan:
    id: str
    label: str
    role: str
    point_of_view: str
    motivation: str
    stance: str
    conversational_style: str
    likely_objection: str
    relationship_to_others: str
    target_line_count: int


@dataclass(frozen=True)
class BeatPlan:
    section: str
    purpose: str
    target_lines: int
    line_style: str


@dataclass(frozen=True)
class ScriptDurationPlan:
    target_duration_sec: int
    target_word_count: int
    target_line_count: int
    words_per_line_min: int
    words_per_line_max: int
    pacing_pattern: str
    speakers: list[SpeakerPlan]
    beats: list[BeatPlan]

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def build_duration_plan(
    request: ScriptGenerationRequest,
    *,
    template: ScriptFormatTemplate,
    platform_rules: PlatformPacingRules,
    target_duration_sec: int,
) -> ScriptDurationPlan:
    words_per_second = platform_rules.estimated_words_per_minute / 60
    budget = dict(template.generation_budget or {})
    budget_line_cap = int(budget.get("max_lines_for_60s_draft") or 14)
    budget_word_cap = int(budget.get("max_total_words") or 250)
    budget_words_per_line = int(budget.get("max_words_per_line") or platform_rules.max_words_per_spoken_line)
    target_word_count = max(20, round(target_duration_sec * words_per_second * 0.88))
    if target_duration_sec <= 60:
        target_word_count = min(target_word_count, budget_word_cap)

    if target_duration_sec <= 18:
        target_line_count = 4 if template.min_speakers <= 1 else max(template.min_speakers + 2, 5)
        words_min, words_max = 4, min(9, platform_rules.max_words_per_spoken_line)
        pacing = "quick hook, brief clash, immediate payoff"
    elif target_duration_sec <= 45:
        target_line_count = max(6, min(9, round(target_duration_sec / 5.5)))
        words_min, words_max = 6, min(12, platform_rules.max_words_per_spoken_line, budget_words_per_line)
        pacing = "clear setup, escalating middle, concise payoff"
    else:
        target_line_count = max(9, min(14, round(target_duration_sec / 6)))
        words_min, words_max = 7, min(platform_rules.max_words_per_spoken_line, budget_words_per_line)
        pacing = "setup, multiple exchanges, callback, payoff"
    if target_duration_sec <= 60:
        target_line_count = min(target_line_count, budget_line_cap)
        words_max = min(words_max, budget_words_per_line)

    speaker_plans = _speaker_plans(request, template, target_line_count)
    return ScriptDurationPlan(
        target_duration_sec=target_duration_sec,
        target_word_count=target_word_count,
        target_line_count=target_line_count,
        words_per_line_min=words_min,
        words_per_line_max=words_max,
        pacing_pattern=pacing,
        speakers=speaker_plans,
        beats=_beat_plan(target_line_count, target_duration_sec, template),
    )


def _speaker_plans(request: ScriptGenerationRequest, template: ScriptFormatTemplate, target_line_count: int) -> list[SpeakerPlan]:
    contexts = list(request.speaker_contexts or [])
    names = [name.strip() for name in request.speaker_names if name.strip()]
    if not names:
        names = template.default_speaker_roles[: template.default_speaker_count]

    while len(names) < template.min_speakers:
        names.append(template.default_speaker_roles[min(len(names), len(template.default_speaker_roles) - 1)])
    names = names[: template.max_speakers]

    context_by_label = {str(item.label).strip().lower(): item for item in contexts if item.label}
    per_speaker_lines = _balanced_counts(len(names), target_line_count)
    plans: list[SpeakerPlan] = []
    for index, name in enumerate(names):
        role = template.default_speaker_roles[min(index, len(template.default_speaker_roles) - 1)]
        context = context_by_label.get(name.lower())
        stance = context.stance if context and context.stance else _default_stance(index, template)
        plans.append(
            SpeakerPlan(
                id=stable_slug(context.id if context and context.id else name, f"speaker_{index + 1}"),
                label=name,
                role=context.role if context and context.role else role,
                point_of_view=context.point_of_view if context and context.point_of_view else _default_point_of_view(role, index, template),
                motivation=context.motivation if context and context.motivation else _default_motivation(role, template),
                stance=stance,
                conversational_style=(
                    context.conversational_style
                    if context and context.conversational_style
                    else _default_style(index, template)
                ),
                likely_objection=context.likely_objection if context and context.likely_objection else _default_objection(index, template),
                relationship_to_others=(
                    context.relationship_to_others
                    if context and context.relationship_to_others
                    else _default_relationship(index, template)
                ),
                target_line_count=per_speaker_lines[index],
            )
        )
    return plans


def _balanced_counts(count: int, total: int) -> list[int]:
    if count <= 0:
        return []
    base = total // count
    remainder = total % count
    return [base + (1 if index < remainder else 0) for index in range(count)]


def _beat_plan(target_line_count: int, target_duration_sec: int, template: ScriptFormatTemplate) -> list[BeatPlan]:
    sections = template.structure or ["hook", "body", "payoff", "cta"]
    if len(sections) == 1:
        return [BeatPlan(sections[0], "single concise beat", target_line_count, "short")]

    base_counts = [1 for _ in sections]
    remaining = max(0, target_line_count - len(sections))
    middle_indices = list(range(1, max(len(sections) - 1, 1))) or [0]
    cursor = 0
    while remaining > 0:
        base_counts[middle_indices[cursor % len(middle_indices)]] += 1
        remaining -= 1
        cursor += 1

    purposes = {
        "hook": "specific topic hook or question",
        "setup": "ground the story in one concrete detail",
        "escalation": "raise the stakes",
        "twist": "reveal the turn",
        "aftermath": "show the consequence",
        "conflict": "state the disagreement",
        "claim": "make the strongest case",
        "rebuttal": "challenge the claim",
        "counterexample": "offer a concrete exception",
        "headline": "state the topical headline",
        "reaction": "make the immediate reaction",
        "implication": "show the absurd or practical consequence",
        "misconception": "name the wrong assumption",
        "explanation": "explain the mechanism",
        "example": "give a concrete example",
        "takeaway": "make the practical lesson memorable",
        "premise": "set the scene",
        "role_setup": "assign each speaker a role",
        "exchange": "build the chaotic back-and-forth",
        "punchline": "land the joke or reversal",
        "payoff": "turn, callback, answer, or punchline",
        "verdict": "give the verdict or unresolved tension",
        "tag": "short final button after the punchline",
        "cta": "natural closing beat, not generic filler",
    }
    return [
        BeatPlan(
            section,
            purposes.get(section, f"{section.replace('_', ' ')} beat"),
            base_counts[index],
            "short" if index in {0, len(sections) - 1} or target_duration_sec <= 30 else "medium",
        )
        for index, section in enumerate(sections)
    ]


def _default_point_of_view(role: str, index: int, template: ScriptFormatTemplate) -> str:
    if template.id == "debate_format":
        return "moderates the disagreement" if index == 0 else ("argues for the idea" if index == 1 else "challenges the idea")
    if template.speaker_mode in {"dialogue", "ensemble"}:
        return "practical and skeptical" if index % 2 else "curious and provocative"
    return f"explains the topic as the {role.lower()}"


def _default_motivation(role: str, template: ScriptFormatTemplate) -> str:
    if template.speaker_mode in {"dialogue", "ensemble", "moderated_debate", "host_guest"}:
        return "make a clear point while responding to the other speaker"
    return f"help viewers understand the {role.lower()} perspective quickly"


def _default_stance(index: int, template: ScriptFormatTemplate) -> str:
    if template.id == "debate_format":
        return "neutral" if index == 0 else ("supportive" if index == 1 else "opposed")
    if template.speaker_mode in {"dialogue", "ensemble"}:
        return "questions the premise" if index % 2 else "pushes the premise forward"
    return "informed and specific"


def _default_style(index: int, template: ScriptFormatTemplate) -> str:
    if template.speaker_mode in {"dialogue", "ensemble"}:
        return "dry, concise replies" if index % 2 else "energetic setup lines"
    if template.speaker_mode == "host_guest":
        return "curious host" if index == 0 else "specific, example-driven answers"
    return "clear short-form narration"


def _default_objection(index: int, template: ScriptFormatTemplate) -> str:
    if template.speaker_mode in {"dialogue", "ensemble", "moderated_debate", "host_guest"}:
        return "asks what the other speaker is missing" if index % 2 else "asks why the audience should care now"
    return "why this matters now"


def _default_relationship(index: int, template: ScriptFormatTemplate) -> str:
    if template.speaker_mode == "host_guest":
        return "host interviewing guest" if index == 0 else "guest responding to host"
    if template.speaker_mode in {"dialogue", "ensemble"}:
        return "familiar sparring partner"
    if template.speaker_mode == "moderated_debate":
        return "moderator" if index == 0 else "opposing debate side"
    return "direct narrator to viewer"
