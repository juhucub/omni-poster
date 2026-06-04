from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import settings
from app.models import Asset, GenerationJob, Project, ScriptRevision
from app.schemas import RenderReadinessEstimate
from app.domains.render.cache_keys import tts_segment_cache_key
from app.domains.script_generation.formats import get_format_template


TARGET_SECONDS = 60
CLONE_PROVIDERS = {"xtts", "openvoice", "rvc"}


class DraftReadinessPlanner:
    def estimate(
        self,
        *,
        project: Project,
        script_revision: ScriptRevision | None,
        background_asset: Asset | None,
        voice_manifest: dict[str, Any],
        output_kind: str = "draft",
        recent_jobs: list[GenerationJob] | None = None,
    ) -> RenderReadinessEstimate:
        generated = dict(script_revision.generated_script_json or {}) if script_revision else {}
        template = get_format_template(str(generated.get("content_format_id") or "educational_short"))
        budget = dict(template.generation_budget or {})
        max_lines = int(budget.get("max_lines_for_60s_draft") or 6)
        max_speakers = int(budget.get("max_speakers_for_draft") or template.max_speakers)
        max_words = int(budget.get("max_words_per_line") or 12)
        lines = list(script_revision.parsed_lines_json or []) if script_revision else []
        speakers = sorted({str(line.get("speaker") or "").strip() for line in lines if str(line.get("speaker") or "").strip()})
        total_words = sum(len(str(line.get("text") or "").split()) for line in lines)
        blocking: list[str] = []
        hints: list[str] = []

        if output_kind not in {"draft", "preview"}:
            hints.append("Use draft mode for the 60-second local iteration target.")
        if not lines:
            blocking.append("Add a speaker-separated script before estimating draft speed.")
        if not background_asset:
            blocking.append("Select a scene before rendering.")
        if len(lines) > max_lines:
            blocking.append(f"Reduce to {max_lines} lines for 60-second draft.")
        if len(speakers) > max_speakers:
            blocking.append(f"Reduce to {max_speakers} speakers for 60-second draft.")
        too_long = [line for line in lines if len(str(line.get("text") or "").split()) > max_words]
        if too_long:
            blocking.append(f"Split or shorten {len(too_long)} line(s) over {max_words} words.")

        tts_cache_hits = 0
        tts_cache_misses = 0
        tts_segments: list[dict[str, Any]] = []
        clone_misses = 0
        low = 6.0
        high = 18.0
        render_cache = Path(settings.MEDIA_DIR) / "render_cache"
        voice_profiles = dict((voice_manifest.get("speakers") or {}))
        for index, line in enumerate(lines):
            speaker = str(line.get("speaker") or "").strip()
            text = str(line.get("text") or "").strip()
            entry = dict(voice_profiles.get(speaker) or {})
            profile = dict(entry.get("voice_profile") or {})
            provider = str(entry.get("requested_provider") or profile.get("requested_provider") or profile.get("provider") or "espeak").lower()
            fallback_allowed = bool(entry.get("fallback_allowed", profile.get("fallback_allowed", True)))
            voice_profile_id = profile.get("id") or entry.get("voice_profile_id")
            cache_key = tts_segment_cache_key(
                speaker=speaker,
                text=text,
                voice_profile=profile,
                requested_provider=provider,
                fallback_allowed=fallback_allowed,
                output_kind=output_kind,
            )
            cached = (render_cache / "tts_segments" / f"{cache_key}.wav").exists()
            tts_segments.append(
                {
                    "line_index": index,
                    "line_id": line.get("line_id") or line.get("id") or f"line_{index + 1:03d}",
                    "speaker": speaker,
                    "voice_profile_id": voice_profile_id,
                    "provider": provider,
                    "cache_key_prefix": cache_key[:16],
                    "cached": cached,
                    "text_preview": text[:96],
                }
            )
            if cached:
                tts_cache_hits += 1
                low += 0.1
                high += 0.5
            elif provider in CLONE_PROVIDERS:
                tts_cache_misses += 1
                clone_misses += 1
                low += 25.0
                high += 90.0
            else:
                tts_cache_misses += 1
                low += 0.5
                high += 1.5

        if clone_misses:
            blocking.append("XTTS/OpenVoice/RVC cold cache makes a 60-second draft unlikely.")
            hints.append("Warm the render cache or explicitly choose a faster draft voice profile.")
        if total_words > int(budget.get("max_total_words") or 999):
            hints.append(f"Keep total script words under {budget.get('max_total_words')} for this preset.")
        recent_hint = self._recent_hint(recent_jobs or [])
        if recent_hint:
            hints.append(recent_hint)

        estimated_high = max(high, low)
        return RenderReadinessEstimate(
            target_seconds=TARGET_SECONDS,
            estimated_seconds_low=round(low, 1),
            estimated_seconds_high=round(estimated_high, 1),
            draft_ready=not blocking and estimated_high <= TARGET_SECONDS,
            blocking_reasons=blocking,
            optimization_hints=hints or ["Draft mode is the correct local iteration path; final render may remain slower."],
            recommended_mode="draft",
            max_recommended_lines=max_lines,
            max_recommended_speakers=max_speakers,
            max_recommended_words_per_line=max_words,
            expected_cache_dependency="high" if clone_misses else "medium" if tts_cache_misses else "low",
            cache_warmth={
                "tts_segment_hits": tts_cache_hits,
                "tts_segment_misses": tts_cache_misses,
                "tts_segments": tts_segments,
                "clone_provider_misses": clone_misses,
                "render_cache_root": str(Path(settings.MEDIA_DIR) / "render_cache"),
            },
        )

    def _recent_hint(self, jobs: list[GenerationJob]) -> str | None:
        for job in jobs:
            summary = dict((job.tts_result_json or {}).get("performance_summary") or {})
            total = summary.get("total_seconds")
            if total:
                return f"Recent {job.output_kind} job took {float(total):.1f}s; use its timing profile as the evidence baseline."
        return None
