import os
import sqlite3
import pytest
from io import BytesIO
from datetime import datetime
from fastapi import UploadFile
from app.services.upload import UploadService, UploadMeta, UPLOAD_DB, UPLOAD_DIR

@pytest.fixture(scope='function')
def service():
    """Create a fresh UploadService instance for each test."""
    # Clean up local storage before each test
    if os.path.exists(UPLOAD_DB):
        os.remove(UPLOAD_DB)
    if os.path.isdir(UPLOAD_DIR):
        for fn in os.listdir(UPLOAD_DIR):
            path = os.path.join(UPLOAD_DIR, fn)
            if os.path.isfile(path):
                os.remove(path)
    return UploadService()

async def make_uploadfile(content: bytes, filename: str, content_type: str):
    """Helper function to create UploadFile instances for testing."""
    bio = BytesIO(content)
    return UploadFile(
        file=bio,
        filename=filename,
        headers={"content-type": content_type},
    )

@pytest.mark.asyncio
async def test_save_to_storage_local(service):
    """Test saving files to local storage."""
    data = b"hello world"
    uf = await make_uploadfile(data, 'test.txt', 'text/plain')
    url = await service.save_to_storage(uf, 'user1')
    
    assert url.startswith('file://')
    path = url.replace('file://', '')
    assert os.path.exists(path)
    
    with open(path, 'rb') as f:
        assert f.read() == data

@pytest.mark.asyncio
async def test_record_upload(service):
    """Test recording upload metadata."""
    meta = UploadMeta(
        project_id='proj-123',
        filename='test.txt',
        url='file:///tmp/test.txt',
        size=123,
        content_type='text/plain',
        uploader_id='user1'
    )
    
    service.record_upload(meta)
    
    # Verify record was inserted
    conn = sqlite3.connect(UPLOAD_DB)
    try:
        cursor = conn.execute('SELECT * FROM uploads WHERE project_id = ?', ('proj-123',))
        row = cursor.fetchone()
        assert row is not None
        assert row[1] == 'proj-123'  # project_id
        assert row[2] == 'test.txt'  # filename
        assert row[6] == 'user1'     # uploader_id
    finally:
        conn.close()

def test_get_user_upload_history_empty(service):
    """Test getting upload history for user with no uploads."""
    history = service.get_user_upload_history('nonexistent_user')
    assert history == []

def test_get_user_upload_history_with_data(service):
    """Test getting upload history with multiple uploads."""
    # Create test data
    uploads = [
        UploadMeta(
            project_id='proj-1',
            filename='video1.mp4',
            url='file:///uploads/video1.mp4',
            size=1000,
            content_type='video/mp4',
            uploader_id='user1',
            timestamp=datetime(2023, 1, 1, 10, 0, 0)
        ),
        UploadMeta(
            project_id='proj-2',
            filename='audio1.mp3',
            url='file:///uploads/audio1.mp3',
            size=500,
            content_type='audio/mpeg',
            uploader_id='user1',
            timestamp=datetime(2023, 1, 2, 10, 0, 0)
        ),
        UploadMeta(
            project_id='proj-3',
            filename='video2.mp4',
            url='file:///uploads/video2.mp4',
            size=2000,
            content_type='video/mp4',
            uploader_id='user2',  # Different user
            timestamp=datetime(2023, 1, 3, 10, 0, 0)
        ),
    ]
    
    # Insert test data
    for upload in uploads:
        service.record_upload(upload)
    
    # Get history for user1
    history = service.get_user_upload_history('user1')
    
    assert len(history) == 2
    # Should be ordered by upload time, newest first
    assert history[0]['filename'] == 'audio1.mp3'
    assert history[1]['filename'] == 'video1.mp4'
    
    # Verify all expected fields are present
    for record in history:
        assert 'project_id' in record
        assert 'filename' in record
        assert 'url' in record
        assert 'size' in record
        assert 'content_type' in record
        assert 'uploader_id' in record
        assert 'uploaded_at' in record
        assert record['uploader_id'] == 'user1'

def test_get_user_upload_history_limit(service):
    """Test that the limit parameter works correctly."""
    # Create more uploads than the limit
    for i in range(5):
        meta = UploadMeta(
            project_id=f'proj-{i}',
            filename=f'file-{i}.txt',
            url=f'file:///uploads/file-{i}.txt',
            size=100,
            content_type='text/plain',
            uploader_id='user1',
            timestamp=datetime(2023, 1, i+1, 10, 0, 0)
        )
        service.record_upload(meta)
    
    # Request with limit
    history = service.get_user_upload_history('user1', limit=3)
    assert len(history) == 3
    
    # Should get the 3 most recent
    assert history[0]['filename'] == 'file-4.txt'
    assert history[1]['filename'] == 'file-3.txt'
    assert history[2]['filename'] == 'file-2.txt'

def test_get_project_files(service):
    """Test getting all files for a specific project."""
    # Create test data with multiple files for same project
    uploads = [
        UploadMeta(
            project_id='proj-123',
            filename='video.mp4',
            url='file:///uploads/video.mp4',
            size=1000,
            content_type='video/mp4',
            uploader_id='user1',
            timestamp=datetime(2023, 1, 1, 10, 0, 0)
        ),
        UploadMeta(
            project_id='proj-123',
            filename='audio.mp3',
            url='file:///uploads/audio.mp3',
            size=500,
            content_type='audio/mpeg',
            uploader_id='user1',
            timestamp=datetime(2023, 1, 1, 10, 1, 0)
        ),
        UploadMeta(
            project_id='proj-456',  # Different project
            filename='other.txt',
            url='file:///uploads/other.txt',
            size=100,
            content_type='text/plain',
            uploader_id='user1',
            timestamp=datetime(2023, 1, 1, 10, 2, 0)
        ),
    ]
    
    for upload in uploads:
        service.record_upload(upload)
    
    # Get files for specific project
    files = service.get_project_files('proj-123', 'user1')
    
    assert len(files) == 2
    # Should be ordered by upload time, oldest first for project files
    assert files[0]['filename'] == 'video.mp4'
    assert files[1]['filename'] == 'audio.mp3'
    
    # Test security - user can't see other user's projects
    files = service.get_project_files('proj-123', 'user2')
    assert len(files) == 0

def test_delete_upload_record(service):
    """Test deleting upload records."""
    meta = UploadMeta(
        project_id='proj-delete',
        filename='delete-me.txt',
        url='file:///uploads/delete-me.txt',
        size=100,
        content_type='text/plain',
        uploader_id='user1'
    )
    service.record_upload(meta)
    
    # Verify it exists
    history = service.get_user_upload_history('user1')
    assert len(history) == 1
    
    # Delete it
    deleted = service.delete_upload_record('proj-delete', 'user1')
    assert deleted is True
    
    # Verify it's gone
    history = service.get_user_upload_history('user1')
    assert len(history) == 0
    
    # Try to delete non-existent
    deleted = service.delete_upload_record('proj-nonexistent', 'user1')
    assert deleted is False

def test_get_upload_stats(service):
    """Test getting upload statistics."""
    # Initially no stats
    stats = service.get_upload_stats('user1')
    assert stats['total_uploads'] == 0
    assert stats['total_projects'] == 0
    assert stats['total_size_bytes'] == 0
    
    # Add some uploads
    uploads = [
        UploadMeta(
            project_id='proj-1',
            filename='file1.txt',
            url='file:///uploads/file1.txt',
            size=100,
            content_type='text/plain',
            uploader_id='user1',
            timestamp=datetime(2023, 1, 1, 10, 0, 0)
        ),
        UploadMeta(
            project_id='proj-1',  # Same project
            filename='file2.txt',
            url='file:///uploads/file2.txt',
            size=200,
            content_type='text/plain',
            uploader_id='user1',
            timestamp=datetime(2023, 1, 2, 10, 0, 0)
        ),
        UploadMeta(
            project_id='proj-2',  # Different project
            filename='file3.txt',
            url='file:///uploads/file3.txt',
            size=300,
            content_type='text/plain',
            uploader_id='user1',
            timestamp=datetime(2023, 1, 3, 10, 0, 0)
        ),
    ]
    
    for upload in uploads:
        service.record_upload(upload)
    
    # Check stats
    stats = service.get_upload_stats('user1')
    assert stats['total_uploads'] == 3
    assert stats['total_projects'] == 2
    assert stats['total_size_bytes'] == 600
    assert stats['first_upload'] == '2023-01-01T10:00:00'
    assert stats['last_upload'] == '2023-01-03T10:00:00'

@pytest.mark.asyncio
async def test_upload_file_without_filename_fails(service):
    """Test that uploading a file without filename raises an error."""
    bio = BytesIO(b"test content")
    uf = UploadFile(file=bio, filename=None)
    
    with pytest.raises(Exception):  # Should raise HTTPException
        await service.save_to_storage(uf, 'user1')

def test_database_indexes_created(service):
    """Test that database indexes are created properly."""
    conn = sqlite3.connect(UPLOAD_DB)
    try:
        # Check that indexes exist
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]
        
        assert 'idx_uploader_id' in indexes
        assert 'idx_project_id' in indexes
    finally:
        conn.close()