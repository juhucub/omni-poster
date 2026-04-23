from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.dependencies import get_current_user
from app.models import User
from app.schemas import (
    CharacterPresetListResponse,
    CharacterPresetRequest,
    CharacterPresetSummary,
    OkResponse,
    VoiceLabPreviewRequest,
    VoiceLabPreviewResponse,
)
from app.services.character_presets import (
    delete_character_preset,
    get_character_preset,
    list_character_presets,
    resolve_character_portrait_path,
    upsert_character_preset,
    voice_lab_preview_dir,
)
from app.services.tts import LocalSpeechService, TextToSpeechError

router = APIRouter(tags=["character_presets"])


def _to_summary(preset: dict) -> CharacterPresetSummary:
    portrait_path = resolve_character_portrait_path(preset)
    return CharacterPresetSummary(
        id=preset["id"],
        display_name=preset["display_name"],
        speaker_names=list(preset.get("speaker_names", [])),
        portrait_filename=preset.get("portrait_filename"),
        portrait_url=f"/character-presets/{preset['id']}/portrait" if portrait_path else None,
        tts_provider=preset["tts_provider"],
        voice=preset["voice"],
        rate=preset["rate"],
        pitch=preset["pitch"],
        word_gap=preset["word_gap"],
        amplitude=preset["amplitude"],
        notes=preset.get("notes", ""),
        sample_text=preset.get("sample_text", ""),
        source=preset.get("source", "runtime"),
    )


@router.get("/character-presets", response_model=CharacterPresetListResponse)
def get_character_presets(current_user: User = Depends(get_current_user)):
    _ = current_user
    return CharacterPresetListResponse(items=[_to_summary(preset) for preset in list_character_presets()])


@router.post("/character-presets", response_model=CharacterPresetSummary, status_code=status.HTTP_201_CREATED)
def create_character_preset(
    payload: CharacterPresetRequest,
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    preset = upsert_character_preset(payload.model_dump())
    return _to_summary(preset)


@router.put("/character-presets/{preset_id}", response_model=CharacterPresetSummary)
def update_character_preset(
    preset_id: str,
    payload: CharacterPresetRequest,
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    preset = upsert_character_preset(payload.model_dump(), preset_id=preset_id)
    return _to_summary(preset)


@router.delete("/character-presets/{preset_id}", response_model=OkResponse)
def remove_character_preset(
    preset_id: str,
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    if not delete_character_preset(preset_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character preset not found in runtime overrides.")
    return OkResponse()


@router.get("/character-presets/{preset_id}/portrait")
def get_character_preset_portrait(
    preset_id: str,
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    preset = get_character_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character preset not found.")
    portrait_path = resolve_character_portrait_path(preset)
    if not portrait_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portrait not found for character preset.")
    return FileResponse(portrait_path, media_type="image/png", filename=portrait_path.name)


@router.post("/voice-lab/preview", response_model=VoiceLabPreviewResponse)
def create_voice_lab_preview(
    payload: VoiceLabPreviewRequest,
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    preset = get_character_preset(payload.preset_id)
    if not preset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character preset not found.")

    preview_dir = voice_lab_preview_dir()
    service = LocalSpeechService(
        speaker_voice_overrides={
            preset["display_name"]: {
                "tts_provider": preset.get("tts_provider", "espeak"),
                "voice": preset["voice"],
                "rate": payload.rate or preset["rate"],
                "pitch": payload.pitch or preset["pitch"],
                "word_gap": payload.word_gap if payload.word_gap is not None else preset["word_gap"],
                "amplitude": payload.amplitude or preset["amplitude"],
            }
        }
    )
    try:
        segments = service.synthesize_dialogue(
            [{"speaker": preset["display_name"], "text": payload.text, "order": 0}],
            preview_dir,
        )
    except TextToSpeechError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    audio_path = Path(segments[0].audio_path)
    return VoiceLabPreviewResponse(
        preset_id=preset["id"],
        voice=segments[0].voice,
        duration_seconds=segments[0].duration_seconds,
        sample_text=payload.text,
        content_url=f"/voice-lab/previews/{audio_path.name}",
    )


@router.get("/voice-lab/previews/{filename}")
def get_voice_lab_preview(
    filename: str,
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    preview_path = voice_lab_preview_dir() / Path(filename).name
    if not preview_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice preview not found.")
    return FileResponse(preview_path, media_type="audio/wav", filename=preview_path.name)
