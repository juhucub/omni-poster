import uuid
import os
import logging
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends
from app.models import UploadResponse
from app.dependencies import get_current_user

logger = logging.getLogger("uvicorn.error")
router = APIRouter()

from app.services.
##########################
#configuration and helpers
###########################
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

def save_file(file: UploadFile, dest_path: str) -> None:
    #saves uploaded file to disk in streaming chunks for mem efficiency
    try:
        with open(dest_path, "wb") as buffer:
            for chunk in file.file:
                buffer.write(chunk)
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        raise
    finally:
        file.file.close()

##########################
#Endpoints
###########################
@app.post("/upload", response_model=UploadResponse)
async def upload(
    video: UploadFile = File(..., description="Raw video or images to be processed"),
    audio: UploadFile = File(..., description="Audio file (mp3/wav) to be processed"),
    thumbnail: Optional[UploadFile] = File(None, description="Thumbnail image for the video")
):
    # Accepts raw assets, saves to disk or cloud storage, and returns a project_id
    # Validates file types
    # Processes files as needed (e.g., extracting frames from video)

    #basic Validation
    for f, name in [(video, 'video'), (audio, 'audio')]:
        media_type = f.content_type.split('/')[0]
        if media_type not in ['video', 'audio', 'image']:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported file type for {name}. Expected video or audio. type : {f.content_type}"
            )
        project_id = str(uuid.uuid4())

        try:
            save_file(video, os.path.join(UPLOAD_DIR, f"{project_id}_video"))
            save_file(audio, os.path.join(UPLOAD_DIR, f"{project_id}_audio"))
            if thumbnail:
                save_file(thumbnail, os.path.join(UPLOAD_DIR, f"{project_id}_thumbnail"))   
        except Exception as e:
            logger.error(f"Failed to save files for project {project_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save uploaded files"
            )
        
        #initialize job status
        JOBS[project_id] = {"status": "uploaded"}

        return UploadResponse(project_id=project_id)

