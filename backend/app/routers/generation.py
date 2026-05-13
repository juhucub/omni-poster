from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.http_rate_limit import enforce_rate_limit
from app.dependencies import get_current_user, get_db
from app.models import Asset, GenerationJob, OutputVideo, Project, User
from app.routers.projects import get_owned_project
from app.schemas import (
    GenerationJobCreateRequest,
    GenerationJobListResponse,
    GenerationJobSummary,
    OkResponse,
    OutputVideoListResponse,
)
from app.services.audit import record_audit
from app.services.notifications import create_notification
from app.services.project_state import sync_project_state, to_generation_summary, to_output_video_summary, to_project_preview_settings
from app.services.storage import guess_mime_type, resolve_generated_job_artifact
from app.services.voice_profiles import (
    character_preset_portrait_url,
    get_character_preset_model,
    resolve_preset_for_project_speaker,
    runtime_voice_profile_payload,
)
from app.tasks.generation import (
    ACTIVE_GENERATION_STATUSES,
    process_generation_job,
    reconcile_stale_generation_jobs,
)

router = APIRouter(tags=["generation"])


def _slugify(value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")
    return slug or "speaker"


def latest_background_asset(project: Project) -> Asset | None:
    if project.background_asset_id:
        return next((asset for asset in project.assets if asset.id == project.background_asset_id), None)
    assets = [asset for asset in project.assets if asset.kind in {"background_video", "background_preset", "background_image"}]
    assets.sort(key=lambda asset: asset.created_at, reverse=True)
    return assets[0] if assets else None


def _default_voice_profile_payload(speaker: str, slot_index: int) -> dict:
    default_voice = settings.TTS_ESPEAK_VOICE_SLOT_1 if slot_index % 2 == 0 else settings.TTS_ESPEAK_VOICE_SLOT_2
    return {
        "id": f"ephemeral_{_slugify(speaker)}",
        "display_name": speaker,
        "provider": "espeak",
        "fallback_provider": "espeak",
        "voice": default_voice,
        "espeak_voice": default_voice,
        "espeak_rate": settings.TTS_ESPEAK_RATE,
        "espeak_pitch": settings.TTS_ESPEAK_PITCH,
        "espeak_word_gap": settings.TTS_ESPEAK_WORD_GAP,
        "espeak_amplitude": settings.TTS_ESPEAK_AMPLITUDE,
        "controls": {},
        "style": {},
        "fallback_voice_settings": {
            "voice": default_voice,
            "rate": settings.TTS_ESPEAK_RATE,
            "pitch": settings.TTS_ESPEAK_PITCH,
            "word_gap": settings.TTS_ESPEAK_WORD_GAP,
            "amplitude": settings.TTS_ESPEAK_AMPLITUDE,
        },
        "reference_audios": [],
        "language": "en",
        "model_id": None,
        "embedding_path": None,
        "provider_metadata": {},
    }


def build_generation_voice_manifest(project_id: int, parsed_lines: list[dict], db: Session) -> dict:
    """Snapshot speaker voice/profile choices so the worker renders the same mapping the UI queued."""
    speakers: dict[str, dict] = {}
    speaker_order: list[str] = []
    for index, line in enumerate(parsed_lines):
        speaker = str(line.get("speaker") or f"Speaker {index + 1}").strip()
        text = str(line.get("text") or "").strip()
        if not speaker or not text or speaker in speakers:
            continue

        slot_index = len(speaker_order)
        speaker_order.append(speaker)
        preset = resolve_preset_for_project_speaker(project_id, speaker, db)
        profile_payload: dict
        character_preset_id = None
        character_display_name = speaker
        character_portrait_filename = None
        character_portrait_url = None
        if preset:
            character_preset_id = preset["id"]
            character_display_name = preset["display_name"]
            character_portrait_filename = preset.get("portrait_filename")
            preset_model = get_character_preset_model(preset["id"], db)
            if preset_model:
                profile_payload = runtime_voice_profile_payload(preset_model.voice_profile, preset_model.display_name)
                character_portrait_url = character_preset_portrait_url(preset_model)
            else:
                profile_payload = _default_voice_profile_payload(speaker, slot_index)
        else:
            profile_payload = _default_voice_profile_payload(speaker, slot_index)

        provider = str(profile_payload.get("provider") or "espeak").strip().lower()
        # Explicit clone-capable providers fail closed in render jobs instead of silently switching voices.
        fallback_allowed = provider not in {"openvoice", "xtts", "rvc"}
        profile_payload = {
            **profile_payload,
            "requested_provider": provider,
            "fallback_allowed": fallback_allowed,
        }
        speakers[speaker] = {
            "speaker": speaker,
            "slot_index": slot_index,
            "character_preset_id": character_preset_id,
            "character_display_name": character_display_name,
            "character_portrait_filename": character_portrait_filename,
            "character_portrait_url": character_portrait_url,
            "voice_profile_id": profile_payload.get("id"),
            "provider": provider,
            "requested_provider": provider,
            "fallback_allowed": fallback_allowed,
            "voice_profile": profile_payload,
        }

    return {
        "version": 1,
        "policy": "openvoice_fail_closed",
        "speaker_order": speaker_order,
        "speakers": speakers,
    }


@router.post("/projects/{project_id}/generation-jobs", response_model=GenerationJobSummary, status_code=status.HTTP_201_CREATED)
@router.post("/projects/{project_id}/renders", response_model=GenerationJobSummary, status_code=status.HTTP_201_CREATED)
def create_generation_job(
    project_id: int,
    payload: GenerationJobCreateRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce_rate_limit(
        "generation.create",
        str(current_user.id),
        limit=settings.HEAVY_ENDPOINT_RATE_LIMIT_COUNT,
        window_seconds=settings.HEAVY_ENDPOINT_RATE_LIMIT_WINDOW_SECONDS,
    )
    project = get_owned_project(db, current_user.id, project_id)
    background_asset = latest_background_asset(project)
    if not background_asset:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project needs a background video or preset")

    script_revision = project.current_script_revision
    if payload.script_revision_id is not None:
        script_revision = next(
            (revision for revision in project.script_revisions if revision.id == payload.script_revision_id),
            None,
        )
    if not script_revision:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project needs an editable script")

    reconciled = reconcile_stale_generation_jobs(db, project_id=project.id)
    if reconciled:
        db.commit()

    existing_active_job = (
        db.query(GenerationJob)
        .filter(
            GenerationJob.project_id == project.id,
            GenerationJob.output_kind == payload.output_kind,
            GenerationJob.status.in_(tuple(ACTIVE_GENERATION_STATUSES)),
        )
        .order_by(GenerationJob.created_at.desc())
        .first()
    )
    if existing_active_job:
        response.status_code = status.HTTP_200_OK
        return to_generation_summary(existing_active_job)

    job = GenerationJob(
        project_id=project.id,
        input_asset_id=background_asset.id,
        script_revision_id=script_revision.id,
        style_preset=payload.background_style,
        output_kind=payload.output_kind,
        provider_name=payload.provider_name,
        voice_manifest_json=build_generation_voice_manifest(project.id, script_revision.parsed_lines_json, db),
        # Preview settings are snapshotted with the job because users may keep editing the project while it renders.
        render_settings_json=to_project_preview_settings(project).model_dump(),
        status="queued",
        progress=0,
    )
    project.status = "render_queued"
    db.add(job)
    db.flush()
    create_notification(
        db,
        user_id=current_user.id,
        project_id=project.id,
        category="render.queued",
        message=f"{payload.output_kind.title()} render job #{job.id} is queued.",
        payload={"job_id": job.id, "output_kind": payload.output_kind},
    )
    record_audit(
        db,
        user_id=current_user.id,
        action="render.queued",
        entity_type="generation_job",
        entity_id=job.id,
        metadata={"project_id": project.id, "output_kind": payload.output_kind},
    )
    db.commit()
    db.refresh(job)
    process_generation_job.delay(job.id)
    return to_generation_summary(job)


@router.get("/generation-jobs/{job_id}", response_model=GenerationJobSummary)
def get_generation_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = (
        db.query(GenerationJob)
        .join(Project, Project.id == GenerationJob.project_id)
        .filter(GenerationJob.id == job_id, Project.user_id == current_user.id)
        .one_or_none()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation job not found")
    reconciled = reconcile_stale_generation_jobs(db, project_id=job.project_id)
    if reconciled and job.id in reconciled:
        db.commit()
        db.refresh(job)
    return to_generation_summary(job)


@router.get("/generation-jobs/{job_id}/artifacts/{artifact_path:path}")
def get_generation_job_artifact(
    job_id: int,
    artifact_path: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = (
        db.query(GenerationJob)
        .join(Project, Project.id == GenerationJob.project_id)
        .filter(GenerationJob.id == job_id, Project.user_id == current_user.id)
        .one_or_none()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation job not found")
    # Artifact paths are resolved after ownership checks so debug WAV/JSON files stay project-private.
    artifact = resolve_generated_job_artifact(job.id, artifact_path)
    return FileResponse(
        artifact,
        media_type=guess_mime_type(str(artifact)),
        filename=artifact.name,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/projects/{project_id}/generation-jobs", response_model=GenerationJobListResponse)
def list_project_generation_jobs(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    reconciled = reconcile_stale_generation_jobs(db, project_id=project.id)
    if reconciled:
        db.commit()
    jobs = (
        db.query(GenerationJob)
        .filter(GenerationJob.project_id == project.id)
        .order_by(GenerationJob.created_at.desc())
        .limit(20)
        .all()
    )
    return GenerationJobListResponse(items=[to_generation_summary(job) for job in jobs])


@router.get("/projects/{project_id}/generation-jobs/active", response_model=GenerationJobSummary)
def get_active_generation_job(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    reconciled = reconcile_stale_generation_jobs(db, project_id=project.id)
    if reconciled:
        db.commit()
    job = (
        db.query(GenerationJob)
        .filter(
            GenerationJob.project_id == project.id,
            GenerationJob.status.in_(tuple(ACTIVE_GENERATION_STATUSES)),
        )
        .order_by(GenerationJob.created_at.desc())
        .first()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active generation job")
    return to_generation_summary(job)


@router.get("/projects/{project_id}/outputs", response_model=OutputVideoListResponse)
def list_project_outputs(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    outputs = sorted(project.output_videos, key=lambda output: output.created_at, reverse=True)
    return OutputVideoListResponse(items=[to_output_video_summary(item) for item in outputs])


@router.post("/generation-jobs/{job_id}/cancel", response_model=OkResponse)
def cancel_generation_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = (
        db.query(GenerationJob)
        .join(Project, Project.id == GenerationJob.project_id)
        .filter(GenerationJob.id == job_id, Project.user_id == current_user.id)
        .one_or_none()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation job not found")
    if job.status != "queued":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only queued jobs can be canceled")
    job.status = "canceled"
    job.finished_at = datetime.utcnow()
    project = db.get(Project, job.project_id)
    if project:
        sync_project_state(project)
    db.commit()
    return OkResponse()
