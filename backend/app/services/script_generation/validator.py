from __future__ import annotations

from app.schemas import GeneratedScript
from app.services.script_generation.formats import ScriptFormatTemplate
from app.services.script_generation.normalizer import STAGE_DIRECTION_RE
from app.services.script_generation.platforms import PlatformPacingRules


class ScriptValidator:
    def validate(
        self,
        script: GeneratedScript,
        *,
        template: ScriptFormatTemplate,
        platform_rules: PlatformPacingRules,
    ) -> list[str]:
        warnings: list[str] = []
        speaker_ids = {speaker.id for speaker in script.speakers}
        if len(script.speakers) < template.min_speakers or len(script.speakers) > template.max_speakers:
            warnings.append(
                f"Speaker count {len(script.speakers)} does not match {template.id} constraints "
                f"({template.min_speakers}-{template.max_speakers})."
            )

        if not script.lines:
            warnings.append("Script has no spoken lines.")
            return warnings

        for line in script.lines:
            if line.speaker_id not in speaker_ids:
                warnings.append(f"Line {line.id} references missing speaker {line.speaker_id}.")
            if not line.text.strip():
                warnings.append(f"Line {line.id} has no spoken text.")
            if not line.caption_text.strip():
                warnings.append(f"Line {line.id} has no caption text.")
            if len(line.text.split()) > platform_rules.max_words_per_spoken_line:
                warnings.append(f"Line {line.id} exceeds platform line word pacing.")
            if STAGE_DIRECTION_RE.search(line.text):
                warnings.append(f"Line {line.id} still contains stage directions.")

        if script.lines[0].section != "hook":
            warnings.append("Hook does not appear at the beginning.")
        if not any(line.section == "payoff" for line in script.lines[-3:]):
            warnings.append("Payoff does not appear near the end.")
        if not script.caption_blocks:
            warnings.append("No caption blocks were generated.")

        duration_delta = abs(script.total_estimated_duration_sec - script.target_duration_sec)
        if duration_delta > max(12, script.target_duration_sec * 0.45):
            warnings.append("Estimated duration is not close to target duration.")

        if template.dialogue_must_alternate and len(script.speakers) > 1:
            repeated = 0
            previous = None
            for line in script.lines:
                if previous == line.speaker_id:
                    repeated += 1
                previous = line.speaker_id
            if repeated > max(1, len(script.lines) // 3):
                warnings.append("Dialogue does not alternate speakers enough for the selected format.")

        return warnings
