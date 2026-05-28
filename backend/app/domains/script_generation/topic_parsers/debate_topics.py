from __future__ import annotations

import re
from dataclasses import dataclass


STOPWORDS = {
    "about",
    "against",
    "are",
    "argument",
    "better",
    "best",
    "case",
    "debate",
    "for",
    "from",
    "make",
    "makes",
    "more",
    "other",
    "over",
    "should",
    "than",
    "that",
    "the",
    "this",
    "video",
    "whether",
    "which",
    "with",
}


TERMINAL_FRAGMENT_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "because",
    "but",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "or",
    "than",
    "the",
    "to",
    "versus",
    "vs",
    "whether",
    "with",
}


@dataclass(frozen=True)
class DebateTopic:
    raw_idea: str
    topic: str
    side_a: str
    side_b: str
    moderator_framing: str
    side_a_keywords: tuple[str, ...]
    side_b_keywords: tuple[str, ...]


def normalize_debate_topic(idea: str) -> DebateTopic:
    raw_idea = _collapse_spaces(idea)
    cleaned = _strip_debate_prefix(raw_idea)

    explicit = _parse_explicit_sides(cleaned)
    if explicit:
        side_a, side_b = explicit
        side_a = _clean_side(side_a)
        side_b = _normalize_side_b(_clean_side(side_b), side_a)
        topic = f"{side_a} versus {side_b}"
        return _topic(raw_idea, topic, side_a, side_b, topic)

    proposition = _parse_proposition(cleaned)
    if proposition:
        subject, action = proposition
        if action == "required":
            side_a = f"requiring {subject}"
            side_b = f"keeping {subject} optional"
            frame = f"whether {subject} should be required"
            return _topic(raw_idea, frame, side_a, side_b, frame)

    topic = cleaned or raw_idea or "the topic"
    side_a = f"supporting {topic}"
    side_b = f"challenging {topic}"
    frame = topic
    return _topic(raw_idea, frame, side_a, side_b, frame)


def is_sentence_complete(text: str) -> bool:
    stripped = text.strip()
    if not stripped or stripped[-1] not in ".?!":
        return False
    terminal = _terminal_word(stripped)
    return terminal not in TERMINAL_FRAGMENT_WORDS


def keyword_terms(value: str) -> tuple[str, ...]:
    terms: list[str] = []
    for token in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", value.lower()):
        if len(token) < 2 or token in STOPWORDS:
            continue
        _append_unique(terms, token)
        singular = _singular(token)
        if singular != token and singular not in STOPWORDS:
            _append_unique(terms, singular)
        if token == "requiring":
            _append_unique(terms, "require")
            _append_unique(terms, "required")
        if token == "required":
            _append_unique(terms, "require")
            _append_unique(terms, "requiring")
        if token == "optional":
            _append_unique(terms, "option")
    return tuple(terms)


def _topic(raw_idea: str, topic: str, side_a: str, side_b: str, frame: str) -> DebateTopic:
    return DebateTopic(
        raw_idea=raw_idea,
        topic=topic,
        side_a=side_a,
        side_b=side_b,
        moderator_framing=frame,
        side_a_keywords=keyword_terms(side_a),
        side_b_keywords=keyword_terms(side_b),
    )


def _parse_explicit_sides(value: str) -> tuple[str, str] | None:
    candidates = [
        re.compile(r"^(?P<a>.+?)\s+(?:vs\.?|versus)\s+(?P<b>.+)$", re.IGNORECASE),
        re.compile(r"^(?:whether\s+)?(?P<a>.+?)\s+or\s+(?P<b>.+)$", re.IGNORECASE),
    ]
    for pattern in candidates:
        match = pattern.search(value)
        if not match:
            continue
        side_a = _strip_comparison_tail(match.group("a"))
        side_b = _strip_comparison_tail(match.group("b"))
        if side_a and side_b:
            return side_a, side_b
    return None


def _parse_proposition(value: str) -> tuple[str, str] | None:
    match = re.search(r"^(?P<subject>.+?)\s+should\s+be\s+required(?:\b.*)?$", value, re.IGNORECASE)
    if not match:
        return None
    subject = _clean_side(match.group("subject"))
    if subject:
        return subject, "required"
    return None


def _strip_debate_prefix(value: str) -> str:
    cleaned = _collapse_spaces(value.strip(" \"'?.!"))
    replacements = [
        r"^(?:please\s+)?(?:write|create|generate|make)\s+(?:a\s+|an\s+)?",
        r"^(?:a\s+|an\s+)?debate\s+(?:about|over|on)\s+",
        r"^(?:a\s+|an\s+)?debate\s+whether\s+",
        r"^whether\s+",
    ]
    previous = None
    while previous != cleaned:
        previous = cleaned
        for pattern in replacements:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def _strip_comparison_tail(value: str) -> str:
    cleaned = _collapse_spaces(value.strip(" \"'?.!,;:"))
    cleaned = re.sub(
        r"\s+(?:are|is|was|were|would\s+be|should\s+be|make|makes)\s+"
        r"(?:the\s+)?(?:better|best|stronger|more|right|correct)\b.*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return _collapse_spaces(cleaned.strip(" \"'?.!,;:"))


def _clean_side(value: str) -> str:
    cleaned = _strip_debate_prefix(_strip_comparison_tail(value))
    cleaned = re.sub(r"^(?:the\s+case\s+for|the\s+case\s+against)\s+", "", cleaned, flags=re.IGNORECASE)
    return _collapse_spaces(cleaned.strip(" \"'?.!,;:"))


def _normalize_side_b(side_b: str, side_a: str) -> str:
    if _singular(side_b.lower()) == "animal" and _singular(side_a.lower()) != "animal":
        return "other animals"
    return side_b


def _collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _terminal_word(value: str) -> str:
    tokens = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", value.lower())
    return tokens[-1] if tokens else ""


def _singular(value: str) -> str:
    lowered = value.lower().strip()
    if lowered.endswith("ies") and len(lowered) > 4:
        return f"{lowered[:-3]}y"
    if lowered.endswith("s") and not lowered.endswith("ss") and len(lowered) > 3:
        return lowered[:-1]
    return lowered


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)
