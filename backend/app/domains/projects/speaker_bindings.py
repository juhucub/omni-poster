from __future__ import annotations


def extract_script_speaker_samples(parsed_lines: list[dict]) -> dict[str, str]:
    """Return the first sample text line for each speaker in the parsed script."""
    result: dict[str, str] = {}
    for line in parsed_lines:
        speaker = str(line.get("speaker") or "").strip()
        text = str(line.get("text") or "").strip()
        if speaker and text and speaker not in result:
            result[speaker] = text
    return result
