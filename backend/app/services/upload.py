import os
import logging
import sqlite3
from datetime import datetime
from typing import Optional
from fastapi import UploadFile, HTTPException, status

from pydantic import Field, BaseModel

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

UPLOAD_DB = os.getenv("UPLOAD_DB", "./uploads.db")

logger = logging.getLogger("uvicorn.error")

#Pydantic model for upload metadata
class UploadMeta(BaseModel):
    filename: str
    url: str
    size: int
    content_type: str
    uploader_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

#Service for handling file storage AND UPLOAD HISTORY
class UploadService:
    
    def __init__(self):
        # s3 client if i was fancy but i am NOT
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(UPLOAD_DB)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS uploads (
                filename TEXT,
                url TEXT,
                size INTEGER,
                content_type TEXT,
                uploader_id TEXT,
                timestamp TEXT
            )
            """
        )
        conn.commit()
        conn.close()

#would save upload file to s4 but im not doing that. local disk is loml
#returns accessible URL of stored file
async def save_to_storage(self, file: UploadFile, uploader_id: str) -> str:

    #sanitize filename
    safe_name = os.path.basename(file.filename)
    #build unique key
    key = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{safe_name}"

    #Stream file and count size
    dest_path = os.path.join(UPLOAD_DIR, key)
    size = 0
    try:
        with open(dest_path, "wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                buffer.write(chunk)
                size += len(chunk)
        logger.info(f"File saved to {dest_path}")
        return f"file://{os.path.abspath(dest_path)}"        
    except Exception as e:
        logger.error(f"Error saving file {file.filename}: {e}")
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = "Failed to save uploaded file"
        ) 
    finally:
        await file.close()

#Records upload meta data in my lovely DB
def record_upload(self, meta: UploadMeta) -> None:
    conn = sqlite3.connect(UPLOAD_DB)
    conn.execute(
        "INSERT INTO uploads VALUES (?, ?, ?, ?, ?, ?)",
        (
            meta.filename,
            meta.url,
            meta.size,
            meta.content_type,
            meta.uploader_id,
            meta.timestamp.isoformat()
        )
    )
    conn.commit()
    conn.close()

def get_upload_service() -> UploadService:
    return UploadService()