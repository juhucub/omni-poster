from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.schemas import ScriptGenerationRequest, ScriptGenerationResponse
from app.domains.script_generation.formats import ScriptFormatTemplate
from app.domains.script_generation.platforms import PlatformPacingRules

logger = logging.getLogger(__name__)

SCRIPT_GENERATION_CACHE_VERSION = 1


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _normalized_idea(value: str) -> str:
    return " ".join(value.lower().strip().split())


class ScriptGenerationCache:
    def __init__(self, *, namespace: str | None = None) -> None:
        self.namespace = namespace or "global"
        self.cache_dir = Path(settings.MEDIA_DIR) / "generated" / "script_generation_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def key(
        self,
        request: ScriptGenerationRequest,
        *,
        template: ScriptFormatTemplate,
        platform_rules: PlatformPacingRules,
        target_duration_sec: int,
        provider_name: str,
        model: str | None,
    ) -> str:
        payload = {
            "version": SCRIPT_GENERATION_CACHE_VERSION,
            "namespace": self.namespace,
            "format_id": template.id,
            "idea": _normalized_idea(request.idea),
            "target_duration_sec": target_duration_sec,
            "platform": platform_rules.id,
            "platform_targets": request.platform_targets or [request.platform],
            "tone": request.tone,
            "audience": request.audience,
            "speaker_names": [name.strip().lower() for name in request.speaker_names if name.strip()],
            "speaker_roles": [role.strip().lower() for role in request.speaker_roles if role.strip()],
            "speaker_contexts": [item.model_dump(exclude_none=True) for item in request.speaker_contexts],
            "quality_hints": request.quality_hints.model_dump(exclude_none=True) if request.quality_hints else {},
            "metadata_hints": request.metadata_hints.model_dump(exclude_none=True) if request.metadata_hints else {},
            "previous_context": request.previous_context or "",
            "provider": provider_name,
            "model": model,
            "ollama_settings": {
                "temperature": settings.OLLAMA_SCRIPT_TEMPERATURE,
                "num_predict": settings.OLLAMA_NUM_PREDICT,
                "num_ctx": settings.OLLAMA_NUM_CTX,
            },
        }
        return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()

    def path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, key: str) -> ScriptGenerationResponse | None:
        path = self.path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return ScriptGenerationResponse(**payload["response"])
        except Exception as exc:
            logger.warning("script_generation.cache_read_failed key=%s error=%s", key[:12], exc)
            return None

    def set(self, key: str, response: ScriptGenerationResponse) -> None:
        path = self.path(key)
        tmp_path = path.with_suffix(".tmp")
        payload = {
            "version": SCRIPT_GENERATION_CACHE_VERSION,
            "key": key,
            "response": response.model_dump(mode="json"),
        }
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_path.replace(path)


def should_cache_response(request: ScriptGenerationRequest, response: ScriptGenerationResponse) -> bool:
    if request.debug:
        return False
    metadata = response.provider_metadata
    if metadata.provider_name != "ollama":
        return False
    if metadata.fallback_used:
        return False
    if metadata.failure_type:
        return False
    return True
