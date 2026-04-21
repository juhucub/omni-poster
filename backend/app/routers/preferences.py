from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import User, UserPreference
from app.schemas import PreferenceResponse, PreferenceUpdate

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", response_model=PreferenceResponse)
def get_preferences(current_user: User = Depends(get_current_user)):
    prefs = current_user.preferences or UserPreference(user_id=current_user.id)
    return PreferenceResponse(
        preferences={
            "default_platform": prefs.default_platform,
            "default_social_account_id": prefs.default_social_account_id,
            "metadata_style": prefs.metadata_style,
            "auto_select_default_account": prefs.auto_select_default_account,
        }
    )


@router.patch("", response_model=PreferenceResponse)
def update_preferences(
    payload: PreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    prefs = current_user.preferences
    if not prefs:
        prefs = UserPreference(user_id=current_user.id)
        db.add(prefs)
        db.flush()
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(prefs, field, value)
    db.commit()
    db.refresh(prefs)
    return PreferenceResponse(
        preferences={
            "default_platform": prefs.default_platform,
            "default_social_account_id": prefs.default_social_account_id,
            "metadata_style": prefs.metadata_style,
            "auto_select_default_account": prefs.auto_select_default_account,
        }
    )
