from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.celery_app import celery
from app.db import SessionLocal
from app.models import PlatformMetadata, Project, PublishJob, PublishedPost, SocialAccount
from app.services.notifications import create_notification
from app.services.project_state import sync_project_state
from app.services.youtube_accounts import YouTubeOAuthError, ensure_valid_access_token
from app.services.youtube_publish import YouTubePublishError, upload_short

logger = logging.getLogger(__name__)


@celery.task(name="app.tasks.publish.process_publish_job")
def process_publish_job(job_id: int) -> dict:
    db: Session = SessionLocal()
    try:
        job = db.get(PublishJob, job_id)
        if not job:
            return {"ok": False, "reason": "missing_job"}
        if job.status == "published":
            return {"ok": True, "status": "published"}
        if job.status not in {"publish_queued", "queued", "retrying"}:
            return {"ok": True, "status": job.status}

        project = db.get(Project, job.project_id)
        account = db.get(SocialAccount, job.social_account_id)
        metadata = db.get(PlatformMetadata, job.platform_metadata_id)
        output_video = job.output_video
        output_asset = output_video.asset if output_video else None
        if not project or not account or not metadata or not output_asset:
            raise RuntimeError("Publish job references missing project data.")
        if project.status not in {"approved", "scheduled", "publish_queued", "publishing", "failed"} or not project.approved_at:
            raise RuntimeError("Project must be approved before publishing.")
        if account.status != "linked":
            raise RuntimeError("Linked YouTube account requires reconnect.")

        job.status = "publishing"
        job.attempt_count += 1
        job.started_at = datetime.utcnow()
        job.finished_at = None
        job.last_error = None
        project.status = "publishing"
        db.commit()

        access_token = ensure_valid_access_token(db, account)
        db.commit()

        upload = upload_short(
            access_token=access_token,
            video_path=output_asset.storage_key,
            title=metadata.title,
            description=metadata.description,
            tags=metadata.tags_json,
            scheduled_for=job.scheduled_for,
        )

        post = job.published_post
        if not post:
            post = PublishedPost(
                project_id=project.id,
                publish_job_id=job.id,
                social_account_id=account.id,
                platform="youtube",
                external_post_id=upload["external_post_id"],
                external_url=upload["external_url"],
            )
            db.add(post)
        else:
            post.external_post_id = upload["external_post_id"]
            post.external_url = upload["external_url"]
            post.published_at = datetime.utcnow()

        job.status = "published"
        job.finished_at = datetime.utcnow()
        project.status = "published"
        create_notification(
            db,
            user_id=project.user_id,
            project_id=project.id,
            category="publish.succeeded",
            message="The approved video was published successfully.",
            payload={"job_id": job.id, "external_url": post.external_url},
        )
        db.commit()
        return {"ok": True, "status": job.status, "external_post_id": post.external_post_id}
    except (RuntimeError, YouTubeOAuthError, YouTubePublishError) as exc:
        logger.exception("Publish job %s failed", job_id)
        db.rollback()
        job = db.get(PublishJob, job_id)
        if job:
            project = db.get(Project, job.project_id)
            job.status = "failed"
            job.last_error = str(exc)
            job.finished_at = datetime.utcnow()
            if project:
                project.status = "failed"
                create_notification(
                    db,
                    user_id=project.user_id,
                    project_id=project.id,
                    category="publish.failed",
                    message="A publish job failed and can be retried.",
                    payload={"job_id": job.id, "error": str(exc)},
                )
            db.commit()
        return {"ok": False, "reason": str(exc)}
    finally:
        db.close()
