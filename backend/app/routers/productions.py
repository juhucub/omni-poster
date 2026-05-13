from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import Project, SocialAccount, User
from app.routers.generation import create_generation_job
from app.routers.projects import get_owned_project
from app.schemas import (
    GenerationJobCreateRequest,
    GenerationJobSummary,
    OkResponse,
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectPreviewSettings,
    ProjectPreviewSettingsUpdate,
    ProjectSummary,
    ProjectUpdateRequest,
)
from app.services.audit import record_audit
from app.services.project_state import sync_project_state, to_project_preview_settings, to_project_summary, update_project_preview_settings

router = APIRouter(prefix="/productions", tags=["productions"])


@router.get("", response_model=ProjectListResponse)
def list_productions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    projects = (
        db.query(Project)
        .filter(Project.user_id == current_user.id, Project.archived_at.is_(None))
        .order_by(Project.updated_at.desc())
        .all()
    )
    return ProjectListResponse(items=[to_project_summary(project) for project in projects])


@router.post("", response_model=ProjectSummary, status_code=status.HTTP_201_CREATED)
def create_production(
    payload: ProjectCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = Project(
        user_id=current_user.id,
        name=payload.name,
        target_platform=payload.target_platform,
        automation_mode=payload.automation_mode,
        allowed_platforms_json=list(payload.allowed_platforms or [payload.target_platform]),
    )
    db.add(project)
    db.flush()
    record_audit(
        db,
        user_id=current_user.id,
        action="production.created",
        entity_type="project",
        entity_id=project.id,
        metadata={"target_platform": payload.target_platform, "automation_mode": payload.automation_mode},
    )
    db.commit()
    db.refresh(project)
    return to_project_summary(project)


@router.get("/{production_id}", response_model=ProjectSummary)
def get_production(production_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return to_project_summary(get_owned_project(db, current_user.id, production_id))


@router.patch("/{production_id}", response_model=ProjectSummary)
def update_production(
    production_id: int,
    payload: ProjectUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, production_id)
    if payload.name is not None:
        project.name = payload.name
    if payload.background_style is not None:
        project.background_style = payload.background_style
    if payload.automation_mode is not None:
        project.automation_mode = payload.automation_mode
    if payload.preferred_account_type is not None:
        project.preferred_account_type = payload.preferred_account_type
    if payload.allowed_platforms is not None:
        project.allowed_platforms_json = list(payload.allowed_platforms)
    if payload.publish_windows is not None:
        project.publish_windows_json = payload.publish_windows
    if payload.selected_social_account_id is not None:
        account = (
            db.query(SocialAccount)
            .filter(
                SocialAccount.id == payload.selected_social_account_id,
                SocialAccount.user_id == current_user.id,
                SocialAccount.status != "revoked",
            )
            .one_or_none()
        )
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Social account not found")
        project.selected_social_account_id = payload.selected_social_account_id
    sync_project_state(project)
    record_audit(
        db,
        user_id=current_user.id,
        action="production.updated",
        entity_type="project",
        entity_id=project.id,
    )
    db.commit()
    db.refresh(project)
    return to_project_summary(project)


@router.patch("/{production_id}/preview-settings", response_model=ProjectPreviewSettings)
def patch_production_preview_settings(
    production_id: int,
    payload: ProjectPreviewSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, production_id)
    update_project_preview_settings(project, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(project)
    return to_project_preview_settings(project)


@router.post("/{production_id}/approve-preview", response_model=ProjectSummary)
def approve_production_preview(
    production_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, production_id)
    if not project.current_output_video_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Production has no preview to approve")
    project.approved_at = datetime.utcnow()
    project.status = "approved"
    record_audit(
        db,
        user_id=current_user.id,
        action="production.preview_approved",
        entity_type="project",
        entity_id=project.id,
    )
    db.commit()
    db.refresh(project)
    return to_project_summary(project)


@router.post("/{production_id}/render", response_model=GenerationJobSummary, status_code=status.HTTP_201_CREATED)
def render_production(
    production_id: int,
    payload: GenerationJobCreateRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_generation_job(production_id, payload, request, response, current_user, db)


@router.post("/{production_id}/archive", response_model=OkResponse)
def archive_production(
    production_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, production_id)
    project.archived_at = datetime.utcnow()
    project.status = "archived"
    db.commit()
    return OkResponse()
