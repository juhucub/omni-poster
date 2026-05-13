from __future__ import annotations

import logging
import time

from app.core.config import settings
from app.schemas import (
    GeneratedScript,
    ScriptGenerationProviderMetadata,
    ScriptGenerationRequest,
    ScriptGenerationResponse,
)
from app.services.script_generation.formats import get_format_template
from app.services.script_generation.normalizer import ScriptNormalizer
from app.services.script_generation.platforms import get_platform_rules
from app.services.script_generation.prompt_builder import ScriptPromptBuilder
from app.services.script_generation.providers import (
    DeterministicFallbackScriptGenerationProvider,
    OllamaScriptGenerationProvider,
    ProviderResult,
    ScriptGenerationProviderError,
)
from app.services.script_generation.validator import ScriptValidator

logger = logging.getLogger(__name__)


class ScriptGenerationService:
    def __init__(self) -> None:
        self.prompt_builder = ScriptPromptBuilder()
        self.normalizer = ScriptNormalizer()
        self.validator = ScriptValidator()
        self.fallback_provider = DeterministicFallbackScriptGenerationProvider()

    def generate(self, request: ScriptGenerationRequest) -> ScriptGenerationResponse:
        started = time.monotonic()
        template = get_format_template(request.content_format_id)
        platform_rules = get_platform_rules(request.platform)
        target_duration_sec = min(
            request.target_duration_sec or platform_rules.default_duration_sec,
            platform_rules.max_duration_sec,
        )
        prompt = self.prompt_builder.build(
            request,
            template=template,
            platform_rules=platform_rules,
            target_duration_sec=target_duration_sec,
        )
        provider_result: ProviderResult
        fallback_reason: str | None = None
        failure_diagnostics: dict = {}

        try:
            if (request.provider or "auto") in {"auto", "ollama"} and settings.OLLAMA_ENABLED:
                logger.info("script_generation.provider_selected provider=ollama model=%s", settings.OLLAMA_MODEL)
                provider_result = OllamaScriptGenerationProvider().generate(
                    request,
                    prompt=prompt,
                    template=template,
                    platform_rules=platform_rules,
                    target_duration_sec=target_duration_sec,
                )
            else:
                fallback_reason = "provider_disabled_or_not_selected"
                provider_result = self._fallback(request, prompt, template, platform_rules, target_duration_sec, fallback_reason)
        except ScriptGenerationProviderError as exc:
            fallback_reason = f"{exc.failure_type}: {exc}"
            failure_diagnostics = dict(exc.diagnostics)
            logger.warning("script_generation.fallback_used reason=%s", fallback_reason)
            provider_result = self._fallback(request, prompt, template, platform_rules, target_duration_sec, fallback_reason)
        except Exception as exc:
            fallback_reason = f"ollama_unavailable_or_invalid: {exc}"
            failure_diagnostics = {"failure_type": "ollama_network_error"}
            logger.warning("script_generation.fallback_used reason=%s", fallback_reason)
            provider_result = self._fallback(request, prompt, template, platform_rules, target_duration_sec, fallback_reason)

        try:
            script, normalization_warnings = self.normalizer.normalize(
                provider_result.payload,
                idea=request.idea,
                content_format_id=template.id,
                platform=platform_rules.id,
                target_duration_sec=target_duration_sec,
                tone=request.tone,
                audience=request.audience,
                template=template,
                platform_rules=platform_rules,
            )
        except Exception as exc:
            if provider_result.provider_name == self.fallback_provider.provider_name:
                raise
            failure_diagnostics = {**provider_result.diagnostics, "failure_type": "schema_validation_failed", "error": str(exc)}
            provider_result = self._fallback(request, prompt, template, platform_rules, target_duration_sec, "schema_validation_failed")
            script, normalization_warnings = self.normalizer.normalize(
                provider_result.payload,
                idea=request.idea,
                content_format_id=template.id,
                platform=platform_rules.id,
                target_duration_sec=target_duration_sec,
                tone=request.tone,
                audience=request.audience,
                template=template,
                platform_rules=platform_rules,
            )
        validation_warnings = normalization_warnings + self.validator.validate(
            script,
            template=template,
            platform_rules=platform_rules,
        )
        if provider_result.provider_name != self.fallback_provider.provider_name and self._has_hard_failure(validation_warnings):
            logger.warning("script_generation.validation_fallback warnings=%s", validation_warnings)
            failure_diagnostics = {**provider_result.diagnostics, "failure_type": "schema_validation_failed"}
            provider_result = self._fallback(request, prompt, template, platform_rules, target_duration_sec, "validation_failed")
            script, normalization_warnings = self.normalizer.normalize(
                provider_result.payload,
                idea=request.idea,
                content_format_id=template.id,
                platform=platform_rules.id,
                target_duration_sec=target_duration_sec,
                tone=request.tone,
                audience=request.audience,
                template=template,
                platform_rules=platform_rules,
            )
            validation_warnings = normalization_warnings + self.validator.validate(
                script,
                template=template,
                platform_rules=platform_rules,
            )

        duration_ms = int((time.monotonic() - started) * 1000)
        diagnostics = {
            **failure_diagnostics,
            **provider_result.diagnostics,
            **({"prompt": prompt} if request.debug else {}),
        }
        provider_metadata = ScriptGenerationProviderMetadata(
            provider_name=provider_result.provider_name,
            model=provider_result.model,
            fallback_used=provider_result.fallback_used,
            fallback_reason=provider_result.fallback_reason or fallback_reason,
            generation_duration_ms=duration_ms,
            repair_attempted=provider_result.repair_attempted,
            prompt_char_count=diagnostics.get("prompt_char_count") or len(prompt),
            response_char_count=diagnostics.get("response_char_count"),
            timeout_seconds=diagnostics.get("timeout_seconds"),
            num_predict=diagnostics.get("num_predict"),
            num_ctx=diagnostics.get("num_ctx"),
            ollama_total_duration=diagnostics.get("ollama_total_duration"),
            ollama_load_duration=diagnostics.get("ollama_load_duration"),
            ollama_prompt_eval_count=diagnostics.get("ollama_prompt_eval_count"),
            ollama_eval_count=diagnostics.get("ollama_eval_count"),
            failure_type=diagnostics.get("failure_type"),
            diagnostics=diagnostics,
        )
        script.provider_metadata = provider_metadata.model_dump()
        script.validation_warnings = validation_warnings
        logger.info(
            "script_generation.completed provider=%s model=%s fallback=%s duration_ms=%s warnings=%s",
            provider_metadata.provider_name,
            provider_metadata.model,
            provider_metadata.fallback_used,
            duration_ms,
            len(validation_warnings),
        )
        return ScriptGenerationResponse(
            generated_script=script,
            provider_metadata=provider_metadata,
            validation_warnings=validation_warnings,
            fallback_used=provider_metadata.fallback_used,
        )

    def _fallback(
        self,
        request: ScriptGenerationRequest,
        prompt: str,
        template,
        platform_rules,
        target_duration_sec: int,
        reason: str,
    ) -> ProviderResult:
        result = self.fallback_provider.generate(
            request,
            prompt=prompt,
            template=template,
            platform_rules=platform_rules,
            target_duration_sec=target_duration_sec,
        )
        result.fallback_reason = reason
        return result

    def _has_hard_failure(self, warnings: list[str]) -> bool:
        hard_markers = ("has no spoken lines", "references missing speaker", "has no caption text", "Speaker count")
        return any(any(marker in warning for marker in hard_markers) for warning in warnings)


def generated_script_to_dialogue_lines(script: GeneratedScript | dict) -> list[dict]:
    if isinstance(script, dict):
        script = GeneratedScript(**script)
    return [
        {
            "id": None,
            "speaker": line.speaker_label,
            "text": line.text,
            "caption_text": line.caption_text,
            "section": line.section,
            "line_id": line.id,
            "order": index,
        }
        for index, line in enumerate(script.lines)
    ]
