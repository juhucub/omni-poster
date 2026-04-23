from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_TEXT = "Hey, welcome back. Today we're testing a new character voice."


def _bundled_presets_path() -> Path:
    return Path(settings.BUNDLED_MEDIA_DIR) / "character_presets.json"


def _runtime_lab_dir() -> Path:
    path = Path(settings.MEDIA_DIR) / "voice_lab"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _runtime_presets_path() -> Path:
    return _runtime_lab_dir() / "character_presets.json"


def _normalize_speaker_name(value: str) -> str:
    return " ".join(value.lower().strip().split())


def _default_preset_payload(payload: dict[str, Any], source: str) -> dict[str, Any]:
    speaker_names = payload.get("speaker_names") or [payload.get("display_name") or "Speaker"]
    return {
        "id": payload.get("id") or uuid.uuid4().hex[:12],
        "display_name": payload.get("display_name") or "Speaker",
        "speaker_names": speaker_names,
        "portrait_filename": payload.get("portrait_filename"),
        "tts_provider": payload.get("tts_provider") or "espeak",
        "voice": payload.get("voice") or settings.TTS_ESPEAK_VOICE_SLOT_1,
        "rate": int(payload.get("rate") if payload.get("rate") is not None else settings.TTS_ESPEAK_RATE),
        "pitch": int(payload.get("pitch") if payload.get("pitch") is not None else settings.TTS_ESPEAK_PITCH),
        "word_gap": int(payload.get("word_gap") if payload.get("word_gap") is not None else settings.TTS_ESPEAK_WORD_GAP),
        "amplitude": int(payload.get("amplitude") if payload.get("amplitude") is not None else settings.TTS_ESPEAK_AMPLITUDE),
        "notes": payload.get("notes") or "",
        "sample_text": payload.get("sample_text") or DEFAULT_SAMPLE_TEXT,
        "source": source,
    }


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Character preset file is invalid JSON: %s", path)
        return []
    if not isinstance(payload, list):
        logger.warning("Character preset file is not a list: %s", path)
        return []
    return [item for item in payload if isinstance(item, dict)]


def _write_runtime_presets(presets: list[dict[str, Any]]) -> None:
    path = _runtime_presets_path()
    serializable = []
    for preset in presets:
        item = dict(preset)
        item.pop("source", None)
        serializable.append(item)
    path.write_text(json.dumps(serializable, indent=2) + "\n", encoding="utf-8")


def list_character_presets() -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for payload in _load_json_list(_bundled_presets_path()):
        preset = _default_preset_payload(payload, "bundled")
        merged[preset["id"]] = preset
    for payload in _load_json_list(_runtime_presets_path()):
        preset = _default_preset_payload(payload, "runtime")
        merged[preset["id"]] = preset
    presets = sorted(merged.values(), key=lambda item: (item["display_name"].lower(), item["id"]))
    logger.info("Loaded %s character presets (%s bundled path, %s runtime path)", len(presets), _bundled_presets_path(), _runtime_presets_path())
    return presets


def get_character_preset(preset_id: str) -> dict[str, Any] | None:
    for preset in list_character_presets():
        if preset["id"] == preset_id:
            return preset
    return None


def resolve_character_preset_for_speaker(speaker: str) -> dict[str, Any] | None:
    target = _normalize_speaker_name(speaker)
    for preset in list_character_presets():
        aliases = [_normalize_speaker_name(value) for value in preset.get("speaker_names", [])]
        aliases.append(_normalize_speaker_name(preset["display_name"]))
        if target in aliases:
            return preset
    return None


def upsert_character_preset(payload: dict[str, Any], preset_id: str | None = None) -> dict[str, Any]:
    runtime_presets = [_default_preset_payload(item, "runtime") for item in _load_json_list(_runtime_presets_path())]
    target_id = preset_id or payload.get("id") or uuid.uuid4().hex[:12]
    normalized = _default_preset_payload({**payload, "id": target_id}, "runtime")

    replaced = False
    for index, preset in enumerate(runtime_presets):
        if preset["id"] == target_id:
            runtime_presets[index] = normalized
            replaced = True
            break
    if not replaced:
        runtime_presets.append(normalized)

    _write_runtime_presets(runtime_presets)
    logger.info("Saved character preset %s (%s)", target_id, "updated" if replaced else "created")
    saved = get_character_preset(target_id)
    if not saved:
        raise RuntimeError(f"Failed to persist character preset {target_id}")
    return saved


def delete_character_preset(preset_id: str) -> bool:
    runtime_presets = [_default_preset_payload(item, "runtime") for item in _load_json_list(_runtime_presets_path())]
    remaining = [preset for preset in runtime_presets if preset["id"] != preset_id]
    if len(remaining) == len(runtime_presets):
        return False
    _write_runtime_presets(remaining)
    logger.info("Deleted runtime character preset %s", preset_id)
    return True


def resolve_character_portrait_path(preset: dict[str, Any] | None) -> Path | None:
    if not preset or not preset.get("portrait_filename"):
        return None
    filename = Path(str(preset["portrait_filename"])).name
    candidates = [
        Path(settings.BUNDLED_MEDIA_DIR) / "characters" / filename,
        Path(settings.MEDIA_DIR) / "characters" / filename,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def voice_lab_preview_dir() -> Path:
    path = _runtime_lab_dir() / "previews"
    path.mkdir(parents=True, exist_ok=True)
    return path
