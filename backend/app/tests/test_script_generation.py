from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.schemas import ScriptGenerationRequest
from app.services.script_generation import ScriptGenerationService
from app.services.script_generation.debate_topics import is_sentence_complete, normalize_debate_topic
from app.services.script_generation.formats import get_format_template, list_content_format_presets
from app.services.script_generation.platforms import get_platform_rules
from app.services.script_generation.service import generated_script_to_dialogue_lines
from app.services.script_generation.validator import ScriptValidator


FORMATS = [
    "reddit_story",
    "character_dialogue",
    "podcast_clip",
    "debate_format",
    "meme_news_reaction",
    "educational_short",
    "multi_speaker_skit",
]


def _quality_lines(topic: str, speaker_id: str = "host", speaker_label: str = "Host") -> list[dict]:
    return [
        {"section": "hook", "speaker_id": speaker_id, "speaker_label": speaker_label, "text": f"{topic} changes the plan fast.", "caption_text": f"{topic} changes the plan fast."},
        {"section": "body", "speaker_id": speaker_id, "speaker_label": speaker_label, "text": f"The first {topic} detail sets up the conflict.", "caption_text": f"The first {topic} detail sets up the conflict."},
        {"section": "body", "speaker_id": speaker_id, "speaker_label": speaker_label, "text": f"That {topic} detail gives viewers a concrete reason.", "caption_text": f"That {topic} detail gives viewers a concrete reason."},
        {"section": "payoff", "speaker_id": speaker_id, "speaker_label": speaker_label, "text": f"Now the {topic} payoff feels earned.", "caption_text": f"Now the {topic} payoff feels earned."},
        {"section": "cta", "speaker_id": speaker_id, "speaker_label": speaker_label, "text": f"Save this {topic} checklist.", "caption_text": f"Save this {topic} checklist."},
    ]


def _generate(content_format_id: str):
    return ScriptGenerationService().generate(
        ScriptGenerationRequest(
            idea="why creators need repeatable video workflows",
            content_format_id=content_format_id,
            platform="tiktok",
            target_duration_sec=45,
            speaker_names=["Alex", "Blair", "Casey"],
            provider="deterministic_fallback",
        )
    ).generated_script


def test_content_format_registry_exposes_all_requested_presets(auth_client: TestClient):
    presets = list_content_format_presets()
    assert [preset.id for preset in presets] == FORMATS
    for preset in presets:
        assert preset.display_name
        assert preset.best_use_case
        assert preset.ideal_duration_range_sec[0] < preset.ideal_duration_range_sec[1]
        assert preset.default_speaker_roles
        assert preset.tone_options
        assert preset.section_structure
        assert preset.caption_style_hints
        assert preset.validation_rules
        assert preset.generation_budget.max_lines_for_60s_draft >= 5
        assert preset.generation_budget.max_words_per_line >= 9
        assert preset.generation_budget.section_line_counts

    response = auth_client.get("/script-generation/formats")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 7
    assert [item["id"] for item in body["items"]] == FORMATS
    assert all(item["generation_budget"]["target_segment_count"] for item in body["items"])


def test_script_generation_request_accepts_new_compatible_shape():
    request = ScriptGenerationRequest(
        idea="how format presets speed up production",
        format_id="reddit_story",
        platform_targets=["tiktok", "youtube_shorts"],
        timing_target={"target_duration_sec": 30, "min_duration_sec": 25, "max_duration_sec": 35},
        quality_hints={"specificity": "specific", "retention_style": "confessional hook"},
        metadata_hints={"hashtags": ["#storytime"]},
        speaker_roles=["Narrator"],
        previous_context=["The last draft was too generic."],
    )
    assert request.content_format_id == "reddit_story"
    assert request.format_id == "reddit_story"
    assert request.target_duration_sec == 30
    assert request.platform == "tiktok"
    assert request.platform_targets == ["tiktok", "youtube_shorts"]
    assert request.quality_hints.specificity == "specific"
    assert request.metadata_hints.hashtags == ["#storytime"]


def test_every_predefined_format_generates_valid_output(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    for content_format_id in FORMATS:
        script = _generate(content_format_id)
        assert script.content_format_id == content_format_id
        assert script.script_id == script.id
        assert script.format_id == content_format_id
        assert script.short_summary
        assert script.platform_targets
        assert script.estimated_total_duration_sec == script.total_estimated_duration_sec
        assert script.fallback_used is True
        assert script.generation_provider == "deterministic_fallback"
        assert script.lines
        assert script.caption_blocks
        assert all(line.text and line.caption_text for line in script.lines)
        assert all(line.beat_index == index and line.order == index for index, line in enumerate(script.lines))
        assert all("(" not in line.text and "[" not in line.text for line in script.lines)


def test_deterministic_format_specific_speaker_shapes(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    reddit = _generate("reddit_story")
    assert len(reddit.speakers) == 1
    assert {line.speaker_id for line in reddit.lines} == {reddit.speakers[0].id}

    debate = _generate("debate_format")
    assert [speaker.role for speaker in debate.speakers] == ["Moderator", "Speaker A", "Speaker B"]

    character = _generate("character_dialogue")
    assert len(character.speakers) >= 2
    assert len({line.speaker_id for line in character.lines}) >= 2

    educational = _generate("educational_short")
    assert educational.lines[0].section == "hook"
    assert any(line.section == "takeaway" for line in educational.lines)


def test_platform_pacing_controls_line_and_caption_chunking(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    script = ScriptGenerationService().generate(
        ScriptGenerationRequest(
            idea="a detailed explanation of platform pacing",
            content_format_id="educational_short",
            platform="instagram_reels",
            target_duration_sec=30,
            provider="deterministic_fallback",
        )
    ).generated_script
    rules = get_platform_rules("instagram_reels")
    assert all(len(line.text.split()) <= rules.max_words_per_spoken_line for line in script.lines)
    assert all(len(str(block.text).split()) <= rules.caption_words_per_block for block in script.caption_blocks)


def test_ollama_unavailable_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://ollama.test:11434")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "local-test-model")

    def fail_post(*_args, **_kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "post", fail_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="fallback test", content_format_id="reddit_story", provider="ollama")
    )
    assert response.fallback_used is True
    assert response.provider_metadata.provider_name == "deterministic_fallback"
    assert response.provider_metadata.failure_type == "ollama_network_error"
    assert response.generated_script.lines


def test_ollama_http_error_reports_failure_type_and_fallback(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)

    def fake_post(*_args, **_kwargs):
        request = httpx.Request("POST", "http://ollama.test/api/generate")
        return httpx.Response(500, text="model failed", request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="http error", content_format_id="reddit_story", provider="ollama")
    )
    assert response.fallback_used is True
    assert response.provider_metadata.failure_type == "ollama_http_error"


def test_ollama_request_includes_json_bounds(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_SCRIPT_TEMPERATURE", 0.2)
    monkeypatch.setattr(settings, "OLLAMA_NUM_PREDICT", 777)
    monkeypatch.setattr(settings, "OLLAMA_NUM_CTX", 4096)
    captured = {}

    def fake_post(*_args, **kwargs):
        captured.update(kwargs["json"])
        request = httpx.Request("POST", "http://ollama.test/api/generate")
        payload = {
            "speakers": [{"id": "host", "label": "Host", "role": "Teacher"}],
            "lines": _quality_lines("request body", "host", "Host"),
        }
        return httpx.Response(200, json={"response": json.dumps(payload)}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="request body test", content_format_id="educational_short", target_duration_sec=15, provider="ollama")
    )
    assert response.fallback_used is False
    assert captured["stream"] is False
    assert captured["format"] == "json"
    assert captured["options"]["temperature"] == 0.2
    assert captured["options"]["num_predict"] == 420
    assert captured["options"]["num_ctx"] == 4096


def test_ollama_prompt_uses_compact_preset_budget(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)
    captured = {}

    def fake_post(*_args, **kwargs):
        captured["prompt"] = kwargs["json"]["prompt"]
        request = httpx.Request("POST", "http://ollama.test/api/generate")
        payload = {
            "speakers": [
                {"id": "moderator", "label": "Moderator", "role": "Moderator"},
                {"id": "speaker_a", "label": "Speaker A", "role": "Speaker A"},
                {"id": "speaker_b", "label": "Speaker B", "role": "Speaker B"},
            ],
            "lines": [
                {"section": "hook", "speaker_id": "moderator", "speaker_label": "Moderator", "text": "Budget debate starts with the timing problem.", "caption_text": "Budget debate starts with the timing problem."},
                {"section": "claim", "speaker_id": "speaker_a", "speaker_label": "Speaker A", "text": "Supporting budget debate works when every segment is short.", "caption_text": "Supporting budget debate works when every segment is short."},
                {"section": "rebuttal", "speaker_id": "speaker_b", "speaker_label": "Speaker B", "text": "Challenging budget debate starts when cold voices dominate.", "caption_text": "Challenging budget debate starts when cold voices dominate."},
                {"section": "counterexample", "speaker_id": "speaker_a", "speaker_label": "Speaker A", "text": "Supporting budget debate improves with cached exact audio.", "caption_text": "Supporting budget debate improves with cached exact audio."},
                {"section": "tension", "speaker_id": "speaker_b", "speaker_label": "Speaker B", "text": "Challenging budget debate still needs truthful warnings.", "caption_text": "Challenging budget debate still needs truthful warnings."},
                {"section": "verdict", "speaker_id": "moderator", "speaker_label": "Moderator", "text": "Budget debate is draft first, final later.", "caption_text": "Budget debate is draft first, final later."},
                {"section": "cta", "speaker_id": "moderator", "speaker_label": "Moderator", "text": "Vote for draft or fidelity.", "caption_text": "Vote for draft or fidelity."},
            ],
        }
        return httpx.Response(200, json={"response": json.dumps(payload)}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="budget debate", content_format_id="debate_format", target_duration_sec=45, provider="ollama")
    )
    assert response.fallback_used is False
    assert "Preset budget:" in captured["prompt"]
    assert "Content format preset:" not in captured["prompt"]
    assert "max_lines_for_60s_draft" in captured["prompt"]
    assert "Debate topic:" in captured["prompt"]
    assert '"side_a":"supporting budget debate"' in captured["prompt"]
    assert '"side_b":"challenging budget debate"' in captured["prompt"]
    assert "Speaker A=side_a" in captured["prompt"]
    assert len(captured["prompt"]) < 2200


@pytest.mark.parametrize(
    "idea,side_a,side_b",
    [
        ("a debate whether dogs or cats are the better animal", "dogs", "cats"),
        ("a debate whether dogs or other animals are better", "dogs", "other animals"),
        ("a debate whether dogs or animals are the better animal", "dogs", "other animals"),
        ("AI art vs human art", "AI art", "human art"),
        ("school uniforms should be required", "requiring school uniforms", "keeping school uniforms optional"),
    ],
)
def test_debate_topic_normalizer_extracts_sides(idea, side_a, side_b):
    topic = normalize_debate_topic(idea)
    assert topic.raw_idea == idea
    assert topic.side_a == side_a
    assert topic.side_b == side_b
    assert topic.side_a_keywords
    assert topic.side_b_keywords


def test_debate_generation_preserves_request_idea(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    idea = "a debate whether dogs or animals are the better animal"
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(
            idea=idea,
            content_format_id="debate_format",
            platform="tiktok",
            target_duration_sec=45,
            provider="deterministic_fallback",
        )
    )
    assert response.generated_script.idea == idea
    assert response.generated_script.provider_metadata["diagnostics"]["provider_used"] == "deterministic_fallback"


@pytest.mark.parametrize(
    "idea",
    [
        "a debate whether dogs or cats are the better animal",
        "a debate whether dogs or other animals are better",
        "a debate whether dogs or animals are the better animal",
        "AI art vs human art",
        "school uniforms should be required",
    ],
)
def test_debate_fallback_is_topic_grounded_and_sentence_complete(monkeypatch, idea):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(
            idea=idea,
            content_format_id="debate_format",
            platform="tiktok",
            target_duration_sec=45,
            provider="deterministic_fallback",
        )
    )
    script = response.generated_script
    topic = normalize_debate_topic(idea)
    combined = " ".join(line.text for line in script.lines).lower()
    speaker_a = next(speaker for speaker in script.speakers if speaker.role == "Speaker A")
    speaker_b = next(speaker for speaker in script.speakers if speaker.role == "Speaker B")
    speaker_a_text = " ".join(line.text for line in script.lines if line.speaker_id == speaker_a.id).lower()
    speaker_b_text = " ".join(line.text for line in script.lines if line.speaker_id == speaker_b.id).lower()

    assert not any("Hard quality failure" in warning for warning in response.validation_warnings)
    assert all(is_sentence_complete(line.text) for line in script.lines)
    assert "workflow" not in combined
    assert "speed versus quality" not in combined
    assert "review step" not in combined
    assert any(term in speaker_a_text for term in topic.side_a_keywords)
    assert any(term in speaker_b_text for term in topic.side_b_keywords)


def test_debate_validator_rejects_polluted_fallback_language(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    idea = "a debate whether dogs or animals are the better animal"
    script = ScriptGenerationService().generate(
        ScriptGenerationRequest(
            idea=idea,
            content_format_id="debate_format",
            platform="tiktok",
            target_duration_sec=45,
            provider="deterministic_fallback",
        )
    ).generated_script
    script.lines[0].text = "Two characters debate whether cats or dogs are better."
    script.lines[1].text = "The workflow gets faster when the review step is repeatable."
    script.lines[2].text = "The case against it is"
    script.lines[3].text = "The workflow looks efficient after review."

    warnings = ScriptValidator().validate(
        script,
        template=get_format_template("debate_format"),
        platform_rules=get_platform_rules("tiktok"),
        idea=idea,
    )
    hard_warnings = [warning for warning in warnings if "Hard quality failure" in warning]
    assert any("placeholder/example language" in warning for warning in hard_warnings)
    assert any("cats-or-dogs canned topic" in warning for warning in hard_warnings)
    assert any("generic fallback language" in warning for warning in hard_warnings)
    assert any("incomplete sentence fragment" in warning for warning in hard_warnings)
    assert any("Speaker A does not argue" in warning for warning in hard_warnings)


def test_valid_ollama_json_parses_successfully(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)

    def fake_post(*_args, **_kwargs):
        request = httpx.Request("POST", "http://ollama.test/api/generate")
        payload = {
            "content_format_id": "educational_short",
            "speakers": [{"id": "teacher", "label": "Teacher", "role": "Teacher"}],
            "lines": _quality_lines("valid json", "teacher", "Teacher"),
        }
        return httpx.Response(
            200,
            json={"response": json.dumps(payload), "total_duration": 10, "load_duration": 2, "prompt_eval_count": 15, "eval_count": 20},
            request=request,
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="valid json test", content_format_id="educational_short", target_duration_sec=15, provider="ollama")
    )
    assert response.provider_metadata.provider_name == "ollama"
    assert response.fallback_used is False
    assert response.provider_metadata.ollama_total_duration == 10
    assert response.provider_metadata.ollama_eval_count == 20


def test_script_generation_cache_returns_hit_without_second_provider_call(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://ollama.test:11434")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "cache-test-model")
    calls = []

    def fake_post(*_args, **_kwargs):
        calls.append("called")
        request = httpx.Request("POST", "http://ollama.test/api/generate")
        payload = {
            "content_format_id": "educational_short",
            "speakers": [{"id": "teacher", "label": "Teacher", "role": "Teacher"}],
            "lines": _quality_lines("cache behavior", "teacher", "Teacher"),
        }
        return httpx.Response(200, json={"response": json.dumps(payload)}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    request = ScriptGenerationRequest(
        idea="cache behavior for repeat script generation",
        content_format_id="educational_short",
        target_duration_sec=15,
        provider="ollama",
    )
    service = ScriptGenerationService()
    first = service.generate(request, user_scope="cache-test-user")
    second = service.generate(request, user_scope="cache-test-user")

    assert first.provider_metadata.diagnostics["cache"]["hit"] is False
    assert second.provider_metadata.diagnostics["cache"]["hit"] is True
    assert len(calls) == 1
    assert second.generated_script.id == first.generated_script.id


def test_markdown_wrapped_ollama_json_parses(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)

    def fake_post(*_args, **_kwargs):
        request = httpx.Request("POST", "http://ollama.test/api/generate")
        payload = {
            "speakers": [{"id": "host", "label": "Host", "role": "Host"}],
            "lines": _quality_lines("wrapped json", "host", "Host"),
        }
        return httpx.Response(200, json={"response": f"```json\n{json.dumps(payload)}\n```"}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="wrapped json test", content_format_id="educational_short", target_duration_sec=15, provider="ollama")
    )
    assert response.fallback_used is False
    assert response.generated_script.lines[0].text == "wrapped json changes the plan fast."


def test_label_and_empty_caption_normalize(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)

    def fake_post(*_args, **_kwargs):
        request = httpx.Request("POST", "http://ollama.test/api/generate")
        payload = {
            "speakers": [{"id": "peter", "label": "Peter", "role": "Character A"}],
            "lines": [
                {"section": "intro", "speaker_id": "peter", "label": "Peter", "text": "label caption should be copied.", "caption_text": ""},
                {"section": "body", "speaker_id": "peter", "label": "Peter", "text": "The label caption issue stays render ready.", "caption_text": ""},
                {"section": "body", "speaker_id": "peter", "label": "Peter", "text": "A label caption line keeps the topic visible.", "caption_text": ""},
                {"section": "payoff", "speaker_id": "peter", "label": "Peter", "text": "Now label caption normalization is clear.", "caption_text": ""},
                {"section": "cta", "speaker_id": "peter", "label": "Peter", "text": "Save this label caption note.", "caption_text": ""},
            ],
        }
        return httpx.Response(200, json={"response": json.dumps(payload)}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="label caption test", content_format_id="educational_short", target_duration_sec=15, provider="ollama")
    )
    line = response.generated_script.lines[0]
    assert line.speaker_label == "Peter"
    assert line.caption_text == line.text
    assert line.section == "hook"


def test_wrong_returned_format_is_corrected_with_warning(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)

    def fake_post(*_args, **_kwargs):
        request = httpx.Request("POST", "http://ollama.test/api/generate")
        payload = {
            "content_format_id": "educational_short",
            "speakers": [{"id": "a", "label": "A", "role": "Character A"}, {"id": "b", "label": "B", "role": "Character B"}],
            "lines": [
                {"section": "hook", "speaker_id": "a", "speaker_label": "A", "text": "Format correction starts with the topic.", "caption_text": "Format correction starts with the topic."},
                {"section": "body", "speaker_id": "b", "speaker_label": "B", "text": "Format correction needs the second speaker.", "caption_text": "Format correction needs the second speaker."},
                {"section": "body", "speaker_id": "a", "speaker_label": "A", "text": "Format correction keeps the disagreement moving.", "caption_text": "Format correction keeps the disagreement moving."},
                {"section": "payoff", "speaker_id": "b", "speaker_label": "B", "text": "Format correction lands when mapping survives.", "caption_text": "Format correction lands when mapping survives."},
                {"section": "cta", "speaker_id": "a", "speaker_label": "A", "text": "Save this format correction check.", "caption_text": "Save this format correction check."},
            ],
        }
        return httpx.Response(200, json={"response": json.dumps(payload)}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="format correction", content_format_id="character_dialogue", target_duration_sec=15, provider="ollama")
    )
    assert response.generated_script.content_format_id == "character_dialogue"
    assert any("content_format_id" in warning for warning in response.validation_warnings)


def test_invalid_ollama_after_retry_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)
    def fake_post(*_args, **_kwargs):
        request = httpx.Request("POST", "http://ollama.test/api/generate")
        return httpx.Response(200, json={"response": "still not json"}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="invalid retry test", content_format_id="podcast_clip", provider="ollama")
    )
    assert response.fallback_used is True
    assert response.provider_metadata.provider_name == "deterministic_fallback"
    assert response.provider_metadata.failure_type == "invalid_json_after_repair"
    assert response.provider_metadata.repair_attempted is True


def test_malformed_ollama_output_repairs_once_and_uses_ollama(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)
    calls = []

    def fake_post(*_args, **kwargs):
        calls.append(kwargs["json"]["prompt"])
        request = httpx.Request("POST", "http://ollama.test/api/generate")
        if len(calls) == 1:
            return httpx.Response(200, json={"response": "Here is the JSON: {not valid"}, request=request)
        payload = {
            "speakers": [{"id": "host", "label": "Host", "role": "Teacher"}],
            "lines": _quality_lines("repairable output", "host", "Host"),
        }
        return httpx.Response(200, json={"response": json.dumps(payload)}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="repairable output", content_format_id="educational_short", target_duration_sec=15, provider="ollama")
    )
    assert response.fallback_used is False
    assert response.provider_metadata.provider_name == "ollama"
    assert response.provider_metadata.repair_attempted is True
    assert len(calls) == 2


def test_low_quality_ollama_output_repairs_then_falls_back_if_still_bad(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)
    calls = []

    def fake_post(*_args, **kwargs):
        calls.append(kwargs["json"]["prompt"])
        request = httpx.Request("POST", "http://ollama.test/api/generate")
        payload = {
            "speakers": [{"id": "host", "label": "Host", "role": "Teacher"}],
            "lines": [{"section": "hook", "speaker_id": "host", "speaker_label": "Host", "text": "This is a clean line.", "caption_text": "This is a clean line."}],
        }
        return httpx.Response(200, json={"response": json.dumps(payload)}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="specific solar battery rebate", content_format_id="educational_short", target_duration_sec=30, provider="ollama")
    )
    assert response.fallback_used is True
    assert response.provider_metadata.failure_type == "quality_validation_failed_after_repair"
    assert response.provider_metadata.repair_attempted is True
    assert len(calls) == 2


def test_target_duration_changes_line_count_and_estimate(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    short = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="duration planning for creators", content_format_id="educational_short", target_duration_sec=15, provider="deterministic_fallback")
    ).generated_script
    long = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="duration planning for creators", content_format_id="educational_short", target_duration_sec=60, provider="deterministic_fallback")
    ).generated_script
    assert len(short.lines) < len(long.lines)
    assert short.total_estimated_duration_sec < long.total_estimated_duration_sec
    assert long.provider_metadata["diagnostics"]["duration_plan"]["target_duration_sec"] == 60


def test_dialogue_ollama_output_preserves_speaker_separated_mapping(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)

    def fake_post(*_args, **_kwargs):
        request = httpx.Request("POST", "http://ollama.test/api/generate")
        payload = {
            "speakers": [{"id": "alex", "label": "Alex", "role": "Character A"}, {"id": "blair", "label": "Blair", "role": "Character B"}],
            "lines": [
                {"section": "hook", "speaker_id": "alex", "speaker_label": "Alex", "text": "Creator workflow fails when every clip starts over.", "caption_text": "Creator workflow fails when every clip starts over."},
                {"section": "body", "speaker_id": "blair", "speaker_label": "Blair", "text": "Creator workflow improves when assets repeat.", "caption_text": "Creator workflow improves when assets repeat."},
                {"section": "body", "speaker_id": "alex", "speaker_label": "Alex", "text": "Creator workflow still needs a specific idea.", "caption_text": "Creator workflow still needs a specific idea."},
                {"section": "payoff", "speaker_id": "blair", "speaker_label": "Blair", "text": "Creator workflow wins when mapping survives.", "caption_text": "Creator workflow wins when mapping survives."},
                {"section": "cta", "speaker_id": "alex", "speaker_label": "Alex", "text": "Save this creator workflow check.", "caption_text": "Save this creator workflow check."},
            ],
        }
        return httpx.Response(200, json={"response": json.dumps(payload)}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(
            idea="creator workflow mapping",
            content_format_id="character_dialogue",
            target_duration_sec=15,
            speaker_names=["Alex", "Blair"],
            provider="ollama",
        )
    )
    assert response.fallback_used is False
    assert [line.speaker_label for line in response.generated_script.lines[:2]] == ["Alex", "Blair"]
    assert len({line.speaker_id for line in response.generated_script.lines}) == 2


def test_character_perspective_context_is_prompted_and_preserved(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)
    captured = {}

    def fake_post(*_args, **kwargs):
        captured["prompt"] = kwargs["json"]["prompt"]
        request = httpx.Request("POST", "http://ollama.test/api/generate")
        payload = {
            "speakers": [{"id": "mira", "label": "Mira", "role": "Analyst"}],
            "lines": _quality_lines("perspective context", "mira", "Mira"),
        }
        return httpx.Response(200, json={"response": json.dumps(payload)}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(
            idea="perspective context test",
            content_format_id="educational_short",
            target_duration_sec=15,
            speaker_names=["Mira"],
            speaker_contexts=[
                {
                    "id": "mira",
                    "label": "Mira",
                    "role": "Analyst",
                    "stance": "contrarian but practical",
                    "point_of_view": "cares about render-ready production details",
                }
            ],
            provider="ollama",
        )
    )
    assert "contrarian but practical" in captured["prompt"]
    assert response.generated_script.speakers[0].stance == "contrarian but practical"
    assert response.provider_metadata.diagnostics["speaker_count"] == 1


def test_ollama_timeout_reports_failure_type_and_valid_fallback(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)
    calls = []

    def fake_post(*_args, **kwargs):
        calls.append(kwargs)
        raise httpx.ReadTimeout("too slow")

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="timeout fallback", content_format_id="character_dialogue", provider="ollama")
    )
    assert response.fallback_used is True
    assert response.provider_metadata.failure_type == "ollama_timeout"
    assert response.generated_script.content_format_id == "character_dialogue"
    assert response.provider_metadata.repair_attempted is False
    assert len(calls) == 1
    assert calls[0]["timeout"].read == settings.OLLAMA_DRAFT_TIMEOUT_SECONDS


def test_deterministic_fallback_respects_draft_budget(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(
            idea="a long budgeted draft script for creator workflow timing",
            content_format_id="multi_speaker_skit",
            target_duration_sec=60,
            speaker_names=["A", "B", "C"],
            provider="deterministic_fallback",
        )
    )
    script = response.generated_script
    budget = get_format_template("multi_speaker_skit").generation_budget
    assert len(script.lines) <= budget["max_lines_for_60s_draft"]
    assert all(len(line.text.split()) <= budget["max_words_per_line"] for line in script.lines)


def test_script_validator_catches_budget_overages(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    script = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="budget overage validation", content_format_id="educational_short", target_duration_sec=60, provider="deterministic_fallback")
    ).generated_script
    script.lines = script.lines + script.lines + script.lines
    script.lines[0].text = " ".join(["long"] * 20)
    warnings = ScriptValidator().validate(
        script,
        template=get_format_template("educational_short"),
        platform_rules=get_platform_rules("tiktok"),
        idea="budget overage validation",
    )
    assert any("Reduce to 6 lines" in warning for warning in warnings)
    assert any("Split this line or shorten it" in warning for warning in warnings)


def test_character_dialogue_fallback_preserves_format_infers_names_and_alternates(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(
            idea="Peter and Stewie argue about AI videos",
            content_format_id="character_dialogue",
            platform="tiktok",
            provider="deterministic_fallback",
        )
    )
    script = response.generated_script
    assert script.content_format_id == "character_dialogue"
    assert [speaker.label for speaker in script.speakers[:2]] == ["Peter", "Stewie"]
    assert all(line.caption_text for line in script.lines)
    assert all(script.lines[index].speaker_id != script.lines[index + 1].speaker_id for index in range(len(script.lines) - 1))


def test_generated_script_converts_to_render_compatible_segments(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    script = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="Peter and Stewie test render flow", content_format_id="character_dialogue", provider="deterministic_fallback")
    ).generated_script
    segments = generated_script_to_dialogue_lines(script)
    assert segments
    assert {"speaker", "text", "order", "caption_text", "section", "line_id"}.issubset(segments[0])
    assert segments[0]["caption_text"]


def test_script_generation_endpoint_and_project_revision_persist_generated_script(auth_client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    generated = auth_client.post(
        "/script-generation/generate",
        json={"idea": "why script structure matters", "content_format_id": "debate_format", "platform": "tiktok"},
    )
    assert generated.status_code == 200
    generated_script = generated.json()["generated_script"]
    assert generated_script["speakers"]
    assert generated_script["caption_blocks"]

    project = auth_client.post("/projects", json={"name": "Generated Script Project", "target_platform": "youtube"})
    assert project.status_code == 201
    project_id = project.json()["id"]
    saved = auth_client.put(
        f"/projects/{project_id}/script",
        json={"generated_script": generated_script, "source": "generated"},
    )
    assert saved.status_code == 200
    current = saved.json()["current_revision"]
    assert current["generated_script"]["id"] == generated_script["id"]
    assert current["parsed_lines"][0]["speaker"]
    assert current["parsed_lines"][0]["text"]
    assert current["parsed_lines"][0]["caption_text"]
    assert current["parsed_lines"][0]["section"]
    assert current["parsed_lines"][0]["line_id"] == generated_script["lines"][0]["id"]


def test_script_revision_line_metadata_survives_get_and_restore(auth_client: TestClient):
    project = auth_client.post("/projects", json={"name": "Script Metadata Project", "target_platform": "youtube"})
    assert project.status_code == 201
    project_id = project.json()["id"]

    saved = auth_client.put(
        f"/projects/{project_id}/script",
        json={
            "parsed_lines": [
                {
                    "speaker": "Host",
                    "text": "Stable IDs keep voice cache reuse auditable.",
                    "caption_text": "Stable IDs keep cache reuse auditable.",
                    "section": "hook",
                    "line_id": "line_host_001",
                    "order": 0,
                },
                {
                    "speaker": "Guest",
                    "text": "Captions need to survive script editing too.",
                    "caption_text": "Captions survive script editing too.",
                    "section": "body",
                    "line_id": "line_guest_002",
                    "order": 1,
                },
            ],
            "source": "manual",
        },
    )
    assert saved.status_code == 200
    revision_id = saved.json()["current_revision"]["id"]
    first_line = saved.json()["current_revision"]["parsed_lines"][0]
    assert first_line["caption_text"] == "Stable IDs keep cache reuse auditable."
    assert first_line["section"] == "hook"
    assert first_line["line_id"] == "line_host_001"

    fetched = auth_client.get(f"/projects/{project_id}/script")
    assert fetched.status_code == 200
    fetched_line = fetched.json()["current_revision"]["parsed_lines"][1]
    assert fetched_line["caption_text"] == "Captions survive script editing too."
    assert fetched_line["section"] == "body"
    assert fetched_line["line_id"] == "line_guest_002"

    restored = auth_client.post(f"/projects/{project_id}/script-revisions/{revision_id}/restore")
    assert restored.status_code == 200
    restored_line = restored.json()["current_revision"]["parsed_lines"][0]
    assert restored_line["caption_text"] == "Stable IDs keep cache reuse auditable."
    assert restored_line["section"] == "hook"
    assert restored_line["line_id"] == "line_host_001"


def test_project_script_generation_settings_persist_and_reload(auth_client: TestClient):
    project = auth_client.post("/projects", json={"name": "Format Settings Project", "target_platform": "youtube"})
    assert project.status_code == 201
    project_id = project.json()["id"]

    updated = auth_client.patch(
        f"/projects/{project_id}/script-generation-settings",
        json={
            "content_format_id": "multi_speaker_skit",
            "platform": "youtube_shorts",
            "target_duration_sec": 55,
            "tone": "chaotic",
            "audience": "creator operators",
            "speaker_names": ["Avery", "Blair", "Casey"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["content_format_id"] == "multi_speaker_skit"

    fetched = auth_client.get(f"/projects/{project_id}")
    assert fetched.status_code == 200
    settings_payload = fetched.json()["script_generation_settings"]
    assert settings_payload["content_format_id"] == "multi_speaker_skit"
    assert settings_payload["target_duration_sec"] == 55
    assert settings_payload["speaker_names"] == ["Avery", "Blair", "Casey"]
