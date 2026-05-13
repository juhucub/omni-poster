from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.models import User
from app.schemas import ScriptGenerationRequest, ScriptGenerationResponse
from app.services.script_generation import ScriptGenerationService

router = APIRouter(prefix="/script-generation", tags=["script-generation"])


@router.post("/generate", response_model=ScriptGenerationResponse)
def generate_structured_script(
    payload: ScriptGenerationRequest,
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    return ScriptGenerationService().generate(payload)
