import os
import uuid
import logging
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends, Body
from app.models import UploadResponse
from app.services.upload import get_upload_service, UploadService, UploadMeta, UPLOAD_DIR
from app.dependencies import get_current_user
from app.models import User

logger = logging.getLogger("uvicorn.error")
router = APIRouter()

router.post("/upload", response_model=UploadResponse)
async def upload(
    video: UploadFile = File(...),
    audio: UploadFile = File(...),
    thumbnail: Optional[UploadFile] = File(None),
    upload_service: UploadService = Depends(get_upload_service),
    current_user: User = Depends(get_current_user)
):
    """
    Authenticated upload endpoint: validates media, saves locally, and records metadata.
    """
    # Ensure both required files are provided
    if not video or not audio:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Both video and audio files are required"
        )
    
    # Validate mime types
    for f, name in [(video, 'video'), (audio, 'audio')]:
        media_type = f.content_type.split('/')[0] if f.content_type else 'unknown'
        if media_type not in ['video', 'audio']:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported file type for {name}: {f.content_type}"
            )
    
    # Validate thumbnail if provided
    if thumbnail:
        thumb_type = thumbnail.content_type.split('/')[0] if thumbnail.content_type else 'unknown'
        if thumb_type != 'image':
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Thumbnail must be an image file: {thumbnail.content_type}"
            )
    
    project_id = str(uuid.uuid4())
    results = {}

    for f, label in [(video, 'video'), (audio, 'audio'), (thumbnail, 'thumbnail')]:
        if f:
            url = await upload_service.save_to_storage(f, current_user.username)
            meta = UploadMeta(
                project_id=project_id,
                filename=f.filename,
                url=url,
                size=f.size or 0,
                content_type=f.content_type,
                uploader_id=current_user.username
            )
            upload_service.record_upload(meta)
            results[label] = url

    logger.info(f"Files uploaded for project {project_id} by user {current_user.username}")
    return UploadResponse(project_id=project_id, urls=results)

@router.post("/generate_video", response_model=dict)
async def generate_video(
    payload: dict = Body(...)
):
    """
    Stub generate_video endpoint: accepts project_id and returns status plus video URL.
    """
    project_id = payload.get("project_id")
    if not project_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="`project_id` is required"
        )
    # Stub URL: in real use you'd point to the generated asset
    final_path = os.path.join(UPLOAD_DIR, f"{project_id}_final.mp4")
    video_url = f"file://{os.path.abspath(final_path)}"
    return {"project_id": project_id, "status": "processing", "video_url": video_url}

@router.get("/upload_history")
async def get_upload_history(
    current_user: User = Depends(get_current_user),
    upload_service: UploadService = Depends(get_upload_service)
) -> List[dict]:
    """
    Get upload history for the authenticated user.
    Returns a list of upload records with metadata.
    """
    try:
        history = upload_service.get_user_upload_history(current_user.username)
        return history
    except Exception as e:
        logger.error(f"Error fetching upload history for user {current_user.username}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch upload history"
        )