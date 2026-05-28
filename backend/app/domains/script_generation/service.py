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
from app.domains.script_generation.formats import get_format_template
from app.domains.script_generation.cache import ScriptGenerationCache, should_cache_response
from app.domains.script_generation.normalizer import ScriptNormalizer
from app.domains.script_generation.platforms import get_platform_rules
from app.domains.script_generation.planner import build_duration_plan
from app.domains.script_generation.prompt_builder import ScriptPromptBuilder
from app.domains.script_generation.providers import (
    DeterministicFallbackScriptGenerationProvider,
    OllamaScriptGenerationProvider,
    ProviderResult,
    ScriptGenerationProviderError,
)
from app.domains.script_generation.validator import ScriptValidator

logger = logging.getLogger(__name__)


class ScriptGenerationService:
    def __init__(self) -> None:
        self.prompt_builder = ScriptPromptBuilder()
        self.normalizer = ScriptNormalizer()
        self.validator = ScriptValidator()
        self.fallback_provider = DeterministicFallbackScriptGenerationProvider()

    def generate(self, request: ScriptGenerationRequest, *, user_scope: str | None = None) -> ScriptGenerationResponse:
        started = time.monotonic()
        timings: dict[str, int] = {"request_received": 0}

        def mark(stage: str, stage_started: float) -> None:
            timings[stage] = int((time.monotonic() - stage_started) * 1000)

        stage_started = time.monotonic()
        template = get_format_template(request.content_format_id)
        platform_rules = get_platform_rules(request.platform)
        target_duration_sec = min(
            request.target_duration_sec or platform_rules.default_duration_sec,
            platform_rules.max_duration_sec,
        )
        plan = build_duration_plan(
            request,
            template=template,
            platform_rules=platform_rules,
            target_duration_sec=target_duration_sec,
        )
        mark("request_planned", stage_started)
        stage_started = time.monotonic()
        prompt = self.prompt_builder.build(
            request,
            template=template,
            platform_rules=platform_rules,
            target_duration_sec=target_duration_sec,
            plan=plan,
        )
        mark("prompt_built", stage_started)
        intended_provider = "ollama" if (request.provider or "auto") in {"auto", "ollama"} and settings.OLLAMA_ENABLED else self.fallback_provider.provider_name
        intended_model = settings.OLLAMA_MODEL if intended_provider == "ollama" else None
        cache = ScriptGenerationCache(namespace=user_scope)
        cache_key = cache.key(
            request,
            template=template,
            platform_rules=platform_rules,
            target_duration_sec=target_duration_sec,
            provider_name=intended_provider,
            model=intended_model,
        )
        stage_started = time.monotonic()
        cached_response = None if request.debug or intended_provider != "ollama" else cache.get(cache_key)
        mark("cache_lookup", stage_started)
        if cached_response is not None:
            duration_ms = int((time.monotonic() - started) * 1000)
            diagnostics = dict(cached_response.provider_metadata.diagnostics or {})
            diagnostics["cache"] = {"hit": True, "key": cache_key, "namespace": cache.namespace}
            diagnostics["cache_hit"] = True
            diagnostics["provider_used"] = cached_response.provider_metadata.provider_name
            diagnostics["stage_timings_ms"] = {**timings, "final_script_ready": duration_ms}
            cached_response.provider_metadata.generation_duration_ms = duration_ms
            cached_response.provider_metadata.diagnostics = diagnostics
            cached_response.generated_script.provider_metadata = cached_response.provider_metadata.model_dump()
            cached_response.generated_script.generation_provider = cached_response.provider_metadata.provider_name
            cached_response.generated_script.generation_model = cached_response.provider_metadata.model
            cached_response.generated_script.fallback_used = cached_response.provider_metadata.fallback_used
            logger.info(
                "script_generation.cache_hit provider=%s model=%s key=%s duration_ms=%s",
                cached_response.provider_metadata.provider_name,
                cached_response.provider_metadata.model,
                cache_key[:12],
                duration_ms,
            )
            return cached_response
        provider_result: ProviderResult
        fallback_reason: str | None = None
        failure_diagnostics: dict = {}
        initial_provider_result: ProviderResult | None = None

        stage_started = time.monotonic()
        try:
            if (request.provider or "auto") in {"auto", "ollama"} and settings.OLLAMA_ENABLED:
                logger.info("script_generation.provider_selected provider=ollama model=%s", settings.OLLAMA_MODEL)
                ollama_provider = OllamaScriptGenerationProvider()
                provider_result = ollama_provider.generate(
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
            fallback_reason = exc.failure_type
            failure_diagnostics = dict(exc.diagnostics)
            logger.warning("script_generation.fallback_used reason=%s", fallback_reason)
            provider_result = self._fallback(request, prompt, template, platform_rules, target_duration_sec, fallback_reason)
            provider_result.diagnostics = {**failure_diagnostics, **provider_result.diagnostics}
            provider_result.repair_attempted = bool(failure_diagnostics.get("repair_attempted"))
        except Exception as exc:
            fallback_reason = f"ollama_unavailable_or_invalid: {exc}"
            failure_diagnostics = {"failure_type": "ollama_network_error"}
            logger.warning("script_generation.fallback_used reason=%s", fallback_reason)
            provider_result = self._fallback(request, prompt, template, platform_rules, target_duration_sec, fallback_reason)
        mark("model_call_or_fallback", stage_started)

        initial_provider_result = provider_result
        stage_started = time.monotonic()
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
            self._apply_plan_speaker_defaults(script, plan)
        except Exception as exc:
            if provider_result.provider_name == self.fallback_provider.provider_name:
                raise
            provider_result = self._repair_or_fallback(
                request,
                provider_result=provider_result,
                prompt=prompt,
                plan=plan,
                template=template,
                platform_rules=platform_rules,
                target_duration_sec=target_duration_sec,
                issues=[f"schema normalization failed: {exc}"],
                failure_type="schema_validation_failed",
            )
            if provider_result.provider_name == self.fallback_provider.provider_name:
                failure_diagnostics = {**(initial_provider_result.diagnostics if initial_provider_result else {}), "failure_type": "schema_validation_failed", "error": str(exc)}
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
            self._apply_plan_speaker_defaults(script, plan)
        mark("normalized", stage_started)
        stage_started = time.monotonic()
        validation_warnings = normalization_warnings + self.validator.validate(
            script,
            template=template,
            platform_rules=platform_rules,
            idea=request.idea,
        )
        mark("validated", stage_started)
        if provider_result.provider_name == self.fallback_provider.provider_name:
            validation_warnings = self._filter_fallback_warnings(validation_warnings)
        if provider_result.provider_name != self.fallback_provider.provider_name and self._has_hard_failure(validation_warnings):
            logger.warning("script_generation.validation_fallback warnings=%s", validation_warnings)
            stage_started = time.monotonic()
            provider_result = self._repair_or_fallback(
                request,
                provider_result=provider_result,
                prompt=prompt,
                plan=plan,
                template=template,
                platform_rules=platform_rules,
                target_duration_sec=target_duration_sec,
                issues=validation_warnings,
                failure_type="quality_validation_failed",
            )
            mark("repair_or_fallback", stage_started)
            if provider_result.provider_name == self.fallback_provider.provider_name:
                failure_diagnostics = {**(initial_provider_result.diagnostics if initial_provider_result else {}), "failure_type": "quality_validation_failed"}
            stage_started = time.monotonic()
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
            self._apply_plan_speaker_defaults(script, plan)
            mark("renormalized", stage_started)
            stage_started = time.monotonic()
            validation_warnings = normalization_warnings + self.validator.validate(
                script,
                template=template,
                platform_rules=platform_rules,
                idea=request.idea,
            )
            mark("revalidated", stage_started)
            if provider_result.provider_name == self.fallback_provider.provider_name:
                validation_warnings = self._filter_fallback_warnings(validation_warnings)
            if provider_result.provider_name != self.fallback_provider.provider_name and self._has_hard_failure(validation_warnings):
                failure_diagnostics = {**provider_result.diagnostics, "failure_type": "quality_validation_failed_after_repair"}
                provider_result = self._fallback(
                    request,
                    prompt,
                    template,
                    platform_rules,
                    target_duration_sec,
                    "quality_validation_failed_after_repair",
                )
                provider_result.diagnostics = {**failure_diagnostics, **provider_result.diagnostics}
                provider_result.repair_attempted = bool(failure_diagnostics.get("repair_attempted"))
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
                self._apply_plan_speaker_defaults(script, plan)
                validation_warnings = normalization_warnings + self.validator.validate(
                    script,
                    template=template,
                    platform_rules=platform_rules,
                    idea=request.idea,
                )
                validation_warnings = self._filter_fallback_warnings(validation_warnings)

        duration_ms = int((time.monotonic() - started) * 1000)
        diagnostics = {
            **failure_diagnostics,
            **provider_result.diagnostics,
            "provider_used": provider_result.provider_name,
            "fallback_used": provider_result.fallback_used,
            "fallback_reason": provider_result.fallback_reason or fallback_reason,
            "target_duration_sec": target_duration_sec,
            "estimated_duration_sec": script.total_estimated_duration_sec,
            "speaker_count": len(script.speakers),
            "line_count": len(script.lines),
            "duration_plan": plan.model_dump(),
            "cache": {"hit": False, "key": cache_key, "namespace": cache.namespace},
            "cache_hit": False,
            "repair_attempted": provider_result.repair_attempted or bool(provider_result.diagnostics.get("repair_attempted")),
            "quality_warnings": validation_warnings,
            "stage_timings_ms": {**timings, "final_script_ready": duration_ms},
            **({"prompt": prompt} if request.debug else {}),
        }
        provider_metadata = ScriptGenerationProviderMetadata(
            provider_name=provider_result.provider_name,
            model=provider_result.model,
            fallback_used=provider_result.fallback_used,
            fallback_reason=provider_result.fallback_reason or fallback_reason,
            generation_duration_ms=duration_ms,
            repair_attempted=provider_result.repair_attempted or bool(diagnostics.get("repair_attempted")),
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
        script.generation_provider = provider_metadata.provider_name
        script.generation_model = provider_metadata.model
        script.fallback_used = provider_metadata.fallback_used
        script.estimated_total_duration_sec = script.total_estimated_duration_sec
        script.script_id = script.script_id or script.id
        script.format_id = script.format_id or script.content_format_id
        if not script.platform_targets:
            script.platform_targets = [script.platform]
        response = ScriptGenerationResponse(
            generated_script=script,
            provider_metadata=provider_metadata,
            validation_warnings=validation_warnings,
            fallback_used=provider_metadata.fallback_used,
        )
        if should_cache_response(request, response):
            stage_started = time.monotonic()
            cache.set(cache_key, response)
            mark("cache_write", stage_started)
            provider_metadata.diagnostics["stage_timings_ms"] = {**timings, "final_script_ready": int((time.monotonic() - started) * 1000)}
            script.provider_metadata = provider_metadata.model_dump()
        logger.info(
            "script_generation.completed provider=%s model=%s fallback=%s duration_ms=%s warnings=%s",
            provider_metadata.provider_name,
            provider_metadata.model,
            provider_metadata.fallback_used,
            duration_ms,
            len(validation_warnings),
        )
        return response

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
        hard_markers = ("Hard quality failure:", "Speaker count")
        return any(any(marker in warning for marker in hard_markers) for warning in warnings)

    def _filter_fallback_warnings(self, warnings: list[str]) -> list[str]:
        return [warning for warning in warnings if "Script looks generic or fallback-like" not in warning]

    def _apply_plan_speaker_defaults(self, script: GeneratedScript, plan) -> None:
        by_id = {speaker.id: speaker for speaker in plan.speakers}
        by_label = {speaker.label.lower(): speaker for speaker in plan.speakers}
        for speaker in script.speakers:
            planned = by_id.get(speaker.id) or by_label.get(speaker.label.lower())
            if not planned:
                continue
            speaker.point_of_view = speaker.point_of_view or planned.point_of_view
            speaker.motivation = speaker.motivation or planned.motivation
            speaker.stance = speaker.stance or planned.stance
            speaker.conversational_style = speaker.conversational_style or planned.conversational_style
            speaker.likely_objection = speaker.likely_objection or planned.likely_objection
            speaker.relationship_to_others = speaker.relationship_to_others or planned.relationship_to_others

    def _repair_or_fallback(
        self,
        request: ScriptGenerationRequest,
        *,
        provider_result: ProviderResult,
        prompt: str,
        plan,
        template,
        platform_rules,
        target_duration_sec: int,
        issues: list[str],
        failure_type: str,
    ) -> ProviderResult:
        if provider_result.repair_attempted:
            return self._fallback(request, prompt, template, platform_rules, target_duration_sec, failure_type)
        try:
            repair_prompt = self.prompt_builder.build_repair_prompt(
                original_prompt=prompt,
                bad_output=provider_result.payload,
                issues=issues,
                plan=plan,
            )
            return OllamaScriptGenerationProvider().repair(
                request,
                prompt=repair_prompt,
                template=template,
                platform_rules=platform_rules,
                target_duration_sec=target_duration_sec,
                previous_diagnostics=provider_result.diagnostics,
                failure_type=failure_type,
            )
        except ScriptGenerationProviderError as exc:
            fallback = self._fallback(request, prompt, template, platform_rules, target_duration_sec, exc.failure_type)
            fallback.diagnostics = {**provider_result.diagnostics, **exc.diagnostics}
            return fallback


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
