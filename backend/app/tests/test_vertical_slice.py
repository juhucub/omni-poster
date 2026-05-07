from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import math
import subprocess
import sys
import types
import wave

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db import SessionLocal
from app.models import GenerationJob, SocialAccount, VoicePreviewJob, VoiceProfile, VoiceReferenceAudio
from app.services.voice_preview_jobs import STALE_VOICE_PREVIEW_ERROR_CODE
from app.services.character_presets import get_character_preset
from app.services.crypto import decrypt_secret
from app.services.render_profiling import RenderProfiler
from app.services.rendering import ProjectRenderService
from app.services.storage import generated_job_artifact_url, generated_job_segment_dir
from app.services.character_voice_recipes import validate_selected_character_recipe
from app.services.tts import LocalSpeechService, OpenVoiceProvider, SpeechSegment, TTSOrchestrator, TextToSpeechError, XTTSProvider
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


def _write_wav(path: Path, *, seconds: float = 1.6, sample_rate: int = 16000, sample: bytes = b"\x00\x00") -> None:
    frame_count = int(seconds * sample_rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(sample * frame_count)


def _write_sine_wav(path: Path, *, seconds: float = 1.6, sample_rate: int = 16000, frequency: float = 180.0) -> None:
    frame_count = int(seconds * sample_rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = bytearray()
    for index in range(frame_count):
        value = int(12000 * math.sin(2 * math.pi * frequency * index / sample_rate))
        frames.extend(value.to_bytes(2, byteorder="little", signed=True))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(bytes(frames))


def _write_stewie_selected_recipe_tree(root: Path) -> dict[str, Path]:
    checkpoint_dir = root / "shared" / "xtts_v2"
    clean_dir = root / "stewie_griffin" / "dataset" / "clean"
    golden_dir = root / "stewie_griffin" / "previews" / "golden"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    clean_dir.mkdir(parents=True, exist_ok=True)
    golden_dir.mkdir(parents=True, exist_ok=True)
    (checkpoint_dir / "config.json").write_text("{}", encoding="utf-8")
    (checkpoint_dir / "vocab.json").write_text("{}", encoding="utf-8")
    (checkpoint_dir / "model.pth").write_bytes(b"checkpoint")
    _write_sine_wav(clean_dir / "ref_a.wav", seconds=0.8)
    _write_sine_wav(clean_dir / "ref_b.wav", seconds=0.8, frequency=220)
    _write_sine_wav(golden_dir / "xtts_checkpoint_smoke.wav", seconds=0.8, frequency=260)
    recipe_path = root / "stewie_griffin" / "selected_recipe.json"
    recipe_path.write_text(
        json.dumps(
            {
                "provider": "xtts",
                "character": "stewie_griffin",
                "status": "golden_preview_selected",
                "xtts_checkpoint_dir_local": str(checkpoint_dir),
                "reference_wavs_local": str(clean_dir / "*.wav"),
                "golden_preview_local": str(golden_dir / "xtts_checkpoint_smoke.wav"),
                "language": "en",
                "recipe": {"temperature": 0.7, "speed": 1.0, "split_sentences": True},
                "render_verified": False,
            }
        ),
        encoding="utf-8",
    )
    return {
        "root": root,
        "checkpoint_dir": checkpoint_dir,
        "clean_dir": clean_dir,
        "golden_preview": golden_dir / "xtts_checkpoint_smoke.wav",
        "recipe_path": recipe_path,
    }


def _fake_reference_audio_ffmpeg_run(recorded: dict[str, object] | None = None, *, seconds: float = 1.8, silence_stderr: str = ""):
    def fake_run(command, check, capture_output, text):
        if recorded is not None:
            recorded.setdefault("commands", []).append(command)
        if command[-1] == "-":
            return subprocess.CompletedProcess(command, 0, stdout="", stderr=silence_stderr)
        output_seconds = seconds
        if "-t" in command:
            output_seconds = float(command[command.index("-t") + 1])
        _write_wav(Path(command[-1]), seconds=output_seconds)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    return fake_run


def test_render_profiler_records_rss_and_serializes(tmp_path: Path):
    rss_values = iter([100, 150, 220])
    profiler = RenderProfiler(
        job_id=7,
        project_id=3,
        output_kind="preview",
        rss_reader=lambda: next(rss_values, 220),
    )

    profiler.add_context(path=tmp_path / "render.mp4", nested={"value": tmp_path / "audio.wav"})
    with profiler.stage("test.stage", marker=tmp_path / "marker"):
        profiler.sample_memory()

    payload = profiler.to_dict()
    assert payload["job_id"] == 7
    assert payload["context"]["path"].endswith("render.mp4")
    assert payload["stages"][0]["name"] == "test.stage"
    assert payload["stages"][0]["observed_peak_rss_bytes"] == 220
    assert payload["summary"]["peak_observed_rss_bytes"] == 220

    profile_path = tmp_path / "generation_profile.json"
    profiler.write_json(profile_path)
    loaded = json.loads(profile_path.read_text(encoding="utf-8"))
    assert loaded["summary"]["top_stages"][0]["name"] == "test.stage"


def test_render_profiler_handles_missing_rss(tmp_path: Path):
    profiler = RenderProfiler(rss_reader=lambda: None)
    with profiler.stage("no.rss"):
        pass

    payload = profiler.to_dict()
    assert payload["stages"][0]["rss_before_bytes"] is None
    assert payload["stages"][0]["rss_after_bytes"] is None
    assert payload["summary"]["peak_observed_rss_bytes"] is None


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
    db = SessionLocal()
    try:
        job = db.get(VoicePreviewJob, response.json()["job_id"])
        assert job is not None
        assert job.requested_provider == "openvoice"
        assert job.fallback_allowed is False
    finally:
        db.close()


def test_voice_lab_calibration_matrix_queues_recipe_previews(auth_client: TestClient, monkeypatch):
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

    from app.services.voice_profiles import reference_audio_content_hash_from_paths

    processed_reference_path = Path("test_storage") / "voice_lab" / "reference_audio" / "vp_host_calm_v1" / "processed_reference.wav"
    _write_wav(processed_reference_path, sample=b"\x04\x00")
    reference_hash = reference_audio_content_hash_from_paths([processed_reference_path])
    embedding_path = Path("test_storage") / "voice_lab" / "embeddings" / f"vp_host_calm_v1_{reference_hash[:16]}.pth"
    embedding_path.parent.mkdir(parents=True, exist_ok=True)
    embedding_path.write_bytes(b"embedding")
    processed_reference = str(processed_reference_path)
    embedding_path_value = str(embedding_path)
    db = SessionLocal()
    try:
        profile = db.get(VoiceProfile, "vp_host_calm_v1")
        assert profile is not None
        reference = VoiceReferenceAudio(
            voice_profile_id="vp_host_calm_v1",
            storage_path=processed_reference,
            original_storage_path="test_storage/voice_lab/reference_audio/vp_host_calm_v1/original.wav",
            processed_storage_path=processed_reference,
            mime_type="audio/wav",
            duration_ms=1600,
            sha256="raw-reference",
            processed_sha256=reference_hash,
            validation_status="passed",
            validation_json={"status": "passed"},
            authorization_confirmed=True,
        )
        db.add(reference)
        db.flush()
        profile.embedding_path = embedding_path_value
        profile.provider_metadata_json = {
            "embedding_artifact_path": embedding_path_value,
            "reference_audio_sha256": reference_hash,
            "processed_reference_audio": {
                str(reference.id): {
                    "normalized_reference_path": processed_reference,
                    "chunks": [
                        {
                            "path": processed_reference,
                            "duration_seconds": 1.6,
                            "start_seconds": 0.0,
                            "end_seconds": 1.6,
                        }
                    ],
                }
            },
        }
        db.commit()
    finally:
        db.close()

    scheduled: list[dict] = []

    def fake_apply_async(*, kwargs=None, task_id=None, **_extra):
        scheduled.append({"kwargs": kwargs, "task_id": task_id})
        return None

    monkeypatch.setattr(process_voice_lab_preview, "apply_async", fake_apply_async)
    response = auth_client.post(
        "/voice-lab/calibration-matrix",
        json={
            "preset_id": "host_calm_v1",
            "provider_preference": "openvoice",
            "fallback_allowed": False,
            "phrases": ["Calibration phrase one.", "Calibration phrase two."],
            "recipes": [
                {
                    "base_speaker": "EN-US",
                    "style_preset": "default",
                    "speaking_rate": 0.92,
                    "pause_bias": 1.25,
                    "pitch": -1,
                    "energy": 1.1,
                }
            ],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["voice_profile_id"] == "vp_host_calm_v1"
    assert len(payload["items"]) == 2
    assert len(scheduled) == 2
    first = payload["items"][0]
    assert first["status"] == "queued"
    assert first["calibration"]["recipe"] == {
        "base_speaker": "EN-US",
        "style_preset": "default",
        "speaking_rate": 0.92,
        "pause_bias": 1.25,
        "pitch": -1.0,
        "energy": 1.1,
        "emotion": None,
        "accent": None,
    }
    assert first["calibration"]["controls"] == {
        "speaking_rate": 0.92,
        "pause_length": 1.25,
        "pitch": -1.0,
        "energy": 1.1,
    }
    assert first["calibration"]["supported_controls"] == ["speaking_rate"]
    assert first["calibration"]["processed_reference_paths"] == [processed_reference]
    assert len(first["calibration"]["processed_reference_audio_ids"]) == 1
    assert first["calibration"]["embedding_path"] == embedding_path_value
    assert first["calibration"]["reference_audio_sha256"] == reference_hash
    assert {"energy", "pause_length", "pitch", "style_preset"}.issubset(set(first["calibration"]["unsupported_controls"]))

    db = SessionLocal()
    try:
        job = db.get(VoicePreviewJob, first["job_id"])
        assert job is not None
        assert job.calibration_json["recipe"]["base_speaker"] == "EN-US"
        assert job.calibration_json["embedding_path"] == embedding_path_value
        assert job.fallback_allowed is False
        assert scheduled[0]["kwargs"]["preview_job_id"] == job.id
    finally:
        db.close()


def test_voice_lab_preview_auto_runs_sync_when_selection_resolves_to_espeak(auth_client: TestClient, monkeypatch):
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

    output_path = Path("test_storage") / "voice_lab" / "previews" / "resolved_sync.wav"
    _write_wav(output_path)
    scheduled = {"called": False}

    def fake_resolve_provider_selection(self, voice_profile, requested_provider=None, fallback_allowed=True):
        return {
            "selection_order": ["openvoice", "espeak"],
            "selected_provider": "espeak",
            "provider_state": {
                "openvoice": {"available": False, "reason": "missing_models"},
                "espeak": {"available": True, "reason": None},
            },
            "fallback_allowed": True,
        }

    def fake_synthesize_dialogue(self, *, lines, voice_profile_map, output_dir, requested_provider=None, fallback_allowed=True, options=None):
        assert requested_provider == "espeak"
        assert fallback_allowed is True
        return [
            SpeechSegment(
                speaker=lines[0]["speaker"],
                text=lines[0]["text"],
                voice="en-us+f3",
                slot_index=0,
                audio_path=str(output_path),
                duration_seconds=1.2,
                voice_profile_id="vp_host_calm_v1",
                provider_used="espeak",
                fallback_used=True,
                controls_applied={"speaking_rate": 1.0},
                reference_audio_count=0,
            )
        ]

    monkeypatch.setattr(TTSOrchestrator, "resolve_provider_selection", fake_resolve_provider_selection)
    monkeypatch.setattr(TTSOrchestrator, "synthesize_dialogue", fake_synthesize_dialogue)
    monkeypatch.setattr(process_voice_lab_preview, "apply_async", lambda **kwargs: scheduled.update(called=True))

    response = auth_client.post(
        "/voice-lab/preview",
        json={
            "preset_id": "host_calm_v1",
            "provider_preference": "auto",
            "text": "Use the best available provider.",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["provider_used"] == "espeak"
    assert scheduled["called"] is False


def test_reference_audio_upload_normalizes_audio_and_invalidates_embedding(auth_client: TestClient, monkeypatch):
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

    stale_embedding = Path("test_storage") / "voice_lab" / "embeddings" / "vp_host_calm_v1.pth"
    stale_embedding.parent.mkdir(parents=True, exist_ok=True)
    stale_embedding.write_bytes(b"stale")
    stale_hashed_embedding = Path("test_storage") / "voice_lab" / "embeddings" / "vp_host_calm_v1_deadbeefdeadbeef.pth"
    stale_hashed_embedding.write_bytes(b"stale-hashed")

    db = SessionLocal()
    try:
        from app.models import VoiceProfile

        profile = db.get(VoiceProfile, "vp_host_calm_v1")
        assert profile is not None
        profile.embedding_path = str(stale_embedding)
        profile.provider_metadata_json = {"embedding_status": "ready", "embedding_ready": True}
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr("app.services.voice_profiles._ffmpeg_binary", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr("app.services.voice_profiles.subprocess.run", _fake_reference_audio_ffmpeg_run(seconds=1.8))

    response = auth_client.post(
        "/voice-profiles/reference-audio",
        files={"file": ("reference.mp3", b"fake-mp3", "audio/mpeg")},
        data={
            "voice_profile_id": "vp_host_calm_v1",
            "authorization_confirmed": "true",
            "authorization_note": "owned",
        },
    )

    assert response.status_code == 201
    assert response.json()["reference_audio"]["mime_type"] == "audio/wav"
    assert response.json()["reference_audio"]["storage_path"].endswith(".wav")
    assert response.json()["reference_audio"]["original_storage_path"].endswith("original.mp3")
    assert response.json()["reference_audio"]["processed_storage_path"].endswith("processed_reference.wav")
    assert response.json()["reference_audio"]["processed_sha256"]
    assert response.json()["reference_audio"]["validation_status"] == "passed"
    assert response.json()["reference_audio"]["original_content_url"].endswith("/original")
    assert response.json()["reference_audio"]["processed_content_url"].endswith("/processed")
    assert response.json()["reference_audio"]["duration_ms"] >= 1800
    assert response.json()["voice_profile"]["embedding_path"] is None
    assert response.json()["voice_profile"]["provider_metadata"]["embedding_status"] == "not_prepared"
    assert response.json()["voice_profile"]["provider_metadata"]["reference_validation_status"] == "passed"
    assert stale_embedding.exists() is False
    assert stale_hashed_embedding.exists() is False

    original_response = auth_client.get(response.json()["reference_audio"]["original_content_url"])
    processed_response = auth_client.get(response.json()["reference_audio"]["processed_content_url"])
    assert original_response.status_code == 200
    assert processed_response.status_code == 200
    assert processed_response.content.startswith(b"RIFF")


def test_character_reference_dataset_upload_analyze_and_attach_model(auth_client: TestClient, monkeypatch, tmp_path: Path):
    bundled_file = Path("test_storage") / "bundled" / "character_presets.json"
    bundled_file.write_text(
        """
[
  {
    "id": "peter_griffin_character_v1",
    "display_name": "Peter Griffin",
    "speaker_names": ["Peter Griffin"],
    "tts_provider": "xtts",
    "fallback_provider": "espeak",
    "character_slug": "peter_griffin",
    "voice": "en-us+m3",
    "rate": 150,
    "pitch": 38,
    "word_gap": 1,
    "amplitude": 145
  }
]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    auth_client.get("/character-presets")
    monkeypatch.setattr("app.services.voice_profiles._ffmpeg_binary", lambda: "/usr/bin/ffmpeg")

    def fake_run(command, check, capture_output, text):
        if command[-1] == "-":
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        output_seconds = 1.8
        if "-t" in command:
            output_seconds = float(command[command.index("-t") + 1])
        _write_sine_wav(Path(command[-1]), seconds=output_seconds, frequency=145.0)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("app.services.voice_profiles.subprocess.run", fake_run)

    created = auth_client.post(
        "/voice-profiles/vp_peter_griffin_character_v1/reference-datasets",
        json={"display_name": "Peter licensed refs", "character_slug": "peter_griffin"},
    )
    assert created.status_code == 201
    dataset_id = created.json()["dataset"]["id"]
    assert created.json()["voice_profile"]["reference_dataset_id"] == dataset_id
    assert created.json()["dataset"]["character_slug"] == "peter_griffin"

    uploaded = auth_client.post(
        f"/voice-profiles/vp_peter_griffin_character_v1/reference-datasets/{dataset_id}/clips",
        files={"file": ("reference.mp3", b"fake-mp3", "audio/mpeg")},
        data={"authorization_confirmed": "true", "authorization_note": "licensed"},
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["reference_audio"]["reference_dataset_id"] == dataset_id
    assert uploaded.json()["dataset"]["accepted_clip_count"] == 1
    assert uploaded.json()["dataset"]["metrics"]["clean_speech_duration_seconds"] > 0

    analyzed = auth_client.post(
        f"/voice-profiles/vp_peter_griffin_character_v1/reference-datasets/{dataset_id}/analyze"
    )
    assert analyzed.status_code == 200
    assert analyzed.json()["dataset"]["status"] == "analyzed"
    assert analyzed.json()["dataset"]["prosody_metrics"]["pitch_median_hz"] > 0

    checkpoint = tmp_path / "xtts" / "model.pth"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"checkpoint")
    attached = auth_client.post(
        "/voice-profiles/vp_peter_griffin_character_v1/models/attach",
        json={
            "provider": "xtts",
            "model_checkpoint_path": str(checkpoint),
            "reference_dataset_id": dataset_id,
            "recipe": {"provider": "xtts", "speaking_rate": 0.95},
        },
    )
    assert attached.status_code == 200
    assert attached.json()["provider"] == "xtts"
    assert attached.json()["model_checkpoint_path"] == str(checkpoint)
    assert attached.json()["selected_recipe"]["reference_dataset_id"] == dataset_id


def test_prosody_analyzer_extracts_pitch_pause_and_energy(tmp_path: Path):
    from app.services.voice_replication import analyze_audio_prosody

    audio_path = tmp_path / "tone.wav"
    _write_sine_wav(audio_path, seconds=1.5, frequency=220.0)

    metrics = analyze_audio_prosody(audio_path)

    assert metrics["pitch_median_hz"] > 150
    assert metrics["pitch_range_semitones"] >= 0
    assert metrics["energy_mean"] > 0
    assert metrics["voiced_ratio"] > 0.5


def test_character_calibration_batch_scores_and_saves_recipe(auth_client: TestClient, monkeypatch):
    bundled_file = Path("test_storage") / "bundled" / "character_presets.json"
    bundled_file.write_text(
        """
[
  {
    "id": "stewie_griffin_character_v1",
    "display_name": "Stewie Griffin",
    "speaker_names": ["Stewie Griffin"],
    "tts_provider": "espeak",
    "fallback_provider": "espeak",
    "character_slug": "stewie_griffin",
    "voice": "en-gb+m3",
    "rate": 168,
    "pitch": 62,
    "word_gap": 1,
    "amplitude": 145
  }
]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    auth_client.get("/character-presets")
    db = SessionLocal()
    try:
        profile = db.get(VoiceProfile, "vp_stewie_griffin_character_v1")
        assert profile is not None
        profile.provider_metadata_json = {
            "target_prosody_metrics": {
                "pitch_median_hz": 220,
                "pitch_range_semitones": 1,
                "speaking_rate": 0.8,
                "pause_count": 0,
                "mean_pause_length_seconds": 0,
                "energy_mean": 0.25,
                "phrase_pitch_movement": {"mean_abs_delta_hz": 2},
            }
        }
        db.commit()
    finally:
        db.close()

    def fake_provider_state(self):
        return {
            "espeak": {"available": True},
            "openvoice": {"available": False, "reason": "disabled"},
            "xtts": {"available": False, "reason": "disabled"},
            "rvc": {"available": False, "reason": "disabled"},
        }

    def fake_synthesize_line(self, *, text, voice_profile, output_path, requested_provider=None, fallback_allowed=True, options=None):
        _write_sine_wav(output_path, seconds=1.2, frequency=220.0)
        from app.services.tts import SynthesisResult

        return SynthesisResult(
            audio_path=str(output_path),
            voice="Stewie Griffin",
            duration_seconds=1.2,
            provider_used=requested_provider or "espeak",
            fallback_used=False,
            controls_applied=voice_profile.get("controls") or {},
            reference_audio_count=0,
            provider_state=fake_provider_state(self),
            cache_hit=False,
            voice_profile_id=voice_profile["id"],
        )

    monkeypatch.setattr(TTSOrchestrator, "provider_state", fake_provider_state)
    monkeypatch.setattr(TTSOrchestrator, "synthesize_line", fake_synthesize_line)

    batch = auth_client.post(
        "/voice-lab/calibration-batches",
        json={
            "voice_profile_id": "vp_stewie_griffin_character_v1",
            "calibration_script": "Victory is mine.",
            "candidates": [{"provider": "espeak", "rate": 1.0, "pitch_shift": 0.0}],
        },
    )
    assert batch.status_code == 201
    assert batch.json()["status"] == "completed"
    assert batch.json()["rankings"][0]["score"] > 0.5
    recipe = batch.json()["rankings"][0]["recipe"]
    recipe["calibration_score"] = batch.json()["rankings"][0]["score"]

    saved = auth_client.post(
        "/voice-profiles/vp_stewie_griffin_character_v1/calibration-recipe",
        json={"recipe": recipe},
    )
    assert saved.status_code == 200
    assert saved.json()["selected_recipe"]["provider"] == "espeak"
    assert saved.json()["calibration_score"] == recipe["calibration_score"]


def test_character_render_verification_marks_profile_verified(auth_client: TestClient, tmp_path: Path):
    profile_response = auth_client.post(
        "/voice-profiles",
        json={
            "display_name": "Verified Character",
            "provider": "espeak",
            "fallback_provider": "espeak",
            "voice": "en-us+f3",
            "espeak_rate": 155,
            "espeak_pitch": 45,
            "espeak_word_gap": 1,
            "espeak_amplitude": 140,
            "selected_recipe": {"provider": "espeak"},
        },
    )
    assert profile_response.status_code == 201
    voice_profile_id = profile_response.json()["id"]
    segment_path = tmp_path / "segments" / "000_verified.wav"
    composite_path = tmp_path / "audio" / "dialogue_composite.wav"
    final_audio_path = tmp_path / "audio" / "final_video_audio.wav"
    _write_sine_wav(segment_path, seconds=1.1, frequency=180.0)
    _write_sine_wav(composite_path, seconds=1.1, frequency=180.0)
    _write_sine_wav(final_audio_path, seconds=1.1, frequency=180.0)
    db = SessionLocal()
    try:
        job = GenerationJob(
            project_id=1,
            input_asset_id=1,
            script_revision_id=1,
            style_preset="none",
            output_kind="preview",
            provider_name="local-compositor",
            status="completed",
            progress=100,
            tts_result_json={
                "status": "completed",
                "segments": [
                    {
                        "voice_profile_id": voice_profile_id,
                        "provider_used": "espeak",
                        "fallback_used": False,
                        "audio_path": str(segment_path),
                        "voice_profile_settings": {
                            "provider": "espeak",
                            "selected_recipe": {"provider": "espeak"},
                        },
                    }
                ],
                "assembly": {
                    "composite_audio_path": str(composite_path),
                    "final_video_audio_path": str(final_audio_path),
                },
            },
        )
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    verified = auth_client.post(f"/voice-profiles/{voice_profile_id}/verify-render/{job_id}")
    assert verified.status_code == 200
    assert verified.json()["verification"]["status"] == "passed"
    assert verified.json()["voice_profile"]["last_verified_render_job_id"] == job_id


def test_stewie_selected_recipe_validates_required_paths(monkeypatch, tmp_path: Path):
    tree = _write_stewie_selected_recipe_tree(tmp_path / "voice_models")
    monkeypatch.setattr(settings, "VOICE_MODELS_DIR", str(tree["root"]))

    recipe = validate_selected_character_recipe("stewie_griffin")

    assert recipe.provider == "xtts"
    assert recipe.character == "stewie_griffin"
    assert recipe.checkpoint_dir == tree["checkpoint_dir"]
    assert len(recipe.reference_wavs) == 2
    assert recipe.golden_preview_wav == tree["golden_preview"]
    assert recipe.settings["temperature"] == 0.7


def test_xtts_provider_uses_stewie_selected_recipe_exactly(monkeypatch, tmp_path: Path):
    XTTSProvider.clear_worker_cache()
    tree = _write_stewie_selected_recipe_tree(tmp_path / "voice_models")
    monkeypatch.setattr(settings, "VOICE_MODELS_DIR", str(tree["root"]))
    monkeypatch.setattr(settings, "XTTS_DEVICE", "cpu")
    monkeypatch.setattr(settings, "XTTS_WORKER_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "XTTS_WORKER_CACHE_MAX_ENTRIES", 2)
    recorded: dict[str, object] = {}

    class FakeConfig:
        def load_json(self, path):
            recorded["config_path"] = path

    class FakeModel:
        def load_checkpoint(self, config, checkpoint_dir, eval):
            recorded["checkpoint_dir"] = checkpoint_dir
            recorded["eval"] = eval

        def to(self, device):
            recorded["device"] = device

        def get_conditioning_latents(self, audio_path):
            recorded["reference_wavs"] = audio_path
            return "latent", "embedding"

        def inference(self, text, language, latent, embedding, **kwargs):
            recorded["text"] = text
            recorded["language"] = language
            recorded["inference_kwargs"] = kwargs
            return {"wav": [0.0] * 24000}

    class FakeXtts:
        @staticmethod
        def init_from_config(config):
            recorded["init_from_config"] = True
            return FakeModel()

    class FakeTensor:
        def unsqueeze(self, axis):
            recorded["unsqueeze_axis"] = axis
            return self

    def fake_torchaudio_save(path, tensor, sample_rate):
        recorded["output_path"] = path
        recorded["sample_rate"] = sample_rate
        _write_sine_wav(Path(path), seconds=0.8, sample_rate=sample_rate)

    modules = {
        "TTS": types.ModuleType("TTS"),
        "TTS.tts": types.ModuleType("TTS.tts"),
        "TTS.tts.configs": types.ModuleType("TTS.tts.configs"),
        "TTS.tts.configs.xtts_config": types.ModuleType("TTS.tts.configs.xtts_config"),
        "TTS.tts.models": types.ModuleType("TTS.tts.models"),
        "TTS.tts.models.xtts": types.ModuleType("TTS.tts.models.xtts"),
        "torch": types.ModuleType("torch"),
        "torchaudio": types.ModuleType("torchaudio"),
    }
    modules["TTS.tts.configs.xtts_config"].XttsConfig = FakeConfig
    modules["TTS.tts.models.xtts"].Xtts = FakeXtts
    modules["torch"].tensor = lambda wav: FakeTensor()
    modules["torchaudio"].save = fake_torchaudio_save
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    provider = XTTSProvider()
    monkeypatch.setattr(provider, "healthcheck", lambda: {"available": True, "reason": None, "metadata": {"device": "cpu"}})
    output_path = tmp_path / "rendered.wav"
    profiler = RenderProfiler(job_id=5, project_id=2, output_kind="preview", rss_reader=lambda: 100)

    result = provider.synthesize_line(
        text="Victory is mine.",
        voice_profile={"id": "vp_stewie", "display_name": "Stewie Griffin", "provider": "xtts", "character_slug": "stewie_griffin"},
        output_path=output_path,
        options={"profiler": profiler},
    )

    assert recorded["checkpoint_dir"] == str(tree["checkpoint_dir"])
    assert len(recorded["reference_wavs"]) == 2
    assert recorded["language"] == "en"
    assert recorded["inference_kwargs"]["temperature"] == 0.7
    assert recorded["inference_kwargs"]["speed"] == 1.0
    assert recorded["sample_rate"] == 24000
    assert result["provider_used"] == "xtts"
    assert result["reference_audio_count"] == 2
    assert result["recipe_used"]["checkpoint_dir"] == str(tree["checkpoint_dir"])
    assert result["golden_preview_wav"] == str(tree["golden_preview"])
    stage_names = [stage["name"] for stage in profiler.to_dict()["stages"]]
    assert "xtts.config_load" in stage_names
    assert "xtts.checkpoint_load" in stage_names
    assert "xtts.conditioning_latents" in stage_names
    assert "xtts.inference" in stage_names
    assert "xtts.wav_save" in stage_names


def test_xtts_provider_reuses_selected_recipe_runtime_without_audio_cache(monkeypatch, tmp_path: Path):
    XTTSProvider.clear_worker_cache()
    tree = _write_stewie_selected_recipe_tree(tmp_path / "voice_models")
    monkeypatch.setattr(settings, "VOICE_MODELS_DIR", str(tree["root"]))
    monkeypatch.setattr(settings, "XTTS_DEVICE", "cpu")
    monkeypatch.setattr(settings, "XTTS_WORKER_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "XTTS_WORKER_CACHE_MAX_ENTRIES", 2)
    monkeypatch.setattr(settings, "XTTS_TORCH_INFERENCE_MODE_ENABLED", True)
    monkeypatch.setattr(settings, "XTTS_CPU_NUM_THREADS", 3)
    monkeypatch.setattr(settings, "XTTS_CPU_INTEROP_THREADS", 2)
    counters = {
        "config_loads": 0,
        "model_inits": 0,
        "checkpoint_loads": 0,
        "device_moves": 0,
        "latent_calls": 0,
        "inferences": 0,
        "wav_saves": 0,
        "set_num_threads": 0,
        "set_num_interop_threads": 0,
        "inference_mode_entries": 0,
    }
    torch_state = {"num_threads": 0, "interop_threads": 0, "inference_depth": 0}
    saved_paths: list[str] = []

    class FakeConfig:
        def load_json(self, path):
            counters["config_loads"] += 1

    class FakeModel:
        def load_checkpoint(self, config, checkpoint_dir, eval):
            counters["checkpoint_loads"] += 1

        def to(self, device):
            counters["device_moves"] += 1

        def get_conditioning_latents(self, audio_path):
            counters["latent_calls"] += 1
            return "latent", "embedding"

        def inference(self, text, language, latent, embedding, split_sentences=None, **kwargs):
            assert torch_state["inference_depth"] == 1
            counters["inferences"] += 1
            return {"wav": [0.0] * 24000}

    class FakeXtts:
        @staticmethod
        def init_from_config(config):
            counters["model_inits"] += 1
            return FakeModel()

    class FakeTensor:
        def unsqueeze(self, axis):
            return self

    def fake_torchaudio_save(path, tensor, sample_rate):
        counters["wav_saves"] += 1
        saved_paths.append(path)
        _write_sine_wav(Path(path), seconds=0.8, sample_rate=sample_rate)

    modules = {
        "TTS": types.ModuleType("TTS"),
        "TTS.tts": types.ModuleType("TTS.tts"),
        "TTS.tts.configs": types.ModuleType("TTS.tts.configs"),
        "TTS.tts.configs.xtts_config": types.ModuleType("TTS.tts.configs.xtts_config"),
        "TTS.tts.models": types.ModuleType("TTS.tts.models"),
        "TTS.tts.models.xtts": types.ModuleType("TTS.tts.models.xtts"),
        "torch": types.ModuleType("torch"),
        "torchaudio": types.ModuleType("torchaudio"),
    }
    modules["TTS.tts.configs.xtts_config"].XttsConfig = FakeConfig
    modules["TTS.tts.models.xtts"].Xtts = FakeXtts
    modules["torch"].tensor = lambda wav: FakeTensor()

    def fake_set_num_threads(value):
        counters["set_num_threads"] += 1
        torch_state["num_threads"] = value

    def fake_set_num_interop_threads(value):
        counters["set_num_interop_threads"] += 1
        torch_state["interop_threads"] = value

    class FakeInferenceMode:
        def __enter__(self):
            counters["inference_mode_entries"] += 1
            torch_state["inference_depth"] += 1

        def __exit__(self, exc_type, exc, tb):
            torch_state["inference_depth"] -= 1

    modules["torch"].set_num_threads = fake_set_num_threads
    modules["torch"].set_num_interop_threads = fake_set_num_interop_threads
    modules["torch"].get_num_threads = lambda: torch_state["num_threads"]
    modules["torch"].get_num_interop_threads = lambda: torch_state["interop_threads"]
    modules["torch"].inference_mode = lambda: FakeInferenceMode()
    modules["torchaudio"].save = fake_torchaudio_save
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    provider = XTTSProvider()
    monkeypatch.setattr(provider, "healthcheck", lambda: {"available": True, "reason": None, "metadata": {"device": "cpu"}})
    profiler = RenderProfiler(job_id=6, project_id=2, output_kind="preview", rss_reader=lambda: 100)
    profile = {
        "id": "vp_stewie",
        "display_name": "Stewie Griffin",
        "provider": "xtts",
        "character_slug": "stewie_griffin",
    }
    first_path = tmp_path / "first.wav"
    second_path = tmp_path / "second.wav"

    provider.synthesize_line(text="First line.", voice_profile=profile, output_path=first_path, options={"profiler": profiler})
    provider.synthesize_line(text="Second line.", voice_profile=profile, output_path=second_path, options={"profiler": profiler})

    assert counters["config_loads"] == 1
    assert counters["model_inits"] == 1
    assert counters["checkpoint_loads"] == 1
    assert counters["device_moves"] == 1
    assert counters["latent_calls"] == 1
    assert counters["inferences"] == 2
    assert counters["wav_saves"] == 2
    assert counters["set_num_threads"] == 1
    assert counters["set_num_interop_threads"] == 1
    assert counters["inference_mode_entries"] == 2
    assert saved_paths == [str(first_path), str(second_path)]
    assert first_path.exists()
    assert second_path.exists()
    assert first_path != second_path
    stage_names = [stage["name"] for stage in profiler.to_dict()["stages"]]
    assert stage_names.count("xtts.runtime_cache_miss") == 1
    assert stage_names.count("xtts.runtime_cache_hit") == 1
    assert stage_names.count("xtts.conditioning_latents") == 1
    assert stage_names.count("xtts.conditioning_latents_cache_hit") == 1
    assert stage_names.count("xtts.inference") == 2
    assert stage_names.count("xtts.wav_save") == 2
    assert stage_names.count("xtts.torch_runtime_config") == 1
    profile_payload = profiler.to_dict()
    assert profile_payload["context"]["xtts_torch_runtime"]["actual_num_threads"] == 3
    assert profile_payload["context"]["xtts_torch_runtime"]["actual_interop_threads"] == 2
    inference_stages = [stage for stage in profile_payload["stages"] if stage["name"] == "xtts.inference"]
    assert all(stage["metadata"]["inference_mode_enabled"] is True for stage in inference_stages)
    assert all(stage["metadata"]["effective_inference_kwargs"]["split_sentences"] is True for stage in inference_stages)


def test_xtts_provider_worker_cache_misses_when_reference_identity_changes(monkeypatch, tmp_path: Path):
    XTTSProvider.clear_worker_cache()
    tree = _write_stewie_selected_recipe_tree(tmp_path / "voice_models")
    monkeypatch.setattr(settings, "VOICE_MODELS_DIR", str(tree["root"]))
    monkeypatch.setattr(settings, "XTTS_DEVICE", "cpu")
    monkeypatch.setattr(settings, "XTTS_WORKER_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "XTTS_WORKER_CACHE_MAX_ENTRIES", 2)
    counters = {"config_loads": 0, "model_inits": 0, "checkpoint_loads": 0, "latent_calls": 0}

    class FakeConfig:
        def load_json(self, path):
            counters["config_loads"] += 1

    class FakeModel:
        def load_checkpoint(self, config, checkpoint_dir, eval):
            counters["checkpoint_loads"] += 1

        def to(self, device):
            return None

        def get_conditioning_latents(self, audio_path):
            counters["latent_calls"] += 1
            return "latent", "embedding"

        def inference(self, text, language, latent, embedding, **kwargs):
            return {"wav": [0.0] * 24000}

    class FakeXtts:
        @staticmethod
        def init_from_config(config):
            counters["model_inits"] += 1
            return FakeModel()

    class FakeTensor:
        def unsqueeze(self, axis):
            return self

    def fake_torchaudio_save(path, tensor, sample_rate):
        _write_sine_wav(Path(path), seconds=0.8, sample_rate=sample_rate)

    modules = {
        "TTS": types.ModuleType("TTS"),
        "TTS.tts": types.ModuleType("TTS.tts"),
        "TTS.tts.configs": types.ModuleType("TTS.tts.configs"),
        "TTS.tts.configs.xtts_config": types.ModuleType("TTS.tts.configs.xtts_config"),
        "TTS.tts.models": types.ModuleType("TTS.tts.models"),
        "TTS.tts.models.xtts": types.ModuleType("TTS.tts.models.xtts"),
        "torch": types.ModuleType("torch"),
        "torchaudio": types.ModuleType("torchaudio"),
    }
    modules["TTS.tts.configs.xtts_config"].XttsConfig = FakeConfig
    modules["TTS.tts.models.xtts"].Xtts = FakeXtts
    modules["torch"].tensor = lambda wav: FakeTensor()
    modules["torchaudio"].save = fake_torchaudio_save
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    provider = XTTSProvider()
    monkeypatch.setattr(provider, "healthcheck", lambda: {"available": True, "reason": None, "metadata": {"device": "cpu"}})
    profiler = RenderProfiler(job_id=7, project_id=2, output_kind="preview", rss_reader=lambda: 100)
    profile = {
        "id": "vp_stewie",
        "display_name": "Stewie Griffin",
        "provider": "xtts",
        "character_slug": "stewie_griffin",
    }

    provider.synthesize_line(text="First line.", voice_profile=profile, output_path=tmp_path / "first.wav", options={"profiler": profiler})
    _write_sine_wav(tree["clean_dir"] / "ref_a.wav", seconds=1.1, frequency=310)
    provider.synthesize_line(text="Second line.", voice_profile=profile, output_path=tmp_path / "second.wav", options={"profiler": profiler})

    assert counters["config_loads"] == 2
    assert counters["model_inits"] == 2
    assert counters["checkpoint_loads"] == 2
    assert counters["latent_calls"] == 2
    stage_names = [stage["name"] for stage in profiler.to_dict()["stages"]]
    assert stage_names.count("xtts.runtime_cache_miss") == 2
    assert "xtts.runtime_cache_hit" not in stage_names


def test_xtts_provider_torch_runtime_config_tolerates_unsupported_setters(monkeypatch):
    XTTSProvider.clear_worker_cache()
    monkeypatch.setattr(settings, "XTTS_TORCH_INFERENCE_MODE_ENABLED", True)
    monkeypatch.setattr(settings, "XTTS_CPU_NUM_THREADS", 4)
    monkeypatch.setattr(settings, "XTTS_CPU_INTEROP_THREADS", 2)
    fake_torch = types.SimpleNamespace(
        set_num_threads=lambda value: (_ for _ in ()).throw(RuntimeError("threads already initialized")),
        set_num_interop_threads=lambda value: (_ for _ in ()).throw(RuntimeError("interop already initialized")),
        get_num_threads=lambda: 8,
        get_num_interop_threads=lambda: 1,
    )
    profiler = RenderProfiler(job_id=8, project_id=2, output_kind="preview", rss_reader=lambda: 100)

    metadata = XTTSProvider()._configure_torch_runtime(fake_torch, profiler)

    assert metadata["requested_num_threads"] == 4
    assert metadata["requested_interop_threads"] == 2
    assert metadata["actual_num_threads"] == 8
    assert metadata["actual_interop_threads"] == 1
    assert "set_num_threads_error" in metadata
    assert "set_num_interop_threads_error" in metadata
    assert [stage["name"] for stage in profiler.to_dict()["stages"]] == ["xtts.torch_runtime_config"]


def test_xtts_preview_split_sentence_override_is_preview_only(monkeypatch, tmp_path: Path):
    XTTSProvider.clear_worker_cache()
    tree = _write_stewie_selected_recipe_tree(tmp_path / "voice_models")
    monkeypatch.setattr(settings, "VOICE_MODELS_DIR", str(tree["root"]))
    monkeypatch.setattr(settings, "XTTS_DEVICE", "cpu")
    monkeypatch.setattr(settings, "XTTS_WORKER_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "XTTS_WORKER_CACHE_MAX_ENTRIES", 2)
    monkeypatch.setattr(settings, "XTTS_PREVIEW_SPLIT_SENTENCES_OVERRIDE", "false")
    recorded_kwargs: list[dict[str, object]] = []

    class FakeConfig:
        def load_json(self, path):
            return None

    class FakeModel:
        def load_checkpoint(self, config, checkpoint_dir, eval):
            return None

        def to(self, device):
            return None

        def get_conditioning_latents(self, audio_path):
            return "latent", "embedding"

        def inference(self, text, language, latent, embedding, split_sentences=None, **kwargs):
            recorded_kwargs.append({"split_sentences": split_sentences, **kwargs})
            return {"wav": [0.0] * 24000}

    class FakeXtts:
        @staticmethod
        def init_from_config(config):
            return FakeModel()

    class FakeTensor:
        def unsqueeze(self, axis):
            return self

    def fake_torchaudio_save(path, tensor, sample_rate):
        _write_sine_wav(Path(path), seconds=0.8, sample_rate=sample_rate)

    modules = {
        "TTS": types.ModuleType("TTS"),
        "TTS.tts": types.ModuleType("TTS.tts"),
        "TTS.tts.configs": types.ModuleType("TTS.tts.configs"),
        "TTS.tts.configs.xtts_config": types.ModuleType("TTS.tts.configs.xtts_config"),
        "TTS.tts.models": types.ModuleType("TTS.tts.models"),
        "TTS.tts.models.xtts": types.ModuleType("TTS.tts.models.xtts"),
        "torch": types.ModuleType("torch"),
        "torchaudio": types.ModuleType("torchaudio"),
    }
    modules["TTS.tts.configs.xtts_config"].XttsConfig = FakeConfig
    modules["TTS.tts.models.xtts"].Xtts = FakeXtts
    modules["torch"].tensor = lambda wav: FakeTensor()
    modules["torchaudio"].save = fake_torchaudio_save
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    provider = XTTSProvider()
    monkeypatch.setattr(provider, "healthcheck", lambda: {"available": True, "reason": None, "metadata": {"device": "cpu"}})
    profile = {
        "id": "vp_stewie",
        "display_name": "Stewie Griffin",
        "provider": "xtts",
        "character_slug": "stewie_griffin",
    }

    provider.synthesize_line(
        text="Preview line.",
        voice_profile=profile,
        output_path=tmp_path / "preview.wav",
        options={"output_kind": "preview"},
    )
    provider.synthesize_line(
        text="Export line.",
        voice_profile=profile,
        output_path=tmp_path / "export.wav",
        options={"output_kind": "final"},
    )

    assert recorded_kwargs[0]["split_sentences"] is False
    assert recorded_kwargs[1]["split_sentences"] is True


def test_stewie_render_verification_requires_golden_preview(auth_client: TestClient, monkeypatch, tmp_path: Path):
    tree = _write_stewie_selected_recipe_tree(tmp_path / "voice_models")
    monkeypatch.setattr(settings, "VOICE_MODELS_DIR", str(tree["root"]))
    profile_response = auth_client.post(
        "/voice-profiles",
        json={
            "display_name": "Stewie Griffin",
            "provider": "xtts",
            "fallback_provider": "espeak",
            "voice": "en-gb+m3",
            "espeak_rate": 168,
            "espeak_pitch": 62,
            "espeak_word_gap": 1,
            "espeak_amplitude": 145,
            "character_slug": "stewie_griffin",
        },
    )
    assert profile_response.status_code == 201
    voice_profile_id = profile_response.json()["id"]
    segment_path = tmp_path / "segments" / "000_stewie.wav"
    composite_path = tmp_path / "audio" / "dialogue_composite.wav"
    final_audio_path = tmp_path / "audio" / "final_video_audio.wav"
    _write_sine_wav(segment_path, seconds=1.0, frequency=180.0)
    _write_sine_wav(composite_path, seconds=1.0, frequency=180.0)
    _write_sine_wav(final_audio_path, seconds=1.0, frequency=180.0)
    recipe = validate_selected_character_recipe("stewie_griffin").public_payload()
    db = SessionLocal()
    try:
        job = GenerationJob(
            project_id=1,
            input_asset_id=1,
            script_revision_id=1,
            style_preset="none",
            output_kind="preview",
            provider_name="local-compositor",
            status="completed",
            progress=100,
            tts_result_json={
                "status": "completed",
                "segments": [
                    {
                        "voice_profile_id": voice_profile_id,
                        "provider_used": "xtts",
                        "fallback_used": False,
                        "audio_path": str(segment_path),
                        "golden_preview_wav": str(tree["golden_preview"]),
                        "recipe_used": recipe,
                        "selected_recipe": recipe,
                        "voice_profile_settings": {"provider": "xtts", "selected_recipe": recipe},
                    }
                ],
                "assembly": {
                    "composite_audio_path": str(composite_path),
                    "final_video_audio_path": str(final_audio_path),
                },
            },
        )
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    verified = auth_client.post(f"/voice-profiles/{voice_profile_id}/verify-render/{job_id}")
    assert verified.status_code == 200
    body = verified.json()
    assert body["verification"]["status"] == "passed"
    assert body["verification"]["fallback_used"] is False
    assert body["verification"]["golden_preview_wav"] == str(tree["golden_preview"])
    assert body["verification"]["recipe_used"]["provider"] == "xtts"
    assert {item["kind"] for item in body["verification"]["audio_checks"]} >= {
        "golden_preview_wav",
        "render_segment_wav",
        "composite_audio_wav",
        "final_video_extracted_audio",
    }


def test_reference_audio_upload_rejects_unreadable_audio(auth_client: TestClient, monkeypatch):
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

    def fake_run(command, check, capture_output, text):
        raise subprocess.CalledProcessError(1, command, stderr="invalid data found when processing input")

    monkeypatch.setattr("app.services.voice_profiles._ffmpeg_binary", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr("app.services.voice_profiles.subprocess.run", fake_run)

    response = auth_client.post(
        "/voice-profiles/reference-audio",
        files={"file": ("broken.mp3", b"not-audio", "audio/mpeg")},
        data={
            "voice_profile_id": "vp_host_calm_v1",
            "authorization_confirmed": "true",
            "authorization_note": "owned",
        },
    )

    assert response.status_code == 400
    assert "could not be decoded or normalized" in response.json()["detail"]


def test_reference_audio_upload_only_trims_leading_silence(auth_client: TestClient, monkeypatch):
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
    recorded: dict[str, object] = {}

    monkeypatch.setattr("app.services.voice_profiles._ffmpeg_binary", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr("app.services.voice_profiles.subprocess.run", _fake_reference_audio_ffmpeg_run(recorded, seconds=2.3))

    response = auth_client.post(
        "/voice-profiles/reference-audio",
        files={"file": ("reference.mp3", b"fake-mp3", "audio/mpeg")},
        data={
            "voice_profile_id": "vp_host_calm_v1",
            "authorization_confirmed": "true",
            "authorization_note": "owned",
        },
    )

    assert response.status_code == 201
    command = next(command for command in recorded["commands"] if command[-1] != "-" and "-ss" not in command)
    assert "-af" in command
    silence_filter = command[command.index("-af") + 1]
    assert "start_periods=1" in silence_filter
    assert "stop_periods" not in silence_filter


def test_reference_audio_upload_processes_long_mp3_into_short_chunks(auth_client: TestClient, monkeypatch, caplog):
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
    recorded: dict[str, object] = {}
    caplog.set_level("INFO")

    monkeypatch.setattr("app.services.voice_profiles._ffmpeg_binary", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr("app.services.voice_profiles.subprocess.run", _fake_reference_audio_ffmpeg_run(recorded, seconds=480.0))

    response = auth_client.post(
        "/voice-profiles/reference-audio",
        files={"file": ("long-reference.mp3", b"fake-long-mp3", "audio/mpeg")},
        data={
            "voice_profile_id": "vp_host_calm_v1",
            "authorization_confirmed": "true",
            "authorization_note": "owned",
        },
    )

    assert response.status_code == 201
    metadata = response.json()["voice_profile"]["provider_metadata"]
    assert metadata["processed_reference_duration_seconds"] <= 60.0
    assert len(metadata["processed_reference_paths"]) == 6
    assert all(Path(path).exists() for path in metadata["processed_reference_paths"])
    assert all(duration <= 10.0 for duration in metadata["selected_chunk_durations"])
    assert metadata["last_reference_original_filename"] == "long-reference.mp3"
    assert any("voice.reference_audio.uploaded" in record.message for record in caplog.records)
    assert any("-ss" in command for command in recorded["commands"])


def test_reference_audio_upload_rejects_mostly_silent_audio(auth_client: TestClient, monkeypatch):
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
    silence_stderr = "\n".join(
        [
            "[silencedetect] silence_start: 0.1",
            "[silencedetect] silence_end: 3.9 | silence_duration: 3.8",
        ]
    )

    monkeypatch.setattr("app.services.voice_profiles._ffmpeg_binary", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        "app.services.voice_profiles.subprocess.run",
        _fake_reference_audio_ffmpeg_run(seconds=4.0, silence_stderr=silence_stderr),
    )

    response = auth_client.post(
        "/voice-profiles/reference-audio",
        files={"file": ("silent.mp3", b"fake-mp3", "audio/mpeg")},
        data={
            "voice_profile_id": "vp_host_calm_v1",
            "authorization_confirmed": "true",
            "authorization_note": "owned",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["validation"]["hard_failures"][0]["code"] == "too_much_silence"


def test_reference_audio_upload_rejects_clipped_audio(auth_client: TestClient, monkeypatch):
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

    def fake_run(command, check, capture_output, text):
        if command[-1] != "-":
            _write_wav(Path(command[-1]), seconds=2.0, sample=b"\xff\x7f")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("app.services.voice_profiles._ffmpeg_binary", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr("app.services.voice_profiles.subprocess.run", fake_run)

    response = auth_client.post(
        "/voice-profiles/reference-audio",
        files={"file": ("clipped.mp3", b"fake-mp3", "audio/mpeg")},
        data={
            "voice_profile_id": "vp_host_calm_v1",
            "authorization_confirmed": "true",
            "authorization_note": "owned",
        },
    )

    assert response.status_code == 400
    codes = [item["code"] for item in response.json()["detail"]["validation"]["hard_failures"]]
    assert "clipping_detected" in codes


def test_reference_audio_upload_accepts_soft_warning_metadata(auth_client: TestClient, monkeypatch):
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
    silence_stderr = "\n".join(
        [
            "[silencedetect] silence_start: 0.4",
            "[silencedetect] silence_end: 1.0 | silence_duration: 0.6",
            "[silencedetect] silence_start: 1.4",
            "[silencedetect] silence_end: 2.0 | silence_duration: 0.6",
            "[silencedetect] silence_start: 2.4",
            "[silencedetect] silence_end: 3.0 | silence_duration: 0.6",
            "[silencedetect] silence_start: 3.4",
        ]
    )

    monkeypatch.setattr("app.services.voice_profiles._ffmpeg_binary", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        "app.services.voice_profiles.subprocess.run",
        _fake_reference_audio_ffmpeg_run(seconds=4.0, silence_stderr=silence_stderr),
    )

    response = auth_client.post(
        "/voice-profiles/reference-audio",
        files={"file": ("warning.mp3", b"fake-mp3", "audio/mpeg")},
        data={
            "voice_profile_id": "vp_host_calm_v1",
            "authorization_confirmed": "true",
            "authorization_note": "owned",
        },
    )

    assert response.status_code == 201
    validation = response.json()["reference_audio"]["validation"]
    assert response.json()["reference_audio"]["validation_status"] == "warning"
    assert validation["warnings"][0]["code"] == "poor_speech_ratio"
    assert response.json()["voice_profile"]["provider_metadata"]["reference_validation_status"] == "warning"


def test_prepare_voice_profile_persists_embedding_metadata(auth_client: TestClient, monkeypatch):
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
    from app.models import VoiceReferenceAudio
    from app.services.voice_profiles import reference_audio_content_hash_from_paths

    reference_path = Path("test_storage") / "voice_lab" / "reference_audio" / "prepare_ref.wav"
    _write_wav(reference_path, sample=b"\x02\x00")
    reference_path_two = Path("test_storage") / "voice_lab" / "reference_audio" / "prepare_ref_two.wav"
    _write_wav(reference_path_two, sample=b"\x03\x00")
    reference_hash = reference_audio_content_hash_from_paths([reference_path, reference_path_two])
    artifact_path = Path("test_storage") / "voice_lab" / "embeddings" / f"vp_host_calm_v1_{reference_hash[:16]}.pth"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"embedding")
    db = SessionLocal()
    try:
        db.add(
            VoiceReferenceAudio(
                voice_profile_id="vp_host_calm_v1",
                storage_path=str(reference_path),
                mime_type="audio/wav",
                duration_ms=1600,
                sha256="raw-upload",
                authorization_confirmed=True,
                created_by_user_id=1,
            )
        )
        db.add(
            VoiceReferenceAudio(
                voice_profile_id="vp_host_calm_v1",
                storage_path=str(reference_path_two),
                mime_type="audio/wav",
                duration_ms=1600,
                sha256="raw-upload-two",
                authorization_confirmed=True,
                created_by_user_id=1,
            )
        )
        db.commit()
    finally:
        db.close()

    def fake_prepare_voice_profile(self, voice_profile, requested_provider=None):
        return {
            "provider_used": "openvoice",
            "provider_state": {"openvoice": {"available": True}},
            "prepared": True,
            "cached_artifact_path": str(artifact_path),
            "message": "prepared",
            "provider_metadata": {
                "embedding_status": "ready",
                "embedding_ready": True,
                "embedding_artifact_path": str(artifact_path),
                "reference_audio_sha256": reference_hash,
                "target_embedding_hash": "embedding-hash",
                "active_reference_count": 2,
                "reference_audio_mode": "average_all_clips",
            },
        }

    monkeypatch.setattr(TTSOrchestrator, "prepare_voice_profile", fake_prepare_voice_profile)

    response = auth_client.post("/voice-profiles/vp_host_calm_v1/prepare")

    assert response.status_code == 200
    assert response.json()["cached_artifact_path"] == str(artifact_path)
    listed = auth_client.get("/voice-profiles")
    profile = next(item for item in listed.json()["items"] if item["id"] == "vp_host_calm_v1")
    assert profile["embedding_path"] == str(artifact_path)
    assert profile["provider_metadata"]["embedding_status"] == "ready"
    assert profile["provider_metadata"]["active_reference_count"] == 2


def test_prepare_voice_profile_marks_failed_when_embedding_extraction_fails(auth_client: TestClient, monkeypatch):
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

    def fake_prepare_voice_profile(self, voice_profile, requested_provider=None):
        raise TextToSpeechError(
            code="reference_embedding_extraction_failed",
            message="OpenVoice could not extract a speaker embedding.",
            provider_state={"openvoice": {"available": True}},
        )

    monkeypatch.setattr(TTSOrchestrator, "prepare_voice_profile", fake_prepare_voice_profile)

    response = auth_client.post("/voice-profiles/vp_host_calm_v1/prepare")

    assert response.status_code == 503
    listed = auth_client.get("/voice-profiles")
    profile = next(item for item in listed.json()["items"] if item["id"] == "vp_host_calm_v1")
    assert profile["embedding_path"] is None
    assert profile["provider_metadata"]["embedding_status"] == "failed"
    assert profile["provider_metadata"]["last_error"]["code"] == "reference_embedding_extraction_failed"


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


def test_voice_profile_diagnostics_cli_payload_includes_reference_embedding_and_preview(auth_client: TestClient):
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
    from app.models import VoiceProfile, VoiceReferenceAudio
    from app.scripts.voice_profile_diagnostics import build_voice_profile_diagnostics

    reference_path = Path("test_storage") / "voice_lab" / "reference_audio" / "diag_ref.wav"
    chunk_path = Path("test_storage") / "voice_lab" / "reference_chunks" / "vp_host_calm_v1" / "diag_chunk.wav"
    embedding_path = Path("test_storage") / "voice_lab" / "embeddings" / "vp_host_calm_v1_diag.pth"
    preview_path = Path("test_storage") / "voice_lab" / "previews" / "diag_preview.wav"
    _write_wav(reference_path, sample=b"\x09\x00")
    _write_wav(chunk_path, seconds=3.0, sample=b"\x0a\x00")
    embedding_path.parent.mkdir(parents=True, exist_ok=True)
    embedding_path.write_bytes(b"embedding")
    _write_wav(preview_path, seconds=1.0)

    db = SessionLocal()
    try:
        reference = VoiceReferenceAudio(
            voice_profile_id="vp_host_calm_v1",
            storage_path=str(reference_path),
            mime_type="audio/wav",
            duration_ms=1600,
            sha256="raw-reference",
            authorization_confirmed=True,
            created_by_user_id=1,
        )
        db.add(reference)
        db.flush()
        profile = db.get(VoiceProfile, "vp_host_calm_v1")
        assert profile is not None
        profile.embedding_path = str(embedding_path)
        profile.provider_metadata_json = {
            "embedding_status": "ready",
            "embedding_artifact_path": str(embedding_path),
            "reference_audio_sha256": "processed-reference-hash",
            "target_embedding_hash": "target-embedding-hash",
            "processed_reference_audio": {
                str(reference.id): {
                    "normalized_reference_path": str(reference_path),
                    "chunks": [{"path": str(chunk_path), "duration_seconds": 3.0}],
                }
            },
        }
        db.add(
            VoicePreviewJob(
                user_id=1,
                preset_id="host_calm_v1",
                voice_profile_id="vp_host_calm_v1",
                requested_provider="openvoice",
                fallback_allowed=False,
                sample_text="Diagnostics.",
                status="completed",
                progress=100,
                stage="completed",
                provider_used="openvoice",
                fallback_used=False,
                preview_audio_path=str(preview_path),
            )
        )
        db.commit()
    finally:
        db.close()

    payload = build_voice_profile_diagnostics("vp_host_calm_v1")

    assert payload["voice_profile_id"] == "vp_host_calm_v1"
    assert payload["reference_audio_sha256"] == "processed-reference-hash"
    assert payload["processed_chunk_paths"] == [str(chunk_path)]
    assert payload["selected_chunk_durations"] == [3.0]
    assert payload["target_embedding_path"] == str(embedding_path)
    assert payload["target_embedding_hash"] == "target-embedding-hash"
    assert payload["last_preview_output_path"] == str(preview_path)
    assert payload["openvoice_conversion_applied"] is True


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


def test_tts_orchestrator_does_not_fallback_when_openvoice_selected_but_unavailable(tmp_path: Path):
    orchestrator = TTSOrchestrator(
        registry=StubRegistry(
            {
                "openvoice": StubProvider(response={"provider_used": "openvoice"}),
                "espeak": StubProvider(response={"provider_used": "espeak", "voice": "en-us+f3"}),
            },
            {
                "openvoice": {"available": False, "reason": "missing_models"},
                "espeak": {"available": True, "reason": None},
            },
        )
    )

    with pytest.raises(TextToSpeechError) as exc_info:
        orchestrator.synthesize_line(
            text="OpenVoice only.",
            voice_profile={
                "id": "vp_openvoice_selected",
                "display_name": "Host",
                "provider": "openvoice",
                "fallback_provider": "espeak",
                "voice": "en-us+f3",
                "reference_audios": [],
                "controls": {},
            },
            output_path=tmp_path / "render.wav",
            requested_provider="openvoice",
            fallback_allowed=False,
        )

    assert exc_info.value.attempted_providers == ["openvoice"]
    assert exc_info.value.provider_failures["openvoice"]["code"] == "missing_models"
    assert "espeak" not in exc_info.value.provider_failures


def test_tts_orchestrator_does_not_fallback_when_xtts_selected_but_unavailable(tmp_path: Path):
    orchestrator = TTSOrchestrator(
        registry=StubRegistry(
            {
                "xtts": StubProvider(response={"provider_used": "xtts"}),
                "espeak": StubProvider(response={"provider_used": "espeak", "voice": "en-us+f3"}),
            },
            {
                "xtts": {"available": False, "reason": "package_missing"},
                "espeak": {"available": True, "reason": None},
            },
        )
    )

    with pytest.raises(TextToSpeechError) as exc_info:
        orchestrator.synthesize_line(
            text="XTTS only.",
            voice_profile={
                "id": "vp_xtts_selected",
                "display_name": "Character XTTS",
                "provider": "xtts",
                "fallback_provider": "espeak",
                "voice": "en-us+f3",
                "reference_audios": [{"processed_storage_path": "authorized.wav"}],
                "controls": {},
            },
            output_path=tmp_path / "render.wav",
            requested_provider="xtts",
            fallback_allowed=False,
        )

    assert exc_info.value.attempted_providers == ["xtts"]
    assert exc_info.value.provider_failures["xtts"]["code"] == "package_missing"
    assert "espeak" not in exc_info.value.provider_failures


def test_tts_orchestrator_does_not_use_xtts_voice_cache_for_render_segments(monkeypatch, tmp_path: Path):
    orchestrator = TTSOrchestrator(
        registry=StubRegistry(
            {"xtts": StubProvider(response={"provider_used": "xtts", "voice": "XTTS Character"})},
            {"xtts": {"available": True, "reason": None}},
        )
    )

    monkeypatch.setattr(
        orchestrator,
        "_copy_cache_if_present",
        lambda *args, **kwargs: pytest.fail("XTTS render synthesis must not read the shared voice cache"),
    )
    monkeypatch.setattr(
        orchestrator,
        "_save_to_cache",
        lambda *args, **kwargs: pytest.fail("XTTS render synthesis must not write the shared voice cache"),
    )

    result = orchestrator.synthesize_line(
        text="This exact line must be synthesized fresh.",
        voice_profile={
            "id": "vp_xtts_no_cache",
            "display_name": "XTTS Character",
            "provider": "xtts",
            "fallback_provider": "espeak",
            "language": "en",
            "model_checkpoint_path": str(tmp_path / "xtts-model"),
            "reference_audios": [{"processed_storage_path": str(tmp_path / "reference.wav")}],
            "controls": {"speaking_rate": 1.0},
        },
        output_path=tmp_path / "render.wav",
        requested_provider="xtts",
        fallback_allowed=False,
    )

    assert result.provider_used == "xtts"
    assert result.fallback_used is False
    assert result.cache_hit is False


def test_tts_orchestrator_reuses_provider_health_snapshot_for_dialogue(tmp_path: Path):
    class CountingRegistry(StubRegistry):
        def __init__(self, providers, state):
            super().__init__(providers, state)
            self.healthcheck_calls = 0

        def healthcheck(self):
            self.healthcheck_calls += 1
            return super().healthcheck()

    registry = CountingRegistry(
        {"xtts": StubProvider(response={"provider_used": "xtts", "voice": "XTTS Character"})},
        {"xtts": {"available": True, "reason": None}},
    )
    orchestrator = TTSOrchestrator(registry=registry)
    profiler = RenderProfiler(job_id=9, project_id=2, output_kind="preview", rss_reader=lambda: 100)

    segments = orchestrator.synthesize_dialogue(
        lines=[
            {"speaker": "Guest", "text": "First line."},
            {"speaker": "Guest", "text": "Second line."},
        ],
        voice_profile_map={
            "Guest": {
                "id": "vp_xtts",
                "display_name": "XTTS Character",
                "provider": "xtts",
                "fallback_provider": "espeak",
                "fallback_allowed": False,
            }
        },
        output_dir=tmp_path,
        fallback_allowed=False,
        options={"profiler": profiler},
    )

    assert len(segments) == 2
    assert registry.healthcheck_calls == 1
    assert [stage["name"] for stage in profiler.to_dict()["stages"]].count("tts.provider_health_check") == 1


def test_openvoice_prepare_voice_profile_uses_all_reference_clips(monkeypatch, tmp_path: Path):
    provider = OpenVoiceProvider()
    ref_one = tmp_path / "ref_one.wav"
    ref_two = tmp_path / "ref_two.wav"
    _write_wav(ref_one)
    _write_wav(ref_two, sample=b"\x01\x00")
    converter_dir = tmp_path / "converter"
    converter_dir.mkdir(parents=True, exist_ok=True)
    recorded: dict[str, object] = {}
    expected_reference_hash = provider._reference_audio_hash([ref_one, ref_two])

    monkeypatch.setattr(settings, "OPENVOICE_CHECKPOINTS_DIR", str(tmp_path))
    monkeypatch.setattr(
        provider,
        "healthcheck",
        lambda: {"available": True, "reason": None, "metadata": {"device": "cpu"}},
    )
    monkeypatch.setattr(provider, "_import_runtime", lambda: (None, "se_extractor", "converter_cls", "torch_module"))
    monkeypatch.setattr(provider, "_get_converter", lambda converter_dir, device, converter_cls: object())

    def fake_get_target_embedding(reference_paths, converter, se_extractor, device, torch_module, artifact_path=None):
        recorded["reference_paths"] = [str(path) for path in reference_paths]
        recorded["artifact_path"] = str(artifact_path)
        return "embedding"

    monkeypatch.setattr(provider, "_get_target_embedding", fake_get_target_embedding)

    result = provider.prepare_voice_profile(
        {
            "id": "vp_test",
            "reference_audios": [
                {"storage_path": str(ref_one)},
                {"storage_path": str(ref_two)},
            ],
        }
    )

    assert recorded["reference_paths"] == [str(ref_one), str(ref_two)]
    assert str(recorded["artifact_path"]).endswith(f"vp_test_{expected_reference_hash[:16]}.pth")
    assert result["provider_metadata"]["reference_audio_sha256"] == expected_reference_hash
    assert result["provider_metadata"]["reference_audio_mode"] == "average_all_clips"


def test_openvoice_prepare_voice_profile_uses_processed_reference_chunks(monkeypatch, tmp_path: Path):
    provider = OpenVoiceProvider()
    normalized_ref = tmp_path / "long_reference.wav"
    chunk_one = tmp_path / "chunk_one.wav"
    chunk_two = tmp_path / "chunk_two.wav"
    _write_wav(normalized_ref, seconds=120.0, sample=b"\x01\x00")
    _write_wav(chunk_one, seconds=10.0, sample=b"\x02\x00")
    _write_wav(chunk_two, seconds=10.0, sample=b"\x03\x00")
    converter_dir = tmp_path / "converter"
    converter_dir.mkdir(parents=True, exist_ok=True)
    recorded: dict[str, object] = {}
    expected_reference_hash = provider._reference_audio_hash([chunk_one, chunk_two])

    monkeypatch.setattr(settings, "OPENVOICE_CHECKPOINTS_DIR", str(tmp_path))
    monkeypatch.setattr(
        provider,
        "healthcheck",
        lambda: {"available": True, "reason": None, "metadata": {"device": "cpu"}},
    )
    monkeypatch.setattr(provider, "_import_runtime", lambda: (None, "se_extractor", "converter_cls", "torch_module"))
    monkeypatch.setattr(provider, "_get_converter", lambda converter_dir, device, converter_cls: object())

    def fake_get_target_embedding(reference_paths, converter, se_extractor, device, torch_module, artifact_path=None):
        recorded["reference_paths"] = [str(path) for path in reference_paths]
        recorded["artifact_path"] = str(artifact_path)
        return "embedding"

    monkeypatch.setattr(provider, "_get_target_embedding", fake_get_target_embedding)

    result = provider.prepare_voice_profile(
        {
            "id": "vp_test",
            "reference_audios": [{"id": 42, "storage_path": str(normalized_ref)}],
            "provider_metadata": {
                "processed_reference_audio_ids": [42],
                "processed_reference_paths": [str(chunk_one), str(chunk_two)],
            },
        }
    )

    assert recorded["reference_paths"] == [str(chunk_one), str(chunk_two)]
    assert str(recorded["artifact_path"]).endswith(f"vp_test_{expected_reference_hash[:16]}.pth")
    assert result["provider_metadata"]["reference_audio_sha256"] == expected_reference_hash


def test_openvoice_prepare_voice_profile_prefers_processed_reference_path(monkeypatch, tmp_path: Path):
    provider = OpenVoiceProvider()
    original_ref = tmp_path / "original_upload.mp3"
    processed_ref = tmp_path / "processed_reference.wav"
    original_ref.write_bytes(b"not-used")
    _write_wav(processed_ref, seconds=2.0, sample=b"\x04\x00")
    converter_dir = tmp_path / "converter"
    converter_dir.mkdir(parents=True, exist_ok=True)
    recorded: dict[str, object] = {}
    expected_reference_hash = provider._reference_audio_hash([processed_ref])

    monkeypatch.setattr(settings, "OPENVOICE_CHECKPOINTS_DIR", str(tmp_path))
    monkeypatch.setattr(
        provider,
        "healthcheck",
        lambda: {"available": True, "reason": None, "metadata": {"device": "cpu"}},
    )
    monkeypatch.setattr(provider, "_import_runtime", lambda: (None, "se_extractor", "converter_cls", "torch_module"))
    monkeypatch.setattr(provider, "_get_converter", lambda converter_dir, device, converter_cls: object())

    def fake_get_target_embedding(reference_paths, converter, se_extractor, device, torch_module, artifact_path=None):
        recorded["reference_paths"] = [str(path) for path in reference_paths]
        return "embedding"

    monkeypatch.setattr(provider, "_get_target_embedding", fake_get_target_embedding)

    result = provider.prepare_voice_profile(
        {
            "id": "vp_test",
            "reference_audios": [
                {
                    "storage_path": str(original_ref),
                    "processed_storage_path": str(processed_ref),
                }
            ],
        }
    )

    assert recorded["reference_paths"] == [str(processed_ref)]
    assert result["provider_metadata"]["reference_audio_sha256"] == expected_reference_hash


def test_openvoice_reference_content_hash_changes_embedding_artifact_path(tmp_path: Path):
    provider = OpenVoiceProvider()
    ref_one = tmp_path / "ref_one.wav"
    ref_two = tmp_path / "ref_two.wav"
    _write_wav(ref_one, sample=b"\x00\x00")
    _write_wav(ref_two, sample=b"\x04\x00")

    hash_one = provider._reference_audio_hash([ref_one])
    hash_two = provider._reference_audio_hash([ref_two])
    artifact_one = provider._embedding_artifact_path({"id": "vp_test"}, hash_one)
    artifact_two = provider._embedding_artifact_path({"id": "vp_test"}, hash_two)

    assert hash_one != hash_two
    assert artifact_one != artifact_two
    assert artifact_one.name == f"vp_test_{hash_one[:16]}.pth"
    assert artifact_two.name == f"vp_test_{hash_two[:16]}.pth"


def test_openvoice_unchanged_reference_reuses_cached_embedding_artifact(monkeypatch, tmp_path: Path):
    provider = OpenVoiceProvider()
    reference_path = tmp_path / "reference.wav"
    _write_wav(reference_path, sample=b"\x08\x00")
    reference_hash = provider._reference_audio_hash([reference_path])
    artifact_path = provider._embedding_artifact_path({"id": "vp_test"}, reference_hash)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"cached")
    recorded: dict[str, object] = {}

    def fake_load_cached_target_embedding(path, device, torch_module):
        recorded["path"] = str(path)
        return "cached-target"

    def fail_extract(*args, **kwargs):
        raise AssertionError("unchanged references should reuse the cached embedding artifact")

    monkeypatch.setattr(provider, "_load_cached_target_embedding", fake_load_cached_target_embedding)
    monkeypatch.setattr(provider, "_extract_reference_embedding", fail_extract)

    result = provider._get_target_embedding(
        [reference_path],
        converter=object(),
        se_extractor=object(),
        device="cpu",
        torch_module=object(),
        artifact_path=artifact_path,
    )

    assert result == "cached-target"
    assert recorded["path"] == str(artifact_path)


def test_openvoice_extract_reference_embedding_disables_vad(monkeypatch, tmp_path: Path):
    provider = OpenVoiceProvider()
    reference_path = tmp_path / "reference.wav"
    _write_wav(reference_path, sample=b"\x06\x00")
    recorded: dict[str, object] = {}

    class FakeSeExtractor:
        def get_se(self, path, converter, vad):
            recorded["path"] = path
            recorded["vad"] = vad
            return "target-embedding", None

    result = provider._extract_reference_embedding(reference_path, object(), FakeSeExtractor(), "cpu")

    assert result == "target-embedding"
    assert recorded == {"path": str(reference_path), "vad": False}


def test_openvoice_extract_reference_embedding_fails_closed(monkeypatch, tmp_path: Path):
    provider = OpenVoiceProvider()
    reference_path = tmp_path / "reference.wav"
    _write_wav(reference_path, sample=b"\x07\x00")
    monkeypatch.setattr(
        provider,
        "healthcheck",
        lambda: {"available": True, "reason": None, "metadata": {"device": "cpu"}},
    )

    class FailingSeExtractor:
        def get_se(self, path, converter, vad):
            raise RuntimeError("bad reference")

    with pytest.raises(TextToSpeechError) as exc_info:
        provider._extract_reference_embedding(reference_path, object(), FailingSeExtractor(), "cpu")

    assert exc_info.value.code == "reference_embedding_extraction_failed"
    assert "generic" not in exc_info.value.message.lower()


def test_openvoice_synthesize_line_passes_selected_profile_target_embedding(monkeypatch, tmp_path: Path):
    provider = OpenVoiceProvider()
    reference_path = tmp_path / "selected_reference.wav"
    _write_wav(reference_path, sample=b"\x05\x00")
    converter_dir = tmp_path / "converter"
    converter_dir.mkdir(parents=True)
    base_speaker_path = tmp_path / "base_speakers" / "ses" / "en-default.pth"
    base_speaker_path.parent.mkdir(parents=True)
    base_speaker_path.write_bytes(b"source")
    selected_target = "selected-profile-target"
    source_embedding = "base-source"
    recorded: dict[str, object] = {}

    class FakeModel:
        hps = type("Hps", (), {"data": type("Data", (), {"spk2id": {"EN-Default": 0}})()})()

        def tts_to_file(self, text, speaker_id, output_path, speed):
            _write_wav(Path(output_path), seconds=1.0)

    class FakeConverter:
        def convert(self, audio_src_path, src_se, tgt_se, output_path, message):
            recorded["audio_src_path"] = audio_src_path
            recorded["src_se"] = src_se
            recorded["tgt_se"] = tgt_se
            recorded["output_path"] = output_path
            _write_wav(Path(output_path), seconds=1.0)

    fake_converter = FakeConverter()
    monkeypatch.setattr(settings, "OPENVOICE_CHECKPOINTS_DIR", str(tmp_path))
    monkeypatch.setattr(
        provider,
        "healthcheck",
        lambda: {"available": True, "reason": None, "metadata": {"device": "cpu"}},
    )
    monkeypatch.setattr(provider, "_import_runtime", lambda: (object, object(), object, object()))
    monkeypatch.setattr(provider, "_get_melo_model", lambda language_code, device, tts_cls: FakeModel())
    monkeypatch.setattr(provider, "_get_converter", lambda converter_dir, device, converter_cls: fake_converter)
    monkeypatch.setattr(provider, "_get_target_embedding", lambda reference_paths, converter, se_extractor, device, torch_module, artifact_path=None: selected_target)
    monkeypatch.setattr(provider, "_get_source_embedding", lambda base_speaker_path, device, torch_module: source_embedding)

    voice_profile = {
        "id": "vp_selected",
        "display_name": "Selected",
        "provider": "openvoice",
        "language": "en",
        "reference_audios": [{"storage_path": str(reference_path)}],
        "controls": {"speaking_rate": 0.9, "emotion": "warm", "pitch": 12, "energy": 1.3},
        "style": {"base_speaker": "EN-Default"},
        "provider_metadata": {},
    }

    result = provider.synthesize_line(
        text="Use the selected profile.",
        voice_profile=voice_profile,
        output_path=tmp_path / "preview.wav",
        options={},
    )

    reference_hash = provider._reference_audio_hash([reference_path])
    assert result["provider_used"] == "openvoice"
    assert result["audio_path"] == str(tmp_path / "preview.wav")
    assert recorded["audio_src_path"] != result["audio_path"]
    assert recorded["src_se"] == source_embedding
    assert recorded["tgt_se"] == selected_target
    assert voice_profile["embedding_path"].endswith(f"vp_selected_{reference_hash[:16]}.pth")
    assert voice_profile["provider_metadata"]["reference_audio_sha256"] == reference_hash
    assert voice_profile["provider_metadata"]["base_speaker"] == "en-default"
    assert result["controls_applied"] == {"speaking_rate": 0.9}


def test_openvoice_synthesize_line_fails_when_source_embedding_missing(monkeypatch, tmp_path: Path):
    provider = OpenVoiceProvider()
    reference_path = tmp_path / "reference.wav"
    _write_wav(reference_path)
    (tmp_path / "converter").mkdir(parents=True)

    monkeypatch.setattr(settings, "OPENVOICE_CHECKPOINTS_DIR", str(tmp_path))
    monkeypatch.setattr(
        provider,
        "healthcheck",
        lambda: {"available": True, "reason": None, "metadata": {"device": "cpu"}},
    )
    monkeypatch.setattr(provider, "_import_runtime", lambda: (object, object(), object, object()))

    with pytest.raises(TextToSpeechError) as exc_info:
        provider.synthesize_line(
            text="No source fallback.",
            voice_profile={
                "id": "vp_selected",
                "display_name": "Selected",
                "provider": "openvoice",
                "language": "en",
                "reference_audios": [{"storage_path": str(reference_path)}],
                "controls": {},
            },
            output_path=tmp_path / "preview.wav",
            options={},
        )

    assert exc_info.value.code == "openvoice_source_embedding_missing"


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


def test_local_speech_service_prefers_generation_voice_manifest(monkeypatch, tmp_path: Path):
    manifest = {
        "version": 1,
        "speakers": {
            "Host": {
                "speaker": "Host",
                "voice_profile_id": "vp_openvoice_host",
                "provider": "openvoice",
                "requested_provider": "openvoice",
                "fallback_allowed": False,
                "voice_profile": {
                    "id": "vp_openvoice_host",
                    "display_name": "Host Clone",
                    "provider": "openvoice",
                    "fallback_provider": "espeak",
                    "voice": "en-us+f3",
                    "reference_audios": [{"id": 1, "storage_path": "authorized.wav", "sha256": "abc"}],
                    "controls": {},
                    "requested_provider": "openvoice",
                    "fallback_allowed": False,
                },
            }
        },
    }
    service = LocalSpeechService(voice_manifest=manifest)
    captured: dict[str, object] = {}

    def fake_synthesize_line(*, text, voice_profile, output_path, requested_provider=None, fallback_allowed=True, options=None):
        captured["voice_profile"] = dict(voice_profile)
        captured["requested_provider"] = requested_provider
        captured["fallback_allowed"] = fallback_allowed
        _write_wav(output_path, seconds=0.8)
        return type(
            "Result",
            (),
            {
                "audio_path": str(output_path),
                "voice": "Host Clone",
                "duration_seconds": 0.8,
                "provider_used": "openvoice",
                "fallback_used": False,
                "controls_applied": {},
                "reference_audio_count": 1,
                "provider_state": {"openvoice": {"available": True}},
                "cache_hit": False,
                "voice_profile_id": "vp_openvoice_host",
            },
        )()

    monkeypatch.setattr(service.orchestrator, "synthesize_line", fake_synthesize_line)

    segments = service.synthesize_dialogue(
        [{"speaker": "Host", "text": "Use the selected clone.", "order": 0}],
        tmp_path,
    )

    assert captured["requested_provider"] == "openvoice"
    assert captured["fallback_allowed"] is False
    assert captured["voice_profile"]["id"] == "vp_openvoice_host"
    assert segments[0].provider_used == "openvoice"
    assert segments[0].fallback_used is False


def test_project_render_service_does_not_overlay_fallback_for_tts_errors(monkeypatch):
    service = ProjectRenderService()

    def fail_tts(**kwargs):
        raise TextToSpeechError(
            code="openvoice_missing_models",
            message="OpenVoice is unavailable.",
            provider_state={"openvoice": {"available": False, "reason": "missing_models"}},
        )

    monkeypatch.setattr(service, "_render_speaker_video", fail_tts)
    monkeypatch.setattr(
        service.video_service,
        "generate_video",
        lambda **kwargs: pytest.fail("overlay fallback should not be used for TTS errors"),
    )

    with pytest.raises(TextToSpeechError):
        service.render_preview(
            project_id=1,
            background_video_path="missing.mp4",
            parsed_lines=[{"speaker": "Host", "text": "Hello"}],
            style_preset="none",
            voice_manifest={"speakers": {}},
        )


def test_render_timing_prefers_actual_audio_clip_duration(monkeypatch):
    service = ProjectRenderService()
    segment_path = generated_job_segment_dir(76) / "000_stewie.wav"
    _write_wav(segment_path, seconds=1.8)
    segments = [
        SpeechSegment(
            speaker="Stewie",
            text="Longer than the metadata says.",
            voice="en-us+f3",
            slot_index=0,
            audio_path=str(segment_path),
            duration_seconds=1.0,
        )
    ]

    timed_segments = service._build_timed_segments(segments)

    assert timed_segments[0]["duration_seconds"] == 1.8


def test_render_speech_output_dir_uses_persisted_job_artifact_storage(tmp_path: Path):
    service = ProjectRenderService()
    speech_dir = service._speech_output_dir(42, tmp_path)

    assert speech_dir == generated_job_segment_dir(42)
    assert speech_dir.exists()
    assert str(speech_dir).endswith("generated/42/segments")


def test_render_audio_assembly_uses_segment_audio_paths(monkeypatch):
    service = ProjectRenderService()
    segment_path = generated_job_segment_dir(77) / "000_host.wav"
    _write_wav(segment_path, seconds=1.1)
    captured: dict[str, str] = {}
    segments = [
        SpeechSegment(
            speaker="Host",
            text="Persisted render segment.",
            voice="Host",
            slot_index=0,
            audio_path=str(segment_path),
            duration_seconds=1.1,
            voice_profile_id="vp_host",
            provider_used="openvoice",
            fallback_used=False,
        )
    ]

    def fake_run(command, check, capture_output, text):
        composite_audio_path = Path(command[-1])
        concat_list_path = composite_audio_path.parent / "dialogue_segments.txt"
        captured["concat_list"] = concat_list_path.read_text(encoding="utf-8")
        captured["command"] = " ".join(command)
        captured["output_path"] = command[-1]
        _write_wav(composite_audio_path, seconds=1.1)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("app.services.rendering.subprocess.run", fake_run)
    timed_segments = service._build_timed_segments(segments)
    composite_audio = service._build_composite_audio_track(
        timed_segments=timed_segments,
        job_id=77,
        project_id=1,
        work_dir=Path("unused"),
    )

    assert str(segment_path.resolve()) in captured["concat_list"]
    assert str(segment_path.resolve()) in captured["command"]
    assert timed_segments[0]["segment"].audio_path == str(segment_path)
    assert composite_audio == generated_job_segment_dir(77).parent / "audio" / "dialogue_composite.wav"
    assert captured["output_path"] == str(composite_audio)


def test_render_preview_final_mp4_uses_persisted_segment_wavs(monkeypatch, tmp_path: Path):
    service = ProjectRenderService()
    job_id = 90
    segment_dir = generated_job_segment_dir(job_id)
    host_segment = segment_dir / "000_host_openvoice.wav"
    guest_segment = segment_dir / "001_guest_openvoice.wav"
    _write_wav(host_segment, seconds=0.8)
    _write_wav(guest_segment, seconds=1.0)
    background_path = tmp_path / "background.mp4"
    background_path.write_bytes(b"fake-video")
    portrait_path = tmp_path / "portrait.png"
    caption_path = tmp_path / "caption.png"
    portrait_path.write_bytes(b"fake-portrait")
    caption_path.write_bytes(b"fake-caption")
    captured: dict[str, str] = {}

    def fake_synthesize_dialogue(self, parsed_lines, work_dir):
        assert work_dir == segment_dir
        return [
            SpeechSegment(
                speaker="Host",
                text=parsed_lines[0]["text"],
                voice="Host Clone",
                slot_index=0,
                audio_path=str(host_segment),
                duration_seconds=0.8,
                voice_profile_id="vp_host_openvoice",
                provider_used="openvoice",
                fallback_used=False,
            ),
            SpeechSegment(
                speaker="Guest",
                text=parsed_lines[1]["text"],
                voice="Guest Clone",
                slot_index=1,
                audio_path=str(guest_segment),
                duration_seconds=1.0,
                voice_profile_id="vp_guest_openvoice",
                provider_used="openvoice",
                fallback_used=False,
            ),
        ]

    def fake_run(command, check, capture_output, text):
        output_audio_path = Path(command[-1])
        if "-filter_complex" in command:
            concat_list_path = output_audio_path.parent / "dialogue_segments.txt"
            captured["concat_list"] = concat_list_path.read_text(encoding="utf-8")
            captured["command"] = " ".join(command)
            captured["composite_audio_path"] = command[-1]
        else:
            captured["final_video_audio_path"] = command[-1]
        _write_wav(output_audio_path, seconds=1.8)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    class FakeVideoClip:
        w = 1080
        h = 1920
        duration = 8.0
        fps = 24

        def __init__(self, path=None):
            captured["background_path"] = str(path)

        def without_audio(self):
            return self

        def resized(self, new_size=None, height=None):
            return self

        def cropped(self, **kwargs):
            return self

        def subclipped(self, start, end):
            captured["background_duration"] = str(end - start)
            return self

        def close(self):
            return None

    class FakeImageClip:
        def __init__(self, path):
            self.path = path

        def resized(self, height=None, new_size=None):
            return self

        def with_opacity(self, opacity):
            return self

        def with_position(self, position):
            return self

        def with_duration(self, duration):
            return self

        def with_start(self, start):
            return self

        def close(self):
            return None

    class FakeAudioFileClip:
        def __init__(self, path):
            self.path = str(path)
            captured["audio_file_clip_path"] = self.path
            self.duration = 1.8

        def close(self):
            return None

    class FakeCompositeVideoClip:
        def __init__(self, layers, size):
            self.layers = layers
            self.size = size
            self.duration = 0

        def with_audio(self, audio_clip):
            captured["final_audio_path"] = audio_clip.path
            return self

        def with_duration(self, duration):
            self.duration = duration
            return self

        def write_videofile(self, path, **kwargs):
            captured["final_mp4_path"] = str(path)
            captured["temp_audiofile"] = kwargs["temp_audiofile"]
            Path(path).write_bytes(b"mp4")

        def close(self):
            return None

    fake_moviepy = types.ModuleType("moviepy")
    fake_moviepy.AudioFileClip = FakeAudioFileClip
    fake_moviepy.CompositeVideoClip = FakeCompositeVideoClip
    fake_moviepy.ImageClip = FakeImageClip
    fake_moviepy.VideoFileClip = FakeVideoClip
    fake_moviepy.concatenate_videoclips = lambda clips: clips[0]

    monkeypatch.setitem(sys.modules, "moviepy", fake_moviepy)
    monkeypatch.setattr(LocalSpeechService, "synthesize_dialogue", fake_synthesize_dialogue)
    monkeypatch.setattr("app.services.rendering.subprocess.run", fake_run)
    monkeypatch.setattr(service, "_resolve_character_portrait", lambda speaker, slot_index, work_dir: portrait_path)
    monkeypatch.setattr(service, "_build_dialogue_card", lambda segment, work_dir: caption_path)

    result = service.render_preview(
        project_id=1,
        background_video_path=str(background_path),
        parsed_lines=[
            {"speaker": "Host", "text": "The render segment is correct."},
            {"speaker": "Guest", "text": "The final video must use it."},
        ],
        style_preset="none",
        output_kind="preview",
        voice_manifest={"speakers": {}},
        job_id=job_id,
    )

    assert str(host_segment.resolve()) in captured["concat_list"]
    assert str(guest_segment.resolve()) in captured["concat_list"]
    assert str(host_segment.resolve()) in captured["command"]
    assert str(guest_segment.resolve()) in captured["command"]
    assert captured["audio_file_clip_path"] == captured["composite_audio_path"]
    assert captured["final_audio_path"] == captured["composite_audio_path"]
    tts_result = result["metadata"]["tts_result"]
    assert tts_result["assembly"]["composite_audio_path"] == captured["composite_audio_path"]
    assert tts_result["assembly"]["final_mp4_path"] == captured["final_mp4_path"]
    assert tts_result["assembly"]["final_video_audio_path"] == captured["final_video_audio_path"]
    assert tts_result["assembly"]["final_video_audio_artifact_url"].endswith("/audio/final_video_audio.wav")
    assert tts_result["render_profile"]["artifact_url"].endswith("/generation_profile.json")
    assert result["metadata"]["render_profile_artifact_url"].endswith("/generation_profile.json")
    profile_path = generated_job_segment_dir(job_id).parent / "generation_profile.json"
    profile_payload = json.loads(profile_path.read_text(encoding="utf-8"))
    stage_names = [stage["name"] for stage in profile_payload["stages"]]
    assert "render.full_generation_path" in stage_names
    assert "ffmpeg.composite_audio_build" in stage_names
    assert "moviepy.ffmpeg_encode_and_mp4_write" in stage_names
    assert profile_payload["context"]["segment_count"] == 2
    assert profile_payload["context"]["resolution"] == {"width": 1080, "height": 1920}
    assert profile_payload["context"]["ffmpeg_threads"] >= 1
    assert tts_result["segments"][0]["audio_path"] == str(host_segment)
    assert tts_result["segments"][0]["audio_path_used_for_final_assembly"] == str(host_segment)
    assert tts_result["segments"][0]["provider_used"] == "openvoice"
    assert tts_result["segments"][0]["fallback_used"] is False
    assert tts_result["segments"][1]["audio_path_used_for_final_assembly"] == str(guest_segment)


def test_xtts_render_job_synthesizes_exact_script_segments_to_persisted_wavs(monkeypatch, tmp_path: Path):
    service = ProjectRenderService()
    job_id = 91
    segment_dir = generated_job_segment_dir(job_id)
    background_path = tmp_path / "background.mp4"
    portrait_path = tmp_path / "portrait.png"
    caption_path = tmp_path / "caption.png"
    background_path.write_bytes(b"fake-video")
    portrait_path.write_bytes(b"fake-portrait")
    caption_path.write_bytes(b"fake-caption")
    parsed_lines = [
        {"speaker": "Stewie", "text": "Victory shall be mine.", "order": 0},
        {"speaker": "Brian", "text": "Let's verify the second line.", "order": 1},
        {"speaker": "Stewie", "text": "And now the third exact line.", "order": 2},
    ]
    voice_manifest = {
        "version": 1,
        "speakers": {
            "Stewie": {
                "speaker": "Stewie",
                "requested_provider": "xtts",
                "fallback_allowed": False,
                "voice_profile_id": "vp_stewie_xtts",
                "character_display_name": "Stewie Griffin",
                "voice_profile": {
                    "id": "vp_stewie_xtts",
                    "display_name": "Stewie Griffin",
                    "provider": "xtts",
                    "fallback_provider": "espeak",
                    "language": "en",
                    "character_slug": "stewie_griffin",
                    "reference_audios": [{"id": 1, "processed_storage_path": "stewie_ref.wav"}],
                    "provider_metadata": {},
                    "controls": {"speaking_rate": 1.0},
                    "style": {},
                    "selected_recipe": {"provider": "xtts", "language": "en"},
                    "fallback_allowed": False,
                },
            },
            "Brian": {
                "speaker": "Brian",
                "requested_provider": "xtts",
                "fallback_allowed": False,
                "voice_profile_id": "vp_brian_xtts",
                "character_display_name": "Brian Griffin",
                "voice_profile": {
                    "id": "vp_brian_xtts",
                    "display_name": "Brian Griffin",
                    "provider": "xtts",
                    "fallback_provider": "espeak",
                    "language": "en",
                    "reference_audios": [{"id": 2, "processed_storage_path": "brian_ref.wav"}],
                    "provider_metadata": {},
                    "controls": {"speaking_rate": 0.95},
                    "style": {},
                    "fallback_allowed": False,
                },
            },
        },
    }
    captured: dict[str, object] = {"synthesis_calls": []}

    def fake_synthesize_line(self, *, text, voice_profile, output_path, requested_provider=None, fallback_allowed=True, options=None):
        assert output_path.parent == segment_dir
        assert requested_provider == "xtts"
        assert fallback_allowed is False
        assert voice_profile["provider"] == "xtts"
        call_index = len(captured["synthesis_calls"])
        seconds = 0.7 + (call_index * 0.1)
        _write_wav(output_path, seconds=seconds)
        captured["synthesis_calls"].append(
            {
                "text": text,
                "voice_profile_id": voice_profile["id"],
                "output_path": str(output_path),
                "seconds": seconds,
            }
        )
        return type(
            "Result",
            (),
            {
                "audio_path": str(output_path),
                "voice": voice_profile["display_name"],
                "duration_seconds": seconds,
                "provider_used": "xtts",
                "fallback_used": False,
                "controls_applied": dict(voice_profile.get("controls") or {}),
                "reference_audio_count": len(voice_profile.get("reference_audios") or []),
                "provider_state": {"xtts": {"available": True, "reason": None}},
                "cache_hit": False,
                "voice_profile_id": voice_profile["id"],
                "provider_failures": {},
                "fallback_reason": None,
                "recipe_used": dict(voice_profile.get("selected_recipe") or {}),
                "golden_preview_wav": None,
            },
        )()

    def fake_run(command, check, capture_output, text):
        output_audio_path = Path(command[-1])
        if "-filter_complex" in command:
            audio_inputs = [Path(command[index + 1]).resolve() for index, item in enumerate(command) if item == "-i"]
            concat_list_path = output_audio_path.parent / "dialogue_segments.txt"
            captured["concat_list"] = concat_list_path.read_text(encoding="utf-8")
            captured["audio_inputs"] = audio_inputs
            captured["composite_audio_path"] = command[-1]
        else:
            captured["final_video_audio_path"] = command[-1]
        _write_wav(output_audio_path, seconds=2.4)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    class FakeVideoClip:
        w = 1080
        h = 1920
        duration = 8.0
        fps = 24

        def __init__(self, path=None):
            captured["background_path"] = str(path)

        def without_audio(self):
            return self

        def resized(self, new_size=None, height=None):
            return self

        def cropped(self, **kwargs):
            return self

        def subclipped(self, start, end):
            captured["background_duration"] = end - start
            return self

        def close(self):
            return None

    class FakeImageClip:
        def __init__(self, path):
            self.path = path

        def resized(self, height=None, new_size=None):
            return self

        def with_opacity(self, opacity):
            return self

        def with_position(self, position):
            return self

        def with_duration(self, duration):
            return self

        def with_start(self, start):
            return self

        def close(self):
            return None

    class FakeAudioFileClip:
        def __init__(self, path):
            self.path = str(path)
            captured["audio_file_clip_path"] = self.path
            self.duration = 2.4

        def close(self):
            return None

    class FakeCompositeVideoClip:
        def __init__(self, layers, size):
            self.layers = layers
            self.size = size
            self.duration = 0

        def with_audio(self, audio_clip):
            captured["final_audio_path"] = audio_clip.path
            return self

        def with_duration(self, duration):
            self.duration = duration
            return self

        def write_videofile(self, path, **kwargs):
            captured["final_mp4_path"] = str(path)
            Path(path).write_bytes(b"mp4")

        def close(self):
            return None

    fake_moviepy = types.ModuleType("moviepy")
    fake_moviepy.AudioFileClip = FakeAudioFileClip
    fake_moviepy.CompositeVideoClip = FakeCompositeVideoClip
    fake_moviepy.ImageClip = FakeImageClip
    fake_moviepy.VideoFileClip = FakeVideoClip
    fake_moviepy.concatenate_videoclips = lambda clips: clips[0]

    monkeypatch.setitem(sys.modules, "moviepy", fake_moviepy)
    monkeypatch.setattr(TTSOrchestrator, "synthesize_line", fake_synthesize_line)
    monkeypatch.setattr("app.services.rendering.subprocess.run", fake_run)
    monkeypatch.setattr(service, "_resolve_character_portrait", lambda speaker, slot_index, work_dir: portrait_path)
    monkeypatch.setattr(service, "_build_dialogue_card", lambda segment, work_dir: caption_path)

    result = service.render_preview(
        project_id=1,
        background_video_path=str(background_path),
        parsed_lines=parsed_lines,
        style_preset="none",
        output_kind="preview",
        voice_manifest=voice_manifest,
        job_id=job_id,
    )

    synthesis_calls = captured["synthesis_calls"]
    assert [call["text"] for call in synthesis_calls] == [line["text"] for line in parsed_lines]
    segment_paths = [Path(call["output_path"]) for call in synthesis_calls]
    assert len(segment_paths) == len(parsed_lines)
    assert all(path.parent == segment_dir for path in segment_paths)
    assert all(path.exists() for path in segment_paths)
    assert captured["audio_inputs"] == [path.resolve() for path in segment_paths]
    assert captured["audio_file_clip_path"] == captured["composite_audio_path"]
    assert captured["final_audio_path"] == captured["composite_audio_path"]

    tts_result = result["metadata"]["tts_result"]
    assert tts_result["status"] == "completed"
    assert [segment["text"] for segment in tts_result["segments"]] == [line["text"] for line in parsed_lines]
    assert [segment["provider_used"] for segment in tts_result["segments"]] == ["xtts", "xtts", "xtts"]
    assert [segment["fallback_used"] for segment in tts_result["segments"]] == [False, False, False]
    assert [segment["voice_profile_id"] for segment in tts_result["segments"]] == [
        "vp_stewie_xtts",
        "vp_brian_xtts",
        "vp_stewie_xtts",
    ]
    assert [segment["voice_profile_name"] for segment in tts_result["segments"]] == [
        "Stewie Griffin",
        "Brian Griffin",
        "Stewie Griffin",
    ]
    assert [segment["audio_path"] for segment in tts_result["segments"]] == [str(path) for path in segment_paths]
    assert all(segment["used_for_final_assembly"] is True for segment in tts_result["segments"])
    assert all(segment["artifact_url"].endswith(f"/segments/{Path(segment['audio_path']).name}") for segment in tts_result["segments"])
    assert tts_result["assembly"]["composite_audio_path"] == captured["composite_audio_path"]
    assert tts_result["assembly"]["final_mp4_path"] == captured["final_mp4_path"]
    assert tts_result["assembly"]["final_video_audio_path"] == captured["final_video_audio_path"]
    assert [item["segment_audio_path"] for item in tts_result["assembly"]["segments"]] == [str(path) for path in segment_paths]


def test_render_segment_metadata_exposes_safe_artifact_url():
    service = ProjectRenderService()
    segment_path = generated_job_segment_dir(88) / "000_host.wav"
    _write_wav(segment_path, seconds=0.9)
    segment = SpeechSegment(
        speaker="Host",
        text="Compare this render segment.",
        voice="Host",
        slot_index=0,
        audio_path=str(segment_path),
        duration_seconds=0.9,
        voice_profile_id="vp_host_calm_v1",
        provider_used="openvoice",
        fallback_used=False,
        provider_failures={},
    )

    metadata = service._segment_artifact_metadata(
        index=0,
        item={"segment": segment, "duration_seconds": 0.9},
        voice_manifest={
            "speakers": {
                "Host": {
                    "character_display_name": "Host",
                    "voice_profile": {
                        "display_name": "Host",
                        "provider": "openvoice",
                        "embedding_path": "voice_lab/embeddings/vp_host_hash.pth",
                        "style": {"base_speaker": "EN-US", "style_preset": "default"},
                        "controls": {"speaking_rate": 0.95, "emotion": "warm"},
                        "provider_metadata": {
                            "reference_audio_sha256": "processed-reference-hash",
                            "target_embedding_hash": "embedding-hash",
                            "reference_validation_status": "warning",
                        },
                        "reference_audios": [
                            {
                                "id": 7,
                                "original_storage_path": "original.mp3",
                                "processed_storage_path": "processed_reference.wav",
                                "processed_sha256": "processed-sha",
                                "validation_status": "warning",
                            }
                        ],
                    },
                }
            }
        },
        job_id=88,
    )

    assert metadata["segment_index"] == 0
    assert metadata["speaker"] == "Host"
    assert metadata["voice_profile_id"] == "vp_host_calm_v1"
    assert metadata["provider_used"] == "openvoice"
    assert metadata["fallback_used"] is False
    assert metadata["local_file_path"] == str(segment_path)
    assert metadata["artifact_url"] == "/generation-jobs/88/artifacts/segments/000_host.wav"
    assert metadata["voice_profile_settings"]["embedding_path"] == "voice_lab/embeddings/vp_host_hash.pth"
    assert metadata["voice_profile_settings"]["reference_audio_sha256"] == "processed-reference-hash"
    assert metadata["voice_profile_settings"]["base_speaker"] == "EN-US"
    assert metadata["reference_artifacts"][0]["processed_storage_path"] == "processed_reference.wav"


def test_render_config_caps_preview_fps_for_large_backgrounds(monkeypatch):
    service = ProjectRenderService()

    class FakeClip:
        fps = 60

    preview_config = service._render_config(FakeClip(), "preview")
    final_config = service._render_config(FakeClip(), "final")

    assert preview_config["fps"] == 24
    assert final_config["fps"] == 30
    assert preview_config["width"] == 1080
    assert preview_config["height"] == 1920
    assert preview_config["preset"] == "veryfast"
    assert preview_config["crf"] == 24
    assert final_config["preset"] == "faster"
    assert final_config["crf"] == 22

    monkeypatch.setattr(settings, "RENDER_PREVIEW_FPS_CAP", 12)
    monkeypatch.setattr(settings, "RENDER_EXPORT_FPS_CAP", 18)
    monkeypatch.setattr(settings, "RENDER_PREVIEW_WIDTH", 540)
    monkeypatch.setattr(settings, "RENDER_PREVIEW_HEIGHT", 960)
    monkeypatch.setattr(settings, "RENDER_FFMPEG_THREAD_CAP", 1)
    monkeypatch.setattr(settings, "RENDER_PREVIEW_ENCODE_PRESET", "ultrafast")
    monkeypatch.setattr(settings, "RENDER_PREVIEW_CRF", 28)

    throttled_preview = service._render_config(FakeClip(), "preview")
    throttled_final = service._render_config(FakeClip(), "final")

    assert throttled_preview["fps"] == 12
    assert throttled_final["fps"] == 18
    assert throttled_preview["width"] == 540
    assert throttled_preview["height"] == 960
    assert throttled_preview["threads"] == 1
    assert throttled_preview["preset"] == "ultrafast"
    assert throttled_preview["crf"] == 28


def test_tts_provider_capabilities_route_returns_registry_state(auth_client: TestClient):
    response = auth_client.get("/tts/providers")

    assert response.status_code == 200
    items = response.json()["items"]
    providers = {item["provider"] for item in items}
    assert {"espeak", "openvoice", "xtts", "rvc"}.issubset(providers)
    openvoice = next(item for item in items if item["provider"] == "openvoice")
    assert openvoice["supported_controls"] == ["speaking_rate"]
    xtts = next(item for item in items if item["provider"] == "xtts")
    rvc = next(item for item in items if item["provider"] == "rvc")
    assert xtts["supports_voice_cloning"] is True
    assert rvc["supports_voice_cloning"] is True


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


def _write_voice_manifest_presets() -> None:
    bundled_file = Path("test_storage") / "bundled" / "character_presets.json"
    bundled_file.write_text(
        """
[
  {
    "id": "host_clone_v1",
    "display_name": "Host",
    "speaker_names": ["Host"],
    "portrait_filename": "speaker_1.png",
    "tts_provider": "openvoice",
    "fallback_provider": "espeak",
    "model_id": "openvoice_v2",
    "language": "en",
    "voice": "en-us+f3",
    "rate": 150,
    "pitch": 42,
    "word_gap": 1,
    "amplitude": 140
  },
  {
    "id": "guest_local_v1",
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


def test_generation_job_snapshots_selected_voice_profiles(auth_client: TestClient, monkeypatch):
    _write_voice_manifest_presets()
    flow = _create_project_flow(auth_client)
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: None)

    create_job = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )

    assert create_job.status_code == 201
    manifest = create_job.json()["voice_manifest"]
    assert manifest["policy"] == "openvoice_fail_closed"
    assert manifest["speakers"]["Host"]["voice_profile_id"] == "vp_host_clone_v1"
    assert manifest["speakers"]["Host"]["requested_provider"] == "openvoice"
    assert manifest["speakers"]["Host"]["fallback_allowed"] is False
    assert manifest["speakers"]["Guest"]["voice_profile_id"] == "vp_guest_local_v1"
    assert manifest["speakers"]["Guest"]["fallback_allowed"] is True


def test_saved_calibration_recipe_is_snapshotted_for_video_render(auth_client: TestClient, monkeypatch):
    _write_voice_manifest_presets()
    auth_client.get("/character-presets")
    save_response = auth_client.post(
        "/voice-profiles/vp_host_clone_v1/calibration-recipe",
        json={
            "recipe": {
                "base_speaker": "EN-US",
                "style_preset": "default",
                "speaking_rate": 0.88,
                "pause_bias": 1.5,
                "pitch": -2,
                "energy": 1.15,
                "emotion": "serious",
                "accent": "default",
            }
        },
    )
    assert save_response.status_code == 200
    profile = save_response.json()
    assert profile["base_speaker"] == "EN-US"
    assert profile["style_preset"] == "default"
    assert profile["pace"] == 0.88
    assert profile["pause_bias"] == 1.5
    assert profile["pitch"] == -2.0
    assert profile["energy"] == 1.15
    assert profile["provider_metadata"]["calibration_status"] == "saved"
    assert profile["provider_metadata"]["last_calibration_recipe"]["base_speaker"] == "EN-US"

    flow = _create_project_flow(auth_client)
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: None)
    create_job = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )

    assert create_job.status_code == 201
    host_profile = create_job.json()["voice_manifest"]["speakers"]["Host"]["voice_profile"]
    assert host_profile["style"]["base_speaker"] == "EN-US"
    assert host_profile["style"]["style_preset"] == "default"
    assert host_profile["controls"]["speaking_rate"] == 0.88
    assert host_profile["controls"]["pause_length"] == 1.5
    assert host_profile["controls"]["pitch"] == -2.0
    assert host_profile["controls"]["energy"] == 1.15
    assert host_profile["controls"]["emotion"] == "serious"
    assert host_profile["controls"]["accent"] == "default"
    assert host_profile["provider_metadata"]["last_calibration_recipe"]["speaking_rate"] == 0.88


def test_generation_worker_uses_persisted_voice_manifest_after_binding_changes(auth_client: TestClient, monkeypatch):
    _write_voice_manifest_presets()
    flow = _create_project_flow(auth_client)
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: None)
    create_job = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    assert create_job.status_code == 201
    job_id = create_job.json()["id"]

    updated_bindings = auth_client.put(
        f"/projects/{flow['project_id']}/speaker-bindings",
        json={
            "items": [
                {"speaker_name": "Host", "character_preset_id": "guest_local_v1"},
                {"speaker_name": "Guest", "character_preset_id": "guest_local_v1"},
            ]
        },
    )
    assert updated_bindings.status_code == 200

    source_preview = Path("test_storage") / "source_preview.mp4"
    source_preview.write_bytes(b"rendered-preview")
    captured: dict[str, dict] = {}

    def fake_render_preview(self, *args, **kwargs):
        captured["voice_manifest"] = kwargs["voice_manifest"]
        segment_path = generated_job_segment_dir(kwargs["job_id"]) / "000_host.wav"
        _write_wav(segment_path, seconds=1.5)
        artifact_url = generated_job_artifact_url(kwargs["job_id"], segment_path)
        profile_url = generated_job_artifact_url(kwargs["job_id"], segment_path.parent.parent / "generation_profile.json")
        return {
            "output_path": str(source_preview),
            "duration_seconds": 1.5,
            "metadata": {
                "render_profile_artifact_url": profile_url,
                "tts_result": {
                    "status": "completed",
                    "provider_state": {"openvoice": {"available": True}},
                    "render_profile": {"artifact_url": profile_url, "summary": {"total_duration_seconds": 1.23}},
                    "segments": [
                        {
                            "speaker": "Host",
                            "provider_used": "openvoice",
                            "voice_profile_id": "vp_host_clone_v1",
                            "fallback_used": False,
                            "local_file_path": str(segment_path),
                            "artifact_url": artifact_url,
                            "duration_seconds": 1.5,
                        }
                    ],
                }
            },
        }

    monkeypatch.setattr(ProjectRenderService, "render_preview", fake_render_preview)
    result = process_generation_job(job_id)

    assert result["ok"] is True
    assert captured["voice_manifest"]["speakers"]["Host"]["voice_profile_id"] == "vp_host_clone_v1"
    job = auth_client.get(f"/generation-jobs/{job_id}")
    assert job.status_code == 200
    assert job.json()["tts_result"]["segments"][0]["provider_used"] == "openvoice"
    assert job.json()["tts_result"]["segments"][0]["artifact_url"].endswith("/segments/000_host.wav")
    assert job.json()["tts_result"]["render_profile"]["artifact_url"].endswith("/generation_profile.json")
    assert job.json()["tts_result"]["generation_job_duration_seconds"] >= 0
    outputs = auth_client.get(f"/projects/{flow['project_id']}/outputs")
    assert outputs.status_code == 200
    assert outputs.json()["items"][0]["asset"]["metadata"]["tts_result"]["segments"][0]["voice_profile_id"] == "vp_host_clone_v1"
    assert outputs.json()["items"][0]["asset"]["metadata"]["tts_result"]["segments"][0]["artifact_url"].endswith("/segments/000_host.wav")


def test_generation_worker_persists_tts_provider_failure(auth_client: TestClient, monkeypatch):
    _write_voice_manifest_presets()
    flow = _create_project_flow(auth_client)
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: None)
    create_job = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    assert create_job.status_code == 201
    job_id = create_job.json()["id"]

    def fail_render(self, *args, **kwargs):
        assert kwargs["voice_manifest"]["speakers"]["Host"]["fallback_allowed"] is False
        raise TextToSpeechError(
            code="openvoice_missing_models",
            message="OpenVoice is unavailable.",
            provider_state={"openvoice": {"available": False, "reason": "missing_models"}},
            attempted_providers=["openvoice"],
            provider_failures={"openvoice": {"code": "missing_models"}},
            suggested_action="Install OpenVoice checkpoints.",
        )

    monkeypatch.setattr(ProjectRenderService, "render_preview", fail_render)
    result = process_generation_job(job_id)

    assert result["ok"] is False
    job = auth_client.get(f"/generation-jobs/{job_id}")
    assert job.status_code == 200
    assert job.json()["status"] == "failed"
    assert job.json()["tts_result"]["error"]["attempted_providers"] == ["openvoice"]
    assert job.json()["provider_state"]["openvoice"]["reason"] == "missing_models"


def test_generation_worker_persists_xtts_provider_failure(auth_client: TestClient, monkeypatch):
    _write_voice_manifest_presets()
    flow = _create_project_flow(auth_client)
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: None)
    create_job = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    assert create_job.status_code == 201
    job_id = create_job.json()["id"]

    db = SessionLocal()
    try:
        from sqlalchemy.orm.attributes import flag_modified

        job = db.get(GenerationJob, job_id)
        assert job is not None
        manifest = dict(job.voice_manifest_json)
        host_entry = dict(manifest["speakers"]["Host"])
        host_profile = dict(host_entry["voice_profile"])
        host_profile.update(
            {
                "provider": "xtts",
                "requested_provider": "xtts",
                "fallback_allowed": False,
                "reference_audios": [{"id": 1, "processed_storage_path": "host_xtts_ref.wav"}],
            }
        )
        host_entry.update(
            {
                "provider": "xtts",
                "requested_provider": "xtts",
                "fallback_allowed": False,
                "voice_profile": host_profile,
            }
        )
        manifest["speakers"]["Host"] = host_entry
        job.voice_manifest_json = manifest
        flag_modified(job, "voice_manifest_json")
        db.commit()
    finally:
        db.close()

    def fail_render(self, *args, **kwargs):
        host_entry = kwargs["voice_manifest"]["speakers"]["Host"]
        assert host_entry["requested_provider"] == "xtts"
        assert host_entry["fallback_allowed"] is False
        raise TextToSpeechError(
            code="xtts_package_missing",
            message="XTTS is unavailable.",
            provider_state={"xtts": {"available": False, "reason": "package_missing"}},
            attempted_providers=["xtts"],
            provider_failures={"xtts": {"code": "package_missing"}},
            suggested_action="Install Coqui TTS in the runtime image.",
        )

    monkeypatch.setattr(ProjectRenderService, "render_preview", fail_render)
    result = process_generation_job(job_id)

    assert result["ok"] is False
    job = auth_client.get(f"/generation-jobs/{job_id}")
    assert job.status_code == 200
    body = job.json()
    assert body["status"] == "failed"
    assert body["tts_result"]["error"]["attempted_providers"] == ["xtts"]
    assert body["tts_result"]["error"]["provider_failures"]["xtts"]["code"] == "package_missing"
    assert body["provider_state"]["xtts"]["reason"] == "package_missing"


def test_generation_job_artifact_endpoint_serves_scoped_segment_wav(auth_client: TestClient, monkeypatch):
    _write_voice_manifest_presets()
    flow = _create_project_flow(auth_client)
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: None)
    create_job = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    assert create_job.status_code == 201
    job_id = create_job.json()["id"]
    segment_path = generated_job_segment_dir(job_id) / "000_host.wav"
    _write_wav(segment_path, seconds=0.5)

    response = auth_client.get(f"/generation-jobs/{job_id}/artifacts/segments/000_host.wav")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/")
    assert response.content.startswith(b"RIFF")


def test_generation_job_artifact_endpoint_rejects_path_traversal(auth_client: TestClient, monkeypatch):
    _write_voice_manifest_presets()
    flow = _create_project_flow(auth_client)
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: None)
    create_job = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    assert create_job.status_code == 201
    job_id = create_job.json()["id"]

    response = auth_client.get(f"/generation-jobs/{job_id}/artifacts/../secrets.wav")

    assert response.status_code == 404


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


def test_generation_job_list_exposes_latest_completed_job(auth_client: TestClient, monkeypatch):
    flow = _create_project_flow(auth_client)
    monkeypatch.setattr(process_generation_job, "delay", lambda job_id: None)

    create_job = auth_client.post(
        f"/projects/{flow['project_id']}/generation-jobs",
        json={"background_style": "none"},
    )
    assert create_job.status_code == 201
    job_id = create_job.json()["id"]

    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        assert job is not None
        job.status = "completed"
        job.progress = 100
        job.tts_result_json = {
            "segments": [
                {
                    "segment_index": 0,
                    "speaker": "Host",
                    "voice_profile_id": "vp_host_clone_v1",
                    "provider_used": "openvoice",
                    "fallback_used": False,
                    "artifact_url": f"/generation-jobs/{job_id}/artifacts/segments/000_host.wav",
                }
            ]
        }
        db.commit()
    finally:
        db.close()

    active = auth_client.get(f"/projects/{flow['project_id']}/generation-jobs/active")
    assert active.status_code == 404

    jobs = auth_client.get(f"/projects/{flow['project_id']}/generation-jobs")
    assert jobs.status_code == 200
    assert jobs.json()["items"][0]["id"] == job_id
    assert jobs.json()["items"][0]["status"] == "completed"
    assert jobs.json()["items"][0]["tts_result"]["segments"][0]["artifact_url"].endswith("/segments/000_host.wav")


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
