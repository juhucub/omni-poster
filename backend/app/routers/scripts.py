from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import ScriptRevision, User
from app.routers.projects import get_owned_project
from app.schemas import ScriptResponse, ScriptUpdateRequest
from app.services.project_state import sync_project_state, to_script_summary
from app.services.scripts import parse_dialogue_script

router = APIRouter(tags=["scripts"])


def _save_script_revision(db: Session, project_id: int, raw_text: str, source: str) -> ScriptRevision:
    lines, characters = parse_dialogue_script(raw_text)
    db.query(ScriptRevision).filter(
        ScriptRevision.project_id == project_id,
        ScriptRevision.is_current.is_(True),
    ).update({"is_current": False})

    revision = ScriptRevision(
        project_id=project_id,
        raw_text=raw_text,
        parsed_lines_json=lines,
        characters_json=characters,
        source=source,
        is_current=True,
    )
    db.add(revision)
    db.flush()
    return revision


@router.get("/projects/{project_id}/script", response_model=ScriptResponse)
def get_project_script(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    return ScriptResponse(current_revision=to_script_summary(project.current_script_revision))


@router.put("/projects/{project_id}/script", response_model=ScriptResponse)
def update_project_script(
    project_id: int,
    payload: ScriptUpdateRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    revision = _save_script_revision(db, project.id, payload.raw_text, payload.source)
    project.current_script_revision_id = revision.id
    sync_project_state(project)
    db.commit()
    db.refresh(revision)
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
    revision = _save_script_revision(db, project.id, raw_text, source)
    project.current_script_revision_id = revision.id
    sync_project_state(project)
    db.commit()
    db.refresh(project)
    return ScriptResponse(current_revision=to_script_summary(project.current_script_revision))
