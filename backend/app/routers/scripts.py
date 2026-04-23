from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import ScriptRevision, User
from app.routers.projects import get_owned_project
from app.schemas import (
    ScriptGenerateRequest,
    ScriptResponse,
    ScriptRevisionListResponse,
    ScriptUpdateRequest,
)
from app.services.audit import record_audit
from app.services.notifications import create_notification
from app.services.project_state import sync_project_state, to_script_summary
from app.services.scripts import generate_script_draft, save_script_revision

router = APIRouter(tags=["scripts"])


@router.get("/projects/{project_id}/script", response_model=ScriptResponse)
def get_project_script(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    return ScriptResponse(current_revision=to_script_summary(project.current_script_revision))


@router.get("/projects/{project_id}/script-revisions", response_model=ScriptRevisionListResponse)
def list_script_revisions(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    revisions = sorted(project.script_revisions, key=lambda item: item.created_at, reverse=True)
    return ScriptRevisionListResponse(items=[to_script_summary(item) for item in revisions if to_script_summary(item) is not None])


@router.post("/projects/{project_id}/script-revisions/{revision_id}/restore", response_model=ScriptResponse)
def restore_script_revision(
    project_id: int,
    revision_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    revision = (
        db.query(ScriptRevision)
        .filter(ScriptRevision.id == revision_id, ScriptRevision.project_id == project.id)
        .one_or_none()
    )
    if not revision:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script revision not found")
    restored = save_script_revision(
        db,
        project_id=project.id,
        raw_text=revision.raw_text,
        parsed_lines=None,
        source="restore",
        parent_revision_id=revision.id,
        generation_provider=revision.generation_provider,
    )
    project.current_script_revision_id = restored.id
    sync_project_state(project)
    record_audit(
        db,
        user_id=current_user.id,
        action="script.restored",
        entity_type="script_revision",
        entity_id=restored.id,
        metadata={"project_id": project.id, "restored_from": revision.id},
    )
    db.commit()
    db.refresh(project)
    return ScriptResponse(current_revision=to_script_summary(project.current_script_revision))


@router.put("/projects/{project_id}/script", response_model=ScriptResponse)
def update_project_script(
    project_id: int,
    payload: ScriptUpdateRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    revision = save_script_revision(
        db,
        project_id=project.id,
        raw_text=payload.raw_text,
        parsed_lines=payload.parsed_lines,
        source=payload.source,
        parent_revision_id=payload.parent_revision_id or project.current_script_revision_id,
    )
    project.current_script_revision_id = revision.id
    sync_project_state(project)
    create_notification(
        db,
        user_id=current_user.id,
        project_id=project.id,
        category="script.updated",
        message=f"Script revision #{revision.id} is ready for the next render.",
        payload={"revision_id": revision.id},
    )
    record_audit(
        db,
        user_id=current_user.id,
        action="script.updated",
        entity_type="script_revision",
        entity_id=revision.id,
        metadata={"project_id": project.id, "source": payload.source},
    )
    db.commit()
    db.refresh(revision)
    db.refresh(project)
    return ScriptResponse(current_revision=to_script_summary(project.current_script_revision))


@router.post("/projects/{project_id}/script/generate", response_model=ScriptResponse, status_code=status.HTTP_201_CREATED)
def generate_project_script(
    project_id: int,
    payload: ScriptGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    raw_text, provider = generate_script_draft(payload.prompt, payload.character_names, payload.tone)
    revision = save_script_revision(
        db,
        project_id=project.id,
        raw_text=raw_text,
        parsed_lines=None,
        source="generated",
        parent_revision_id=project.current_script_revision_id,
        generation_provider=provider,
    )
    project.current_script_revision_id = revision.id
    sync_project_state(project)
    create_notification(
        db,
        user_id=current_user.id,
        project_id=project.id,
        category="script.generated",
        message="An AI-assisted script draft is ready to edit.",
        payload={"revision_id": revision.id, "provider": provider},
    )
    record_audit(
        db,
        user_id=current_user.id,
        action="script.generated",
        entity_type="script_revision",
        entity_id=revision.id,
        metadata={"project_id": project.id, "provider": provider},
    )
    db.commit()
    db.refresh(project)
    return ScriptResponse(current_revision=to_script_summary(project.current_script_revision))


@router.post("/projects/{project_id}/script/import", response_model=ScriptResponse, status_code=status.HTTP_201_CREATED)
async def import_project_script(
    project_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    raw_text = (await file.read()).decode("utf-8")
    source = f"upload:{Path(file.filename or 'script.txt').suffix or '.txt'}"
    revision = save_script_revision(
        db,
        project_id=project.id,
        raw_text=raw_text,
        parsed_lines=None,
        source=source,
        parent_revision_id=project.current_script_revision_id,
    )
    project.current_script_revision_id = revision.id
    sync_project_state(project)
    record_audit(
        db,
        user_id=current_user.id,
        action="script.imported",
        entity_type="script_revision",
        entity_id=revision.id,
        metadata={"project_id": project.id, "source": source},
    )
    db.commit()
    db.refresh(project)
    return ScriptResponse(current_revision=to_script_summary(project.current_script_revision))
