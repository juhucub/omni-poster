from __future__ import annotations

import glob
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import REPO_ROOT, settings


SUPPORTED_FILE_RECIPE_CHARACTERS = {"stewie_griffin"}
XTTS_CHECKPOINT_FILENAMES = ("model.pth", "model.pt", "checkpoint.pth", "checkpoint.pt")
XTTS_CHECKPOINT_SUFFIXES = (".pth", ".pt", ".safetensors")


class CharacterVoiceRecipeError(RuntimeError):
    def __init__(self, *, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


@dataclass(frozen=True)
class CharacterVoiceRecipe:
    character: str
    provider: str
    checkpoint_dir: Path
    checkpoint_file: Path
    config_path: Path
    vocab_path: Path
    reference_wavs: list[Path]
    golden_preview_wav: Path
    language: str
    settings: dict[str, Any]
    raw: dict[str, Any]

    def public_payload(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "character": self.character,
            "checkpoint_dir": str(self.checkpoint_dir),
            "checkpoint_file": str(self.checkpoint_file),
            "reference_wavs": [str(path) for path in self.reference_wavs],
            "reference_wav_count": len(self.reference_wavs),
            "golden_preview": str(self.golden_preview_wav),
            "language": self.language,
            "recipe": dict(self.settings),
            "render_verified": bool(self.raw.get("render_verified")),
            "status": str(self.raw.get("status") or "ready_for_test_render"),
        }


def selected_recipe_path(character: str) -> Path:
    return Path(settings.VOICE_MODELS_DIR) / character / "selected_recipe.json"


def _resolve_existing_path(value: str | None) -> Path | None:
    if not value:
        return None
    candidate = Path(value)
    candidates = [candidate] if candidate.is_absolute() else [candidate, REPO_ROOT / candidate]
    for item in candidates:
        if item.exists():
            return item
    return candidates[0]


def _path_pair(recipe: dict[str, Any], local_key: str, container_key: str) -> tuple[Path | None, str | None]:
    for key in (container_key, local_key):
        resolved = _resolve_existing_path(str(recipe.get(key) or ""))
        if resolved and resolved.exists():
            return resolved, key
    for key in (local_key, container_key):
        raw = str(recipe.get(key) or "")
        if raw:
            return _resolve_existing_path(raw), key
    return None, None


def _expand_reference_wavs(recipe: dict[str, Any]) -> tuple[list[Path], str | None]:
    patterns: list[tuple[str, str]] = []
    for key in ("reference_wavs_container", "reference_wavs_local"):
        raw = recipe.get(key)
        if isinstance(raw, str):
            patterns.append((key, raw))
        elif isinstance(raw, list):
            patterns.extend((key, str(item)) for item in raw if item)

    first_key: str | None = None
    matched: list[Path] = []
    for key, pattern in patterns:
        base_pattern = str(_resolve_existing_path(pattern) or pattern)
        paths = [Path(item) for item in sorted(glob.glob(base_pattern))]
        paths = [path for path in paths if path.exists() and path.suffix.lower() == ".wav"]
        if paths:
            first_key = key
            matched.extend(paths)
            break
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in matched:
        marker = str(path.resolve())
        if marker not in seen:
            deduped.append(path)
            seen.add(marker)
    return deduped, first_key


def _find_checkpoint_file(checkpoint_dir: Path) -> Path | None:
    for name in XTTS_CHECKPOINT_FILENAMES:
        candidate = checkpoint_dir / name
        if candidate.exists():
            return candidate
    for candidate in sorted(checkpoint_dir.iterdir()) if checkpoint_dir.exists() else []:
        if candidate.is_file() and candidate.suffix.lower() in XTTS_CHECKPOINT_SUFFIXES:
            return candidate
    return None


def load_selected_character_recipe(character: str = "stewie_griffin") -> dict[str, Any]:
    if character not in SUPPORTED_FILE_RECIPE_CHARACTERS:
        raise CharacterVoiceRecipeError(
            code="character_recipe_not_supported",
            message=f"Selected-recipe file loading is currently enabled only for: {', '.join(sorted(SUPPORTED_FILE_RECIPE_CHARACTERS))}.",
            details={"character": character},
        )
    path = selected_recipe_path(character)
    if not path.exists():
        raise CharacterVoiceRecipeError(
            code="selected_recipe_missing",
            message=f"Selected recipe is missing: {path}",
            details={"character": character, "path": str(path)},
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CharacterVoiceRecipeError(
            code="selected_recipe_invalid_json",
            message=f"Selected recipe is not valid JSON: {path}",
            details={"character": character, "path": str(path)},
        ) from exc
    if not isinstance(payload, dict):
        raise CharacterVoiceRecipeError(
            code="selected_recipe_invalid_shape",
            message="Selected recipe must be a JSON object.",
            details={"character": character, "path": str(path)},
        )
    return payload


def validate_selected_character_recipe(character: str = "stewie_griffin", recipe: dict[str, Any] | None = None) -> CharacterVoiceRecipe:
    payload = dict(recipe or load_selected_character_recipe(character))
    required = ["provider", "character", "language", "recipe"]
    missing = [key for key in required if not payload.get(key)]
    if not (payload.get("xtts_checkpoint_dir_local") or payload.get("xtts_checkpoint_dir_container")):
        missing.append("xtts_checkpoint_dir_local or xtts_checkpoint_dir_container")
    if not (payload.get("reference_wavs_local") or payload.get("reference_wavs_container")):
        missing.append("reference_wavs_local or reference_wavs_container")
    if not (payload.get("golden_preview_local") or payload.get("golden_preview_container") or payload.get("golden_preview")):
        missing.append("golden_preview_local or golden_preview_container")
    if missing:
        raise CharacterVoiceRecipeError(
            code="selected_recipe_missing_fields",
            message=f"Selected recipe is missing required fields: {', '.join(missing)}.",
            details={"character": character, "missing_fields": missing},
        )

    provider = str(payload["provider"]).strip().lower()
    payload_character = str(payload["character"]).strip().lower()
    if provider != "xtts":
        raise CharacterVoiceRecipeError(
            code="selected_recipe_provider_unsupported",
            message=f"Only provider='xtts' is supported for this Stewie golden-recipe slice; got {provider!r}.",
            details={"character": character, "provider": provider},
        )
    if payload_character != character:
        raise CharacterVoiceRecipeError(
            code="selected_recipe_character_mismatch",
            message=f"Selected recipe character mismatch: expected {character}, got {payload_character}.",
            details={"expected_character": character, "actual_character": payload_character},
        )

    checkpoint_dir, checkpoint_key = _path_pair(payload, "xtts_checkpoint_dir_local", "xtts_checkpoint_dir_container")
    if not checkpoint_dir or not checkpoint_dir.exists() or not checkpoint_dir.is_dir():
        raise CharacterVoiceRecipeError(
            code="xtts_checkpoint_dir_missing",
            message=f"XTTS checkpoint directory is missing: {checkpoint_dir}",
            details={"character": character, "source_field": checkpoint_key, "path": str(checkpoint_dir)},
        )
    config_path = checkpoint_dir / "config.json"
    vocab_path = checkpoint_dir / "vocab.json"
    missing_checkpoint_files = [str(path) for path in (config_path, vocab_path) if not path.exists()]
    checkpoint_file = _find_checkpoint_file(checkpoint_dir)
    if not checkpoint_file:
        missing_checkpoint_files.append("model.pth or equivalent checkpoint file")
    if missing_checkpoint_files:
        raise CharacterVoiceRecipeError(
            code="xtts_checkpoint_files_missing",
            message=f"XTTS checkpoint directory is incomplete: {', '.join(missing_checkpoint_files)}.",
            details={"character": character, "checkpoint_dir": str(checkpoint_dir), "missing_files": missing_checkpoint_files},
        )

    reference_wavs, reference_key = _expand_reference_wavs(payload)
    if not reference_wavs:
        raise CharacterVoiceRecipeError(
            code="xtts_reference_wavs_missing",
            message="No Stewie XTTS reference WAVs matched the selected recipe.",
            details={
                "character": character,
                "source_field": reference_key,
                "reference_wavs_local": payload.get("reference_wavs_local"),
                "reference_wavs_container": payload.get("reference_wavs_container"),
            },
        )

    golden_preview, golden_key = _path_pair(payload, "golden_preview_local", "golden_preview_container")
    if not golden_preview:
        golden_preview = _resolve_existing_path(str(payload.get("golden_preview") or ""))
        golden_key = "golden_preview"
    if not golden_preview or not golden_preview.exists() or golden_preview.suffix.lower() != ".wav":
        raise CharacterVoiceRecipeError(
            code="golden_preview_missing",
            message=f"Golden preview WAV is missing: {golden_preview}",
            details={"character": character, "source_field": golden_key, "path": str(golden_preview)},
        )

    settings_payload = dict(payload.get("recipe") or {})
    return CharacterVoiceRecipe(
        character=character,
        provider=provider,
        checkpoint_dir=checkpoint_dir,
        checkpoint_file=checkpoint_file,
        config_path=config_path,
        vocab_path=vocab_path,
        reference_wavs=reference_wavs,
        golden_preview_wav=golden_preview,
        language=str(payload.get("language") or "en"),
        settings=settings_payload,
        raw=payload,
    )


def selected_character_recipe_status(character: str = "stewie_griffin") -> dict[str, Any]:
    try:
        recipe = validate_selected_character_recipe(character)
    except CharacterVoiceRecipeError as exc:
        return {
            "character": character,
            "status": "missing_files" if "missing" in exc.code else "invalid_recipe",
            "ready_for_test_render": False,
            "render_verified": False,
            "error": exc.as_dict(),
        }
    return {
        **recipe.public_payload(),
        "ready_for_test_render": True,
        "golden_preview_url": f"/voice-models/{character}/golden-preview",
        "status": "golden_preview_selected" if not recipe.raw.get("render_verified") else "render_verified",
    }
