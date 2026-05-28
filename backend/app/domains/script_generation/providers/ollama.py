from __future__ import annotations

import json
import re
from typing import Any

from app.core.config import settings
from app.schemas import ScriptGenerationRequest
from app.domains.script_generation.formats import ScriptFormatTemplate
from app.domains.script_generation.platforms import PlatformPacingRules
from app.domains.script_generation.providers.base import (
    ProviderResult,
    ScriptGenerationProvider,
    ScriptGenerationProviderError,
)
from app.infra.ollama import OllamaClient, OllamaHTTPStatusError, OllamaNetworkError, OllamaTimeoutError


def _json_from_text(value: str) -> dict[str, Any]:
    text = value.strip()
    if not text:
        raise ValueError("Ollama response was empty.")

    # Remove common markdown wrappers from model output.
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # Remove single-backtick wrappers like: `{"ok": true}`
    if text.startswith("`") and text.endswith("`"):
        text = text[1:-1].strip()

    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        loaded = json.loads(_extract_json_object(text))

    if not isinstance(loaded, dict):
        raise ValueError("Ollama response JSON must be an object.")

    return loaded


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        raise ValueError("No JSON object found in Ollama response.")
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise ValueError("No complete JSON object found in Ollama response.")


class OllamaScriptGenerationProvider(ScriptGenerationProvider):
    provider_name = "ollama"

    def __init__(self) -> None:
        self.client = OllamaClient(settings.OLLAMA_BASE_URL)
        self.base_url = self.client.base_url
        self.model = settings.OLLAMA_MODEL
        self.timeout_seconds = settings.OLLAMA_TIMEOUT_SECONDS
        self.temperature = settings.OLLAMA_TEMPERATURE
        self.enabled = settings.OLLAMA_ENABLED

    def generate(
        self,
        request: ScriptGenerationRequest,
        *,
        prompt: str,
        template: ScriptFormatTemplate,
        platform_rules: PlatformPacingRules,
        target_duration_sec: int,
    ) -> ProviderResult:
        if not self.enabled:
            raise RuntimeError("Ollama script generation is disabled.")

        try:
            raw_text, diagnostics = self._call(request, prompt, repair=False, target_duration_sec=target_duration_sec)
        except ScriptGenerationProviderError:
            raise
        except Exception as exc:
            raise ScriptGenerationProviderError("ollama_network_error", f"ollama_request_failed: {exc}") from exc

        try:
            payload = _json_from_text(raw_text)
            return ProviderResult(
                payload=payload,
                provider_name=self.provider_name,
                model=self.model,
                diagnostics=diagnostics,
            )
        except Exception as first_error:
            repair_prompt = self._invalid_json_repair_prompt(prompt, raw_text, str(first_error))
            repair_result = self.repair(
                request,
                prompt=repair_prompt,
                template=template,
                platform_rules=platform_rules,
                target_duration_sec=target_duration_sec,
                previous_diagnostics=diagnostics,
                failure_type="invalid_json",
            )
            return repair_result

    def repair(
        self,
        request: ScriptGenerationRequest,
        *,
        prompt: str,
        template: ScriptFormatTemplate,
        platform_rules: PlatformPacingRules,
        target_duration_sec: int,
        previous_diagnostics: dict[str, Any] | None = None,
        failure_type: str = "repair_attempted",
    ) -> ProviderResult:
        _ = (request, template, platform_rules)
        try:
            raw_text, repair_diagnostics = self._call(request, prompt, repair=True, target_duration_sec=target_duration_sec)
            payload = _json_from_text(raw_text)
        except ScriptGenerationProviderError:
            raise
        except Exception as exc:
            diagnostics = {
                **(previous_diagnostics or {}),
                "repair_attempted": True,
                "repair_failure_type": "invalid_json_after_repair",
                "repair_error": str(exc),
            }
            raise ScriptGenerationProviderError("invalid_json_after_repair", f"ollama_invalid_json_after_repair: {exc}", diagnostics) from exc

        diagnostics = {
            **(previous_diagnostics or {}),
            **repair_diagnostics,
            "repair_attempted": True,
            "repaired_failure_type": failure_type,
        }
        return ProviderResult(
            payload=payload,
            provider_name=self.provider_name,
            model=self.model,
            repair_attempted=True,
            diagnostics=diagnostics,
        )
    
    def _timeout_for_request(self, request: ScriptGenerationRequest, target_duration_sec: int) -> float:
        override = request.provider_config.timeout_seconds if request.provider_config else None
        if override:
            return float(override)
        if target_duration_sec <= 60:
            return float(settings.OLLAMA_DRAFT_TIMEOUT_SECONDS)
        return float(self.timeout_seconds)

    def _call(self, request: ScriptGenerationRequest, prompt: str, *, repair: bool, target_duration_sec: int) -> tuple[str, dict[str, Any]]:
        num_predict = self._num_predict(target_duration_sec, repair=repair)
        timeout_seconds = self._timeout_for_request(request, target_duration_sec)
        request_body = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": min(float(settings.OLLAMA_SCRIPT_TEMPERATURE), 0.2),
                "num_predict": num_predict,
                "num_ctx": max(1024, min(int(settings.OLLAMA_NUM_CTX), 8192)),
            },
        }

        diagnostics: dict[str, Any] = {
            "base_url": self.base_url,
            "model": self.model,
            "provider_used": self.provider_name,
            "timeout_seconds": timeout_seconds,
            "prompt_char_count": len(prompt),
            "repair": repair,
            "num_predict": request_body["options"]["num_predict"],
            "num_ctx": request_body["options"]["num_ctx"],
            "temperature": request_body["options"]["temperature"],
            "format": request_body["format"],
            "stream": request_body["stream"],
        }

        try:
            response = self.client.generate(request_body, timeout_seconds=timeout_seconds)
            diagnostics["elapsed_ms"] = response.elapsed_ms
            diagnostics["status_code"] = response.status_code
        except OllamaTimeoutError as exc:
            diagnostics["elapsed_ms"] = exc.elapsed_ms
            diagnostics["failure_type"] = "ollama_timeout"
            raise ScriptGenerationProviderError("ollama_timeout", json.dumps(diagnostics), diagnostics) from exc
        except OllamaHTTPStatusError as exc:
            diagnostics["elapsed_ms"] = exc.elapsed_ms
            diagnostics["status_code"] = exc.status_code
            diagnostics["failure_type"] = "ollama_http_error"
            diagnostics["response_text"] = exc.response_text
            raise ScriptGenerationProviderError("ollama_http_error", json.dumps(diagnostics), diagnostics) from exc
        except OllamaNetworkError as exc:
            diagnostics["elapsed_ms"] = exc.elapsed_ms
            diagnostics["failure_type"] = "ollama_network_error"
            raise ScriptGenerationProviderError("ollama_network_error", json.dumps(diagnostics), diagnostics) from exc

        data = response.payload
        raw_response = str(data.get("response") or "")

        diagnostics.update(
            {
                "response_char_count": len(raw_response),
                "ollama_total_duration": data.get("total_duration"),
                "ollama_load_duration": data.get("load_duration"),
                "ollama_prompt_eval_count": data.get("prompt_eval_count"),
                "ollama_eval_count": data.get("eval_count"),
                "ollama_done": data.get("done"),
                "ollama_done_reason": data.get("done_reason"),
            }
        )

        return raw_response, diagnostics

    def _num_predict(self, target_duration_sec: int, *, repair: bool) -> int:
        configured = max(128, min(int(settings.OLLAMA_NUM_PREDICT), 1400))
        duration_bound = 220 + (target_duration_sec * 12)
        if target_duration_sec <= 20:
            duration_bound = 420
        elif target_duration_sec >= 60:
            duration_bound = 1050
        if repair:
            duration_bound = max(duration_bound, 650)
        return max(128, min(configured, duration_bound))

    def _invalid_json_repair_prompt(self, original_prompt: str, raw_text: str, error: str) -> str:
        return "\n".join(
            [
                "Return strict JSON only. Fix this Ollama output for OmniPoster.",
                "Required JSON object keys: speakers, lines, metadata_suggestions.",
                "Lines need section, speaker_id, speaker_label, text, caption_text, estimated_duration_sec.",
                f"JSON error: {error}",
                f"Original instructions: {original_prompt[:1600]}",
                f"Bad output: {raw_text[:2500]}",
            ]
        )
