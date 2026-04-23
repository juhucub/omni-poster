from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import OutputVideo, ReviewComment, ReviewQueueItem, User
from app.routers.projects import get_owned_project
from app.schemas import (
    ReviewCommentCreateRequest,
    ReviewDecisionRequest,
    ReviewQueueItemSummary,
    ReviewQueueListResponse,
    ReviewSubmitRequest,
)
from app.services.audit import record_audit
from app.services.notifications import create_notification
from app.services.project_state import sync_project_state, to_review_summary

router = APIRouter(tags=["reviews"])


def get_owned_review(db: Session, user_id: int, review_id: int) -> ReviewQueueItem:
    review = (
        db.query(ReviewQueueItem)
        .join(ReviewQueueItem.project)
        .filter(ReviewQueueItem.id == review_id)
        .one_or_none()
    )
    if not review or review.project.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review item not found")
    return review


@router.get("/projects/{project_id}/reviews", response_model=ReviewQueueListResponse)
def list_project_reviews(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    reviews = sorted(project.review_queue_items, key=lambda item: item.created_at, reverse=True)
    return ReviewQueueListResponse(items=[to_review_summary(item) for item in reviews if to_review_summary(item) is not None])


@router.post("/projects/{project_id}/review/submit", response_model=ReviewQueueItemSummary, status_code=status.HTTP_201_CREATED)
def submit_for_review(
    project_id: int,
    payload: ReviewSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    output = (
        db.query(OutputVideo)
        .filter(OutputVideo.id == payload.output_video_id, OutputVideo.project_id == project.id)
        .one_or_none()
    )
    if not output:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Output video not found")

    review = ReviewQueueItem(
        project_id=project.id,
        output_video_id=output.id,
        submitted_by_user_id=current_user.id,
        reviewer_user_id=payload.reviewer_user_id,
        status="pending",
    )
    db.add(review)
    db.flush()

    if payload.note:
        db.add(
            ReviewComment(
                review_queue_item_id=review.id,
                author_user_id=current_user.id,
                kind="note",
                body=payload.note,
            )
        )
    project.status = "in_review"
    project.approved_at = None
    create_notification(
        db,
        user_id=current_user.id,
        project_id=project.id,
        category="review.requested",
        message=f"Project '{project.name}' is waiting for human review.",
        payload={"review_id": review.id, "output_video_id": output.id},
    )
    record_audit(
        db,
        user_id=current_user.id,
        action="review.submitted",
        entity_type="review_queue_item",
        entity_id=review.id,
        metadata={"project_id": project.id, "output_video_id": output.id},
    )
    db.commit()
    db.refresh(review)
    return to_review_summary(review)


@router.post("/reviews/{review_id}/comments", response_model=ReviewQueueItemSummary)
def add_review_comment(
    review_id: int,
    payload: ReviewCommentCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    review = get_owned_review(db, current_user.id, review_id)
    db.add(
        ReviewComment(
            review_queue_item_id=review.id,
            author_user_id=current_user.id,
            kind=payload.kind,
            body=payload.body,
        )
    )
    record_audit(
        db,
        user_id=current_user.id,
        action="review.comment_added",
        entity_type="review_queue_item",
        entity_id=review.id,
        metadata={"kind": payload.kind},
    )
    db.commit()
    db.refresh(review)
    return to_review_summary(review)


@router.post("/reviews/{review_id}/approve", response_model=ReviewQueueItemSummary)
def approve_review(
    review_id: int,
    payload: ReviewDecisionRequest = Body(default=ReviewDecisionRequest()),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    review = get_owned_review(db, current_user.id, review_id)
    review.status = "approved"
    review.reviewed_at = datetime.utcnow()
    review.reviewer_user_id = review.reviewer_user_id or current_user.id
    review.decision_summary = payload.summary or "Approved for publishing."
    review.rejection_reason = None
    review.project.approved_at = review.reviewed_at
    sync_project_state(review.project)
    db.add(
        ReviewComment(
            review_queue_item_id=review.id,
            author_user_id=current_user.id,
            kind="approval",
            body=review.decision_summary,
        )
    )
    create_notification(
        db,
        user_id=review.project.user_id,
        project_id=review.project_id,
        category="review.approved",
        message=f"Project '{review.project.name}' was approved for publishing.",
        payload={"review_id": review.id},
    )
    record_audit(
        db,
        user_id=current_user.id,
        action="review.approved",
        entity_type="review_queue_item",
        entity_id=review.id,
        metadata={"project_id": review.project_id},
    )
    db.commit()
    db.refresh(review)
    return to_review_summary(review)


@router.post("/reviews/{review_id}/request-changes", response_model=ReviewQueueItemSummary)
def request_review_changes(
    review_id: int,
    payload: ReviewDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    review = get_owned_review(db, current_user.id, review_id)
    review.status = "changes_requested"
    review.reviewed_at = datetime.utcnow()
    review.reviewer_user_id = review.reviewer_user_id or current_user.id
    review.decision_summary = payload.summary or "Changes requested before publish."
    review.rejection_reason = payload.rejection_reason or "Update the draft and resubmit."
    review.project.approved_at = None
    sync_project_state(review.project)
    db.add(
        ReviewComment(
            review_queue_item_id=review.id,
            author_user_id=current_user.id,
            kind="change_request",
            body=review.rejection_reason,
        )
    )
    create_notification(
        db,
        user_id=review.project.user_id,
        project_id=review.project_id,
        category="review.changes_requested",
        message=f"Project '{review.project.name}' needs another revision before publishing.",
        payload={"review_id": review.id, "reason": review.rejection_reason},
    )
    record_audit(
        db,
        user_id=current_user.id,
        action="review.changes_requested",
        entity_type="review_queue_item",
        entity_id=review.id,
        metadata={"project_id": review.project_id, "reason": review.rejection_reason},
    )
    db.commit()
    db.refresh(review)
    return to_review_summary(review)
