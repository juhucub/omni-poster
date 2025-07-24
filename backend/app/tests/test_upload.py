import os
import sqlite3
import pytest
from io import BytesIO
from fastapi import UploadFile
from app.services.upload import UploadService, UploadMeta, UPLOAD_DB, UPLOAD_DIR

@pytest.fixture(scope='module')
def service():
    # Clean up local storage
    if os.path.exists(UPLOAD_DB):
        os.remove(UPLOAD_DB)
    if os.path.isdir(UPLOAD_DIR):
        for fn in os.listdir(UPLOAD_DIR):
            path = os.path.join(UPLOAD_DIR, fn)
            if os.path.isfile(path):
                os.remove(path)
    return UploadService()

async def make_uploadfile(content: bytes, filename: str, content_type: str):
    bio = BytesIO(content)
    return UploadFile(
        file=bio,
        filename=filename,
        headers={"content-type": content_type},
    )

@pytest.mark.asyncio
async def test_save_to_storage_local(service):
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
    meta = UploadMeta(
        filename='a.txt',
        url='file:///tmp/a.txt',
        size=123,
        content_type='text/plain',
        uploader_id='user1'
    )
    service.record_upload(meta)
    conn = sqlite3.connect(UPLOAD_DB)
    row = conn.execute('SELECT * FROM uploads').fetchone()
    conn.close()
    assert row[0] == 'a.txt'
    assert row[1] == 'file:///tmp/a.txt'
    assert row[2] == 123
    assert row[3] == 'text/plain'
    assert row[4] == 'user1'