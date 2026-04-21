from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import Project, User
from app.schemas import OkResponse, ProjectCreateRequest, ProjectListResponse, ProjectSummary, ProjectUpdateRequest
from app.services.project_state import sync_project_state, to_project_summary

router = APIRouter(prefix="/projects", tags=["projects"])


def get_owned_project(db: Session, user_id: int, project_id: int) -> Project:
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.get("", response_model=ProjectListResponse)
def list_projects(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    projects = (
        db.query(Project)
        .filter(Project.user_id == current_user.id, Project.archived_at.is_(None))
        .order_by(Project.updated_at.desc())
        .all()
    )
    return ProjectListResponse(items=[to_project_summary(project) for project in projects])


@router.post("", response_model=ProjectSummary, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = Project(
        user_id=current_user.id,
        name=payload.name,
        target_platform=payload.target_platform,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return to_project_summary(project)


@router.get("/{project_id}", response_model=ProjectSummary)
def get_project(project_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = get_owned_project(db, current_user.id, project_id)
    return to_project_summary(project)


@router.patch("/{project_id}", response_model=ProjectSummary)
def update_project(
    project_id: int,
    payload: ProjectUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    if payload.name is not None:
        project.name = payload.name
    if payload.background_style is not None:
        project.background_style = payload.background_style
    if payload.selected_social_account_id is not None:
        project.selected_social_account_id = payload.selected_social_account_id
    sync_project_state(project)
    db.commit()
    db.refresh(project)
    return to_project_summary(project)


@router.post("/{project_id}/approve-preview", response_model=ProjectSummary)
def approve_preview(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    if not project.current_output_video_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project has no preview to approve")
    if project.status not in {"preview_ready", "approved"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project is not ready for approval")
    from datetime import datetime

    project.approved_at = datetime.utcnow()
    project.status = "approved"
    db.commit()
    db.refresh(project)
    return to_project_summary(project)


@router.post("/{project_id}/archive", response_model=OkResponse)
def archive_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    from datetime import datetime

    project.archived_at = datetime.utcnow()
    db.commit()
    return OkResponse()
