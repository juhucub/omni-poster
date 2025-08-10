import os
import re
import uuid
import hashlib
import sqlite3
import logging
import mimetypes    #FIXME MAKE OWN FILE
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Set

from fastapi import UploadFile, HTTPException, status
from pydantic import BaseModel, Field


# Configuration
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
UPLOAD_DB = os.path.join(UPLOAD_DIR, "uploads.db")

logger = logging.getLogger(__name__)

ALLOWED_VIDEO_TYPES = { "video/mp4", "video/webm","video/mpeg"}
ALLOWED_AUDIO_TYPES = { "audio/mpeg", "audio/wav", "audio/mp3" }
ALLOWED_IMAGE_TYPES = { "image/jpeg", "image/png", "image/gif" }
MAX_FILE_SIZE = 50 * 1024 * 1024  # 500 MB
MAX_TOTAL_SIZE = 1 * 1024 * 1024 * 1024  #1 GB

class UploadMeta(BaseModel):
    project_id: str
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


    async def save_to_storage(self, file: UploadFile, uploader_id: str) -> str:
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

async def save_upload_file(
    upload_file: UploadFile, 
    destination: Path,
    chunk_size: int = 1024 * 1024  # 1MB chunks
) -> Path:
    """
    Save an uploaded file to the specified destination path.
    
    Args:
        upload_file: The FastAPI UploadFile object
        destination: Path object where the file should be saved
        chunk_size: Size of chunks to read/write (default 1MB)
    
    Returns:
        Path: The path where the file was saved
        
    Raises:
        HTTPException: If file saving fails
    """
    try:
        # Ensure parent directory exists
        destination.parent.mkdir(parents=True, exist_ok=True)
        
        # Reset file pointer to beginning
        await upload_file.seek(0)
        
        # Save file in chunks to avoid memory issues with large files
        with open(destination, 'wb') as output_file:
            while chunk := await upload_file.read(chunk_size):
                output_file.write(chunk)
        
        # Reset file pointer for potential further processing
        await upload_file.seek(0)
        
        return destination
        
    except IOError as e:
        # Clean up partial file if write failed
        if destination.exists():
            destination.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )
    except Exception as e:
        # Clean up partial file if write failed
        if destination.exists():
            destination.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error saving file: {str(e)}"
        )


def validate_file(
    file: UploadFile,
    allowed_types: Set[str],
    file_label: str,
    max_size: int = MAX_FILE_SIZE
) -> None:
    """
    Validate an uploaded file's type and basic properties.
    
    Args:
        file: The UploadFile to validate
        allowed_types: Set of allowed MIME types
        file_label: Label for the file type (e.g., "video", "audio", "thumbnail")
        max_size: Maximum allowed file size in bytes
        
    Raises:
        HTTPException: If validation fails
    """
    # Check if file exists and has a filename
    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{file_label.capitalize()} file is required and must have a valid filename"
        )
    
    # Validate content type
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported {file_label} type: {file.content_type}. "
                   f"Allowed types: {', '.join(sorted(allowed_types))}"
        )
    
    # Validate filename doesn't contain path traversal attempts
    if '..' in file.filename or '/' in file.filename or '\\' in file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid filename: {file.filename}. Filename cannot contain path separators."
        )
    
    # Check file extension matches content type (basic validation)
    extension = Path(file.filename).suffix.lower()
    expected_extensions = get_expected_extensions(file.content_type)
    
    if extension and expected_extensions and extension not in expected_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension {extension} doesn't match content type {file.content_type}"
        )


def get_expected_extensions(content_type: str) -> Set[str]:
    """
    Get expected file extensions for a given content type.
    
    Args:
        content_type: MIME type string
        
    Returns:
        Set of expected extensions (including the dot)
    """
    extension_map = {
        # Video types
        'video/mp4': {'.mp4', '.m4v'},
        'video/webm': {'.webm'},
        'video/mpeg': {'.mpeg', '.mpg'},
        
        # Audio types
        'audio/mpeg': {'.mp3', '.mpeg'},
        'audio/wav': {'.wav'},
        'audio/mp3': {'.mp3'},
        
        # Image types
        'image/jpeg': {'.jpg', '.jpeg'},
        'image/png': {'.png'},
        'image/gif': {'.gif'},
    }
    
    return extension_map.get(content_type, set())


async def validate_file_magic_number(
    file: UploadFile,
    file_label: str
) -> None:
    """
    Validate file's magic number (file signature) for additional security.
    This provides defense against MIME type spoofing.
    
    Args:
        file: The UploadFile to validate
        file_label: Label for the file type
        
    Raises:
        HTTPException: If validation fails
    """
    # Magic numbers for common file types
    magic_numbers = {
        # Video
        b'\x00\x00\x00\x14\x66\x74\x79\x70': 'video/mp4',  # MP4
        b'\x00\x00\x00\x18\x66\x74\x79\x70': 'video/mp4',  # MP4
        b'\x00\x00\x00\x20\x66\x74\x79\x70': 'video/mp4',  # MP4
        b'\x1a\x45\xdf\xa3': 'video/webm',  # WebM
        
        # Audio
        b'\xff\xfb': 'audio/mpeg',  # MP3
        b'\xff\xf3': 'audio/mpeg',  # MP3
        b'\xff\xf2': 'audio/mpeg',  # MP3
        b'\x49\x44\x33': 'audio/mpeg',  # MP3 with ID3
        b'RIFF': 'audio/wav',  # WAV (check for WAVE later)
        
        # Images
        b'\xff\xd8\xff': 'image/jpeg',  # JPEG
        b'\x89PNG\r\n\x1a\n': 'image/png',  # PNG
        b'GIF87a': 'image/gif',  # GIF87a
        b'GIF89a': 'image/gif',  # GIF89a
    }
    
    # Read first 32 bytes for magic number detection
    await file.seek(0)
    header = await file.read(32)
    await file.seek(0)
    
    if not header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Empty {file_label} file"
        )
    
    # Check magic numbers
    detected_type = None
    for magic, mime_type in magic_numbers.items():
        if header.startswith(magic):
            detected_type = mime_type
            break
    
    # Special case for WAV files (need to check for "WAVE" after "RIFF")
    if header.startswith(b'RIFF') and b'WAVE' in header[:12]:
        detected_type = 'audio/wav'
    
    # If we detected a type, verify it matches the declared type
    if detected_type and not file.content_type.startswith(detected_type.split('/')[0]):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File content doesn't match declared type. "
                   f"Declared: {file.content_type}, Detected: {detected_type}"
        )


async def calculate_file_hash(
    file: UploadFile,
    algorithm: str = 'sha256'
) -> str:
    """
    Calculate hash of uploaded file for integrity checking and deduplication.
    
    Args:
        file: The UploadFile to hash
        algorithm: Hash algorithm to use (default: sha256)
        
    Returns:
        Hex string of the file hash
    """
    hash_func = hashlib.new(algorithm)
    
    await file.seek(0)
    while chunk := await file.read(8192):
        hash_func.update(chunk)
    await file.seek(0)
    
    return hash_func.hexdigest()


# Enhanced validate_file with optional magic number checking
async def validate_file_enhanced(
    file: UploadFile,
    allowed_types: Set[str],
    file_label: str,
    max_size: int = MAX_FILE_SIZE,
    check_magic: bool = True
) -> Optional[str]:
    """
    Enhanced file validation with optional magic number checking.
    
    Args:
        file: The UploadFile to validate
        allowed_types: Set of allowed MIME types
        file_label: Label for the file type
        max_size: Maximum allowed file size in bytes
        check_magic: Whether to validate magic numbers
        
    Returns:
        File hash if validation succeeds
        
    Raises:
        HTTPException: If validation fails
    """
    # Basic validation
    validate_file(file, allowed_types, file_label, max_size)
    
    # Magic number validation if requested
    if check_magic:
        await validate_file_magic_number(file, file_label)
    
    # Calculate and return file hash
    file_hash = await calculate_file_hash(file)
    return file_hash