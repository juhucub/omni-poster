import os
import logging
import sqlite3
from datetime import datetime
from typing import Optional

from fastapi import UploadFile, HTTPException, status
from pydantic import BaseModel, Field

# Configuration
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
UPLOAD_DB = os.path.join(UPLOAD_DIR, "uploads.db")

logger = logging.getLogger(__name__)

class UploadMeta(BaseModel):
    filename: str
    url: str
    size: int
    content_type: str
    uploader_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class UploadService:
    """
    Service for saving files locally and recording upload history in SQLite.
    """
    def __init__(self):
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

    async def save_to_storage(self, file: UploadFile, uploader_id: str = "anonymous") -> str:
        """
        Saves UploadFile to local disk under UPLOAD_DIR and returns a file:// URL.
        """
        safe_name = os.path.basename(file.filename)
        key = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{safe_name}"
        dest_path = os.path.join(UPLOAD_DIR, key)
        size = 0
        try:
            with open(dest_path, "wb") as out_file:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    size += len(chunk)
            logger.info(f"Saved file locally at {dest_path}")
            return f"file://{os.path.abspath(dest_path)}"
        except Exception as e:
            logger.error(f"Local save failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save file to local storage"
            )
        finally:
            await file.close()

    def record_upload(self, meta: UploadMeta) -> None:
        """
        Records upload metadata in SQLite DB.
        """
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