import os
import logging
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, List

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
        try:
            conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS uploads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id TEXT NOT NULL,
                        filename TEXT NOT NULL,
                        url TEXT NOT NULL,
                        size INTEGER NOT NULL,
                        content_type TEXT NOT NULL,
                        uploader_id TEXT NOT NULL,
                        uploaded_at TEXT NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
            )

            # Create index for faster queries by user
            conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_uploader_id 
                    ON uploads(uploader_id)
                    """
            )
                
                # Create index for faster queries by project
            conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_project_id 
                    ON uploads(project_id)
                    """
            )
            conn.commit()
            logger.info("Upload database initialized")
        except Exception as e:
            logger.error(f"Failed to initialize upload database: {e}")
            raise
        finally:
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
        try:
            conn.execute(
                """
                INSERT INTO uploads (project_id, filename, url, size, content_type, uploader_id, uploaded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    meta.project_id,
                    meta.filename,
                    meta.url,
                    meta.size,
                    meta.content_type,
                    meta.uploader_id,
                    meta.timestamp.isoformat()
                )
            )
            conn.commit()
            logger.info(f"Recorded upload metadata for {meta.filename} (project: {meta.project_id})")
        except Exception as e:
            logger.error(f"Failed to record upload metadata: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record upload metadata"
            )
        finally:
            conn.close()
            
        def get_user_upload_history(self, uploader_id: str, limit: int = 100) -> List[Dict[str, Any]]:
            """
            Retrieves upload history for a specific user, ordered by upload time (newest first).
            
            Args:
                uploader_id: The ID of the user whose uploads to retrieve
                limit: Maximum number of records to return (default 100)
                
            Returns:
                List of upload records as dictionaries
            """
            conn = sqlite3.connect(UPLOAD_DB)
            try:
                # Use row factory to get dict-like results
                conn.row_factory = sqlite3.Row
                
                mwahah = conn.execute(
                    """
                    SELECT project_id, filename, url, size, content_type, uploader_id, uploaded_at
                    FROM uploads 
                    WHERE uploader_id = ? 
                    ORDER BY uploaded_at DESC 
                    LIMIT ?
                    """,
                    (uploader_id, limit)
                )
                
                rows = mwahah.fetchall()
                
                # Convert to list of dictionaries
                history = []
                for row in rows:
                    history.append({
                        'project_id': row['project_id'],
                        'filename': row['filename'],
                        'url': row['url'],
                        'size': row['size'],
                        'content_type': row['content_type'],
                        'uploader_id': row['uploader_id'],
                        'uploaded_at': row['uploaded_at']
                    })
                
                logger.info(f"Retrieved {len(history)} upload records for user {uploader_id}")
                return history
                
            except Exception as e:
                logger.error(f"Failed to retrieve upload history for user {uploader_id}: {e}")
                raise
            finally:
                conn.close()

    def delete_upload_record(self, project_id: str, uploader_id: str) -> bool:
        """
        Deletes upload records for a specific project (user can only delete their own).
        
        Args:
            project_id: The project ID to delete
            uploader_id: The user ID (for security)
            
        Returns:
            True if records were deleted, False if no records found
        """
        conn = sqlite3.connect(UPLOAD_DB)
        try:
            cursor = conn.execute(
                "DELETE FROM uploads WHERE project_id = ? AND uploader_id = ?",
                (project_id, uploader_id)
            )
            conn.commit()
            
            deleted_count = cursor.rowcount
            logger.info(f"Deleted {deleted_count} upload records for project {project_id}")
            return deleted_count > 0
            
        except Exception as e:
            logger.error(f"Failed to delete upload records for project {project_id}: {e}")
            raise
        finally:
            conn.close()


    def get_upload_stats(self, uploader_id: str) -> Dict[str, Any]:
        """
        Get upload statistics for a user.
        
        Args:
            uploader_id: The user ID
            
        Returns:
            Dictionary with upload statistics
        """
        conn = sqlite3.connect(UPLOAD_DB)
        try:
            cursor = conn.execute(
                """
                SELECT 
                    COUNT(*) as total_uploads,
                    COUNT(DISTINCT project_id) as total_projects,
                    SUM(size) as total_size,
                    MIN(uploaded_at) as first_upload,
                    MAX(uploaded_at) as last_upload
                FROM uploads 
                WHERE uploader_id = ?
                """,
                (uploader_id,)
            )
            
            row = cursor.fetchone()
            
            if row:
                return {
                    'total_uploads': row[0] or 0,
                    'total_projects': row[1] or 0,
                    'total_size_bytes': row[2] or 0,
                    'first_upload': row[3],
                    'last_upload': row[4]
                }
            else:
                return {
                    'total_uploads': 0,
                    'total_projects': 0,
                    'total_size_bytes': 0,
                    'first_upload': None,
                    'last_upload': None
                } 
        except Exception as e:
            logger.error(f"Failed to get upload stats for user {uploader_id}: {e}")
            raise
        finally:
            conn.close()

def get_upload_service() -> UploadService:
    return UploadService()