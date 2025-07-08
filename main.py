from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
import uuid
import os
import logging

#initialize app and logger
app = FastAPI(title="Unified Social Media Uploader Backend") #fast API instance
logger = logging.getLogger("uvicorn.error")

##########################
#configuration and helpers
###########################
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

#In memory stores for demo (FIXME use a real DB in prod)
JOBS: dict = {}     #job_id -> status/info
OAUTH_TOKENS: dict = {} #user_id -> tokens

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
#Data models
###########################
class UploadResponse(BaseModel):
    project_id: str = Field(..., description="The ID of the created project") 

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

