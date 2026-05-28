from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.schemas import ScriptGenerationRequest
from app.domains.script_generation.formats import ScriptFormatTemplate
from app.domains.script_generation.platforms import PlatformPacingRules


@dataclass
class ProviderResult:
    payload: dict[str, Any]
    provider_name: str
    model: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    repair_attempted: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)


class ScriptGenerationProviderError(RuntimeError):
    def __init__(self, failure_type: str, message: str, diagnostics: dict[str, Any] | None = None):
        super().__init__(message)
        self.failure_type = failure_type
        self.diagnostics = dict(diagnostics or {})
        self.diagnostics["failure_type"] = failure_type


class ScriptGenerationProvider(ABC):
    provider_name: str

    @abstractmethod
    def generate(
        self,
        request: ScriptGenerationRequest,
        *,
        prompt: str,
        template: ScriptFormatTemplate,
        platform_rules: PlatformPacingRules,
        target_duration_sec: int,
    ) -> ProviderResult:
        raise NotImplementedError
