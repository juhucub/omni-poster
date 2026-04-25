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
    get_character_preset,
    get_character_preset_model,
    get_voice_profile,
    get_voice_profile_model,
    list_character_presets,
    list_voice_profiles,
    resolve_character_portrait_path,
    runtime_voice_profile_payload,
    save_reference_audio_upload,
    upsert_character_preset,
    upsert_voice_profile,
    voice_lab_preview_dir,
)
from app.tasks.voice_preview import process_voice_lab_preview

router = APIRouter(tags=["character_presets"])


def _preview_requires_worker(profile_payload: dict, payload: VoiceLabPreviewRequest) -> bool:
    requested_provider = payload.provider_preference.strip().lower() or "auto"
    profile_provider = str(profile_payload.get("provider") or "").strip().lower()
    fallback_provider = str(profile_payload.get("fallback_provider") or "").strip().lower()
    if requested_provider == "espeak":
        return False
    if requested_provider == "openvoice":
        return True
    if profile_provider == "openvoice":
        return True
    return payload.fallback_allowed and fallback_provider == "openvoice"


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


@router.post("/voice-profiles/{voice_profile_id}/prepare", response_model=VoiceProfilePrepareResponse)
def prepare_voice_profile(
    voice_profile_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    profile_model = get_voice_profile_model(voice_profile_id, db)
    if not profile_model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found.")
    orchestrator = TTSOrchestrator()
    payload = runtime_voice_profile_payload(profile_model, profile_model.display_name)
    try:
        result = orchestrator.prepare_voice_profile(payload)
    except TTSProviderError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=exc.as_dict()) from exc
    profile = get_voice_profile(voice_profile_id, db)
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
    fallback_allowed = payload.provider_preference in {"", "auto"}
    provider_state = orchestrator.provider_state()

    if _preview_requires_worker(profile_payload, payload):
        preview_job = create_voice_preview_job(
            user_id=current_user.id,
            preset=preset_model,
            requested_provider=payload.provider_preference,
            fallback_allowed=payload.fallback_allowed,
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
            requested_provider=payload.provider_preference,
            fallback_allowed=fallback_allowed and payload.fallback_allowed,
        )
    except TTSProviderError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=exc.as_dict()) from exc
    result = segments[0]
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
