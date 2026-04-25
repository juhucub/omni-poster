from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import wave

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.models import GenerationJob, SocialAccount, VoicePreviewJob
from app.services.voice_preview_jobs import STALE_VOICE_PREVIEW_ERROR_CODE
from app.services.character_presets import get_character_preset
from app.services.crypto import decrypt_secret
from app.services.rendering import ProjectRenderService
from app.services.tts import LocalSpeechService, SpeechSegment, TTSOrchestrator, TextToSpeechError
from app.tasks.generation import STALE_GENERATION_ERROR, process_generation_job, reconcile_stale_generation_jobs
from app.tasks.publish import process_publish_job
from app.tasks.scheduler import dispatch_due_publish_jobs
from app.tasks.voice_preview import process_voice_lab_preview


class StubRegistry:
    def __init__(self, providers, state):
        self.providers = providers
        self.state = state

    def get(self, provider_name):
        return self.providers.get(provider_name)

    def healthcheck(self):
        return self.state


class StubProvider:
    def __init__(self, *, response=None, error: TextToSpeechError | None = None):
        self.response = response
        self.error = error

    def synthesize_line(self, *, text, voice_profile, output_path, options=None):
        if self.error:
            raise self.error
        output_path.write_bytes(b"RIFF")
        return {
            "audio_path": str(output_path),
            "voice": self.response.get("voice", voice_profile.get("voice", "stub")),
            "duration_seconds": self.response.get("duration_seconds", 1.0),
            "provider_used": self.response["provider_used"],
            "controls_applied": self.response.get("controls_applied", {}),
            "reference_audio_count": self.response.get("reference_audio_count", 0),
        }


def test_background_presets_are_loaded_from_bundled_media_dir(auth_client: TestClient):
    preset_dir = Path("test_storage") / "bundled" / "presets"
    preset_dir.mkdir(parents=True, exist_ok=True)
    (preset_dir / "aurora_grid.mp4").write_bytes(b"preset-video")

    response = auth_client.get("/background-presets")
    assert response.status_code == 200
    assert response.json() == [
        {
            "key": "aurora_grid",
            "name": "Aurora Grid",
            "description": "Curated background preset",
            "filename": "aurora_grid.mp4",
            "content_url": "/background-presets/aurora_grid/content",
        }
    ]


def test_character_presets_list_and_runtime_override(auth_client: TestClient):
    bundled_file = Path("test_storage") / "bundled" / "character_presets.json"
    bundled_file.write_text(
        """
[
  {
    "id": "host_calm_v1",
    "display_name": "Host",
    "speaker_names": ["Host"],
    "portrait_filename": "speaker_1.png",
    "tts_provider": "espeak",
    "voice": "en-us+f3",
    "rate": 150,
    "pitch": 42,
    "word_gap": 1,
    "amplitude": 140
  }
]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    listed = auth_client.get("/character-presets")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == "host_calm_v1"

    created = auth_client.post(
        "/character-presets",
        json={
            "display_name": "Engineer",
            "speaker_names": ["Engineer", "Dev"],
            "portrait_filename": "speaker_2.png",
            "tts_provider": "espeak",
            "voice": "en-us+m2",
            "rate": 160,
            "pitch": 40,
            "word_gap": 1,
            "amplitude": 138,
            "notes": "Runtime test preset",
            "sample_text": "Let's validate this quickly.",
        },
    )
    assert created.status_code == 201

    created_id = created.json()["id"]
    updated = auth_client.put(
        f"/character-presets/{created_id}",
        json={
            "display_name": "Engineer",
            "speaker_names": ["Engineer", "Dev"],
            "portrait_filename": "speaker_2.png",
            "tts_provider": "espeak",
            "voice": "en-us+m2",
            "rate": 162,
            "pitch": 44,
            "word_gap": 2,
            "amplitude": 142,
            "notes": "Adjusted runtime preset",
            "sample_text": "Let's validate this quickly.",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["rate"] == 162

    deleted = auth_client.delete(f"/character-presets/{created_id}")
    assert deleted.status_code == 200
    assert get_character_preset(created_id) is None


def test_character_portrait_prefers_bundled_media_dir_over_runtime(auth_client: TestClient, tmp_path: Path):
    bundled_characters = Path("test_storage") / "bundled" / "characters"
    runtime_characters = Path("test_storage") / "characters"
    bundled_characters.mkdir(parents=True, exist_ok=True)
    runtime_characters.mkdir(parents=True, exist_ok=True)

    bundled_portrait = bundled_characters / "speaker_1.png"
    runtime_portrait = runtime_characters / "speaker_1.png"
    bundled_portrait.write_bytes(b"bundled-portrait")
    runtime_portrait.write_bytes(b"runtime-portrait")

    service = ProjectRenderService()
    resolved = service._resolve_character_portrait("Host", 0, tmp_path)

    assert resolved == bundled_portrait


def test_voice_lab_preview_uses_provider_metadata(auth_client: TestClient, monkeypatch):
    bundled_file = Path("test_storage") / "bundled" / "character_presets.json"
    bundled_file.write_text(
        """
[
  {
    "id": "host_calm_v1",
    "display_name": "Host",
    "speaker_names": ["Host"],
    "portrait_filename": "speaker_1.png",
    "tts_provider": "espeak",
    "voice": "en-us+f3",
    "rate": 150,
    "pitch": 42,
    "word_gap": 1,
    "amplitude": 140
  }
]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    output_path = Path("test_storage") / "voice_lab" / "previews" / "sample.wav"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"RIFF")

    def fake_synthesize_dialogue(self, *, lines, voice_profile_map, output_dir, requested_provider=None, fallback_allowed=True, options=None):
        return [
            SpeechSegment(
                speaker=lines[0]["speaker"],
                text=lines[0]["text"],
                voice="en-us+f3",
                slot_index=0,
                audio_path=str(output_path),
                duration_seconds=1.25,
                voice_profile_id="vp_host_calm_v1",
                provider_used="espeak",
                fallback_used=False,
                controls_applied={"speaking_rate": 0.96},
                reference_audio_count=0,
            )
        ]

    monkeypatch.setattr(TTSOrchestrator, "synthesize_dialogue", fake_synthesize_dialogue)
    response = auth_client.post(
        "/voice-lab/preview",
        json={
            "preset_id": "host_calm_v1",
            "provider_preference": "auto",
            "text": "This is a quick voice lab check.",
            "rate": 149,
            "pitch": 41,
            "word_gap": 1,
            "amplitude": 144,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["preset_id"] == "host_calm_v1"
    assert response.json()["provider_used"] == "espeak"
    assert response.json()["voice_profile_id"] == "vp_host_calm_v1"
    assert response.json()["content_url"].endswith("/voice-lab/previews/sample.wav")


def test_voice_lab_preview_returns_structured_error_when_no_provider_available(auth_client: TestClient, monkeypatch):
    bundled_file = Path("test_storage") / "bundled" / "character_presets.json"
    bundled_file.write_text(
        """
[
  {
    "id": "host_calm_v1",
    "display_name": "Host",
    "speaker_names": ["Host"],
    "portrait_filename": "speaker_1.png",
    "tts_provider": "espeak",
    "voice": "en-us+f3",
    "rate": 150,
    "pitch": 42,
    "word_gap": 1,
    "amplitude": 140
  }
]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    def fake_synthesize_dialogue(self, *, lines, voice_profile_map, output_dir, requested_provider=None, fallback_allowed=True, options=None):
        raise TextToSpeechError(
            code="no_provider_available",
            message="No configured TTS provider is currently usable.",
            provider_state={
                "openvoice": {"available": False, "reason": "missing_models"},
                "espeak": {"available": False, "reason": "missing_binary"},
            },
            fallback_attempted=True,
            suggested_action="Install OpenVoice checkpoints or espeak-ng.",
        )

    monkeypatch.setattr(TTSOrchestrator, "synthesize_dialogue", fake_synthesize_dialogue)
    response = auth_client.post(
        "/voice-lab/preview",
        json={
            "preset_id": "host_calm_v1",
            "text": "This is a quick voice lab check.",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "no_provider_available"
    assert response.json()["detail"]["fallback_attempted"] is True
    assert response.json()["detail"]["provider_state"]["openvoice"]["reason"] == "missing_models"


def test_voice_lab_preview_disables_fallback_for_explicit_provider(auth_client: TestClient, monkeypatch):
    bundled_file = Path("test_storage") / "bundled" / "character_presets.json"
    bundled_file.write_text(
        """
[
  {
    "id": "host_calm_v1",
    "display_name": "Host",
    "speaker_names": ["Host"],
    "portrait_filename": "speaker_1.png",
    "tts_provider": "openvoice",
    "fallback_provider": "espeak",
    "voice": "en-us+f3",
    "rate": 150,
    "pitch": 42,
    "word_gap": 1,
    "amplitude": 140
  }
]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    scheduled = {}

    def fake_apply_async(*, kwargs=None, task_id=None, **_extra):
        scheduled["kwargs"] = kwargs
        scheduled["task_id"] = task_id
        return None

    monkeypatch.setattr(process_voice_lab_preview, "apply_async", fake_apply_async)
    response = auth_client.post(
        "/voice-lab/preview",
        json={
            "preset_id": "host_calm_v1",
            "provider_preference": "openvoice",
            "text": "Use OpenVoice only.",
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert isinstance(response.json()["job_id"], int)
    assert scheduled["kwargs"]["preview_job_id"] == response.json()["job_id"]
    assert scheduled["task_id"] == f"voice-preview-{response.json()['job_id']}"


def test_voice_lab_preview_job_status_returns_completed_payload(auth_client: TestClient):
    bundled_file = Path("test_storage") / "bundled" / "character_presets.json"
    bundled_file.write_text(
        """
[
  {
    "id": "host_calm_v1",
    "display_name": "Host",
    "speaker_names": ["Host"],
    "portrait_filename": "speaker_1.png",
    "tts_provider": "openvoice",
    "fallback_provider": "espeak",
    "voice": "en-us+f3",
    "rate": 150,
    "pitch": 42,
    "word_gap": 1,
    "amplitude": 140
  }
]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    auth_client.get("/character-presets")
    db = SessionLocal()
    try:
        job = VoicePreviewJob(
            user_id=1,
            preset_id="host_calm_v1",
            voice_profile_id="vp_host_calm_v1",
            requested_provider="openvoice",
            fallback_allowed=False,
            sample_text="Queued preview.",
            status="completed",
            progress=100,
            stage="completed",
            voice="en-us+f3",
            provider_used="openvoice",
            fallback_used=False,
            controls_applied_json={"speaking_rate": 1.0},
            provider_state_json={"openvoice": {"available": True}},
            reference_audio_count=1,
            duration_seconds=1.5,
            preview_audio_path="test_storage/voice_lab/previews/sample.wav",
            finished_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
    finally:
        db.close()

    response = auth_client.get(f"/voice-lab/preview-jobs/{job_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["provider_used"] == "openvoice"
    assert response.json()["content_url"].endswith("/voice-lab/previews/sample.wav")


def test_voice_lab_preview_job_status_reconciles_stale_processing_job(auth_client: TestClient):
    bundled_file = Path("test_storage") / "bundled" / "character_presets.json"
    bundled_file.write_text(
        """
[
  {
    "id": "host_calm_v1",
    "display_name": "Host",
    "speaker_names": ["Host"],
    "portrait_filename": "speaker_1.png",
    "tts_provider": "openvoice",
    "fallback_provider": "espeak",
    "voice": "en-us+f3",
    "rate": 150,
    "pitch": 42,
    "word_gap": 1,
    "amplitude": 140
  }
]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    auth_client.get("/character-presets")
    db = SessionLocal()
    try:
        job = VoicePreviewJob(
            user_id=1,
            preset_id="host_calm_v1",
            voice_profile_id="vp_host_calm_v1",
            requested_provider="openvoice",
            fallback_allowed=False,
            sample_text="Queued preview.",
            status="processing",
            progress=20,
            stage="tts_started",
            provider_state_json={"openvoice": {"available": True}},
            started_at=datetime.utcnow() - timedelta(seconds=100),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
    finally:
        db.close()

    response = auth_client.get(f"/voice-lab/preview-jobs/{job_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error"]["code"] == STALE_VOICE_PREVIEW_ERROR_CODE
    assert "likely due to running out of memory" in response.json()["error"]["message"]


def test_voice_lab_preview_job_status_keeps_recent_processing_job_active(auth_client: TestClient):
    bundled_file = Path("test_storage") / "bundled" / "character_presets.json"
    bundled_file.write_text(
        """
[
  {
    "id": "host_calm_v1",
    "display_name": "Host",
    "speaker_names": ["Host"],
    "portrait_filename": "speaker_1.png",
    "tts_provider": "openvoice",
    "fallback_provider": "espeak",
    "voice": "en-us+f3",
    "rate": 150,
    "pitch": 42,
    "word_gap": 1,
    "amplitude": 140
  }
]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    auth_client.get("/character-presets")
    db = SessionLocal()
    try:
        job = VoicePreviewJob(
            user_id=1,
            preset_id="host_calm_v1",
            voice_profile_id="vp_host_calm_v1",
            requested_provider="openvoice",
            fallback_allowed=False,
            sample_text="Queued preview.",
            status="processing",
            progress=20,
            stage="tts_started",
            provider_state_json={"openvoice": {"available": True}},
            started_at=datetime.utcnow() - timedelta(seconds=30),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
    finally:
        db.close()

    response = auth_client.get(f"/voice-lab/preview-jobs/{job_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "processing"
    assert response.json()["error"] is None


def test_tts_orchestrator_marks_fallback_used_when_second_provider_succeeds(tmp_path: Path):
    orchestrator = TTSOrchestrator(
        registry=StubRegistry(
            {
                "openvoice": StubProvider(
                    error=TextToSpeechError(
                        code="openvoice_runtime_failure",
                        message="OpenVoice synthesis failed.",
                        provider_state={"openvoice": {"available": True}},
                    )
                ),
                "espeak": StubProvider(response={"provider_used": "espeak", "voice": "en-us+f3"}),
            },
            {
                "openvoice": {"available": True, "reason": None},
                "espeak": {"available": True, "reason": None},
            },
        )
    )

    result = orchestrator.synthesize_line(
        text="Fallback to espeak.",
        voice_profile={
            "id": "vp_test",
            "display_name": "Host",
            "provider": "openvoice",
            "fallback_provider": "espeak",
            "voice": "en-us+f3",
            "reference_audios": [],
            "controls": {},
        },
        output_path=tmp_path / "preview.wav",
        requested_provider="openvoice",
        fallback_allowed=True,
    )

    assert result.provider_used == "espeak"
    assert result.fallback_used is True


def test_tts_orchestrator_returns_provider_error_when_explicit_provider_cannot_fallback(tmp_path: Path):
    orchestrator = TTSOrchestrator(
        registry=StubRegistry(
            {
                "openvoice": StubProvider(
                    error=TextToSpeechError(
                        code="openvoice_runtime_failure",
                        message="OpenVoice synthesis failed.",
                        provider_state={"openvoice": {"available": True}},
                        suggested_action="Check the OpenVoice runtime logs.",
                    )
                )
            },
            {
                "openvoice": {"available": True, "reason": None},
            },
        )
    )

    with pytest.raises(TextToSpeechError) as exc_info:
        orchestrator.synthesize_line(
            text="OpenVoice only.",
            voice_profile={
                "id": "vp_test",
                "display_name": "Host",
                "provider": "openvoice",
                "fallback_provider": "espeak",
                "voice": "en-us+f3",
                "reference_audios": [],
                "controls": {},
            },
            output_path=tmp_path / "preview.wav",
            requested_provider="openvoice",
            fallback_allowed=False,
        )

    assert exc_info.value.code == "openvoice_runtime_failure"
    assert exc_info.value.attempted_providers == ["openvoice"]
    assert exc_info.value.provider_failures["openvoice"]["code"] == "openvoice_runtime_failure"


def test_local_speech_service_discovers_espeak_provider(monkeypatch):
    service = LocalSpeechService()

    monkeypatch.setattr(
        "app.services.tts.shutil.which",
        lambda binary: {
            "espeak-ng": "/usr/bin/espeak-ng",
        }.get(binary),
    )

    assert service._available_providers() == {"espeak"}


def test_local_speech_service_returns_empty_provider_set_when_no_binary_exists(monkeypatch):
    service = LocalSpeechService()

    monkeypatch.setattr("app.services.tts.shutil.which", lambda binary: None)

    assert service._available_providers() == set()


def test_local_speech_service_falls_back_to_installed_provider():
    service = LocalSpeechService()

    provider = service._provider_for_voice_profile({"tts_provider": "macos", "voice": "en-us+f3"}, {"espeak"})

    assert provider == "espeak"


def test_local_speech_service_raises_clear_error_when_no_provider_available():
    service = LocalSpeechService()

    with pytest.raises(TextToSpeechError) as exc_info:
        service._provider_for_voice_profile({"tts_provider": "espeak", "voice": "en-us+f3"}, set())

    assert exc_info.value.code == "no_provider_available"


def test_local_speech_service_uses_persisted_voice_profiles(monkeypatch, tmp_path: Path):
    bundled_file = Path("test_storage") / "bundled" / "character_presets.json"
    bundled_file.write_text(
        """
[
  {
    "id": "stewie_v1",
    "display_name": "Stewie",
    "speaker_names": ["Stewie"],
    "tts_provider": "espeak",
    "voice": "en-us+f3",
    "rate": 150,
    "pitch": 42,
    "word_gap": 1,
    "amplitude": 140
  },
  {
    "id": "brian_v1",
    "display_name": "Brian",
    "speaker_names": ["Brian"],
    "tts_provider": "espeak",
    "voice": "en-gb+m3",
    "rate": 158,
    "pitch": 46,
    "word_gap": 1,
    "amplitude": 145
  }
]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    service = LocalSpeechService()

    def fake_synthesize_line(*, text, voice_profile, output_path, requested_provider=None, fallback_allowed=True, options=None):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(22050)
            handle.writeframes(b"\x00\x00" * 22050)
        return type(
            "Result",
            (),
            {
                "audio_path": str(output_path),
                "voice": voice_profile["voice"],
                "duration_seconds": 1.0,
                "provider_used": "espeak",
                "fallback_used": False,
                "controls_applied": voice_profile["controls"],
                "reference_audio_count": 0,
                "provider_state": {"espeak": {"available": True}},
                "cache_hit": False,
                "voice_profile_id": voice_profile["id"],
            },
        )()

    monkeypatch.setattr(service.orchestrator, "synthesize_line", fake_synthesize_line)

    segments = service.synthesize_dialogue(
        [
            {"speaker": "Stewie", "text": "This is my line.", "order": 0},
            {"speaker": "Brian", "text": "And this is mine.", "order": 1},
        ],
        tmp_path,
    )

    assert [segment.voice for segment in segments] == ["en-us+f3", "en-gb+m3"]
    assert [segment.voice_profile_id for segment in segments] == ["vp_stewie_v1", "vp_brian_v1"]


def test_render_timing_prefers_actual_audio_clip_duration(monkeypatch):
    service = ProjectRenderService()
    segments = [
        SpeechSegment(
            speaker="Stewie",
            text="Longer than the metadata says.",
            voice="en-us+f3",
            slot_index=0,
            audio_path="unused.wav",
            duration_seconds=1.0,
        )
    ]

    class FakeAudioClip:
        duration = 1.8

    monkeypatch.setattr(service.speech_service, "build_audio_clip", lambda audio_path: FakeAudioClip())
    timed_segments = service._build_timed_segments(segments)

    assert timed_segments[0]["duration_seconds"] == 1.8


def test_render_config_caps_preview_fps_for_large_backgrounds():
    service = ProjectRenderService()

    class FakeClip:
        fps = 60

    preview_config = service._render_config(FakeClip(), "preview")
    final_config = service._render_config(FakeClip(), "final")

    assert preview_config["fps"] == 24
    assert final_config["fps"] == 30


def test_tts_provider_capabilities_route_returns_registry_state(auth_client: TestClient):
    response = auth_client.get("/tts/providers")

    assert response.status_code == 200
    providers = {item["provider"] for item in response.json()["items"]}
    assert {"espeak", "openvoice"}.issubset(providers)


def test_project_speaker_bindings_round_trip(auth_client: TestClient):
    bundled_file = Path("test_storage") / "bundled" / "character_presets.json"
    bundled_file.write_text(
        """
[
  {
    "id": "host_calm_v1",
    "display_name": "Host",
    "speaker_names": ["Host"],
    "portrait_filename": "speaker_1.png",
    "tts_provider": "espeak",
    "voice": "en-us+f3",
    "rate": 150,
    "pitch": 42,
    "word_gap": 1,
    "amplitude": 140
  },
  {
    "id": "guest_sharp_v1",
    "display_name": "Guest",
    "speaker_names": ["Guest"],
    "portrait_filename": "speaker_2.png",
    "tts_provider": "espeak",
    "voice": "en-gb+m3",
    "rate": 158,
    "pitch": 46,
    "word_gap": 1,
    "amplitude": 145
  }
]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    project = auth_client.post("/projects", json={"name": "Binding Test", "target_platform": "youtube"})
    assert project.status_code == 201
    project_id = project.json()["id"]

    script = auth_client.put(
        f"/projects/{project_id}/script",
        json={"raw_text": "<Host> Hello there\n<Guest> General Kenobi", "source": "manual"},
    )
    assert script.status_code == 200

    listed = auth_client.get(f"/projects/{project_id}/speaker-bindings")
    assert listed.status_code == 200
    assert {item["speaker_name"] for item in listed.json()["items"]} == {"Host", "Guest"}

    updated = auth_client.put(
        f"/projects/{project_id}/speaker-bindings",
        json={
          "items": [
            {"speaker_name": "Host", "character_preset_id": "guest_sharp_v1"},
            {"speaker_name": "Guest", "character_preset_id": "host_calm_v1"},
          ]
        },
    )
    assert updated.status_code == 200
    assert {
        item["speaker_name"]: item["character_preset_id"]
        for item in updated.json()["items"]
    } == {
        "Host": "guest_sharp_v1",
        "Guest": "host_calm_v1",
    }


def _create_project_flow(client: TestClient) -> dict:
    project = client.post("/projects", json={"name": "First Project", "target_platform": "youtube"})
    assert project.status_code == 201
    project_id = project.json()["id"]

    script = client.put(
        f"/projects/{project_id}/script",
        json={"raw_text": "<Host> Hello there\n<Guest> General Kenobi", "source": "manual"},
    )
    assert script.status_code == 200

    asset = client.post(
        f"/projects/{project_id}/assets/background",
        files={"file": ("background.mp4", b"fake-video", "video/mp4")},
    )
    assert asset.status_code == 201

    metadata = client.put(
        f"/projects/{project_id}/metadata/youtube",
        json={
            "title": "A Real Short",
            "description": "Description",
            "tags": ["host", "guest"],
            "source": "manual",
        },
    )
    assert metadata.status_code == 200

    return {
        "project_id": project_id,
        "asset_id": asset.json()["id"],
        "metadata_id": metadata.json()["id"],
    }


def _link_youtube_account(client: TestClient, monkeypatch) -> int:
    monkeypatch.setattr(
        "app.services.youtube_accounts.exchange_code_for_tokens",
        lambda code: {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
        },
    )
    monkeypatch.setattr(
        "app.services.youtube_accounts.fetch_channel_identity",
        lambda access_token: {"channel_id": "channel-123", "channel_title": "My Channel"},
    )

    start = client.post("/social-accounts/youtube/connect/start")
    assert start.status_code == 200
    state = start.json()["state"]

    callback = client.get(
        "/social-accounts/youtube/callback",
        params={"code": "oauth-code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 307

    accounts = client.get("/social-accounts")
    assert accounts.status_code == 200
    return accounts.json()["items"][0]["id"]


def test_auth_flow_and_logout(client: TestClient):
    username = "auth_user"
    register = client.post("/auth/register", json={"username": username, "password": "Password1"})
    assert register.status_code == 201
    assert register.cookies.get("access_token")

    me = client.get("/auth/me", cookies=register.cookies)
    assert me.status_code == 200
    assert me.json()["username"] == username

    logout = client.post("/auth/logout", cookies=register.cookies)
    assert logout.status_code == 200

    logged_out_client = TestClient(client.app)
    try:
        after_logout = logged_out_client.get("/auth/me")
    finally:
        logged_out_client.close()
    assert after_logout.status_code == 401


def test_script_validation_and_asset_ownership(auth_client: TestClient, client: TestClient):
    project = auth_client.post("/projects", json={"name": "Ownership", "target_platform": "youtube"})
    project_id = project.json()["id"]

    invalid = auth_client.put(
        f"/projects/{project_id}/script",
        json={"raw_text": "plain text", "source": "manual"},
    )
    assert invalid.status_code == 422

    asset = auth_client.post(
        f"/projects/{project_id}/assets/background",
        files={"file": ("background.mp4", b"fake-video", "video/mp4")},
    )
    assert asset.status_code == 201

    other_user = client.post("/auth/register", json={"username": "other_user", "password": "Password1"})
    assert other_user.status_code == 201
    asset_id = asset.json()["id"]

    forbidden_get = client.get(f"/assets/{asset_id}/content", cookies=other_user.cookies)
    assert forbidden_get.status_code == 404

    forbidden_delete = client.delete(f"/projects/{project_id}/assets/{asset_id}", cookies=other_user.cookies)
    assert forbidden_delete.status_code == 404


def test_generation_job_lifecycle(auth_client: TestClient, monkeypatch):
    flow = _create_project_flow(auth_client)

    source_preview = Path("test_storage") / "source_preview.mp4"
    source_preview.write_bytes(b"rendered-preview")

    monkeypatch.setattr(
        ProjectRenderService,
        "render_preview",
        lambda self, project_id, background_video_path, parsed_lines, style_preset: {
            "output_path": str(source_preview),
            "duration_seconds": 1.5,
        },
    )
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: process_generation_job(job_id))

    create_job = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    assert create_job.status_code == 201
    assert create_job.json()["status"] == "queued"

    job_id = create_job.json()["id"]
    job = auth_client.get(f"/generation-jobs/{job_id}")
    assert job.status_code == 200
    assert job.json()["status"] == "completed"
    assert job.json()["output_video_id"] is not None

    project = auth_client.get(f"/projects/{flow['project_id']}")
    assert project.status_code == 200
    assert project.json()["status"] == "preview_ready"
    assert project.json()["latest_preview"] is not None


def test_generation_job_dedupes_active_job(auth_client: TestClient, monkeypatch):
    flow = _create_project_flow(auth_client)
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: None)

    first = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    assert first.status_code == 201

    second = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["status"] == "queued"

    active = auth_client.get(f"/projects/{flow['project_id']}/generation-jobs/active")
    assert active.status_code == 200
    assert active.json()["id"] == first.json()["id"]


def test_stale_processing_generation_job_is_reconciled(auth_client: TestClient, monkeypatch):
    flow = _create_project_flow(auth_client)
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: None)

    create_job = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    assert create_job.status_code == 201
    stale_job_id = create_job.json()["id"]

    db = SessionLocal()
    try:
        job = db.get(GenerationJob, stale_job_id)
        job.status = "processing"
        job.progress = 20
        job.started_at = datetime.utcnow() - timedelta(minutes=20)
        db.commit()
    finally:
        db.close()

    source_preview = Path("test_storage") / "reconciled_preview.mp4"
    source_preview.write_bytes(b"rendered-preview")
    monkeypatch.setattr(
        ProjectRenderService,
        "render_preview",
        lambda self, project_id, background_video_path, parsed_lines, style_preset: {
            "output_path": str(source_preview),
            "duration_seconds": 1.2,
        },
    )

    next_job = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    assert next_job.status_code == 201
    assert next_job.json()["id"] != stale_job_id

    db = SessionLocal()
    try:
        stale_job = db.get(GenerationJob, stale_job_id)
        assert stale_job.status == "failed"
        assert stale_job.error_message == STALE_GENERATION_ERROR
        assert stale_job.finished_at is not None
    finally:
        db.close()


def test_youtube_link_refresh_and_reconnect_required(auth_client: TestClient, monkeypatch):
    account_id = _link_youtube_account(auth_client, monkeypatch)

    db = SessionLocal()
    try:
        account = db.get(SocialAccount, account_id)
        account.token_expires_at = datetime.utcnow() - timedelta(minutes=5)
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(
        "app.services.youtube_accounts.refresh_tokens",
        lambda refresh_token: {"access_token": "refreshed-token", "expires_in": 1800},
    )

    refresh = auth_client.post(f"/social-accounts/{account_id}/refresh")
    assert refresh.status_code == 200
    assert refresh.json()["status"] == "linked"

    db = SessionLocal()
    try:
        account = db.get(SocialAccount, account_id)
        assert decrypt_secret(account.access_token_encrypted) == "refreshed-token"
        account.token_expires_at = datetime.utcnow() - timedelta(minutes=5)
        account.refresh_token_encrypted = None
        account.status = "linked"
        db.commit()
    finally:
        db.close()

    reconnect = auth_client.post(f"/social-accounts/{account_id}/refresh")
    assert reconnect.status_code == 409

    db = SessionLocal()
    try:
        account = db.get(SocialAccount, account_id)
        assert account.status == "reconnect_required"
    finally:
        db.close()


def test_publish_job_lifecycle_and_history(auth_client: TestClient, monkeypatch):
    flow = _create_project_flow(auth_client)
    account_id = _link_youtube_account(auth_client, monkeypatch)

    preview_source = Path("test_storage") / "publish_preview.mp4"
    preview_source.write_bytes(b"rendered-preview")
    monkeypatch.setattr(
        ProjectRenderService,
        "render_preview",
        lambda self, project_id, background_video_path, parsed_lines, style_preset: {
            "output_path": str(preview_source),
            "duration_seconds": 1.0,
        },
    )
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: process_generation_job(job_id))
    monkeypatch.setattr(process_publish_job, "delay", lambda job_id: process_publish_job(job_id))
    monkeypatch.setattr(
        "app.tasks.publish.upload_short",
        lambda **kwargs: {
            "external_post_id": "video-123",
            "external_url": "https://www.youtube.com/watch?v=video-123",
        },
    )

    generation = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    output_video_id = auth_client.get(f"/generation-jobs/{generation.json()['id']}").json()["output_video_id"]

    project_update = auth_client.patch(
        f"/projects/{flow['project_id']}",
        json={"selected_social_account_id": account_id},
    )
    assert project_update.status_code == 200

    approve = auth_client.post(f"/projects/{flow['project_id']}/approve-preview")
    assert approve.status_code == 200

    publish = auth_client.post(
        f"/projects/{flow['project_id']}/publish-jobs",
        json={
            "social_account_id": account_id,
            "output_video_id": output_video_id,
            "platform_metadata_id": flow["metadata_id"],
            "publish_mode": "now",
            "scheduled_for": None,
        },
    )
    assert publish.status_code == 201
    assert publish.json()["status"] == "queued"

    job = auth_client.get(f"/publish-jobs/{publish.json()['id']}")
    assert job.status_code == 200
    assert job.json()["status"] == "published"
    assert job.json()["published_post_url"] == "https://www.youtube.com/watch?v=video-123"

    history = auth_client.get("/publish-history")
    assert history.status_code == 200
    assert len(history.json()["jobs"]) == 1
    assert len(history.json()["posts"]) == 1


def test_scheduled_publish_dispatch_runs_once(auth_client: TestClient, monkeypatch):
    flow = _create_project_flow(auth_client)
    account_id = _link_youtube_account(auth_client, monkeypatch)

    preview_source = Path("test_storage") / "scheduled_preview.mp4"
    preview_source.write_bytes(b"rendered-preview")
    monkeypatch.setattr(
        ProjectRenderService,
        "render_preview",
        lambda self, project_id, background_video_path, parsed_lines, style_preset: {
            "output_path": str(preview_source),
            "duration_seconds": 1.0,
        },
    )
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: process_generation_job(job_id))
    monkeypatch.setattr(process_publish_job, "delay", lambda job_id: process_publish_job(job_id))
    monkeypatch.setattr(
        "app.tasks.publish.upload_short",
        lambda **kwargs: {
            "external_post_id": "scheduled-video",
            "external_url": "https://www.youtube.com/watch?v=scheduled-video",
        },
    )

    generation = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    output_video_id = auth_client.get(f"/generation-jobs/{generation.json()['id']}").json()["output_video_id"]
    auth_client.patch(f"/projects/{flow['project_id']}", json={"selected_social_account_id": account_id})
    auth_client.post(f"/projects/{flow['project_id']}/approve-preview")

    scheduled_for = (datetime.utcnow() - timedelta(minutes=1)).isoformat()
    publish = auth_client.post(
        f"/projects/{flow['project_id']}/publish-jobs",
        json={
            "social_account_id": account_id,
            "output_video_id": output_video_id,
            "platform_metadata_id": flow["metadata_id"],
            "publish_mode": "schedule",
            "scheduled_for": scheduled_for,
        },
    )
    assert publish.status_code == 201
    assert publish.json()["status"] == "scheduled"

    first_run = dispatch_due_publish_jobs()
    second_run = dispatch_due_publish_jobs()
    assert first_run["dispatched"] == 1
    assert second_run["dispatched"] == 0

    history = auth_client.get("/publish-history")
    assert history.status_code == 200
    assert history.json()["posts"][0]["external_post_id"] == "scheduled-video"


def test_script_generation_revisions_and_restore(auth_client: TestClient):
    project = auth_client.post("/projects", json={"name": "Script Lab", "target_platform": "youtube"})
    assert project.status_code == 201
    project_id = project.json()["id"]

    generated = auth_client.post(
        f"/projects/{project_id}/script/generate",
        json={
            "prompt": "how an approval queue reduces publishing mistakes",
            "character_names": ["Host", "Editor"],
            "tone": "explanatory",
        },
    )
    assert generated.status_code == 201
    first_revision_id = generated.json()["current_revision"]["id"]

    update = auth_client.put(
        f"/projects/{project_id}/script",
        json={
            "parsed_lines": [
                {"speaker": "Host", "text": "We generated a first pass.", "order": 0},
                {"speaker": "Editor", "text": "Now we can revise it line by line.", "order": 1},
            ],
            "source": "manual",
            "parent_revision_id": first_revision_id,
        },
    )
    assert update.status_code == 200
    assert update.json()["current_revision"]["parent_revision_id"] == first_revision_id

    revisions = auth_client.get(f"/projects/{project_id}/script-revisions")
    assert revisions.status_code == 200
    assert len(revisions.json()["items"]) == 2

    restore = auth_client.post(f"/projects/{project_id}/script-revisions/{first_revision_id}/restore")
    assert restore.status_code == 200
    assert restore.json()["current_revision"]["source"] == "restore"


def test_review_queue_routing_and_auto_publish(auth_client: TestClient, monkeypatch):
    flow = _create_project_flow(auth_client)
    account_id = _link_youtube_account(auth_client, monkeypatch)

    preview_source = Path("test_storage") / "review_queue_preview.mp4"
    preview_source.write_bytes(b"rendered-preview")
    monkeypatch.setattr(
        ProjectRenderService,
        "render_preview",
        lambda self, project_id, background_video_path, parsed_lines, style_preset: {
            "output_path": str(preview_source),
            "duration_seconds": 1.25,
        },
    )
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: process_generation_job(job_id))
    monkeypatch.setattr(process_publish_job, "delay", lambda job_id: process_publish_job(job_id))
    monkeypatch.setattr(
        "app.tasks.publish.upload_short",
        lambda **kwargs: {
            "external_post_id": "review-auto-video",
            "external_url": "https://www.youtube.com/watch?v=review-auto-video",
        },
    )

    auth_client.patch(
        f"/projects/{flow['project_id']}",
        json={
            "selected_social_account_id": account_id,
            "automation_mode": "auto",
            "allowed_platforms": ["youtube"],
            "preferred_account_type": "owned_channel",
        },
    )

    generation = auth_client.post(
        f"/projects/{flow['project_id']}/renders",
        json={"background_style": "blur", "output_kind": "preview", "provider_name": "local-compositor"},
    )
    assert generation.status_code == 201
    output_video_id = auth_client.get(f"/generation-jobs/{generation.json()['id']}").json()["output_video_id"]

    submit = auth_client.post(
        f"/projects/{flow['project_id']}/review/submit",
        json={"output_video_id": output_video_id, "note": "Ready for human review."},
    )
    assert submit.status_code == 201
    review_id = submit.json()["id"]
    assert submit.json()["status"] == "pending"

    changes = auth_client.post(
        f"/reviews/{review_id}/request-changes",
        json={"summary": "Tighten the script", "rejection_reason": "Shorten the intro."},
    )
    assert changes.status_code == 200
    assert changes.json()["status"] == "changes_requested"

    approve = auth_client.post(
        f"/reviews/{review_id}/approve",
        json={"summary": "Approved after revision."},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    routing = auth_client.post(f"/projects/{flow['project_id']}/routing/suggest")
    assert routing.status_code == 200
    assert routing.json()["recommended_platform"] == "youtube"
    assert routing.json()["social_account_id"] == account_id

    auto_publish = auth_client.post(
        f"/projects/{flow['project_id']}/publish/auto",
        json={
            "platform": "youtube",
            "output_video_id": output_video_id,
            "platform_metadata_id": flow["metadata_id"],
            "publish_mode": "now",
            "scheduled_for": None,
            "automation_mode": "auto",
        },
    )
    assert auto_publish.status_code == 201
    assert auto_publish.json()["status"] == "queued"

    job = auth_client.get(f"/publish-jobs/{auto_publish.json()['id']}")
    assert job.status_code == 200
    assert job.json()["status"] == "published"
    assert job.json()["published_post_url"] == "https://www.youtube.com/watch?v=review-auto-video"


def test_end_to_end_happy_path(auth_client: TestClient, monkeypatch):
    flow = _create_project_flow(auth_client)
    account_id = _link_youtube_account(auth_client, monkeypatch)

    preview_source = Path("test_storage") / "happy_path_preview.mp4"
    preview_source.write_bytes(b"rendered-preview")
    monkeypatch.setattr(
        ProjectRenderService,
        "render_preview",
        lambda self, project_id, background_video_path, parsed_lines, style_preset: {
            "output_path": str(preview_source),
            "duration_seconds": 2.0,
        },
    )
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: process_generation_job(job_id))
    monkeypatch.setattr(process_publish_job, "delay", lambda job_id: process_publish_job(job_id))
    monkeypatch.setattr(
        "app.tasks.publish.upload_short",
        lambda **kwargs: {
            "external_post_id": "happy-video",
            "external_url": "https://www.youtube.com/watch?v=happy-video",
        },
    )

    generation = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "blur"},
    )
    generation_job = auth_client.get(f"/generation-jobs/{generation.json()['id']}")
    output_video_id = generation_job.json()["output_video_id"]

    auth_client.patch(f"/projects/{flow['project_id']}", json={"selected_social_account_id": account_id})
    approve = auth_client.post(f"/projects/{flow['project_id']}/approve-preview")
    assert approve.status_code == 200

    publish = auth_client.post(
        f"/projects/{flow['project_id']}/publish-jobs",
        json={
            "social_account_id": account_id,
            "output_video_id": output_video_id,
            "platform_metadata_id": flow["metadata_id"],
            "publish_mode": "now",
            "scheduled_for": None,
        },
    )
    assert publish.status_code == 201

    final_project = auth_client.get(f"/projects/{flow['project_id']}")
    assert final_project.status_code == 200
    assert final_project.json()["status"] == "published"

    history = auth_client.get(f"/projects/{flow['project_id']}/publish-history")
    assert history.status_code == 200
    assert history.json()["jobs"][0]["status"] == "published"
    assert history.json()["posts"][0]["external_url"] == "https://www.youtube.com/watch?v=happy-video"
