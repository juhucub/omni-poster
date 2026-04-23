from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import User
from app.routers.projects import get_owned_project
from app.schemas import RoutingSuggestionResponse
from app.services.routing import suggest_destination

router = APIRouter(tags=["routing"])


@router.post("/projects/{project_id}/routing/suggest", response_model=RoutingSuggestionResponse)
def suggest_project_routing(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    return suggest_destination(db, project, current_user)
