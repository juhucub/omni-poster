from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.models import GenerationJob, SocialAccount
from app.services.crypto import decrypt_secret
from app.services.rendering import ProjectRenderService
from app.tasks.generation import STALE_GENERATION_ERROR, process_generation_job, reconcile_stale_generation_jobs
from app.tasks.publish import process_publish_job
from app.tasks.scheduler import dispatch_due_publish_jobs


def test_background_presets_are_loaded_from_bundled_media_dir(auth_client: TestClient):
    preset_dir = Path("test_storage") / "bundled" / "presets"
    preset_dir.mkdir(parents=True, exist_ok=True)
    (preset_dir / "aurora_grid.mp4").write_bytes(b"preset-video")

    response = auth_client.get("/background-presets")
    assert response.status_code == 200
    assert response.json() == [
        {
            "key": "aurora_grid",
            "name": "Aurora Grid",
            "description": "Curated background preset",
            "filename": "aurora_grid.mp4",
            "content_url": "/background-presets/aurora_grid/content",
        }
    ]


def test_character_portrait_prefers_bundled_media_dir_over_runtime(auth_client: TestClient, tmp_path: Path):
    bundled_characters = Path("test_storage") / "bundled" / "characters"
    runtime_characters = Path("test_storage") / "characters"
    bundled_characters.mkdir(parents=True, exist_ok=True)
    runtime_characters.mkdir(parents=True, exist_ok=True)

    bundled_portrait = bundled_characters / "speaker_1.png"
    runtime_portrait = runtime_characters / "speaker_1.png"
    bundled_portrait.write_bytes(b"bundled-portrait")
    runtime_portrait.write_bytes(b"runtime-portrait")

    service = ProjectRenderService()
    resolved = service._resolve_character_portrait("Host", 0, tmp_path)

    assert resolved == bundled_portrait


def _create_project_flow(client: TestClient) -> dict:
    project = client.post("/projects", json={"name": "First Project", "target_platform": "youtube"})
    assert project.status_code == 201
    project_id = project.json()["id"]

    script = client.put(
        f"/projects/{project_id}/script",
        json={"raw_text": "<Host> Hello there\n<Guest> General Kenobi", "source": "manual"},
    )
    assert script.status_code == 200

    asset = client.post(
        f"/projects/{project_id}/assets/background",
        files={"file": ("background.mp4", b"fake-video", "video/mp4")},
    )
    assert asset.status_code == 201

    metadata = client.put(
        f"/projects/{project_id}/metadata/youtube",
        json={
            "title": "A Real Short",
            "description": "Description",
            "tags": ["host", "guest"],
            "source": "manual",
        },
    )
    assert metadata.status_code == 200

    return {
        "project_id": project_id,
        "asset_id": asset.json()["id"],
        "metadata_id": metadata.json()["id"],
    }


def _link_youtube_account(client: TestClient, monkeypatch) -> int:
    monkeypatch.setattr(
        "app.services.youtube_accounts.exchange_code_for_tokens",
        lambda code: {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
        },
    )
    monkeypatch.setattr(
        "app.services.youtube_accounts.fetch_channel_identity",
        lambda access_token: {"channel_id": "channel-123", "channel_title": "My Channel"},
    )

    start = client.post("/social-accounts/youtube/connect/start")
    assert start.status_code == 200
    state = start.json()["state"]

    callback = client.get(
        "/social-accounts/youtube/callback",
        params={"code": "oauth-code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 307

    accounts = client.get("/social-accounts")
    assert accounts.status_code == 200
    return accounts.json()["items"][0]["id"]


def test_auth_flow_and_logout(client: TestClient):
    username = "auth_user"
    register = client.post("/auth/register", json={"username": username, "password": "Password1"})
    assert register.status_code == 201
    assert register.cookies.get("access_token")

    me = client.get("/auth/me", cookies=register.cookies)
    assert me.status_code == 200
    assert me.json()["username"] == username

    logout = client.post("/auth/logout", cookies=register.cookies)
    assert logout.status_code == 200

    logged_out_client = TestClient(client.app)
    try:
        after_logout = logged_out_client.get("/auth/me")
    finally:
        logged_out_client.close()
    assert after_logout.status_code == 401


def test_script_validation_and_asset_ownership(auth_client: TestClient, client: TestClient):
    project = auth_client.post("/projects", json={"name": "Ownership", "target_platform": "youtube"})
    project_id = project.json()["id"]

    invalid = auth_client.put(
        f"/projects/{project_id}/script",
        json={"raw_text": "plain text", "source": "manual"},
    )
    assert invalid.status_code == 422

    asset = auth_client.post(
        f"/projects/{project_id}/assets/background",
        files={"file": ("background.mp4", b"fake-video", "video/mp4")},
    )
    assert asset.status_code == 201

    other_user = client.post("/auth/register", json={"username": "other_user", "password": "Password1"})
    assert other_user.status_code == 201
    asset_id = asset.json()["id"]

    forbidden_get = client.get(f"/assets/{asset_id}/content", cookies=other_user.cookies)
    assert forbidden_get.status_code == 404

    forbidden_delete = client.delete(f"/projects/{project_id}/assets/{asset_id}", cookies=other_user.cookies)
    assert forbidden_delete.status_code == 404


def test_generation_job_lifecycle(auth_client: TestClient, monkeypatch):
    flow = _create_project_flow(auth_client)

    source_preview = Path("test_storage") / "source_preview.mp4"
    source_preview.write_bytes(b"rendered-preview")

    monkeypatch.setattr(
        ProjectRenderService,
        "render_preview",
        lambda self, project_id, background_video_path, parsed_lines, style_preset: {
            "output_path": str(source_preview),
            "duration_seconds": 1.5,
        },
    )
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: process_generation_job(job_id))

    create_job = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    assert create_job.status_code == 201
    assert create_job.json()["status"] == "queued"

    job_id = create_job.json()["id"]
    job = auth_client.get(f"/generation-jobs/{job_id}")
    assert job.status_code == 200
    assert job.json()["status"] == "completed"
    assert job.json()["output_video_id"] is not None

    project = auth_client.get(f"/projects/{flow['project_id']}")
    assert project.status_code == 200
    assert project.json()["status"] == "preview_ready"
    assert project.json()["latest_preview"] is not None


def test_generation_job_dedupes_active_job(auth_client: TestClient, monkeypatch):
    flow = _create_project_flow(auth_client)
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: None)

    first = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    assert first.status_code == 201

    second = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["status"] == "queued"

    active = auth_client.get(f"/projects/{flow['project_id']}/generation-jobs/active")
    assert active.status_code == 200
    assert active.json()["id"] == first.json()["id"]


def test_stale_processing_generation_job_is_reconciled(auth_client: TestClient, monkeypatch):
    flow = _create_project_flow(auth_client)
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: None)

    create_job = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    assert create_job.status_code == 201
    stale_job_id = create_job.json()["id"]

    db = SessionLocal()
    try:
        job = db.get(GenerationJob, stale_job_id)
        job.status = "processing"
        job.progress = 20
        job.started_at = datetime.utcnow() - timedelta(minutes=20)
        db.commit()
    finally:
        db.close()

    source_preview = Path("test_storage") / "reconciled_preview.mp4"
    source_preview.write_bytes(b"rendered-preview")
    monkeypatch.setattr(
        ProjectRenderService,
        "render_preview",
        lambda self, project_id, background_video_path, parsed_lines, style_preset: {
            "output_path": str(source_preview),
            "duration_seconds": 1.2,
        },
    )

    next_job = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    assert next_job.status_code == 201
    assert next_job.json()["id"] != stale_job_id

    db = SessionLocal()
    try:
        stale_job = db.get(GenerationJob, stale_job_id)
        assert stale_job.status == "failed"
        assert stale_job.error_message == STALE_GENERATION_ERROR
        assert stale_job.finished_at is not None
    finally:
        db.close()


def test_youtube_link_refresh_and_reconnect_required(auth_client: TestClient, monkeypatch):
    account_id = _link_youtube_account(auth_client, monkeypatch)

    db = SessionLocal()
    try:
        account = db.get(SocialAccount, account_id)
        account.token_expires_at = datetime.utcnow() - timedelta(minutes=5)
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(
        "app.services.youtube_accounts.refresh_tokens",
        lambda refresh_token: {"access_token": "refreshed-token", "expires_in": 1800},
    )

    refresh = auth_client.post(f"/social-accounts/{account_id}/refresh")
    assert refresh.status_code == 200
    assert refresh.json()["status"] == "linked"

    db = SessionLocal()
    try:
        account = db.get(SocialAccount, account_id)
        assert decrypt_secret(account.access_token_encrypted) == "refreshed-token"
        account.token_expires_at = datetime.utcnow() - timedelta(minutes=5)
        account.refresh_token_encrypted = None
        account.status = "linked"
        db.commit()
    finally:
        db.close()

    reconnect = auth_client.post(f"/social-accounts/{account_id}/refresh")
    assert reconnect.status_code == 409

    db = SessionLocal()
    try:
        account = db.get(SocialAccount, account_id)
        assert account.status == "reconnect_required"
    finally:
        db.close()


def test_publish_job_lifecycle_and_history(auth_client: TestClient, monkeypatch):
    flow = _create_project_flow(auth_client)
    account_id = _link_youtube_account(auth_client, monkeypatch)

    preview_source = Path("test_storage") / "publish_preview.mp4"
    preview_source.write_bytes(b"rendered-preview")
    monkeypatch.setattr(
        ProjectRenderService,
        "render_preview",
        lambda self, project_id, background_video_path, parsed_lines, style_preset: {
            "output_path": str(preview_source),
            "duration_seconds": 1.0,
        },
    )
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: process_generation_job(job_id))
    monkeypatch.setattr(process_publish_job, "delay", lambda job_id: process_publish_job(job_id))
    monkeypatch.setattr(
        "app.tasks.publish.upload_short",
        lambda **kwargs: {
            "external_post_id": "video-123",
            "external_url": "https://www.youtube.com/watch?v=video-123",
        },
    )

    generation = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    output_video_id = auth_client.get(f"/generation-jobs/{generation.json()['id']}").json()["output_video_id"]

    project_update = auth_client.patch(
        f"/projects/{flow['project_id']}",
        json={"selected_social_account_id": account_id},
    )
    assert project_update.status_code == 200

    approve = auth_client.post(f"/projects/{flow['project_id']}/approve-preview")
    assert approve.status_code == 200

    publish = auth_client.post(
        f"/projects/{flow['project_id']}/publish-jobs",
        json={
            "social_account_id": account_id,
            "output_video_id": output_video_id,
            "platform_metadata_id": flow["metadata_id"],
            "publish_mode": "now",
            "scheduled_for": None,
        },
    )
    assert publish.status_code == 201
    assert publish.json()["status"] == "queued"

    job = auth_client.get(f"/publish-jobs/{publish.json()['id']}")
    assert job.status_code == 200
    assert job.json()["status"] == "published"
    assert job.json()["published_post_url"] == "https://www.youtube.com/watch?v=video-123"

    history = auth_client.get("/publish-history")
    assert history.status_code == 200
    assert len(history.json()["jobs"]) == 1
    assert len(history.json()["posts"]) == 1


def test_scheduled_publish_dispatch_runs_once(auth_client: TestClient, monkeypatch):
    flow = _create_project_flow(auth_client)
    account_id = _link_youtube_account(auth_client, monkeypatch)

    preview_source = Path("test_storage") / "scheduled_preview.mp4"
    preview_source.write_bytes(b"rendered-preview")
    monkeypatch.setattr(
        ProjectRenderService,
        "render_preview",
        lambda self, project_id, background_video_path, parsed_lines, style_preset: {
            "output_path": str(preview_source),
            "duration_seconds": 1.0,
        },
    )
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: process_generation_job(job_id))
    monkeypatch.setattr(process_publish_job, "delay", lambda job_id: process_publish_job(job_id))
    monkeypatch.setattr(
        "app.tasks.publish.upload_short",
        lambda **kwargs: {
            "external_post_id": "scheduled-video",
            "external_url": "https://www.youtube.com/watch?v=scheduled-video",
        },
    )

    generation = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    output_video_id = auth_client.get(f"/generation-jobs/{generation.json()['id']}").json()["output_video_id"]
    auth_client.patch(f"/projects/{flow['project_id']}", json={"selected_social_account_id": account_id})
    auth_client.post(f"/projects/{flow['project_id']}/approve-preview")

    scheduled_for = (datetime.utcnow() - timedelta(minutes=1)).isoformat()
    publish = auth_client.post(
        f"/projects/{flow['project_id']}/publish-jobs",
        json={
            "social_account_id": account_id,
            "output_video_id": output_video_id,
            "platform_metadata_id": flow["metadata_id"],
            "publish_mode": "schedule",
            "scheduled_for": scheduled_for,
        },
    )
    assert publish.status_code == 201
    assert publish.json()["status"] == "scheduled"

    first_run = dispatch_due_publish_jobs()
    second_run = dispatch_due_publish_jobs()
    assert first_run["dispatched"] == 1
    assert second_run["dispatched"] == 0

    history = auth_client.get("/publish-history")
    assert history.status_code == 200
    assert history.json()["posts"][0]["external_post_id"] == "scheduled-video"


def test_script_generation_revisions_and_restore(auth_client: TestClient):
    project = auth_client.post("/projects", json={"name": "Script Lab", "target_platform": "youtube"})
    assert project.status_code == 201
    project_id = project.json()["id"]

    generated = auth_client.post(
        f"/projects/{project_id}/script/generate",
        json={
            "prompt": "how an approval queue reduces publishing mistakes",
            "character_names": ["Host", "Editor"],
            "tone": "explanatory",
        },
    )
    assert generated.status_code == 201
    first_revision_id = generated.json()["current_revision"]["id"]

    update = auth_client.put(
        f"/projects/{project_id}/script",
        json={
            "parsed_lines": [
                {"speaker": "Host", "text": "We generated a first pass.", "order": 0},
                {"speaker": "Editor", "text": "Now we can revise it line by line.", "order": 1},
            ],
            "source": "manual",
            "parent_revision_id": first_revision_id,
        },
    )
    assert update.status_code == 200
    assert update.json()["current_revision"]["parent_revision_id"] == first_revision_id

    revisions = auth_client.get(f"/projects/{project_id}/script-revisions")
    assert revisions.status_code == 200
    assert len(revisions.json()["items"]) == 2

    restore = auth_client.post(f"/projects/{project_id}/script-revisions/{first_revision_id}/restore")
    assert restore.status_code == 200
    assert restore.json()["current_revision"]["source"] == "restore"


def test_review_queue_routing_and_auto_publish(auth_client: TestClient, monkeypatch):
    flow = _create_project_flow(auth_client)
    account_id = _link_youtube_account(auth_client, monkeypatch)

    preview_source = Path("test_storage") / "review_queue_preview.mp4"
    preview_source.write_bytes(b"rendered-preview")
    monkeypatch.setattr(
        ProjectRenderService,
        "render_preview",
        lambda self, project_id, background_video_path, parsed_lines, style_preset: {
            "output_path": str(preview_source),
            "duration_seconds": 1.25,
        },
    )
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: process_generation_job(job_id))
    monkeypatch.setattr(process_publish_job, "delay", lambda job_id: process_publish_job(job_id))
    monkeypatch.setattr(
        "app.tasks.publish.upload_short",
        lambda **kwargs: {
            "external_post_id": "review-auto-video",
            "external_url": "https://www.youtube.com/watch?v=review-auto-video",
        },
    )

    auth_client.patch(
        f"/projects/{flow['project_id']}",
        json={
            "selected_social_account_id": account_id,
            "automation_mode": "auto",
            "allowed_platforms": ["youtube"],
            "preferred_account_type": "owned_channel",
        },
    )

    generation = auth_client.post(
        f"/projects/{flow['project_id']}/renders",
        json={"background_style": "blur", "output_kind": "preview", "provider_name": "local-compositor"},
    )
    assert generation.status_code == 201
    output_video_id = auth_client.get(f"/generation-jobs/{generation.json()['id']}").json()["output_video_id"]

    submit = auth_client.post(
        f"/projects/{flow['project_id']}/review/submit",
        json={"output_video_id": output_video_id, "note": "Ready for human review."},
    )
    assert submit.status_code == 201
    review_id = submit.json()["id"]
    assert submit.json()["status"] == "pending"

    changes = auth_client.post(
        f"/reviews/{review_id}/request-changes",
        json={"summary": "Tighten the script", "rejection_reason": "Shorten the intro."},
    )
    assert changes.status_code == 200
    assert changes.json()["status"] == "changes_requested"

    approve = auth_client.post(
        f"/reviews/{review_id}/approve",
        json={"summary": "Approved after revision."},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    routing = auth_client.post(f"/projects/{flow['project_id']}/routing/suggest")
    assert routing.status_code == 200
    assert routing.json()["recommended_platform"] == "youtube"
    assert routing.json()["social_account_id"] == account_id

    auto_publish = auth_client.post(
        f"/projects/{flow['project_id']}/publish/auto",
        json={
            "platform": "youtube",
            "output_video_id": output_video_id,
            "platform_metadata_id": flow["metadata_id"],
            "publish_mode": "now",
            "scheduled_for": None,
            "automation_mode": "auto",
        },
    )
    assert auto_publish.status_code == 201
    assert auto_publish.json()["status"] == "queued"

    job = auth_client.get(f"/publish-jobs/{auto_publish.json()['id']}")
    assert job.status_code == 200
    assert job.json()["status"] == "published"
    assert job.json()["published_post_url"] == "https://www.youtube.com/watch?v=review-auto-video"


def test_end_to_end_happy_path(auth_client: TestClient, monkeypatch):
    flow = _create_project_flow(auth_client)
    account_id = _link_youtube_account(auth_client, monkeypatch)

    preview_source = Path("test_storage") / "happy_path_preview.mp4"
    preview_source.write_bytes(b"rendered-preview")
    monkeypatch.setattr(
        ProjectRenderService,
        "render_preview",
        lambda self, project_id, background_video_path, parsed_lines, style_preset: {
            "output_path": str(preview_source),
            "duration_seconds": 2.0,
        },
    )
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: process_generation_job(job_id))
    monkeypatch.setattr(process_publish_job, "delay", lambda job_id: process_publish_job(job_id))
    monkeypatch.setattr(
        "app.tasks.publish.upload_short",
        lambda **kwargs: {
            "external_post_id": "happy-video",
            "external_url": "https://www.youtube.com/watch?v=happy-video",
        },
    )

    generation = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "blur"},
    )
    generation_job = auth_client.get(f"/generation-jobs/{generation.json()['id']}")
    output_video_id = generation_job.json()["output_video_id"]

    auth_client.patch(f"/projects/{flow['project_id']}", json={"selected_social_account_id": account_id})
    approve = auth_client.post(f"/projects/{flow['project_id']}/approve-preview")
    assert approve.status_code == 200

    publish = auth_client.post(
        f"/projects/{flow['project_id']}/publish-jobs",
        json={
            "social_account_id": account_id,
            "output_video_id": output_video_id,
            "platform_metadata_id": flow["metadata_id"],
            "publish_mode": "now",
            "scheduled_for": None,
        },
    )
    assert publish.status_code == 201

    final_project = auth_client.get(f"/projects/{flow['project_id']}")
    assert final_project.status_code == 200
    assert final_project.json()["status"] == "published"

    history = auth_client.get(f"/projects/{flow['project_id']}/publish-history")
    assert history.status_code == 200
    assert history.json()["jobs"][0]["status"] == "published"
    assert history.json()["posts"][0]["external_url"] == "https://www.youtube.com/watch?v=happy-video"
