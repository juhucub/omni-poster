from __future__ import annotations

from app.schemas import CaptionBlock, ScriptLine
from app.services.script_generation.platforms import PlatformPacingRules


def chunk_words(text: str, words_per_block: int) -> list[str]:
    words = [word for word in text.split() if word.strip()]
    if not words:
        return []
    return [
        " ".join(words[index : index + words_per_block])
        for index in range(0, len(words), max(words_per_block, 1))
    ]


class CaptionBlockBuilder:
    def build(self, lines: list[ScriptLine], platform_rules: PlatformPacingRules) -> list[CaptionBlock]:
        blocks: list[CaptionBlock] = []
        for line in lines:
            caption_text = (line.caption_text or line.text).strip()
            for block_index, chunk in enumerate(chunk_words(caption_text, platform_rules.caption_words_per_block)):
                blocks.append(
                    CaptionBlock(
                        id=f"cap_{line.id}_{block_index + 1:02d}",
                        line_id=line.id,
                        speaker_id=line.speaker_id,
                        text=chunk,
                    )
                )
        return blocks
