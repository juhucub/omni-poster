from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import PlatformMetadata, User
from app.routers.projects import get_owned_project
from app.schemas import PlatformMetadataResponse, PlatformMetadataUpdateRequest

router = APIRouter(tags=["metadata"])


def to_metadata_response(metadata: PlatformMetadata) -> PlatformMetadataResponse:
    return PlatformMetadataResponse(
        id=metadata.id,
        project_id=metadata.project_id,
        platform=metadata.platform,
        title=metadata.title,
        description=metadata.description,
        tags=metadata.tags_json,
        source=metadata.source,
        updated_at=metadata.updated_at,
    )


@router.get("/projects/{project_id}/metadata/youtube", response_model=PlatformMetadataResponse | None)
def get_project_metadata(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    metadata = (
        db.query(PlatformMetadata)
        .filter(PlatformMetadata.project_id == project.id, PlatformMetadata.platform == "youtube")
        .order_by(PlatformMetadata.updated_at.desc())
        .first()
    )
    return to_metadata_response(metadata) if metadata else None


@router.put("/projects/{project_id}/metadata/youtube", response_model=PlatformMetadataResponse)
def save_project_metadata(
    project_id: int,
    payload: PlatformMetadataUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    metadata = (
        db.query(PlatformMetadata)
        .filter(PlatformMetadata.project_id == project.id, PlatformMetadata.platform == "youtube")
        .order_by(PlatformMetadata.updated_at.desc())
        .first()
    )
    if not metadata:
        metadata = PlatformMetadata(project_id=project.id, platform="youtube", title=payload.title)
        db.add(metadata)
    metadata.title = payload.title
    metadata.description = payload.description
    metadata.tags_json = payload.tags
    metadata.source = payload.source
    db.commit()
    db.refresh(metadata)
    return to_metadata_response(metadata)


@router.post("/projects/{project_id}/metadata/youtube/suggest", response_model=PlatformMetadataResponse)
def suggest_project_metadata(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    script = project.current_script_revision
    script_lines = script.parsed_lines_json if script else []
    title_seed = script_lines[0]["text"][:60] if script_lines else project.name
    tags = [speaker.lower().replace(" ", "-") for speaker in (script.characters_json if script else [])][:5]
    metadata = (
        db.query(PlatformMetadata)
        .filter(PlatformMetadata.project_id == project.id, PlatformMetadata.platform == "youtube")
        .order_by(PlatformMetadata.updated_at.desc())
        .first()
    )
    if not metadata:
        metadata = PlatformMetadata(project_id=project.id, platform="youtube", title=title_seed)
        db.add(metadata)
    metadata.title = title_seed
    metadata.description = project.current_script_revision.raw_text[:5000] if project.current_script_revision else ""
    metadata.tags_json = tags
    metadata.source = "suggested"
    db.commit()
    db.refresh(metadata)
    return to_metadata_response(metadata)
