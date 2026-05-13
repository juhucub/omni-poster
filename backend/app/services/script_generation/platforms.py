from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformPacingRules:
    id: str
    label: str
    default_duration_sec: int
    max_duration_sec: int
    hook_max_seconds: int
    max_words_per_spoken_line: int
    caption_words_per_block: int
    pacing_style: str
    cta_style: str
    recommended_caption_density: str
    estimated_words_per_minute: int


PLATFORM_RULES: dict[str, PlatformPacingRules] = {
    "tiktok": PlatformPacingRules(
        id="tiktok",
        label="TikTok",
        default_duration_sec=45,
        max_duration_sec=180,
        hook_max_seconds=3,
        max_words_per_spoken_line=12,
        caption_words_per_block=5,
        pacing_style="fast, punchy, pattern interrupts",
        cta_style="comment or follow prompt",
        recommended_caption_density="high",
        estimated_words_per_minute=165,
    ),
    "youtube_shorts": PlatformPacingRules(
        id="youtube_shorts",
        label="YouTube Shorts",
        default_duration_sec=55,
        max_duration_sec=180,
        hook_max_seconds=4,
        max_words_per_spoken_line=14,
        caption_words_per_block=6,
        pacing_style="clear setup, useful payoff, replayable",
        cta_style="subscribe or watch-next prompt",
        recommended_caption_density="medium-high",
        estimated_words_per_minute=155,
    ),
    "instagram_reels": PlatformPacingRules(
        id="instagram_reels",
        label="Instagram Reels",
        default_duration_sec=40,
        max_duration_sec=90,
        hook_max_seconds=3,
        max_words_per_spoken_line=11,
        caption_words_per_block=5,
        pacing_style="visual, concise, shareable",
        cta_style="save/share prompt",
        recommended_caption_density="medium",
        estimated_words_per_minute=150,
    ),
}


def get_platform_rules(platform: str) -> PlatformPacingRules:
    return PLATFORM_RULES.get(platform) or PLATFORM_RULES["tiktok"]
