from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import Asset, User
from app.routers.projects import get_owned_project
from app.schemas import AssetSummary, BackgroundPresetSummary, OkResponse
from app.services.project_state import to_asset_summary, sync_project_state
from app.services.storage import (
    copy_preset_to_project,
    delete_storage_key,
    list_background_presets,
    resolve_background_preset,
    save_background_asset,
)

router = APIRouter(tags=["assets"])


@router.get("/background-presets", response_model=list[BackgroundPresetSummary])
def get_background_presets():
    return [
        BackgroundPresetSummary(
            key=preset["key"],
            name=preset["name"],
            description=preset["description"],
            filename=preset["filename"],
            content_url=f"/background-presets/{preset['key']}/content",
        )
        for preset in list_background_presets()
    ]


@router.get("/background-presets/{preset_key}/content")
def get_background_preset_content(preset_key: str):
    preset = resolve_background_preset(preset_key)
    return FileResponse(
        preset["path"],
        media_type="video/mp4",
        filename=preset["filename"],
    )


@router.post("/projects/{project_id}/assets/background", response_model=AssetSummary, status_code=status.HTTP_201_CREATED)
async def upload_background_asset(
    project_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    storage_path, size_bytes, mime_type = await save_background_asset(project.id, file)

    asset = Asset(
        user_id=current_user.id,
        project_id=project.id,
        kind="background_video",
        source_type="upload",
        storage_key=str(storage_path),
        original_filename=file.filename or storage_path.name,
        mime_type=mime_type,
        size_bytes=size_bytes,
        metadata_json={"selection_mode": "upload"},
    )
    db.add(asset)
    db.flush()

    project.background_asset_id = asset.id
    project.background_source_type = "upload"
    sync_project_state(project)
    db.commit()
    db.refresh(asset)
    return to_asset_summary(asset)


@router.post("/projects/{project_id}/assets/background/preset/{preset_key}", response_model=AssetSummary, status_code=status.HTTP_201_CREATED)
def select_background_preset(
    project_id: int,
    preset_key: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    storage_path, size_bytes, mime_type = copy_preset_to_project(project.id, preset_key)
    asset = Asset(
        user_id=current_user.id,
        project_id=project.id,
        kind="background_preset",
        source_type="preset",
        preset_key=preset_key,
        storage_key=str(storage_path),
        original_filename=storage_path.name,
        mime_type=mime_type,
        size_bytes=size_bytes,
        metadata_json={"selection_mode": "preset", "preset_key": preset_key},
    )
    db.add(asset)
    db.flush()

    project.background_asset_id = asset.id
    project.background_source_type = "preset"
    sync_project_state(project)
    db.commit()
    db.refresh(asset)
    return to_asset_summary(asset)


@router.get("/projects/{project_id}/assets", response_model=list[AssetSummary])
def list_project_assets(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    return [to_asset_summary(asset) for asset in sorted(project.assets, key=lambda asset: asset.created_at, reverse=True)]


@router.delete("/projects/{project_id}/assets/{asset_id}", response_model=OkResponse)
def delete_project_asset(
    project_id: int,
    asset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.project_id == project.id).one_or_none()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    delete_storage_key(asset.storage_key)
    if project.background_asset_id == asset.id:
        project.background_asset_id = None
        project.background_source_type = "upload"
    db.delete(asset)
    sync_project_state(project)
    db.commit()
    return OkResponse()


@router.get("/assets/{asset_id}/content")
def get_asset_content(
    asset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.user_id == current_user.id).one_or_none()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return FileResponse(asset.storage_key, media_type=asset.mime_type, filename=asset.original_filename)
