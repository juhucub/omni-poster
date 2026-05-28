from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas import ContentFormatPreset, ScriptMetadataSuggestions


@dataclass(frozen=True)
class ScriptFormatTemplate:
    id: str
    label: str
    short_description: str
    best_use_case: str
    purpose: str
    speaker_mode: str
    default_speaker_roles: list[str]
    min_speakers: int
    max_speakers: int
    default_speaker_count: int
    ideal_duration_range_sec: tuple[int, int]
    tone_options: list[str]
    structure: list[str]
    caption_mode: str
    caption_style_hints: list[str]
    pacing_rules: list[str]
    prompt_guidance: list[str]
    validation_rules: list[str]
    default_metadata_hints: dict
    generation_budget: dict
    required_image_slots: list[str] = field(default_factory=list)
    optional_image_slots: list[str] = field(default_factory=list)
    visual_cue_expectations: list[str] = field(default_factory=list)
    speaker_images_required: bool = False
    dialogue_must_alternate: bool = False

    def to_preset(self) -> ContentFormatPreset:
        return ContentFormatPreset(
            id=self.id,  # type: ignore[arg-type]
            display_name=self.label,
            short_description=self.short_description,
            best_use_case=self.best_use_case,
            purpose=self.purpose,
            ideal_duration_range_sec=list(self.ideal_duration_range_sec),
            supported_speaker_count=[self.min_speakers, self.max_speakers],
            default_speaker_roles=self.default_speaker_roles,
            tone_options=self.tone_options,
            pacing_rules=self.pacing_rules,
            section_structure=self.structure,
            caption_style_hints=self.caption_style_hints,
            default_metadata_hints=ScriptMetadataSuggestions(**self.default_metadata_hints),
            prompt_guidance=self.prompt_guidance,
            validation_rules=self.validation_rules,
            speaker_model=self.speaker_mode,
            generation_budget=self.generation_budget,
        )


FORMAT_TEMPLATES: dict[str, ScriptFormatTemplate] = {
    "reddit_story": ScriptFormatTemplate(
        id="reddit_story",
        label="Reddit Story",
        short_description="First-person narrated story built for retention.",
        best_use_case="Confessions, workplace drama, relationship twists, customer stories, and comment-bait narration.",
        purpose="Turn one relatable incident into a narrated story with a fast hook, escalation, reveal, aftermath, and viewer question.",
        speaker_mode="narrator_plus_optional_reaction",
        default_speaker_roles=["Narrator"],
        min_speakers=1,
        max_speakers=2,
        default_speaker_count=1,
        ideal_duration_range_sec=(35, 75),
        tone_options=["confessional", "suspenseful", "dryly funny", "dramatic", "curious"],
        structure=["hook", "setup", "escalation", "twist", "aftermath", "cta"],
        caption_mode="dense_story",
        caption_style_hints=["short cliffhanger chunks", "emphasize the reveal", "question caption near the end"],
        pacing_rules=["open with a concrete surprise", "raise stakes every 1-2 lines", "save the twist for the final third"],
        prompt_guidance=["write in first person unless the user asks for a narrator", "include one specific sensory/detail cue", "end with a natural comment prompt"],
        validation_rules=["1 narrator, optional reaction/comment speaker", "must include setup, escalation, twist, and aftermath"],
        default_metadata_hints={"cta": "comment with your verdict", "hashtags": ["#storytime", "#redditstories", "#shorts"]},
        generation_budget={
            "max_speakers_for_draft": 1,
            "max_lines_for_60s_draft": 6,
            "max_words_per_line": 12,
            "max_total_words": 84,
            "target_segment_count": 6,
            "recommended_tts_mode": "fallback_or_cached_clone",
            "draft_duration_range_sec": [30, 50],
            "final_duration_range_sec": [35, 75],
            "section_line_counts": {"hook": 1, "setup": 1, "escalation": 1, "twist": 1, "aftermath": 1, "cta": 1},
        },
        optional_image_slots=["background_gameplay", "story_context", "comment_card"],
        visual_cue_expectations=["story title card", "detail zoom", "comment reveal", "payoff emphasis"],
    ),
    "character_dialogue": ScriptFormatTemplate(
        id="character_dialogue",
        label="Character Dialogue",
        short_description="Two or more characters with clear personalities and conflict.",
        best_use_case="Recurring character bits, reaction duos, scripted arguments, and creator mascots.",
        purpose="Create distinct character voices that escalate a conflict into a punchline or payoff.",
        speaker_mode="dialogue",
        default_speaker_roles=["Character A", "Character B"],
        min_speakers=2,
        max_speakers=4,
        default_speaker_count=2,
        ideal_duration_range_sec=(20, 60),
        tone_options=["deadpan", "chaotic", "sarcastic", "warm", "argumentative"],
        structure=["hook", "conflict", "escalation", "payoff", "cta"],
        caption_mode="speaker_bubbles",
        caption_style_hints=["speaker-labeled captions", "keep punchlines short", "highlight reversals"],
        pacing_rules=["alternate speakers", "make every reply respond to the prior line", "end on a punchline or reversal"],
        prompt_guidance=["give each speaker a recognizable stance", "avoid generic agreement", "use callbacks when duration allows"],
        validation_rules=["2-4 speakers", "dialogue must alternate naturally", "each speaker needs at least one line"],
        default_metadata_hints={"cta": "follow for the next argument", "hashtags": ["#dialogue", "#skit", "#shorts"]},
        generation_budget={
            "max_speakers_for_draft": 2,
            "max_lines_for_60s_draft": 7,
            "max_words_per_line": 10,
            "max_total_words": 70,
            "target_segment_count": 7,
            "recommended_tts_mode": "fallback_or_cached_clone",
            "draft_duration_range_sec": [20, 45],
            "final_duration_range_sec": [20, 60],
            "section_line_counts": {"hook": 1, "conflict": 1, "escalation": 2, "payoff": 2, "cta": 1},
        },
        optional_image_slots=["speaker_portraits"],
        visual_cue_expectations=["active speaker", "reaction beat", "punchline zoom"],
        speaker_images_required=True,
        dialogue_must_alternate=True,
    ),
    "podcast_clip": ScriptFormatTemplate(
        id="podcast_clip",
        label="Podcast Clip",
        short_description="Conversational short that feels clipped from a longer discussion.",
        best_use_case="Founder clips, expert explainers, interviews, commentary, and thought-leadership snippets.",
        purpose="Simulate a clipped conversation with a cold-open claim, question, insight, example, and takeaway.",
        speaker_mode="host_guest",
        default_speaker_roles=["Host", "Guest"],
        min_speakers=2,
        max_speakers=3,
        default_speaker_count=2,
        ideal_duration_range_sec=(30, 75),
        tone_options=["insightful", "curious", "direct", "reflective", "contrarian"],
        structure=["hook", "question", "insight", "example", "takeaway", "cta"],
        caption_mode="quote_blocks",
        caption_style_hints=["quote-worthy chunks", "emphasize the guest insight", "keep host prompts short"],
        pacing_rules=["start with a cold-open claim", "host asks concise prompts", "guest provides concrete examples"],
        prompt_guidance=["make the guest sound specific", "avoid polished essay narration", "include a practical takeaway"],
        validation_rules=["host plus at least one guest", "must include an example and takeaway"],
        default_metadata_hints={"cta": "save this clip", "hashtags": ["#podcastclip", "#creator", "#shorts"]},
        generation_budget={
            "max_speakers_for_draft": 2,
            "max_lines_for_60s_draft": 6,
            "max_words_per_line": 12,
            "max_total_words": 72,
            "target_segment_count": 6,
            "recommended_tts_mode": "fallback_or_cached_clone",
            "draft_duration_range_sec": [25, 50],
            "final_duration_range_sec": [30, 75],
            "section_line_counts": {"hook": 1, "question": 1, "insight": 1, "example": 1, "takeaway": 1, "cta": 1},
        },
        optional_image_slots=["host_portrait", "guest_portrait", "quote_card"],
        visual_cue_expectations=["quote emphasis", "speaker close-up", "takeaway card"],
    ),
    "debate_format": ScriptFormatTemplate(
        id="debate_format",
        label="Debate Format",
        short_description="Opposing viewpoints with clear contrast and tension.",
        best_use_case="Pros/cons, hot takes, policy questions, product choices, and unresolved creator debates.",
        purpose="Present a claim, rebuttal, counterexample, tension beat, and verdict or open question.",
        speaker_mode="moderated_debate",
        default_speaker_roles=["Moderator", "Speaker A", "Speaker B"],
        min_speakers=3,
        max_speakers=3,
        default_speaker_count=3,
        ideal_duration_range_sec=(30, 70),
        tone_options=["sharp", "balanced", "combative", "analytical", "playful"],
        structure=["hook", "claim", "rebuttal", "counterexample", "tension", "verdict", "cta"],
        caption_mode="speaker_labeled",
        caption_style_hints=["label sides clearly", "short rebuttal captions", "verdict/open question card"],
        pacing_rules=["moderator frames quickly", "side A and B must disagree", "finish with a verdict or open question"],
        prompt_guidance=["make both sides plausible", "use one concrete counterexample", "avoid strawman arguments"],
        validation_rules=["exactly 3 speakers", "both sides must speak", "must include claim and rebuttal"],
        default_metadata_hints={"cta": "drop your verdict", "hashtags": ["#debate", "#hot take", "#shorts"]},
        generation_budget={
            "max_speakers_for_draft": 3,
            "max_lines_for_60s_draft": 7,
            "max_words_per_line": 11,
            "max_total_words": 77,
            "target_segment_count": 7,
            "recommended_tts_mode": "fallback_or_cached_clone",
            "draft_duration_range_sec": [30, 55],
            "final_duration_range_sec": [30, 70],
            "section_line_counts": {"hook": 1, "claim": 1, "rebuttal": 1, "counterexample": 1, "tension": 1, "verdict": 1, "cta": 1},
        },
        optional_image_slots=["debate_topic_card"],
        visual_cue_expectations=["topic card", "side-by-side speakers", "verdict beat"],
        dialogue_must_alternate=True,
    ),
    "meme_news_reaction": ScriptFormatTemplate(
        id="meme_news_reaction",
        label="Meme/News Reaction",
        short_description="Fast topical reaction with absurd implication and punchline.",
        best_use_case="News riffs, trend reactions, brand commentary, and fast meme response clips.",
        purpose="Move from headline to reaction, absurd implication, punchline, and comment prompt.",
        speaker_mode="host_reaction",
        default_speaker_roles=["Narrator", "Reaction"],
        min_speakers=1,
        max_speakers=2,
        default_speaker_count=1,
        ideal_duration_range_sec=(15, 45),
        tone_options=["snarky", "surprised", "absurd", "fast", "playful"],
        structure=["headline", "reaction", "implication", "payoff", "cta"],
        caption_mode="punchy_reaction",
        caption_style_hints=["headline card", "big reaction captions", "short punchline"],
        pacing_rules=["first line reads like a headline", "reaction line must turn the topic", "payoff should be concise"],
        prompt_guidance=["name the concrete topic immediately", "make the implication vivid", "do not invent real facts beyond the prompt"],
        validation_rules=["1-2 speakers", "must include headline and implication"],
        default_metadata_hints={"cta": "send this to the friend who called it", "hashtags": ["#newsreaction", "#meme", "#shorts"]},
        generation_budget={
            "max_speakers_for_draft": 1,
            "max_lines_for_60s_draft": 5,
            "max_words_per_line": 10,
            "max_total_words": 50,
            "target_segment_count": 5,
            "recommended_tts_mode": "fallback_or_cached_clone",
            "draft_duration_range_sec": [15, 35],
            "final_duration_range_sec": [15, 45],
            "section_line_counts": {"headline": 1, "reaction": 1, "implication": 1, "payoff": 1, "cta": 1},
        },
        optional_image_slots=["news_card", "reaction_image"],
        visual_cue_expectations=["headline card", "reaction zoom", "meme punchline"],
    ),
    "educational_short": ScriptFormatTemplate(
        id="educational_short",
        label="Educational Short",
        short_description="One idea explained quickly and memorably.",
        best_use_case="How-tos, product education, creator tips, workflows, and technical explainers.",
        purpose="Correct a misconception, explain the mechanism, show an example, and leave a takeaway.",
        speaker_mode="teacher",
        default_speaker_roles=["Teacher"],
        min_speakers=1,
        max_speakers=2,
        default_speaker_count=1,
        ideal_duration_range_sec=(20, 60),
        tone_options=["clear", "practical", "curious", "direct", "friendly"],
        structure=["hook", "misconception", "explanation", "example", "takeaway", "cta"],
        caption_mode="clear_chunks",
        caption_style_hints=["short concept labels", "example caption", "takeaway card"],
        pacing_rules=["open with misconception or useful hook", "explain one mechanism", "include one concrete example"],
        prompt_guidance=["avoid broad lectures", "make the takeaway actionable", "use the user's topic terms directly"],
        validation_rules=["1 teacher or teacher/student pair", "must include example and takeaway"],
        default_metadata_hints={"cta": "save this for later", "hashtags": ["#learnontiktok", "#education", "#shorts"]},
        generation_budget={
            "max_speakers_for_draft": 1,
            "max_lines_for_60s_draft": 6,
            "max_words_per_line": 12,
            "max_total_words": 72,
            "target_segment_count": 6,
            "recommended_tts_mode": "fallback_or_cached_clone",
            "draft_duration_range_sec": [20, 45],
            "final_duration_range_sec": [20, 60],
            "section_line_counts": {"hook": 1, "misconception": 1, "explanation": 1, "example": 1, "takeaway": 1, "cta": 1},
        },
        optional_image_slots=["diagram", "example"],
        visual_cue_expectations=["concept label", "example reveal", "takeaway card"],
    ),
    "multi_speaker_skit": ScriptFormatTemplate(
        id="multi_speaker_skit",
        label="Multi-Speaker Skit",
        short_description="Short scene with multiple speakers and visual rhythm.",
        best_use_case="Office scenes, creator teams, group chats, chaotic explainers, and ensemble jokes.",
        purpose="Set a premise, assign roles, escalate a chaotic exchange, land a punchline, and add a tag.",
        speaker_mode="ensemble",
        default_speaker_roles=["Character A", "Character B", "Character C"],
        min_speakers=3,
        max_speakers=5,
        default_speaker_count=3,
        ideal_duration_range_sec=(25, 70),
        tone_options=["chaotic", "deadpan", "fast", "playful", "satirical"],
        structure=["premise", "role_setup", "exchange", "punchline", "tag"],
        caption_mode="speaker_bubbles",
        caption_style_hints=["speaker-labeled short captions", "quick exchange chunks", "tag caption"],
        pacing_rules=["give each role a job", "keep exchanges short", "use a final tag after the punchline"],
        prompt_guidance=["make the cast sound distinct", "keep the scene visually playable", "avoid monologues"],
        validation_rules=["3-5 speakers", "all speakers must participate", "must include punchline and tag"],
        default_metadata_hints={"cta": "follow for part two", "hashtags": ["#skit", "#comedy", "#shorts"]},
        generation_budget={
            "max_speakers_for_draft": 3,
            "max_lines_for_60s_draft": 6,
            "max_words_per_line": 9,
            "max_total_words": 54,
            "target_segment_count": 6,
            "recommended_tts_mode": "fallback_or_cached_clone",
            "draft_duration_range_sec": [25, 50],
            "final_duration_range_sec": [25, 70],
            "section_line_counts": {"premise": 1, "role_setup": 1, "exchange": 2, "punchline": 1, "tag": 1},
        },
        optional_image_slots=["speaker_portraits", "prop"],
        visual_cue_expectations=["reaction beat", "scene turn", "punchline"],
        speaker_images_required=True,
        dialogue_must_alternate=True,
    ),
}


def get_format_template(content_format_id: str) -> ScriptFormatTemplate:
    return FORMAT_TEMPLATES.get(content_format_id) or FORMAT_TEMPLATES["educational_short"]


def list_content_format_presets() -> list[ContentFormatPreset]:
    return [template.to_preset() for template in FORMAT_TEMPLATES.values()]


def get_content_format_preset(content_format_id: str) -> ContentFormatPreset:
    return get_format_template(content_format_id).to_preset()
