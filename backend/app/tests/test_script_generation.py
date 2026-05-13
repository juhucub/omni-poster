from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from app.core.config import settings
from app.schemas import ScriptGenerationRequest
from app.services.script_generation import ScriptGenerationService
from app.services.script_generation.platforms import get_platform_rules


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
    assert response.generated_script.lines


def test_malformed_ollama_output_repairs_once(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)
    calls = []

    def fake_post(*_args, **_kwargs):
        calls.append(True)
        request = httpx.Request("POST", "http://ollama.test/api/generate")
        if len(calls) == 1:
            return httpx.Response(200, json={"response": "not json"}, request=request)
        payload = {
            "speakers": [{"id": "host", "label": "Host", "role": "Teacher"}],
            "lines": [{"section": "hook", "speaker_id": "host", "speaker_label": "Host", "text": "Clean repaired line.", "caption_text": "Clean repaired line."}],
        }
        return httpx.Response(200, json={"response": json.dumps(payload)}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="repair test", content_format_id="educational_short", provider="ollama")
    )
    assert response.fallback_used is False
    assert response.provider_metadata.repair_attempted is True
    assert len(calls) == 2


def test_invalid_ollama_after_retry_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)
    calls = []

    def fake_post(*_args, **_kwargs):
        calls.append(True)
        request = httpx.Request("POST", "http://ollama.test/api/generate")
        return httpx.Response(200, json={"response": "still not json"}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    response = ScriptGenerationService().generate(
        ScriptGenerationRequest(idea="invalid retry test", content_format_id="podcast_clip", provider="ollama")
    )
    assert response.fallback_used is True
    assert response.provider_metadata.provider_name == "deterministic_fallback"
    assert len(calls) == 2


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
