from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import PlatformMetadata, User
from app.routers.projects import get_owned_project
from app.schemas import PlatformMetadataResponse, PlatformMetadataUpdateRequest
from app.services.ai import suggest_metadata_from_script
from app.services.audit import record_audit
from app.services.platforms import capability_for, validate_platform_metadata

router = APIRouter(tags=["metadata"])


def _ensure_supported_platform(platform: str) -> str:
    capability_for(platform)
    return platform


def to_metadata_response(metadata: PlatformMetadata) -> PlatformMetadataResponse:
    return PlatformMetadataResponse(
        id=metadata.id,
        project_id=metadata.project_id,
        platform=metadata.platform,
        title=metadata.title,
        description=metadata.description,
        tags=metadata.tags_json,
        extras=metadata.extras_json,
        validation_errors=metadata.validation_errors_json,
        source=metadata.source,
        updated_at=metadata.updated_at,
    )


def _get_or_create_project_metadata(db: Session, project_id: int, platform: str) -> PlatformMetadata:
    metadata = (
        db.query(PlatformMetadata)
        .filter(PlatformMetadata.project_id == project_id, PlatformMetadata.platform == platform)
        .order_by(PlatformMetadata.updated_at.desc())
        .first()
    )
    if not metadata:
        metadata = PlatformMetadata(project_id=project_id, platform=platform, title="")
        db.add(metadata)
        db.flush()
    return metadata


@router.get("/projects/{project_id}/metadata/{platform}", response_model=PlatformMetadataResponse | None)
def get_project_metadata(
    project_id: int,
    platform: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_supported_platform(platform)
    project = get_owned_project(db, current_user.id, project_id)
    metadata = (
        db.query(PlatformMetadata)
        .filter(PlatformMetadata.project_id == project.id, PlatformMetadata.platform == platform)
        .order_by(PlatformMetadata.updated_at.desc())
        .first()
    )
    return to_metadata_response(metadata) if metadata else None


@router.put("/projects/{project_id}/metadata/{platform}", response_model=PlatformMetadataResponse)
def save_project_metadata(
    project_id: int,
    platform: str,
    payload: PlatformMetadataUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_supported_platform(platform)
    project = get_owned_project(db, current_user.id, project_id)
    metadata = _get_or_create_project_metadata(db, project.id, platform)
    metadata.title = payload.title
    metadata.description = payload.description
    metadata.tags_json = payload.tags
    metadata.extras_json = payload.extras
    metadata.source = payload.source
    metadata.validation_errors_json = validate_platform_metadata(
        platform=platform,
        title=payload.title,
        description=payload.description,
        tags=payload.tags,
    )
    record_audit(
        db,
        user_id=current_user.id,
        action="metadata.saved",
        entity_type="platform_metadata",
        entity_id=metadata.id,
        metadata={"project_id": project.id, "platform": platform},
    )
    db.commit()
    db.refresh(metadata)
    return to_metadata_response(metadata)


@router.post("/projects/{project_id}/metadata/{platform}/suggest", response_model=PlatformMetadataResponse)
def suggest_project_metadata(
    project_id: int,
    platform: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_supported_platform(platform)
    project = get_owned_project(db, current_user.id, project_id)
    suggestion = suggest_metadata_from_script(project, platform)
    metadata = _get_or_create_project_metadata(db, project.id, platform)
    metadata.title = suggestion["title"]
    metadata.description = suggestion["description"]
    metadata.tags_json = suggestion["tags"]
    metadata.extras_json = suggestion["extras"]
    metadata.source = "suggested"
    metadata.validation_errors_json = validate_platform_metadata(
        platform=platform,
        title=metadata.title,
        description=metadata.description,
        tags=metadata.tags_json,
    )
    record_audit(
        db,
        user_id=current_user.id,
        action="metadata.suggested",
        entity_type="platform_metadata",
        entity_id=metadata.id,
        metadata={"project_id": project.id, "platform": platform, "provider": suggestion["provider"]},
    )
    db.commit()
    db.refresh(metadata)
    return to_metadata_response(metadata)


@router.get("/projects/{project_id}/metadata/youtube", response_model=PlatformMetadataResponse | None)
def get_project_metadata_youtube(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_project_metadata(project_id, "youtube", current_user, db)


@router.put("/projects/{project_id}/metadata/youtube", response_model=PlatformMetadataResponse)
def save_project_metadata_youtube(
    project_id: int,
    payload: PlatformMetadataUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return save_project_metadata(project_id, "youtube", payload, current_user, db)


@router.post("/projects/{project_id}/metadata/youtube/suggest", response_model=PlatformMetadataResponse)
def suggest_project_metadata_youtube(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return suggest_project_metadata(project_id, "youtube", current_user, db)
