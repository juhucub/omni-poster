from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.models import User
from app.schemas import ContentFormatListResponse, ContentFormatPreset, ScriptGenerationRequest, ScriptGenerationResponse
from app.domains.script_generation import ScriptGenerationService
from app.domains.script_generation.formats import get_content_format_preset, list_content_format_presets

router = APIRouter(prefix="/script-generation", tags=["script-generation"])


@router.get("/formats", response_model=ContentFormatListResponse)
def list_formats():
    return ContentFormatListResponse(items=list_content_format_presets())


@router.get("/formats/{format_id}", response_model=ContentFormatPreset)
def get_format(format_id: str):
    return get_content_format_preset(format_id)


@router.post("/generate", response_model=ScriptGenerationResponse)
def generate_structured_script(
    payload: ScriptGenerationRequest,
    current_user: User = Depends(get_current_user),
):
    return ScriptGenerationService().generate(payload, user_scope=str(current_user.id))
