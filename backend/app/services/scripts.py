from __future__ import annotations

import re
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import ScriptLineItem, ScriptRevision
from app.schemas import ScriptLine

SCRIPT_LINE_RE = re.compile(r"^\s*<([^>]+)>\s*(.+?)\s*$")


def _normalize_script_line(speaker: str, text: str, order: int, line_id: int | None = None) -> dict:
    normalized_speaker = speaker.strip()
    normalized_text = text.strip()
    if not normalized_speaker or not normalized_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Each script line must include a speaker and dialogue text.",
        )
    return {
        "id": line_id,
        "speaker": normalized_speaker,
        "text": normalized_text,
        "order": order,
    }


def parse_dialogue_script(raw_text: str) -> tuple[list[dict], list[str]]:
    lines: list[dict] = []
    characters: list[str] = []

    for raw_line in raw_text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue

        match = SCRIPT_LINE_RE.match(stripped)
        if not match:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Invalid script format. Each non-empty line must follow "
                    "`<Character> dialogue text`."
                ),
            )

        line = _normalize_script_line(match.group(1), match.group(2), len(lines))
        if line["speaker"] not in characters:
            characters.append(line["speaker"])
        lines.append(line)

    if not lines:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Script must include at least one dialogue line.",
        )

    return lines, characters


def parse_script_lines(lines: Iterable[ScriptLine | dict]) -> tuple[list[dict], list[str]]:
    normalized: list[dict] = []
    characters: list[str] = []

    for index, line in enumerate(lines):
        speaker = line.speaker if isinstance(line, ScriptLine) else line.get("speaker")
        text = line.text if isinstance(line, ScriptLine) else line.get("text")
        line_id = line.id if isinstance(line, ScriptLine) else line.get("id")
        normalized_line = _normalize_script_line(speaker, text, index, line_id=line_id)
        normalized.append(normalized_line)
        if normalized_line["speaker"] not in characters:
            characters.append(normalized_line["speaker"])

    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Script must include at least one dialogue line.",
        )

    return normalized, characters


def lines_to_raw_text(lines: Iterable[dict]) -> str:
    return "\n".join(f"<{line['speaker']}> {line['text']}" for line in lines)


def save_script_revision(
    db: Session,
    *,
    project_id: int,
    raw_text: str | None,
    parsed_lines: list[ScriptLine] | list[dict] | None,
    source: str,
    parent_revision_id: int | None = None,
    generation_provider: str | None = None,
) -> ScriptRevision:
    if parsed_lines is not None:
        normalized_lines, characters = parse_script_lines(parsed_lines)
        normalized_raw_text = lines_to_raw_text(normalized_lines)
    else:
        normalized_raw_text = raw_text or ""
        normalized_lines, characters = parse_dialogue_script(normalized_raw_text)

    db.query(ScriptRevision).filter(
        ScriptRevision.project_id == project_id,
        ScriptRevision.is_current.is_(True),
    ).update({"is_current": False})

    revision = ScriptRevision(
        project_id=project_id,
        parent_revision_id=parent_revision_id,
        raw_text=normalized_raw_text,
        parsed_lines_json=normalized_lines,
        characters_json=characters,
        source=source,
        generation_provider=generation_provider,
        is_current=True,
    )
    db.add(revision)
    db.flush()

    for line in normalized_lines:
        db.add(
            ScriptLineItem(
                revision_id=revision.id,
                line_order=line["order"],
                speaker=line["speaker"],
                text=line["text"],
            )
        )
    db.flush()
    return revision


def generate_script_draft(prompt: str, character_names: list[str], tone: str) -> tuple[str, str]:
    names = [name.strip() for name in character_names if name.strip()]
    if len(names) < 2:
        names = ["Host", "Guest"]

    lines = [
        f"<{names[0]}> Today we're breaking down {prompt.strip()}.",
        f"<{names[1]}> We'll keep it {tone.strip()} and easy to follow from start to finish.",
        f"<{names[0]}> First, here's the key idea everyone should understand about {prompt.strip()}.",
        f"<{names[1]}> Then we can show the viewer what matters most and why it changes the outcome.",
        f"<{names[0]}> Finally, we wrap with one clear takeaway and the next best action.",
    ]
    return "\n".join(lines), "template-dialogue"
