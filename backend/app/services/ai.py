from __future__ import annotations

from app.models import Project, ScriptRevision


def suggest_metadata_from_script(project: Project, platform: str) -> dict:
    script: ScriptRevision | None = project.current_script_revision
    script_lines = script.parsed_lines_json if script else []
    title_seed = script_lines[0]["text"][:60] if script_lines else project.name
    tags = [speaker.lower().replace(" ", "-") for speaker in (script.characters_json if script else [])][:5]
    return {
        "title": title_seed,
        "description": project.current_script_revision.raw_text[:5000] if project.current_script_revision else "",
        "tags": tags,
        "extras": {
            "hook": script_lines[0]["text"] if script_lines else project.name,
            "platform": platform,
        },
        "provider": "template-metadata",
    }
