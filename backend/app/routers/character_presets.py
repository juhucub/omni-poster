from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import User
from app.schemas import (
    CharacterPresetListResponse,
    CharacterPresetRequest,
    CharacterPresetSummary,
    OkResponse,
    ProviderCapabilityListResponse,
    TTSFailureResponse,
    VoiceCalibrationMatrixRequest,
    VoiceCalibrationMatrixResponse,
    VoiceCalibrationRecipeSaveRequest,
    VoiceLabPreviewRequest,
    VoiceLabPreviewResponse,
    VoiceProfileListResponse,
    VoiceProfilePrepareResponse,
    VoiceProfileRequest,
    VoiceProfileSummary,
    VoiceReferenceAudioUploadResponse,
)
from app.services.tts import TTSOrchestrator, TTSProviderError, apply_voice_lab_overrides
from app.services.voice_preview_jobs import (
    create_voice_preview_job,
    get_voice_preview_job,
    reconcile_stale_voice_preview_jobs,
    to_voice_preview_response,
)
from app.services.voice_profiles import (
    ensure_voice_profile_editable,
    get_character_preset,
    get_character_preset_model,
    get_voice_profile,
    get_voice_profile_model,
    list_character_presets,
    list_voice_profiles,
    resolve_voice_reference_audio_artifact,
    resolve_character_portrait_path,
    runtime_voice_profile_payload,
    save_reference_audio_upload,
    update_voice_profile_calibration_recipe,
    update_voice_profile_preparation_metadata,
    upsert_character_preset,
    upsert_voice_profile,
    voice_lab_preview_dir,
)
from app.tasks.voice_preview import process_voice_lab_preview

router = APIRouter(tags=["character_presets"])

VOICE_CALIBRATION_TEST_PHRASES = [
    "I need this line to sound calm, specific, and unmistakably like me.",
    "Wait, pause there. The rhythm matters more than the words.",
    "That is the difference between a generic voice and a real character.",
]

DEFAULT_CALIBRATION_RECIPES = [
    {"base_speaker": "EN-Default", "style_preset": "default", "speaking_rate": 0.9, "pause_bias": 0.75, "pitch": -2, "energy": 0.9},
    {"base_speaker": "EN-Default", "style_preset": "default", "speaking_rate": 1.05, "pause_bias": 1.15, "pitch": 0, "energy": 1.0},
    {"base_speaker": "EN-US", "style_preset": "default", "speaking_rate": 0.95, "pause_bias": 1.0, "pitch": 1, "energy": 1.1},
    {"base_speaker": "EN-BR", "style_preset": "default", "speaking_rate": 1.0, "pause_bias": 1.25, "pitch": -1, "energy": 1.0},
]


def _calibration_recipe_controls(recipe: dict[str, object]) -> dict[str, object]:
    controls = {"speaking_rate": recipe.get("speaking_rate")}
    mapping = {
        "pause_length": recipe.get("pause_bias"),
        "pitch": recipe.get("pitch"),
        "energy": recipe.get("energy"),
        "emotion": recipe.get("emotion"),
        "accent": recipe.get("accent"),
    }
    controls.update(mapping)
    return {key: value for key, value in controls.items() if value is not None}


def _unsupported_calibration_controls(provider_name: str, orchestrator: TTSOrchestrator, recipe_controls: dict[str, object]) -> list[str]:
    capabilities = orchestrator.provider_capabilities()
    provider_capability = next((item for item in capabilities if item["provider"] == provider_name), None)
    supported = set((provider_capability or {}).get("supported_controls") or [])
    unsupported = [key for key, value in recipe_controls.items() if value is not None and key not in supported]
    if "style_preset" not in supported:
        unsupported.append("style_preset")
    return sorted(set(unsupported))


def _preview_execution_policy(
    profile_payload: dict[str, object],
    payload: VoiceLabPreviewRequest,
    orchestrator: TTSOrchestrator,
) -> dict[str, object]:
    requested_provider = payload.provider_preference.strip().lower() or "auto"
    resolved_fallback_allowed = requested_provider in {"", "auto"} and payload.fallback_allowed
    selection = orchestrator.resolve_provider_selection(
        profile_payload,
        requested_provider=requested_provider,
        fallback_allowed=resolved_fallback_allowed,
    )
    selected_provider = str(selection.get("selected_provider") or requested_provider or profile_payload.get("provider") or "espeak").lower()
    return {
        "requested_provider": requested_provider,
        "selected_provider": selected_provider,
        "fallback_allowed": resolved_fallback_allowed if requested_provider in {"", "auto"} else False,
        "requires_worker": selected_provider == "openvoice",
        "provider_state": selection["provider_state"],
    }


@router.get("/character-presets", response_model=CharacterPresetListResponse)
def get_character_presets(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ = current_user
    return CharacterPresetListResponse(items=[CharacterPresetSummary(**preset) for preset in list_character_presets(db)])


@router.post("/character-presets", response_model=CharacterPresetSummary, status_code=status.HTTP_201_CREATED)
def create_character_preset(
    payload: CharacterPresetRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    preset = upsert_character_preset(payload.model_dump(), current_user.id, db)
    return CharacterPresetSummary(**preset)


@router.put("/character-presets/{preset_id}", response_model=CharacterPresetSummary)
def update_character_preset(
    preset_id: str,
    payload: CharacterPresetRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    preset = upsert_character_preset(payload.model_dump(), current_user.id, db, preset_id=preset_id)
    return CharacterPresetSummary(**preset)


@router.delete("/character-presets/{preset_id}", response_model=OkResponse)
def remove_character_preset(
    preset_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.voice_profiles import delete_character_preset

    if not delete_character_preset(preset_id, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character preset not found.")
    return OkResponse()


@router.get("/character-presets/{preset_id}/portrait")
def get_character_preset_portrait(
    preset_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    preset = get_character_preset(preset_id, db)
    if not preset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character preset not found.")
    portrait_path = resolve_character_portrait_path(preset)
    if not portrait_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portrait not found for character preset.")
    return FileResponse(portrait_path, media_type="image/png", filename=portrait_path.name)


@router.get("/voice-profiles", response_model=VoiceProfileListResponse)
def get_voice_profiles(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ = current_user
    return VoiceProfileListResponse(items=[VoiceProfileSummary(**item) for item in list_voice_profiles(db)])


@router.post("/voice-profiles", response_model=VoiceProfileSummary, status_code=status.HTTP_201_CREATED)
def create_voice_profile(
    payload: VoiceProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = upsert_voice_profile(payload.model_dump(), current_user.id, db)
    return VoiceProfileSummary(**profile)


@router.put("/voice-profiles/{voice_profile_id}", response_model=VoiceProfileSummary)
def update_voice_profile(
    voice_profile_id: str,
    payload: VoiceProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = upsert_voice_profile(payload.model_dump(), current_user.id, db, profile_id=voice_profile_id)
    return VoiceProfileSummary(**profile)


@router.post("/voice-profiles/reference-audio", response_model=VoiceReferenceAudioUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_reference_audio(
    voice_profile_id: str = Form(...),
    authorization_confirmed: bool = Form(...),
    authorization_note: str | None = Form(default=None),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    voice_profile, reference_audio = save_reference_audio_upload(
        file=file,
        voice_profile_id=voice_profile_id,
        current_user_id=current_user.id,
        authorization_confirmed=authorization_confirmed,
        authorization_note=authorization_note,
        db=db,
    )
    return VoiceReferenceAudioUploadResponse(
        voice_profile=VoiceProfileSummary(**voice_profile),
        reference_audio=reference_audio,
    )


@router.get("/voice-profiles/{voice_profile_id}/reference-audio/{reference_audio_id}/{artifact_kind}")
def get_voice_reference_audio_artifact(
    voice_profile_id: str,
    reference_audio_id: int,
    artifact_kind: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    artifact = resolve_voice_reference_audio_artifact(
        voice_profile_id=voice_profile_id,
        reference_audio_id=reference_audio_id,
        artifact_kind=artifact_kind,
        current_user_id=current_user.id,
        db=db,
    )
    media_type = "audio/wav" if artifact.suffix.lower() == ".wav" else "application/octet-stream"
    return FileResponse(
        artifact,
        media_type=media_type,
        filename=artifact.name,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/voice-profiles/{voice_profile_id}/prepare", response_model=VoiceProfilePrepareResponse)
def prepare_voice_profile(
    voice_profile_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile_model = get_voice_profile_model(voice_profile_id, db)
    if not profile_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found.")
    ensure_voice_profile_editable(profile_model, current_user.id)
    orchestrator = TTSOrchestrator()
    payload = runtime_voice_profile_payload(profile_model, profile_model.display_name)
    try:
        result = orchestrator.prepare_voice_profile(payload)
    except TTSProviderError as exc:
        profile_model.embedding_path = None
        metadata = dict(profile_model.provider_metadata_json or {})
        metadata.update(
            {
                "embedding_status": "failed",
                "embedding_ready": False,
                "embedding_artifact_path": None,
                "last_error": exc.as_dict(),
            }
        )
        profile_model.provider_metadata_json = metadata
        db.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=exc.as_dict()) from exc
    profile_model = update_voice_profile_preparation_metadata(
        profile_model,
        embedding_path=result.get("cached_artifact_path"),
        provider_metadata=result.get("provider_metadata"),
        db=db,
    )
    profile = get_voice_profile(profile_model.id, db)
    return VoiceProfilePrepareResponse(
        voice_profile=VoiceProfileSummary(**profile),
        provider_used=result["provider_used"],
        provider_state=result["provider_state"],
        prepared=result["prepared"],
        cached_artifact_path=result.get("cached_artifact_path"),
        message=result["message"],
    )


@router.get("/tts/providers", response_model=ProviderCapabilityListResponse)
def get_tts_provider_capabilities(current_user: User = Depends(get_current_user)):
    _ = current_user
    orchestrator = TTSOrchestrator()
    return ProviderCapabilityListResponse(items=orchestrator.provider_capabilities())


@router.post(
    "/voice-lab/preview",
    response_model=VoiceLabPreviewResponse,
    responses={503: {"model": TTSFailureResponse}},
)
def create_voice_lab_preview(
    payload: VoiceLabPreviewRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    preset_model = get_character_preset_model(payload.preset_id, db)
    if not preset_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character preset not found.")

    preview_dir = voice_lab_preview_dir()
    profile_payload = runtime_voice_profile_payload(preset_model.voice_profile, preset_model.display_name)
    profile_payload = apply_voice_lab_overrides(
        profile_payload,
        controls=payload.controls,
        rate=payload.rate,
        pitch=payload.pitch,
        word_gap=payload.word_gap,
        amplitude=payload.amplitude,
    )
    orchestrator = TTSOrchestrator()
    execution_policy = _preview_execution_policy(profile_payload, payload, orchestrator)
    provider_state = dict(execution_policy["provider_state"])
    selected_provider = str(execution_policy["selected_provider"])
    resolved_fallback_allowed = bool(execution_policy["fallback_allowed"])

    if execution_policy["requires_worker"]:
        preview_job = create_voice_preview_job(
            user_id=current_user.id,
            preset=preset_model,
            requested_provider=selected_provider,
            fallback_allowed=resolved_fallback_allowed,
            sample_text=payload.text,
            controls_applied=dict(profile_payload.get("controls") or {}),
            provider_state=provider_state,
            reference_audio_count=len(profile_payload.get("reference_audios") or []),
            db=db,
        )
        db.commit()
        celery_task_id = f"voice-preview-{preview_job.id}"
        try:
            process_voice_lab_preview.apply_async(
                kwargs={"preview_job_id": preview_job.id},
                task_id=celery_task_id,
            )
            preview_job.celery_task_id = celery_task_id
            db.commit()
            db.refresh(preview_job)
        except Exception as exc:
            preview_job.status = "failed"
            preview_job.stage = "failed"
            preview_job.error_json = {
                "code": "preview_queue_failed",
                "message": f"Voice preview could not be queued: {exc}",
                "provider_state": provider_state,
                "fallback_attempted": False,
                "attempted_providers": [],
                "provider_failures": {},
                "suggested_action": "Check the worker and broker configuration, then retry the preview.",
            }
            db.commit()
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=preview_job.error_json) from exc
        response.status_code = status.HTTP_202_ACCEPTED
        return to_voice_preview_response(preview_job)

    try:
        segments = orchestrator.synthesize_dialogue(
            lines=[{"speaker": preset_model.display_name, "text": payload.text, "order": 0}],
            voice_profile_map={preset_model.display_name: profile_payload},
            output_dir=preview_dir,
            requested_provider=selected_provider,
            fallback_allowed=resolved_fallback_allowed,
        )
    except TTSProviderError as exc:
        preset_model.voice_profile.embedding_path = None
        metadata = dict(preset_model.voice_profile.provider_metadata_json or {})
        metadata.update(
            {
                "embedding_status": "failed",
                "embedding_ready": False,
                "embedding_artifact_path": None,
                "last_error": exc.as_dict(),
            }
        )
        preset_model.voice_profile.provider_metadata_json = metadata
        db.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=exc.as_dict()) from exc
    result = segments[0]
    if result.provider_used == "openvoice" and profile_payload.get("embedding_path"):
        provider_metadata = dict(profile_payload.get("provider_metadata") or {})
        update_voice_profile_preparation_metadata(
            preset_model.voice_profile,
            embedding_path=str(profile_payload.get("embedding_path")),
            provider_metadata={
                **provider_metadata,
                "embedding_status": "ready",
                "embedding_ready": True,
                "embedding_artifact_path": str(profile_payload.get("embedding_path")),
                "active_reference_count": len(profile_payload.get("reference_audios") or []),
                "reference_audio_mode": "average_all_clips" if len(profile_payload.get("reference_audios") or []) > 1 else "single_clip",
            },
            db=db,
        )
    audio_path = Path(result.audio_path)
    return VoiceLabPreviewResponse(
        status="completed",
        preset_id=preset_model.id,
        voice_profile_id=result.voice_profile_id,
        voice=result.voice,
        provider_used=result.provider_used,
        fallback_used=result.fallback_used,
        controls_applied=result.controls_applied or {},
        reference_audio_count=result.reference_audio_count,
        provider_state=provider_state,
        duration_seconds=result.duration_seconds,
        sample_text=payload.text,
        content_url=f"/voice-lab/previews/{audio_path.name}",
        error=None,
    )


@router.post("/voice-lab/calibration-matrix", response_model=VoiceCalibrationMatrixResponse, status_code=status.HTTP_202_ACCEPTED)
def create_voice_lab_calibration_matrix(
    payload: VoiceCalibrationMatrixRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    preset_model = get_character_preset_model(payload.preset_id, db)
    if not preset_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character preset not found.")
    ensure_voice_profile_editable(preset_model.voice_profile, current_user.id)

    orchestrator = TTSOrchestrator()
    profile_payload = runtime_voice_profile_payload(preset_model.voice_profile, preset_model.display_name)
    requested_provider = (payload.provider_preference or "openvoice").strip().lower()
    fallback_allowed = bool(payload.fallback_allowed) if requested_provider in {"", "auto"} else False
    selection = orchestrator.resolve_provider_selection(
        profile_payload,
        requested_provider=requested_provider,
        fallback_allowed=fallback_allowed,
    )
    selected_provider = str(selection.get("selected_provider") or requested_provider or profile_payload.get("provider") or "openvoice").lower()
    provider_state = dict(selection["provider_state"])
    provider_capabilities = orchestrator.provider_capabilities()
    provider_capability = next((item for item in provider_capabilities if item["provider"] == selected_provider), None)
    supported_controls = list((provider_capability or {}).get("supported_controls") or [])
    phrases = [phrase.strip() for phrase in (payload.phrases or VOICE_CALIBRATION_TEST_PHRASES) if phrase.strip()]
    phrases = phrases[:6] or VOICE_CALIBRATION_TEST_PHRASES[:1]
    recipes = [item.model_dump() for item in payload.recipes] or [dict(item) for item in DEFAULT_CALIBRATION_RECIPES]
    recipes = recipes[:8]

    responses: list[VoiceLabPreviewResponse] = []
    unsupported_seen: set[str] = set()
    for recipe_index, recipe in enumerate(recipes):
        controls = _calibration_recipe_controls(recipe)
        unsupported_controls = _unsupported_calibration_controls(selected_provider, orchestrator, controls)
        unsupported_seen.update(unsupported_controls)
        calibration = {
            "kind": "voice_profile_calibration",
            "recipe_index": recipe_index,
            "recipe": recipe,
            "controls": controls,
            "supported_controls": supported_controls,
            "unsupported_controls": unsupported_controls,
            "processed_reference_paths": list((profile_payload.get("provider_metadata") or {}).get("processed_reference_paths") or []),
            "processed_reference_audio_ids": list((profile_payload.get("provider_metadata") or {}).get("processed_reference_audio_ids") or []),
            "embedding_path": profile_payload.get("embedding_path") or (profile_payload.get("provider_metadata") or {}).get("embedding_artifact_path"),
            "reference_audio_sha256": (profile_payload.get("provider_metadata") or {}).get("reference_audio_sha256"),
        }
        for phrase_index, phrase in enumerate(phrases):
            preview_job = create_voice_preview_job(
                user_id=current_user.id,
                preset=preset_model,
                requested_provider=selected_provider,
                fallback_allowed=fallback_allowed,
                sample_text=phrase,
                controls_applied=controls,
                provider_state=provider_state,
                reference_audio_count=len(profile_payload.get("reference_audios") or []),
                db=db,
                calibration={
                    **calibration,
                    "phrase_index": phrase_index,
                    "phrase": phrase,
                },
            )
            db.commit()
            celery_task_id = f"voice-calibration-{preview_job.id}"
            try:
                process_voice_lab_preview.apply_async(
                    kwargs={"preview_job_id": preview_job.id},
                    task_id=celery_task_id,
                )
                preview_job.celery_task_id = celery_task_id
                db.commit()
                db.refresh(preview_job)
            except Exception as exc:
                preview_job.status = "failed"
                preview_job.stage = "failed"
                preview_job.error_json = {
                    "code": "calibration_queue_failed",
                    "message": f"Voice calibration preview could not be queued: {exc}",
                    "provider_state": provider_state,
                    "fallback_attempted": False,
                    "attempted_providers": [],
                    "provider_failures": {},
                    "suggested_action": "Check the worker and broker configuration, then retry calibration.",
                }
                db.commit()
            responses.append(to_voice_preview_response(preview_job))

    return VoiceCalibrationMatrixResponse(
        preset_id=preset_model.id,
        voice_profile_id=preset_model.voice_profile_id,
        provider_state=provider_state,
        unsupported_controls=sorted(unsupported_seen),
        items=responses,
    )


@router.post("/voice-profiles/{voice_profile_id}/calibration-recipe", response_model=VoiceProfileSummary)
def save_voice_profile_calibration_recipe(
    voice_profile_id: str,
    payload: VoiceCalibrationRecipeSaveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile_model = get_voice_profile_model(voice_profile_id, db)
    if not profile_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found.")
    ensure_voice_profile_editable(profile_model, current_user.id)
    profile_model = update_voice_profile_calibration_recipe(
        profile_model,
        recipe=payload.recipe.model_dump(),
        db=db,
    )
    profile = get_voice_profile(profile_model.id, db)
    return VoiceProfileSummary(**profile)


@router.get("/voice-lab/preview-jobs/{job_id}", response_model=VoiceLabPreviewResponse)
def get_voice_lab_preview_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reconciled = reconcile_stale_voice_preview_jobs(db, user_id=current_user.id)
    if reconciled:
        db.commit()

    job = get_voice_preview_job(job_id, current_user.id, db)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice preview job not found.")
    return to_voice_preview_response(job)


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
