from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.domains.voice.previews import (
    build_ephemeral_voice_profile,
    normalize_manifest_voice_profile,
    preview_fallback_provider,
    preview_requested_provider,
    reference_audio_profile_payload,
    select_preview_provider,
    voice_profile_model_payload,
)
from app.domains.voice.profiles import artifacts as domain_voice_artifacts
from app.domains.voice.profiles import paths as domain_voice_paths
from app.domains.voice.profiles import recipes as domain_voice_recipes
from app.domains.voice.providers import (
    BaseTTSProvider,
    EspeakProvider,
    ProviderCapability,
    ProviderRegistry,
    SpeechSegment,
    SynthesisResult,
    TTSProviderError,
    TextToSpeechError,
    available_provider_names,
    provider_capabilities_payload,
    provider_capability_payload,
    provider_selection_order,
    resolve_provider_selection,
)
from app.domains.voice.providers import espeak as domain_espeak
from app.domains.voice.synthesis import (
    TTSOrchestrator as DomainTTSOrchestrator,
    apply_voice_lab_overrides as domain_apply_voice_lab_overrides,
    audio_stats as domain_audio_stats,
    cached_synthesis_result,
    fallback_reason,
    provider_error_failure,
    provider_synthesis_result,
    unavailable_provider_failure,
    unknown_provider_failure,
    voice_cache_key,
    voice_cache_settings,
    voice_reference_hash,
)
from app.services import character_voice_recipes as service_character_voice_recipes
from app.services import tts as service_tts
from app.services import voice_profiles as service_voice_profiles


def _write_test_wav(path: Path, *, seconds: float = 0.8, sample_rate: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frame_count)


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
    _write_test_wav(clean_dir / "ref_a.wav")
    _write_test_wav(clean_dir / "ref_b.wav")
    golden_preview = golden_dir / "xtts_checkpoint_smoke.wav"
    _write_test_wav(golden_preview)
    recipe_path = root / "stewie_griffin" / "selected_recipe.json"
    recipe_path.parent.mkdir(parents=True, exist_ok=True)
    recipe_path.write_text(
        json.dumps(
            {
                "provider": "xtts",
                "character": "stewie_griffin",
                "status": "golden_preview_selected",
                "xtts_checkpoint_dir_local": str(checkpoint_dir),
                "reference_wavs_local": str(clean_dir / "*.wav"),
                "golden_preview_local": str(golden_preview),
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
        "golden_preview": golden_preview,
        "recipe_path": recipe_path,
    }


class _FakeProvider(BaseTTSProvider):
    def __init__(self, *, name: str, available: bool, reason: str | None = None) -> None:
        self.provider_name = name
        self._available = available
        self._reason = reason

    def healthcheck(self) -> dict[str, object]:
        return {
            "available": self._available,
            "reason": self._reason,
            "metadata": {"name": self.provider_name},
        }


class _SynthesizingFakeProvider(_FakeProvider):
    supported_control_names = ("speaking_rate",)

    def synthesize_line(
        self,
        text: str,
        voice_profile: dict[str, object],
        output_path: Path,
        options: dict[str, object],
    ) -> dict[str, object]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _write_test_wav(output_path, seconds=0.75)
        return {
            "audio_path": str(output_path),
            "voice": str(voice_profile.get("display_name") or self.provider_name),
            "duration_seconds": 0.75,
            "provider_used": self.provider_name,
            "controls_applied": {"speaking_rate": 0.9},
            "reference_audio_count": len(voice_profile.get("reference_audios") or []),
        }


def test_tts_service_shim_preserves_provider_contract_symbol_identity() -> None:
    assert service_tts.BaseTTSProvider is BaseTTSProvider
    assert service_tts.EspeakProvider is EspeakProvider
    assert service_tts.ProviderCapability is ProviderCapability
    assert issubclass(service_tts.ProviderRegistry, ProviderRegistry)
    assert service_tts.SpeechSegment is SpeechSegment
    assert service_tts.SynthesisResult is SynthesisResult
    assert service_tts.TTSProviderError is TTSProviderError
    assert service_tts.TextToSpeechError is TextToSpeechError
    assert issubclass(service_tts.TTSOrchestrator, DomainTTSOrchestrator)


def test_provider_registry_preserves_capabilities_healthcheck_and_lookup() -> None:
    espeak = _FakeProvider(name="espeak", available=True)
    openvoice = _FakeProvider(name="openvoice", available=False, reason="missing_models")
    registry = ProviderRegistry({"espeak": espeak, "openvoice": openvoice})

    capabilities = registry.capabilities()

    assert [cap.provider for cap in capabilities] == ["espeak", "openvoice"]
    assert capabilities[0].available is True
    assert capabilities[1].available is False
    assert capabilities[1].reason == "missing_models"
    assert registry.healthcheck() == {
        "espeak": {"available": True, "reason": None, "metadata": {"name": "espeak"}},
        "openvoice": {"available": False, "reason": "missing_models", "metadata": {"name": "openvoice"}},
    }
    assert registry.get("espeak") is espeak
    assert registry.get("missing") is None


def test_tts_service_orchestrator_remains_usable_with_default_registry() -> None:
    orchestrator = service_tts.TTSOrchestrator()

    assert isinstance(orchestrator, DomainTTSOrchestrator)
    assert set(orchestrator.provider_state()) == {"espeak", "openvoice", "xtts", "rvc"}


def test_domain_tts_orchestrator_uses_injected_registry(tmp_path: Path) -> None:
    provider = _SynthesizingFakeProvider(name="xtts", available=True)
    registry = ProviderRegistry({"xtts": provider})
    orchestrator = DomainTTSOrchestrator(registry)
    output_path = tmp_path / "segment.wav"

    result = orchestrator.synthesize_line(
        text="Hello there",
        voice_profile={
            "id": "vp_test",
            "display_name": "Test Voice",
            "provider": "xtts",
            "reference_audios": [{"id": 1}],
        },
        output_path=output_path,
        fallback_allowed=False,
    )

    assert output_path.exists()
    assert result == SynthesisResult(
        audio_path=str(output_path),
        voice="Test Voice",
        duration_seconds=0.75,
        provider_used="xtts",
        fallback_used=False,
        controls_applied={"speaking_rate": 0.9},
        reference_audio_count=1,
        provider_state={"xtts": {"available": True, "reason": None, "metadata": {"name": "xtts"}}},
        cache_hit=False,
        voice_profile_id="vp_test",
        provider_failures={},
        fallback_reason=None,
        recipe_used={},
        golden_preview_wav=None,
    )


def test_tts_service_audio_stats_alias_delegates_to_domain(tmp_path: Path) -> None:
    audio_path = tmp_path / "sample.wav"
    _write_test_wav(audio_path, seconds=0.5, sample_rate=8000)

    assert service_tts._audio_stats is domain_audio_stats
    assert service_tts._audio_stats(audio_path) == {
        "sample_rate": 8000,
        "frame_count": 4000,
        "channels": 1,
        "duration_seconds": 0.5,
    }


def test_provider_metadata_helpers_preserve_capability_payload_shape() -> None:
    capability = ProviderCapability(
        provider="openvoice",
        available=False,
        reason="missing_models",
        supports_voice_cloning=True,
        supports_prepare=True,
        supported_controls=["speaking_rate"],
        metadata={"checkpoints_dir": "/models/openvoice"},
    )

    assert provider_capability_payload(capability) == {
        "provider": "openvoice",
        "available": False,
        "reason": "missing_models",
        "supports_voice_cloning": True,
        "supports_prepare": True,
        "supported_controls": ["speaking_rate"],
        "metadata": {"checkpoints_dir": "/models/openvoice"},
    }
    assert provider_capabilities_payload([capability]) == [provider_capability_payload(capability)]


def test_provider_metadata_helpers_preserve_available_provider_names() -> None:
    assert available_provider_names(
        {
            "espeak": {"available": True, "reason": None},
            "openvoice": {"available": False, "reason": "missing_models"},
            "xtts": {},
        }
    ) == {"espeak"}


def test_provider_selection_helpers_preserve_order_and_fallback_behavior() -> None:
    voice_profile = {
        "provider": "openvoice",
        "fallback_provider": "xtts",
    }
    state = {
        "openvoice": {"available": False, "reason": "missing_models"},
        "xtts": {"available": False, "reason": "package_missing"},
        "espeak": {"available": True, "reason": None},
    }

    assert provider_selection_order(voice_profile, requested_provider="auto", fallback_allowed=True) == ["openvoice", "xtts", "espeak"]
    assert provider_selection_order(voice_profile, requested_provider="rvc", fallback_allowed=False) == ["rvc", "openvoice"]
    assert resolve_provider_selection(voice_profile, state, requested_provider="auto", fallback_allowed=True) == {
        "selection_order": ["openvoice", "xtts", "espeak"],
        "selected_provider": "espeak",
        "provider_state": state,
        "fallback_allowed": True,
    }


def test_voice_preview_provider_selection_helpers_preserve_selection_order() -> None:
    assert preview_requested_provider({"tts_provider": " OpenVoice ", "provider": "espeak"}) == "openvoice"
    assert preview_requested_provider({"provider": " XTTS "}) == "xtts"
    assert preview_requested_provider({}) == "espeak"
    assert preview_fallback_provider({"fallback_provider": " Espeak "}) == "espeak"
    assert preview_fallback_provider({}) == ""

    assert select_preview_provider({"tts_provider": "openvoice"}, {"openvoice", "espeak"}) == "openvoice"
    assert select_preview_provider({"tts_provider": "openvoice", "fallback_provider": "xtts"}, {"xtts", "espeak"}) == "xtts"
    assert select_preview_provider({"tts_provider": "macos"}, {"espeak"}) == "espeak"
    assert select_preview_provider({"tts_provider": "openvoice"}, set()) is None


def test_local_speech_service_provider_selection_delegates_to_preview_domain() -> None:
    service = service_tts.LocalSpeechService()

    assert service._provider_for_voice_profile({"tts_provider": "openvoice"}, {"openvoice", "espeak"}) == "openvoice"
    assert service._provider_for_voice_profile({"tts_provider": "openvoice", "fallback_provider": "xtts"}, {"xtts", "espeak"}) == "xtts"
    assert service._provider_for_voice_profile({"tts_provider": "macos"}, {"espeak"}) == "espeak"


def test_voice_preview_ephemeral_profile_payload_preserves_shape() -> None:
    payload = {
        "tts_provider": "OpenVoice",
        "fallback_provider": "Espeak",
        "voice": "en-us+f3",
        "rate": 0,
        "pitch": 41,
        "word_gap": 0,
        "amplitude": 120,
        "controls": {"speaking_rate": 0.8},
        "style": {"style_preset": "calm"},
        "reference_audios": [{"id": 1}],
        "language": "",
        "model_id": "melo",
        "embedding_path": "embeddings/vp.pt",
    }

    assert build_ephemeral_voice_profile(
        "Guest Host!!",
        payload,
        default_voice="en-us",
        default_rate=155,
        default_pitch=50,
        default_word_gap=3,
        default_amplitude=90,
    ) == {
        "id": "ephemeral_guest_host",
        "display_name": "Guest Host!!",
        "provider": "openvoice",
        "fallback_provider": "espeak",
        "voice": "en-us+f3",
        "espeak_voice": "en-us+f3",
        "espeak_rate": 0,
        "espeak_pitch": 41,
        "espeak_word_gap": 0,
        "espeak_amplitude": 120,
        "controls": {"speaking_rate": 0.8},
        "style": {"style_preset": "calm"},
        "fallback_voice_settings": {
            "voice": "en-us+f3",
            "rate": 0,
            "pitch": 41,
            "word_gap": 0,
            "amplitude": 120,
        },
        "reference_audios": [{"id": 1}],
        "language": "en",
        "model_id": "melo",
        "embedding_path": "embeddings/vp.pt",
        "fallback_allowed": False,
    }


def test_local_speech_service_ephemeral_profile_delegates_to_preview_domain(monkeypatch) -> None:
    monkeypatch.setattr(settings, "TTS_ESPEAK_VOICE_SLOT_1", "en-us")
    monkeypatch.setattr(settings, "TTS_ESPEAK_RATE", 155)
    monkeypatch.setattr(settings, "TTS_ESPEAK_PITCH", 50)
    monkeypatch.setattr(settings, "TTS_ESPEAK_WORD_GAP", 3)
    monkeypatch.setattr(settings, "TTS_ESPEAK_AMPLITUDE", 90)
    payload = {"provider": "espeak", "voice": "en-us+f3", "rate": 144}

    assert service_tts.LocalSpeechService()._ephemeral_profile("Host", payload) == build_ephemeral_voice_profile(
        "Host",
        payload,
        default_voice="en-us",
        default_rate=155,
        default_pitch=50,
        default_word_gap=3,
        default_amplitude=90,
    )


def test_voice_preview_manifest_profile_normalization_preserves_shape() -> None:
    manifest_entry = {
        "requested_provider": "XTTS",
        "fallback_allowed": False,
        "voice_profile": {
            "id": "vp_manifest",
            "provider": "openvoice",
            "display_name": "Host Clone",
            "controls": {"speaking_rate": 0.85},
        },
    }

    assert normalize_manifest_voice_profile(manifest_entry) == {
        "id": "vp_manifest",
        "provider": "openvoice",
        "display_name": "Host Clone",
        "controls": {"speaking_rate": 0.85},
        "requested_provider": "xtts",
        "fallback_allowed": False,
    }
    assert normalize_manifest_voice_profile({"voice_profile": {"provider": "xtts"}}) == {
        "provider": "xtts",
        "requested_provider": "xtts",
        "fallback_allowed": False,
    }
    assert normalize_manifest_voice_profile({"voice_profile": {"provider": "espeak"}}) == {
        "provider": "espeak",
        "requested_provider": "espeak",
        "fallback_allowed": True,
    }
    assert normalize_manifest_voice_profile({}) is None


def test_local_speech_service_manifest_profile_delegates_to_preview_domain() -> None:
    manifest_entry = {
        "requested_provider": "OpenVoice",
        "fallback_allowed": False,
        "voice_profile": {
            "id": "vp_host",
            "provider": "openvoice",
            "display_name": "Host",
        },
    }
    service = service_tts.LocalSpeechService(voice_manifest={"speakers": {"Host": manifest_entry}})

    assert service._manifest_profile_for_speaker("Host") == normalize_manifest_voice_profile(manifest_entry)


def test_reference_audio_profile_payload_preserves_shape_and_processed_fallback() -> None:
    reference_audio = SimpleNamespace(
        id=42,
        storage_path="voice_lab/vp/ref.wav",
        original_storage_path="uploads/original.wav",
        processed_storage_path=None,
        sha256="raw-sha",
        processed_sha256=None,
        mime_type="audio/wav",
        validation_status="valid",
        validation_json={"sample_rate": 16000},
    )

    assert reference_audio_profile_payload(reference_audio) == {
        "id": 42,
        "storage_path": "voice_lab/vp/ref.wav",
        "original_storage_path": "uploads/original.wav",
        "processed_storage_path": "voice_lab/vp/ref.wav",
        "sha256": "raw-sha",
        "processed_sha256": None,
        "mime_type": "audio/wav",
        "validation_status": "valid",
        "validation": {"sample_rate": 16000},
    }


def test_voice_profile_model_payload_preserves_render_profile_shape() -> None:
    reference_audios = [
        SimpleNamespace(
            id=1,
            storage_path="voice_lab/vp/raw.wav",
            original_storage_path="uploads/raw.wav",
            processed_storage_path="voice_lab/vp/processed.wav",
            sha256="raw-a",
            processed_sha256="processed-a",
            mime_type="audio/wav",
            validation_status="valid",
            validation_json={"duration_ms": 1200},
        )
    ]
    voice_profile = SimpleNamespace(
        id="vp_xtts",
        provider="xtts",
        fallback_provider="espeak",
        espeak_voice="en-us+f3",
        espeak_rate=151,
        espeak_pitch=44,
        espeak_word_gap=5,
        espeak_amplitude=91,
        controls_json={"speed": 0.92},
        style_json={"style_preset": "animated"},
        fallback_voice_settings_json={"voice": "en-us"},
        reference_audios=reference_audios,
        language="en",
        model_id="xtts-v2",
        model_checkpoint_path="voice_models/stewie/checkpoint",
        selected_recipe_json={"temperature": 0.7},
        reference_dataset_id=7,
        character_slug="stewie_griffin",
        calibration_score=0.83,
        last_verified_render_job_id=99,
        embedding_path="voice_lab/vp/embed.pt",
        provider_metadata_json={"runtime": "cpu"},
    )
    preset_model = SimpleNamespace(display_name="Stewie Griffin", voice_profile=voice_profile)

    assert voice_profile_model_payload(preset_model) == {
        "id": "vp_xtts",
        "display_name": "Stewie Griffin",
        "provider": "xtts",
        "fallback_provider": "espeak",
        "voice": "en-us+f3",
        "espeak_voice": "en-us+f3",
        "espeak_rate": 151,
        "espeak_pitch": 44,
        "espeak_word_gap": 5,
        "espeak_amplitude": 91,
        "controls": {"speed": 0.92},
        "style": {"style_preset": "animated"},
        "fallback_voice_settings": {"voice": "en-us"},
        "reference_audios": [
            {
                "id": 1,
                "storage_path": "voice_lab/vp/raw.wav",
                "original_storage_path": "uploads/raw.wav",
                "processed_storage_path": "voice_lab/vp/processed.wav",
                "sha256": "raw-a",
                "processed_sha256": "processed-a",
                "mime_type": "audio/wav",
                "validation_status": "valid",
                "validation": {"duration_ms": 1200},
            }
        ],
        "language": "en",
        "model_id": "xtts-v2",
        "model_checkpoint_path": "voice_models/stewie/checkpoint",
        "selected_recipe": {"temperature": 0.7},
        "reference_dataset_id": 7,
        "character_slug": "stewie_griffin",
        "calibration_score": 0.83,
        "last_verified_render_job_id": 99,
        "embedding_path": "voice_lab/vp/embed.pt",
        "provider_metadata": {"runtime": "cpu"},
        "fallback_allowed": False,
    }


def test_local_speech_service_db_profile_payload_delegates_to_preview_domain(monkeypatch) -> None:
    preset_model = SimpleNamespace(id="preset_1", display_name="Stewie Griffin")
    monkeypatch.setattr(service_tts, "resolve_character_preset_for_speaker", lambda speaker: {"id": "preset_1"})
    monkeypatch.setattr(service_tts, "get_character_preset_model", lambda preset_id, db: preset_model)
    monkeypatch.setattr(
        service_tts,
        "voice_profile_model_payload",
        lambda model: {"delegated_profile": model.display_name},
    )

    assert service_tts.LocalSpeechService()._resolved_profile_for_speaker("Stewie", 0) == {
        "delegated_profile": "Stewie Griffin"
    }


def test_espeak_provider_healthcheck_reports_configured_binary(monkeypatch) -> None:
    monkeypatch.setattr(domain_espeak.shutil, "which", lambda name: "/usr/bin/espeak-ng" if name == "espeak-ng" else None)

    assert EspeakProvider().healthcheck() == {
        "available": True,
        "reason": None,
        "metadata": {"binary": "/usr/bin/espeak-ng"},
    }


def test_espeak_provider_synthesize_line_preserves_command_and_payload(monkeypatch, tmp_path: Path) -> None:
    recorded: dict[str, object] = {}
    output_path = tmp_path / "sample.wav"
    monkeypatch.setattr(domain_espeak.shutil, "which", lambda name: "/usr/bin/espeak-ng" if name == "espeak-ng" else None)

    def fake_run(command, check, capture_output, text):
        recorded["command"] = command
        recorded["check"] = check
        recorded["capture_output"] = capture_output
        recorded["text"] = text
        _write_test_wav(output_path, seconds=0.4)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(domain_espeak.subprocess, "run", fake_run)

    result = EspeakProvider().synthesize_line(
        text="Hello there",
        voice_profile={
            "voice": "en-us+f3",
            "controls": {"speaking_rate": 0.8},
            "fallback_voice_settings": {"rate": 144, "pitch": 45, "word_gap": 7, "amplitude": 120},
            "reference_audios": [{"id": 1}],
        },
        output_path=output_path,
        options={},
    )

    assert recorded == {
        "command": [
            "/usr/bin/espeak-ng",
            "-w",
            str(output_path),
            "-s",
            "144",
            "-p",
            "45",
            "-g",
            "7",
            "-a",
            "120",
            "-v",
            "en-us+f3",
            "Hello there",
        ],
        "check": True,
        "capture_output": True,
        "text": True,
    }
    assert result == {
        "audio_path": str(output_path),
        "voice": "en-us+f3",
        "duration_seconds": 0.6,
        "provider_used": "espeak",
        "controls_applied": {
            "speaking_rate": 0.8,
            "pitch": 45,
            "pause_length": 7,
            "energy": 120,
        },
        "reference_audio_count": 1,
    }


def test_espeak_provider_fails_closed_when_binary_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(domain_espeak.shutil, "which", lambda _name: None)

    with pytest.raises(TTSProviderError) as exc_info:
        EspeakProvider().synthesize_line(
            text="Hello there",
            voice_profile={},
            output_path=tmp_path / "missing.wav",
            options={},
        )

    assert exc_info.value.code == "espeak_not_installed"
    assert exc_info.value.provider_state == {"espeak": {"available": False, "reason": "missing_binary", "metadata": {"binary": None}}}


def test_tts_service_shim_preserves_voice_lab_override_behavior(monkeypatch) -> None:
    monkeypatch.setattr(settings, "TTS_ESPEAK_RATE", 180)
    payload = service_tts.apply_voice_lab_overrides(
        {"voice": "en-us+f3", "controls": {"style_preset": "calm"}},
        controls={"pitch": 44},
        rate=144,
        word_gap=6,
    )

    assert service_tts.apply_voice_lab_overrides is domain_apply_voice_lab_overrides
    assert payload["espeak_rate"] == 144
    assert payload["espeak_word_gap"] == 6
    assert payload["controls"] == {
        "style_preset": "calm",
        "speaking_rate": 0.8,
        "pause_length": 6,
        "pitch": 44,
    }
    assert payload["fallback_voice_settings"] == {
        "voice": "en-us+f3",
        "rate": 144,
        "pitch": None,
        "word_gap": 6,
        "amplitude": None,
    }


def test_tts_voice_cache_key_service_wrapper_delegates_to_domain() -> None:
    profile = {
        "id": "vp_demo",
        "voice": "en-us",
        "controls": {"speaking_rate": 0.8, "pitch": 44, "ignored": "value"},
        "fallback_voice_settings": {"rate": 144, "word_gap": 6},
        "reference_audios": [{"processed_sha256": "b"}, {"sha256": "a"}],
    }
    provider = EspeakProvider()

    assert service_tts.TTSOrchestrator()._voice_cache_key("espeak", "Hello", profile, provider) == voice_cache_key(
        "espeak",
        "Hello",
        profile,
        provider.supported_control_names,
    )


def test_tts_voice_reference_hash_preserves_metadata_override_and_sorted_references() -> None:
    profile = {
        "reference_audios": [
            {"storage_path": "z.wav"},
            {"processed_sha256": "a-processed"},
            {"sha256": "m-original"},
        ],
    }
    overridden = {**profile, "provider_metadata": {"reference_audio_sha256": "explicit-reference"}}

    assert voice_reference_hash(overridden) == "explicit-reference"
    assert voice_reference_hash(profile) == voice_reference_hash(
        {
            "reference_audios": [
                {"sha256": "m-original"},
                {"storage_path": "z.wav"},
                {"processed_sha256": "a-processed"},
            ],
        }
    )


def test_tts_voice_cache_settings_preserve_provider_specific_inputs() -> None:
    openvoice_profile = {
        "language": "en",
        "model_id": "melo",
        "style": {"base_speaker": "EN-US", "style_preset": "calm"},
        "provider_metadata": {
            "embedding_artifact_path": "embeddings/vp.pt",
            "target_embedding_hash": "target-hash",
        },
        "controls": {"speaking_rate": 0.9, "pitch": 50},
    }
    xtts_profile = {
        "language": "en",
        "model_id": "xtts-v2",
        "model_checkpoint_path": "/models/stewie/model.pth",
        "selected_recipe": {"temperature": 0.7},
        "style": {"base_speaker": "dataset", "style_preset": "character"},
        "controls": {"speaking_rate": 0.85, "pause_length": 4},
    }
    fallback_profile = {
        "voice": "en-us",
        "fallback_voice_settings": {"rate": 150, "pitch": 43, "word_gap": 0, "amplitude": 110},
        "controls": {"speaking_rate": 0.75, "energy": 110},
    }

    assert voice_cache_settings("openvoice", openvoice_profile, ("speaking_rate",)) == {
        "controls": {"speaking_rate": 0.9},
        "language": "en",
        "model_id": "melo",
        "base_speaker": "EN-US",
        "style_preset": "calm",
        "embedding_path": "embeddings/vp.pt",
        "target_embedding_hash": "target-hash",
    }
    assert voice_cache_settings("xtts", xtts_profile, ("speaking_rate", "pause_length")) == {
        "controls": {"speaking_rate": 0.85, "pause_length": 4},
        "language": "en",
        "model_id": "xtts-v2",
        "model_checkpoint_path": "/models/stewie/model.pth",
        "selected_recipe": {"temperature": 0.7},
        "base_speaker": "dataset",
        "style_preset": "character",
    }
    assert voice_cache_settings("espeak", fallback_profile, ("speaking_rate", "energy")) == {
        "controls": {"speaking_rate": 0.75, "energy": 110},
        "fallback": {
            "voice": "en-us",
            "rate": 150,
            "pitch": 43,
            "word_gap": 0,
            "amplitude": 110,
        },
    }


def test_tts_voice_cache_key_changes_with_content_affecting_inputs() -> None:
    profile = {
        "id": "vp_cache",
        "voice": "en-us",
        "fallback_voice_settings": {"rate": 144},
        "reference_audios": [{"processed_sha256": "reference-a"}],
    }
    base_key = voice_cache_key("espeak", "Hello", profile, EspeakProvider.supported_control_names)

    assert voice_cache_key("espeak", "Different", profile, EspeakProvider.supported_control_names) != base_key
    assert voice_cache_key(
        "espeak",
        "Hello",
        {**profile, "fallback_voice_settings": {"rate": 170}},
        EspeakProvider.supported_control_names,
    ) != base_key
    assert voice_cache_key(
        "espeak",
        "Hello",
        {**profile, "reference_audios": [{"processed_sha256": "reference-b"}]},
        EspeakProvider.supported_control_names,
    ) != base_key


def test_tts_provider_failure_payload_helpers_preserve_public_shape() -> None:
    provider_health = {"available": False, "reason": "missing_models", "metadata": {"provider": "openvoice"}}
    error = TTSProviderError(
        code="synthesis_failure",
        message="provider failed",
        provider_state={"xtts": {"available": True}},
        fallback_attempted=True,
        suggested_action="Check provider logs.",
    )

    assert unknown_provider_failure("bogus") == {
        "code": "unknown_provider",
        "message": "Unknown TTS provider requested: bogus",
    }
    assert unavailable_provider_failure("openvoice", provider_health) == {
        "code": "missing_models",
        "message": "Provider openvoice is not available in this environment.",
        "provider_state": provider_health,
    }
    assert provider_error_failure(error) == {
        "code": "synthesis_failure",
        "message": "provider failed",
        "provider_state": {"xtts": {"available": True}},
        "fallback_attempted": True,
        "suggested_action": "Check provider logs.",
    }
    assert fallback_reason({"openvoice": {"code": "missing_models"}}, True) == "missing_models"
    assert fallback_reason({"openvoice": {"code": "missing_models"}}, False) is None


def test_tts_synthesis_result_payload_helpers_preserve_cached_result_shape() -> None:
    state = {"espeak": {"available": True}}
    provider_failures = {"openvoice": {"code": "missing_models"}}
    profile = {
        "id": "vp_cached",
        "voice": "en-us",
        "reference_audios": [{"id": 1}, {"id": 2}],
        "selected_recipe": {"temperature": 0.7},
    }

    result = cached_synthesis_result(
        audio_path="/tmp/segment.wav",
        duration_seconds=0.3,
        provider_name="espeak",
        voice_profile=profile,
        state=state,
        controls_applied={"speaking_rate": 0.8},
        provider_failures=provider_failures,
        fallback_used=True,
    )

    assert result == SynthesisResult(
        audio_path="/tmp/segment.wav",
        voice="en-us",
        duration_seconds=0.6,
        provider_used="espeak",
        fallback_used=True,
        controls_applied={"speaking_rate": 0.8},
        reference_audio_count=2,
        provider_state=state,
        cache_hit=True,
        voice_profile_id="vp_cached",
        provider_failures=provider_failures,
        fallback_reason="missing_models",
        recipe_used={"temperature": 0.7},
        golden_preview_wav=None,
    )


def test_tts_synthesis_result_payload_helpers_preserve_provider_result_shape() -> None:
    state = {"xtts": {"available": True}}
    provider_failures = {"openvoice": {"code": "missing_models"}}
    profile = {"id": "vp_xtts", "selected_recipe": {"temperature": 0.6}}
    provider_result = {
        "audio_path": "/tmp/xtts.wav",
        "voice": "Stewie",
        "duration_seconds": 1.2,
        "provider_used": "xtts",
        "controls_applied": {"speaking_rate": 0.9},
        "reference_audio_count": 3,
        "recipe_used": {"temperature": 0.7},
        "golden_preview_wav": "/tmp/golden.wav",
    }

    result = provider_synthesis_result(
        result=provider_result,
        voice_profile=profile,
        state=state,
        provider_failures=provider_failures,
        fallback_used=True,
    )

    assert result == SynthesisResult(
        audio_path="/tmp/xtts.wav",
        voice="Stewie",
        duration_seconds=1.2,
        provider_used="xtts",
        fallback_used=True,
        controls_applied={"speaking_rate": 0.9},
        reference_audio_count=3,
        provider_state=state,
        cache_hit=False,
        voice_profile_id="vp_xtts",
        provider_failures=provider_failures,
        fallback_reason="missing_models",
        recipe_used={"temperature": 0.7},
        golden_preview_wav="/tmp/golden.wav",
    )


def test_voice_profile_service_path_helpers_delegate_to_domain(tmp_path: Path, monkeypatch) -> None:
    media_dir = tmp_path / "media"
    voice_models_dir = tmp_path / "voice_models"
    monkeypatch.setattr(settings, "MEDIA_DIR", str(media_dir))
    monkeypatch.setattr(settings, "VOICE_MODELS_DIR", str(voice_models_dir))

    assert service_voice_profiles.voice_lab_preview_dir is domain_voice_paths.voice_lab_preview_dir
    assert service_voice_profiles.voice_reference_audio_dir is domain_voice_paths.voice_reference_audio_dir
    assert service_voice_profiles.voice_reference_audio_profile_dir is domain_voice_paths.voice_reference_audio_profile_dir
    assert service_voice_profiles.voice_reference_chunk_dir is domain_voice_paths.voice_reference_chunk_dir
    assert service_voice_profiles.voice_cache_dir is domain_voice_paths.voice_cache_dir
    assert service_voice_profiles.voice_embedding_dir is domain_voice_paths.voice_embedding_dir
    assert service_voice_profiles.voice_models_dir is domain_voice_paths.voice_models_dir
    assert service_voice_profiles.character_portrait_dir is domain_voice_paths.character_portrait_dir

    assert service_voice_profiles.voice_lab_preview_dir() == media_dir / "voice_lab" / "previews"
    assert service_voice_profiles.voice_reference_audio_dir() == media_dir / "voice_lab" / "reference_audio"
    assert service_voice_profiles.voice_reference_audio_profile_dir("../Bad Profile!!") == media_dir / "voice_lab" / "reference_audio" / "Bad_Profile"
    assert service_voice_profiles.voice_reference_chunk_dir("vp_1") == media_dir / "voice_lab" / "reference_chunks" / "vp_1"
    assert service_voice_profiles.voice_cache_dir() == media_dir / "voice_cache"
    assert service_voice_profiles.voice_embedding_dir() == media_dir / "voice_lab" / "embeddings"
    assert service_voice_profiles.voice_models_dir() == voice_models_dir
    assert service_voice_profiles.character_portrait_dir() == media_dir / "characters"


def test_voice_profile_artifact_helpers_delegate_to_domain(tmp_path: Path, monkeypatch) -> None:
    media_dir = tmp_path / "media"
    monkeypatch.setattr(settings, "MEDIA_DIR", str(media_dir))
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    first.write_bytes(b"same")
    second.write_bytes(b"different")

    assert service_voice_profiles.voice_embedding_artifact_path is domain_voice_artifacts.voice_embedding_artifact_path
    assert service_voice_profiles.voice_embedding_artifact_path_for_reference is domain_voice_artifacts.voice_embedding_artifact_path_for_reference
    assert service_voice_profiles.reference_audio_content_hash_from_paths is domain_voice_artifacts.reference_audio_content_hash_from_paths
    assert service_voice_profiles._sha256_path is domain_voice_artifacts.sha256_path
    assert domain_voice_artifacts.voice_embedding_artifact_path("vp_1") == media_dir / "voice_lab" / "embeddings" / "vp_1.pth"
    assert domain_voice_artifacts.voice_embedding_artifact_path_for_reference("vp_1", "abcdef1234567890ffff") == (
        media_dir / "voice_lab" / "embeddings" / "vp_1_abcdef1234567890.pth"
    )
    assert domain_voice_artifacts.reference_audio_content_hash_from_paths([first, second]) == (
        domain_voice_artifacts.reference_audio_content_hash_from_paths([second, first])
    )


def test_character_voice_recipe_service_shim_preserves_symbol_identity() -> None:
    assert service_character_voice_recipes.CharacterVoiceRecipe is domain_voice_recipes.CharacterVoiceRecipe
    assert service_character_voice_recipes.CharacterVoiceRecipeError is domain_voice_recipes.CharacterVoiceRecipeError
    assert service_character_voice_recipes.selected_recipe_path is domain_voice_recipes.selected_recipe_path
    assert service_character_voice_recipes.load_selected_character_recipe is domain_voice_recipes.load_selected_character_recipe
    assert service_character_voice_recipes.validate_selected_character_recipe is domain_voice_recipes.validate_selected_character_recipe
    assert service_character_voice_recipes.selected_character_recipe_status is domain_voice_recipes.selected_character_recipe_status


def test_stewie_selected_recipe_validation_preserves_payload(monkeypatch, tmp_path: Path) -> None:
    tree = _write_stewie_selected_recipe_tree(tmp_path / "voice_models")
    monkeypatch.setattr(settings, "VOICE_MODELS_DIR", str(tree["root"]))

    recipe = domain_voice_recipes.validate_selected_character_recipe("stewie_griffin")

    assert recipe.provider == "xtts"
    assert recipe.character == "stewie_griffin"
    assert recipe.checkpoint_dir == tree["checkpoint_dir"]
    assert recipe.checkpoint_file == tree["checkpoint_dir"] / "model.pth"
    assert recipe.config_path == tree["checkpoint_dir"] / "config.json"
    assert recipe.vocab_path == tree["checkpoint_dir"] / "vocab.json"
    assert len(recipe.reference_wavs) == 2
    assert recipe.golden_preview_wav == tree["golden_preview"]
    assert recipe.language == "en"
    assert recipe.settings == {"temperature": 0.7, "speed": 1.0, "split_sentences": True}


def test_stewie_selected_recipe_status_preserves_public_shape(monkeypatch, tmp_path: Path) -> None:
    tree = _write_stewie_selected_recipe_tree(tmp_path / "voice_models")
    monkeypatch.setattr(settings, "VOICE_MODELS_DIR", str(tree["root"]))

    status = domain_voice_recipes.selected_character_recipe_status("stewie_griffin")

    assert status["provider"] == "xtts"
    assert status["character"] == "stewie_griffin"
    assert status["reference_wav_count"] == 2
    assert status["golden_preview"] == str(tree["golden_preview"])
    assert status["ready_for_test_render"] is True
    assert status["golden_preview_url"] == "/voice-models/stewie_griffin/golden-preview"
    assert status["status"] == "golden_preview_selected"


def test_stewie_selected_recipe_validation_fails_closed_for_incomplete_checkpoint(monkeypatch, tmp_path: Path) -> None:
    tree = _write_stewie_selected_recipe_tree(tmp_path / "voice_models")
    monkeypatch.setattr(settings, "VOICE_MODELS_DIR", str(tree["root"]))
    (tree["checkpoint_dir"] / "model.pth").unlink()

    with pytest.raises(domain_voice_recipes.CharacterVoiceRecipeError) as exc_info:
        domain_voice_recipes.validate_selected_character_recipe("stewie_griffin")

    assert exc_info.value.code == "xtts_checkpoint_files_missing"
    assert "model.pth or equivalent checkpoint file" in exc_info.value.details["missing_files"]
