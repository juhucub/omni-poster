from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import NotificationEvent


def create_notification(
    db: Session,
    *,
    user_id: int,
    category: str,
    message: str,
    project_id: int | None = None,
    payload: dict | None = None,
) -> NotificationEvent:
    notification = NotificationEvent(
        user_id=user_id,
        project_id=project_id,
        category=category,
        message=message,
        payload_json=payload or {},
    )
    db.add(notification)
    db.flush()
    return notification
