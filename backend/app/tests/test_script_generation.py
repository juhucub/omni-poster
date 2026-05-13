from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from app.core.config import settings
from app.schemas import ScriptGenerationRequest
from app.services.script_generation import ScriptGenerationService
from app.services.script_generation.platforms import get_platform_rules
from app.services.script_generation.service import generated_script_to_dialogue_lines


FORMATS = [
    "reddit_story",
    "character_dialogue",
    "podcast_clip",
    "debate_format",
    "meme_news_reaction",
    "educational_short",
    "multi_speaker_skit",
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


def test_every_predefined_format_generates_valid_output(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    for content_format_id in FORMATS:
        script = _generate(content_format_id)
        assert script.content_format_id == content_format_id
        assert script.lines
        assert script.caption_blocks
        assert all(line.text and line.caption_text for line in script.lines)
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
    assert any(line.section == "payoff" for line in educational.lines)


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
            "lines": [{"section": "hook", "speaker_id": "host", "speaker_label": "Host", "text": "Clean generated line.", "caption_text": "Clean generated line."}],
        }
        return httpx.Response(200, json={"response": json.dumps(payload)}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="request body test", content_format_id="educational_short", provider="ollama")
    )
    assert response.fallback_used is False
    assert captured["stream"] is False
    assert captured["format"] == "json"
    assert captured["options"]["temperature"] == 0.2
    assert captured["options"]["num_predict"] == 777
    assert captured["options"]["num_ctx"] == 4096


def test_valid_ollama_json_parses_successfully(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)

    def fake_post(*_args, **_kwargs):
        request = httpx.Request("POST", "http://ollama.test/api/generate")
        payload = {
            "content_format_id": "educational_short",
            "speakers": [{"id": "teacher", "label": "Teacher", "role": "Teacher"}],
            "lines": [{"section": "hook", "speaker_id": "teacher", "speaker_label": "Teacher", "text": "This is clean JSON.", "caption_text": "This is clean JSON."}],
        }
        return httpx.Response(
            200,
            json={"response": json.dumps(payload), "total_duration": 10, "load_duration": 2, "prompt_eval_count": 15, "eval_count": 20},
            request=request,
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="valid json test", content_format_id="educational_short", provider="ollama")
    )
    assert response.provider_metadata.provider_name == "ollama"
    assert response.fallback_used is False
    assert response.provider_metadata.ollama_total_duration == 10
    assert response.provider_metadata.ollama_eval_count == 20


def test_markdown_wrapped_ollama_json_parses(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)

    def fake_post(*_args, **_kwargs):
        request = httpx.Request("POST", "http://ollama.test/api/generate")
        payload = {
            "speakers": [{"id": "host", "label": "Host", "role": "Host"}],
            "lines": [{"section": "hook", "speaker_id": "host", "speaker_label": "Host", "text": "Wrapped JSON works.", "caption_text": "Wrapped JSON works."}],
        }
        return httpx.Response(200, json={"response": f"```json\n{json.dumps(payload)}\n```"}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="wrapped json test", content_format_id="educational_short", provider="ollama")
    )
    assert response.fallback_used is False
    assert response.generated_script.lines[0].text == "Wrapped JSON works."


def test_label_and_empty_caption_normalize(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)

    def fake_post(*_args, **_kwargs):
        request = httpx.Request("POST", "http://ollama.test/api/generate")
        payload = {
            "speakers": [{"id": "peter", "label": "Peter", "role": "Character A"}],
            "lines": [{"section": "intro", "speaker_id": "peter", "label": "Peter", "text": "Caption should be copied.", "caption_text": ""}],
        }
        return httpx.Response(200, json={"response": json.dumps(payload)}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="label caption test", content_format_id="educational_short", provider="ollama")
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
                {"section": "hook", "speaker_id": "a", "speaker_label": "A", "text": "First line.", "caption_text": "First line."},
                {"section": "body", "speaker_id": "b", "speaker_label": "B", "text": "Second line.", "caption_text": "Second line."},
                {"section": "payoff", "speaker_id": "a", "speaker_label": "A", "text": "Third line.", "caption_text": "Third line."},
            ],
        }
        return httpx.Response(200, json={"response": json.dumps(payload)}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="format correction", content_format_id="character_dialogue", provider="ollama")
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
    assert response.provider_metadata.failure_type == "invalid_json"


def test_ollama_timeout_reports_failure_type_and_valid_fallback(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)

    def fake_post(*_args, **_kwargs):
        raise httpx.ReadTimeout("too slow")

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="timeout fallback", content_format_id="character_dialogue", provider="ollama")
    )
    assert response.fallback_used is True
    assert response.provider_metadata.failure_type == "ollama_timeout"
    assert response.generated_script.content_format_id == "character_dialogue"


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
