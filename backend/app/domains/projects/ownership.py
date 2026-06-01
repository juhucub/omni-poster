from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Project


def find_owned_project(db: Session, user_id: int, project_id: int) -> Project | None:
    return (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == user_id)
        .one_or_none()
    )
