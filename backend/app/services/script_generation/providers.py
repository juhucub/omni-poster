from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings
from app.schemas import ScriptGenerationRequest
from app.services.script_generation.formats import ScriptFormatTemplate
from app.services.script_generation.normalizer import stable_slug
from app.services.script_generation.platforms import PlatformPacingRules


@dataclass
class ProviderResult:
    payload: dict[str, Any]
    provider_name: str
    model: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    repair_attempted: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)


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


def _json_from_text(value: str) -> dict[str, Any]:
    text = value.strip()

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
        # Last-resort extraction if the model adds extra text.
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        loaded = json.loads(match.group(0))

    if not isinstance(loaded, dict):
        raise ValueError("Ollama response JSON must be an object.")

    return loaded

class OllamaScriptGenerationProvider(ScriptGenerationProvider):
    provider_name = "ollama"

    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
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
            raw_text, diagnostics = self._call(prompt, repair=False)
        except Exception as exc:
            raise RuntimeError(f"ollama_request_failed: {exc}") from exc

        try:
            payload = _json_from_text(raw_text)
            return ProviderResult(
                payload=payload,
                provider_name=self.provider_name,
                model=self.model,
                diagnostics=diagnostics,
            )
        except Exception as first_error:
            # Avoid an expensive second 120s generation by default.
            # JSON mode + cleanup should handle normal formatting mistakes.
            raise RuntimeError(f"ollama_invalid_json: {first_error}") from first_error
    
    def _call(self, prompt: str, *, repair: bool) -> tuple[str, dict[str, Any]]:
        request_body = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": min(float(self.temperature), 0.2),
                "num_predict": 900 if not repair else 500,
                "num_ctx": 4096,
            },
        }

        diagnostics: dict[str, Any] = {
            "base_url": self.base_url,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "prompt_char_count": len(prompt),
            "repair": repair,
            "num_predict": request_body["options"]["num_predict"],
            "num_ctx": request_body["options"]["num_ctx"],
            "format": request_body["format"],
        }

        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json=request_body,
                timeout=httpx.Timeout(
                    timeout=float(self.timeout_seconds),
                    connect=10.0,
                    read=float(self.timeout_seconds),
                    write=30.0,
                    pool=10.0,
                ),
            )
            diagnostics["status_code"] = response.status_code
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            diagnostics["failure_type"] = "ollama_timeout"
            raise RuntimeError(json.dumps(diagnostics)) from exc
        except httpx.HTTPStatusError as exc:
            diagnostics["failure_type"] = "ollama_http_error"
            diagnostics["response_text"] = exc.response.text[:1000] if exc.response is not None else ""
            raise RuntimeError(json.dumps(diagnostics)) from exc
        except httpx.HTTPError as exc:
            diagnostics["failure_type"] = "ollama_network_error"
            raise RuntimeError(json.dumps(diagnostics)) from exc

        data = response.json()
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

class DeterministicFallbackScriptGenerationProvider(ScriptGenerationProvider):
    provider_name = "deterministic_fallback"

    def _infer_character_names_from_idea(self, idea: str) -> list[str]:
        patterns = [
            r"\b([A-Z][a-zA-Z]+)\s+and\s+([A-Z][a-zA-Z]+)\b",
            r"\b([A-Z][a-zA-Z]+)\s+&\s+([A-Z][a-zA-Z]+)\b",
            r"\bbetween\s+([A-Z][a-zA-Z]+)\s+and\s+([A-Z][a-zA-Z]+)\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, idea)
            if match:
                return [match.group(1), match.group(2)]

        return []
    
    def generate(
        self,
        request: ScriptGenerationRequest,
        *,
        prompt: str,
        template: ScriptFormatTemplate,
        platform_rules: PlatformPacingRules,
        target_duration_sec: int,
    ) -> ProviderResult:
        speakers = self._speakers(request, template)
        lines = self._lines(request, template, speakers)
        payload = {
            "idea": request.idea,
            "content_format_id": template.id,
            "platform": platform_rules.id,
            "target_duration_sec": target_duration_sec,
            "tone": request.tone,
            "audience": request.audience,
            "speakers": speakers,
            "lines": lines,
            "sections": ["hook", "body", "payoff", "cta"],
            "metadata_suggestions": {
                "title": self._title(request.idea),
                "description": f"A short-form {template.label.lower()} about {request.idea}.",
                "hashtags": ["#shorts", "#creator", f"#{stable_slug(template.id, 'format')}"],
                "cta": self._cta(platform_rules),
            },
        }
        return ProviderResult(
            payload=payload,
            provider_name=self.provider_name,
            fallback_used=True,
            fallback_reason="deterministic_template",
        )

    def _speakers(self, request: ScriptGenerationRequest, template: ScriptFormatTemplate) -> list[dict[str, Any]]:
        names = [name.strip() for name in request.speaker_names if name.strip()]
        required = template.default_speaker_count

        if template.id == "character_dialogue" and len(names) < 2:
            inferred = self._infer_character_names_from_idea(request.idea)
            if len(inferred) >= 2:
                names = inferred

    def _line(self, speakers: list[dict[str, Any]], index: int, section: str, text: str, visual: str | None = None) -> dict[str, Any]:
        speaker = speakers[index % len(speakers)]
        return {
            "section": section,
            "speaker_id": speaker["id"],
            "speaker_label": speaker["label"],
            "text": text,
            "caption_text": text,
            "visual_cue": {"cue_type": "beat", "description": visual or "", "asset_slot": None} if visual else None,
        }

    def _lines(self, request: ScriptGenerationRequest, template: ScriptFormatTemplate, speakers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        idea = request.idea.strip().rstrip(".")
        if template.id == "reddit_story":
            return [
                self._line(speakers, 0, "hook", f"I thought {idea} was going to be normal.", "Open on a story title card."),
                self._line(speakers, 0, "body", "Then one tiny detail made everybody in the room freeze."),
                self._line(speakers, 0, "body", "The part nobody expected was how fast the truth came out."),
                self._line(speakers, 0, "payoff", f"That is when {idea} turned into the lesson."),
                self._line(speakers, 0, "cta", "Would you have handled it the same way?"),
            ]
        if template.id == "debate_format":
            return [
                self._line(speakers, 0, "hook", f"Quick debate: is {idea} actually worth the hype?"),
                self._line(speakers, 1, "body", "Absolutely. The upside is obvious when you look at the result."),
                self._line(speakers, 2, "body", "I disagree. The hidden cost is what people keep ignoring."),
                self._line(speakers, 0, "body", "Give me the strongest point from each side."),
                self._line(speakers, 1, "payoff", "The strongest point is that it saves time when execution matters."),
                self._line(speakers, 2, "payoff", "The counterpoint is that speed without judgment creates bigger mistakes."),
                self._line(speakers, 0, "cta", "Drop your verdict: side A or side B?"),
            ]
        if template.id == "podcast_clip":
            return [
                self._line(speakers, 0, "hook", f"Give me the one thing people miss about {idea}."),
                self._line(speakers, 1, "body", "They focus on the obvious part and skip the system behind it."),
                self._line(speakers, 0, "body", "So the result looks random when it is actually designed."),
                self._line(speakers, 1, "payoff", "Exactly. Once you see the pattern, the whole clip changes."),
                self._line(speakers, 0, "cta", "Save this before the next time you see it happen."),
            ]
        if template.id == "meme_news_reaction":
            return [
                self._line(speakers, 0, "hook", f"Breaking news: {idea} just got weird."),
                self._line(speakers, 0, "body", "At first it sounds harmless, and then the second detail arrives."),
                self._line(speakers, 0, "body", "That detail is doing all the comedy here."),
                self._line(speakers, 0, "payoff", "The official response somehow made it even funnier."),
                self._line(speakers, 0, "cta", "Send this to the friend who called it first."),
            ]
        if template.id == "multi_speaker_skit":
            return [
                self._line(speakers, 0, "hook", f"We need to talk about {idea}."),
                self._line(speakers, 1, "body", "I already made one small decision and it became everyone else's problem."),
                self._line(speakers, 2, "body", "That is not a decision. That is a side quest with paperwork."),
                self._line(speakers, 0, "body", "Great. So we are aligned that this got out of hand."),
                self._line(speakers, 1, "payoff", "Out of hand is generous. It left the building."),
                self._line(speakers, 2, "cta", "Follow for the meeting after the meeting."),
            ]
        if template.id == "character_dialogue":
            a = speakers[0]["label"] if speakers else "Speaker A"
            b = speakers[1]["label"] if len(speakers) > 1 else "Speaker B"

            return [
                self._line(speakers, 0, "hook", f"{b}, have you noticed {idea} is getting weirdly believable?"),
                self._line(speakers, 1, "hook", "Yes, and somehow that is both impressive and deeply annoying."),
                self._line(speakers, 0, "body", "I saw one today and had to check if it was real twice."),
                self._line(speakers, 1, "body", "That is the problem. The fake ones are learning confidence faster than people are learning skepticism."),
                self._line(speakers, 0, "body", "So now we need subtitles, watermarks, and trust issues?"),
                self._line(speakers, 1, "payoff", "Exactly. The future is vertical, synthetic, and wearing a suspiciously smooth face."),
                self._line(speakers, 0, "cta", "Follow before this clip becomes evidence in a robot trial."),
            ]
        return [
            self._line(speakers, 0, "hook", f"Here is the fastest way to understand {idea}."),
            self._line(speakers, 0, "body", "Start with the problem people can actually feel."),
            self._line(speakers, 0, "body", "Then show the one mechanism that changes the outcome."),
            self._line(speakers, 0, "payoff", "Once that mechanism is clear, the lesson becomes easy to remember."),
            self._line(speakers, 0, "cta", "Save this for the next time you need the shortcut."),
        ]

    def _title(self, idea: str) -> str:
        words = idea.strip().split()
        return " ".join(words[:8]).title() or "Short-Form Script"

    def _cta(self, platform_rules: PlatformPacingRules) -> str:
        return platform_rules.cta_style
