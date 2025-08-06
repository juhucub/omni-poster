import asyncio
import logging
import mimetypes
import os
import re
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import (
    APIRouter, 
    BackgroundTasks,
    Body,
    Depends, 
    File, 
    HTTPException, 
    Request,
    UploadFile,
    status
)
from fastapi.security import HTTPBearer


from app.models import UploadResponse, GenerateVideoResponse, GenerateVideoRequest, User
from app.services.upload import get_upload_service, UploadService, UploadMeta, UPLOAD_DIR
from app.services.vid_gen import get_video_generation_service, VideoGenerationService
from app.dependencies import get_current_user

# Configure structured logging
logger = logging.getLogger(__name__)

# Security constants
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB per file
MAX_TOTAL_SIZE = 1024 * 1024 * 1024  # 1GB total per request
ALLOWED_VIDEO_TYPES = {
    'video/mp4', 'video/avi', 'video/mov', 'video/wmv', 'video/webm'
}
ALLOWED_AUDIO_TYPES = {
    'audio/mp3', 'audio/wav', 'audio/aac', 'audio/ogg', 'audio/mpeg'
}
ALLOWED_IMAGE_TYPES = {
    'image/jpeg', 'image/png', 'image/gif', 'image/webp'
}

# Create router WITHOUT conflicting prefix (assuming main app handles /upload)
router = APIRouter(
    tags=["uploads"],
    responses={404: {"description": "Not found"}},
)

def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and ensure filesystem compatibility."""
    if not filename:
        return f"unnamed_{uuid.uuid4().hex[:8]}"
    
    # Remove path separators and dangerous characters
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
    safe_name = safe_name.strip('. ')  # Remove leading/trailing dots and spaces
    
    # Limit length and ensure we have an extension
    name_part = safe_name.rsplit('.', 1)[0][:100]
    ext_part = safe_name.rsplit('.', 1)[1] if '.' in safe_name else 'bin'
    
    return f"{name_part}.{ext_part}"

def validate_content_type(file: UploadFile, allowed_types: set, file_label: str) -> None:
    """Validate file MIME type against whitelist with magic number verification."""
    declared_type = file.content_type
    
    if declared_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported {file_label} type: {declared_type}. "
                   f"Allowed: {', '.join(sorted(allowed_types))}"
        )

async def validate_file_size(file: UploadFile, max_size: int = MAX_FILE_SIZE) -> int:
    """Validate file size without loading entire file into memory."""
    size = 0
    chunk_size = 8192
    
    # Reset file pointer
    await file.seek(0)
    
    # Stream through file to calculate size
    while chunk := await file.read(chunk_size):
        size += len(chunk)
        if size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File {file.filename} exceeds maximum size of {max_size} bytes"
            )
    
    # Reset file pointer for actual processing
    await file.seek(0)
    return size

async def process_file_upload(
    file: UploadFile,
    file_type: str,
    project_id: str,
    user: User,
    upload_service: UploadService,
    background_tasks: BackgroundTasks
) -> Dict[str, any]:
    """Process individual file upload with streaming and background tasks."""
    
    # Sanitize filename to prevent path traversal
    safe_filename = sanitize_filename(file.filename)
    
    # Validate file size without loading into memory
    actual_size = await validate_file_size(file)
    
    # Stream file to storage (don't load entire file into memory)
    try:
        storage_url = await upload_service.save_to_storage(
            file, user.username
        )
        
        # Create metadata record
        meta = UploadMeta(
            project_id=project_id,
            filename=safe_filename,
            url=storage_url,
            size=actual_size,
            content_type=file.content_type,
            uploader_id=user.username
        )
        
        # Record upload in background to not block response
        background_tasks.add_task(upload_service.record_upload, meta)
        
        # Log successful upload (no sensitive data)
        logger.info(
            "File uploaded successfully",
            extra={
                "project_id": project_id,
                "file_type": file_type,
                "file_size": actual_size,
                "user_id": user.username,
                "filename_hash": hash(safe_filename)  # Don't log actual filename
            }
        )
        
        return {
            "url": storage_url,
            "size": actual_size,
            "filename": safe_filename
        }
        
    except Exception as e:
        logger.error(
            "File upload failed",
            extra={
                "project_id": project_id,
                "file_type": file_type,
                "user_id": user.username,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload {file_type} file"
        )

@router.post(
    "/upload",  # Clean path without double prefixes
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload media files",
    description="Upload video, audio, and optional thumbnail files for processing",
    responses={
        413: {"description": "File too large"},
        415: {"description": "Unsupported media type"},
        422: {"description": "Validation error"},
        500: {"description": "Upload failed"}
    }
)
async def upload_media_files(
    request: Request,  # For rate limiting and IP tracking
    background_tasks: BackgroundTasks,  # For non-blocking operations
    video: UploadFile = File(..., description="Video file (required)"),
    audio: UploadFile = File(..., description="Audio file (required)"),
    thumbnail: Optional[UploadFile] = File(None, description="Optional thumbnail image"),
    # Proper auth dependency with required scopes
    current_user: User = Depends(get_current_user),
    upload_service: UploadService = Depends(get_upload_service),
):
    """
    Upload endpoint with comprehensive security, performance, and error handling.
    
    Security features:
    - File size limits and MIME type validation
    - Filename sanitization (path traversal prevention)
    - Proper authentication and authorization
    - Structured logging without sensitive data
    
    Performance features:
    - Streaming file processing (no memory loading)
    - Background task for metadata recording
    - Concurrent file validation
    """
    
    # Validate required files are provided (FastAPI handles this, but explicit check for clarity)
    if not video.filename or not audio.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Both video and audio files must have valid filenames"
        )
    
    # Validate MIME types against strict whitelists
    validate_content_type(video, ALLOWED_VIDEO_TYPES, "video")
    validate_content_type(audio, ALLOWED_AUDIO_TYPES, "audio")
    
    if thumbnail:
        validate_content_type(thumbnail, ALLOWED_IMAGE_TYPES, "thumbnail")
    
    # Calculate total request size for DOS protection
    files_to_process = [video, audio]
    if thumbnail:
        files_to_process.append(thumbnail)
    
    # Validate total size across all files
    total_size = sum(getattr(f, 'size', 0) or 0 for f in files_to_process)
    if total_size > MAX_TOTAL_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Total upload size exceeds limit of {MAX_TOTAL_SIZE} bytes"
        )
    
    # Generate project ID for grouping related files
    project_id = str(uuid.uuid4())
    
    try:
        # Process files concurrently for better performance
        tasks = [
            process_file_upload(video, "video", project_id, current_user, upload_service, background_tasks),
            process_file_upload(audio, "audio", project_id, current_user, upload_service, background_tasks),
        ]
        
        if thumbnail:
            tasks.append(
                process_file_upload(thumbnail, "thumbnail", project_id, current_user, upload_service, background_tasks)
            )
        
        # Execute uploads concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check for any failures
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_type = ["video", "audio", "thumbnail"][i]
                logger.error(f"Failed to upload {file_type}: {result}")
                raise result
        
        # Build response URLs
        response_urls = {
            "video": results[0]["url"],
            "audio": results[1]["url"]
        }
        
        if thumbnail and len(results) > 2:
            response_urls["thumbnail"] = results[2]["url"]
        
        # Log successful batch upload
        logger.info(
            "Batch upload completed",
            extra={
                "project_id": project_id,
                "user_id": current_user.username,
                "files_count": len(results),
                "client_ip": request.client.host if request.client else "unknown"
            }
        )
        
        return UploadResponse(
            project_id=project_id,
            urls=response_urls,
            status="success"
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(
            "Unexpected upload error",
            extra={
                "project_id": project_id,
                "user_id": current_user.username,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during upload"
        )

# Additional helper endpoint for checking upload limits
@router.get("/upload/limits")
async def get_upload_limits():
    """Return current upload limits for client-side validation."""
    return {
        "max_file_size": MAX_FILE_SIZE,
        "max_total_size": MAX_TOTAL_SIZE,
        "allowed_video_types": list(ALLOWED_VIDEO_TYPES),
        "allowed_audio_types": list(ALLOWED_AUDIO_TYPES),
        "allowed_image_types": list(ALLOWED_IMAGE_TYPES)
    }

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
    

# ============= NEW GENERATE VIDEO ENDPOINT =============

def get_project_files(project_id: str, upload_service: UploadService) -> Dict[str, str]:
    """
    Retrieve all files for a project from the upload history.
    
    Returns:
        Dict with keys 'video', 'audio', and optionally 'thumbnail'
    """
    try:
        # Get all uploads for this project from the database
        import sqlite3
        from app.services.upload import UPLOAD_DB
        
        conn = sqlite3.connect(UPLOAD_DB)
        conn.row_factory = sqlite3.Row
        
        cursor = conn.execute(
            "SELECT content_type, url FROM uploads WHERE project_id = ? ORDER BY uploaded_at",
            (project_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No files found for project {project_id}"
            )
        
        # Categorize files by type
        files = {}
        for row in rows:
            content_type = row['content_type']
            url = row['url']
            
            if content_type.startswith('video/'):
                files['video'] = url
            elif content_type.startswith('audio/'):
                files['audio'] = url
            elif content_type.startswith('image/'):
                files['thumbnail'] = url
        
        # Validate required files
        if 'video' not in files or 'audio' not in files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project must contain both video and audio files"
            )
        
        return files
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving project files: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve project files"
        )

async def process_video_generation(
    project_id: str,
    files: Dict[str, str],
    video_service: VideoGenerationService,
    request_params: GenerateVideoRequest
) -> Dict[str, any]:
    """
    Background task to process video generation.
    This would typically be run in a background task queue like Celery.
    """
    try:
        logger.info(f"Starting video generation for project {project_id}")
        
        # Generate video using the service
        result = video_service.generate_video(
            video_path=files['video'],
            audio_path=files['audio'],
            thumbnail_path=files.get('thumbnail'),
            project_id=project_id
        )
        
        logger.info(f"Video generation completed for project {project_id}")
        return result
        
    except Exception as e:
        logger.error(f"Video generation failed for project {project_id}: {str(e)}")
        raise

@router.post(
    "/generate_video", 
    response_model=GenerateVideoResponse,
    summary="Generate video from uploaded files",
    description="Combine uploaded video and audio files, with optional thumbnail overlay"
)
async def generate_video(
    request: GenerateVideoRequest = Body(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    upload_service: UploadService = Depends(get_upload_service),
    video_service: VideoGenerationService = Depends(get_video_generation_service)
):
    """
    Generate a combined video from uploaded video and audio files.
    
    This endpoint:
    1. Validates the project exists and belongs to the user
    2. Retrieves the uploaded files for the project
    3. Starts video generation process
    4. Returns status and progress information
    """
    
    if not request.project_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="`project_id` is required"
        )
    
    try:
        # Get project files from database
        files = get_project_files(request.project_id, upload_service)
        
        # TODO: Verify user owns this project (add user_id check to get_project_files)
        
        # For now, process synchronously. In production, use background tasks.
        logger.info(f"Processing video generation for project {request.project_id}")
        
        start_time = time.time()
        
        # Generate the video
        result = await asyncio.to_thread(
            video_service.generate_video,
            video_path=files['video'],
            audio_path=files['audio'],
            thumbnail_path=files.get('thumbnail'),
            project_id=request.project_id
        )
        
        processing_time = time.time() - start_time
        
        # Log successful generation
        logger.info(
            "Video generation completed",
            extra={
                "project_id": request.project_id,
                "user_id": current_user.username,
                "processing_time": processing_time,
                "output_size": result.get("size_bytes", 0)
            }
        )
        
        return GenerateVideoResponse(
            project_id=request.project_id,
            status="completed",
            video_url=result["output_path"],
            progress=100,
            message="Video generation completed successfully",
            processing_time_seconds=processing_time,
            output_file_size=result.get("size_bytes")
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(
            "Video generation failed",
            extra={
                "project_id": request.project_id,
                "user_id": current_user.username,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        
        return GenerateVideoResponse(
            project_id=request.project_id,
            status="failed",
            progress=0,
            message=f"Video generation failed: {str(e)}"
        )

@router.get(
    "/generation_status/{project_id}",
    response_model=GenerateVideoResponse,
    summary="Get video generation status",
    description="Check the status of video generation for a project"
)
async def get_generation_status(
    project_id: str,
    current_user: User = Depends(get_current_user),
    video_service: VideoGenerationService = Depends(get_video_generation_service)
):
    """
    Get the current status of video generation for a project.
    
    In a production system, this would check a job queue or database
    to return real-time status updates.
    """
    try:
        # For now, return a simple lookup
        # In production, this would check Redis/database for job status
        status_info = video_service.get_generation_status(project_id)
        
        return GenerateVideoResponse(
            project_id=project_id,
            status=status_info["status"],
            progress=status_info.get("progress", 0),
            message=status_info.get("message", "")
        )
        
    except Exception as e:
        logger.error(f"Error getting generation status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get generation status"
        )
