from __future__ import annotations

import re

from fastapi import HTTPException, status

SCRIPT_LINE_RE = re.compile(r"^\s*<([^>]+)>\s*(.+?)\s*$")


def parse_dialogue_script(raw_text: str) -> tuple[list[dict], list[str]]:
    lines: list[dict] = []
    characters: list[str] = []

    for index, raw_line in enumerate(raw_text.splitlines()):
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

        speaker = match.group(1).strip()
        text = match.group(2).strip()
        if speaker not in characters:
            characters.append(speaker)
        lines.append({"speaker": speaker, "text": text, "order": len(lines)})

    if not lines:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Script must include at least one dialogue line.",
        )

    return lines, characters
