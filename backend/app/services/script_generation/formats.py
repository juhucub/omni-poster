from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScriptFormatTemplate:
    id: str
    label: str
    speaker_mode: str
    default_speaker_roles: list[str]
    min_speakers: int
    max_speakers: int
    default_speaker_count: int
    structure: list[str]
    caption_mode: str
    required_image_slots: list[str] = field(default_factory=list)
    optional_image_slots: list[str] = field(default_factory=list)
    visual_cue_expectations: list[str] = field(default_factory=list)
    speaker_images_required: bool = False
    dialogue_must_alternate: bool = False


FORMAT_TEMPLATES: dict[str, ScriptFormatTemplate] = {
    "reddit_story": ScriptFormatTemplate(
        id="reddit_story",
        label="Reddit Story",
        speaker_mode="single_narrator",
        default_speaker_roles=["Narrator"],
        min_speakers=1,
        max_speakers=1,
        default_speaker_count=1,
        structure=["hook", "body", "payoff", "cta"],
        caption_mode="dense_story",
        optional_image_slots=["background_gameplay", "story_context"],
        visual_cue_expectations=["new setting", "comment reveal", "payoff emphasis"],
    ),
    "character_dialogue": ScriptFormatTemplate(
        id="character_dialogue",
        label="Character Dialogue",
        speaker_mode="dialogue",
        default_speaker_roles=["Character A", "Character B"],
        min_speakers=2,
        max_speakers=4,
        default_speaker_count=2,
        structure=["hook", "body", "payoff", "cta"],
        caption_mode="speaker_bubbles",
        optional_image_slots=["speaker_portraits"],
        visual_cue_expectations=["active speaker", "reaction beat"],
        speaker_images_required=True,
        dialogue_must_alternate=True,
    ),
    "podcast_clip": ScriptFormatTemplate(
        id="podcast_clip",
        label="Podcast Clip",
        speaker_mode="host_guest",
        default_speaker_roles=["Host", "Guest"],
        min_speakers=2,
        max_speakers=3,
        default_speaker_count=2,
        structure=["hook", "body", "payoff", "cta"],
        caption_mode="quote_blocks",
        optional_image_slots=["host_portrait", "guest_portrait"],
        visual_cue_expectations=["quote emphasis", "speaker close-up"],
    ),
    "debate_format": ScriptFormatTemplate(
        id="debate_format",
        label="Debate Format",
        speaker_mode="moderated_debate",
        default_speaker_roles=["Moderator", "Speaker A", "Speaker B"],
        min_speakers=3,
        max_speakers=3,
        default_speaker_count=3,
        structure=["hook", "body", "payoff", "cta"],
        caption_mode="speaker_labeled",
        optional_image_slots=["debate_topic_card"],
        visual_cue_expectations=["topic card", "side-by-side speakers", "verdict beat"],
        dialogue_must_alternate=True,
    ),
    "meme_news_reaction": ScriptFormatTemplate(
        id="meme_news_reaction",
        label="Meme News Reaction",
        speaker_mode="host_reaction",
        default_speaker_roles=["Host"],
        min_speakers=1,
        max_speakers=2,
        default_speaker_count=1,
        structure=["hook", "body", "payoff", "cta"],
        caption_mode="punchy_reaction",
        optional_image_slots=["news_card", "reaction_image"],
        visual_cue_expectations=["headline card", "reaction zoom", "meme punchline"],
    ),
    "educational_short": ScriptFormatTemplate(
        id="educational_short",
        label="Educational Short",
        speaker_mode="teacher",
        default_speaker_roles=["Teacher"],
        min_speakers=1,
        max_speakers=2,
        default_speaker_count=1,
        structure=["hook", "body", "payoff", "cta"],
        caption_mode="clear_chunks",
        optional_image_slots=["diagram", "example"],
        visual_cue_expectations=["concept label", "example reveal", "takeaway card"],
    ),
    "multi_speaker_skit": ScriptFormatTemplate(
        id="multi_speaker_skit",
        label="Multi-Speaker Skit",
        speaker_mode="ensemble",
        default_speaker_roles=["Character A", "Character B", "Character C"],
        min_speakers=3,
        max_speakers=5,
        default_speaker_count=3,
        structure=["hook", "body", "payoff", "cta"],
        caption_mode="speaker_bubbles",
        optional_image_slots=["speaker_portraits", "prop"],
        visual_cue_expectations=["reaction beat", "scene turn", "punchline"],
        speaker_images_required=True,
        dialogue_must_alternate=True,
    ),
}


def get_format_template(content_format_id: str) -> ScriptFormatTemplate:
    return FORMAT_TEMPLATES.get(content_format_id) or FORMAT_TEMPLATES["educational_short"]
