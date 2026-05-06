from __future__ import annotations

import hashlib
import math
import re
import shutil
import wave
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models import GenerationJob, VoiceCalibrationBatch, VoiceProfile, VoiceReferenceDataset
from app.schemas import VoiceCalibrationCandidateRequest
from app.services.tts import TTSOrchestrator, TTSProviderError
from app.services.voice_profiles import (
    ensure_voice_profile_editable,
    get_voice_profile,
    get_voice_profile_model,
    save_reference_audio_upload,
    update_voice_profile_calibration_recipe,
    voice_lab_preview_dir,
    voice_models_dir,
)


DEFAULT_CALIBRATION_CANDIDATES = [
    {"provider": "xtts", "style_preset": "default", "rate": 0.95, "pitch_shift": 0.0, "pause_scale": 1.0},
    {"provider": "xtts", "style_preset": "default", "rate": 1.05, "pitch_shift": 1.0, "pause_scale": 0.9},
    {"provider": "rvc", "style_preset": "default", "rate": 1.0, "rvc_pitch_shift": 0.0, "rvc_index_rate": 0.75},
    {"provider": "openvoice", "style_preset": "default", "rate": 1.0, "openvoice_tone_color": True},
]


def slugify_character(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "character"


def character_voice_model_dir(character_slug: str) -> Path:
    root = voice_models_dir() / slugify_character(character_slug)
    for child in ("dataset", "processed", "xtts", "rvc"):
        path = root / child
        path.mkdir(parents=True, exist_ok=True)
        keep = path / ".gitkeep"
        if not keep.exists():
            keep.touch()
    return root


def seed_character_voice_model_dirs() -> None:
    for slug in ("peter_griffin", "stewie_griffin"):
        character_voice_model_dir(slug)


def serialize_reference_dataset(dataset: VoiceReferenceDataset) -> dict[str, Any]:
    return {
        "id": dataset.id,
        "voice_profile_id": dataset.voice_profile_id,
        "character_slug": dataset.character_slug,
        "display_name": dataset.display_name,
        "storage_path": dataset.storage_path,
        "status": dataset.status,
        "total_duration_seconds": float(dataset.total_duration_seconds or 0.0),
        "clean_speech_duration_seconds": float(dataset.clean_speech_duration_seconds or 0.0),
        "accepted_clip_count": int(dataset.accepted_clip_count or 0),
        "rejected_clip_count": int(dataset.rejected_clip_count or 0),
        "metrics": dict(dataset.metrics_json or {}),
        "prosody_metrics": dict(dataset.prosody_metrics_json or {}),
        "selected_recipe": dict(dataset.selected_recipe_json or {}),
        "created_at": dataset.created_at,
        "updated_at": dataset.updated_at,
    }


def serialize_calibration_batch(batch: VoiceCalibrationBatch) -> dict[str, Any]:
    return {
        "id": batch.id,
        "voice_profile_id": batch.voice_profile_id,
        "reference_dataset_id": batch.reference_dataset_id,
        "status": batch.status,
        "provider_state": dict(batch.provider_state_json or {}),
        "candidates": list(batch.candidates_json or []),
        "rankings": list(batch.rankings_json or []),
        "error": dict(batch.error_json or {}) if batch.error_json else None,
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
    }


def _get_dataset(dataset_id: int, voice_profile_id: str, db: Session) -> VoiceReferenceDataset:
    dataset = (
        db.query(VoiceReferenceDataset)
        .options(joinedload(VoiceReferenceDataset.reference_audios))
        .filter(VoiceReferenceDataset.id == dataset_id, VoiceReferenceDataset.voice_profile_id == voice_profile_id)
        .one_or_none()
    )
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice reference dataset not found")
    return dataset


def create_reference_dataset(
    *,
    voice_profile_id: str,
    display_name: str | None,
    character_slug: str | None,
    current_user_id: int,
    db: Session,
) -> tuple[dict[str, Any], dict[str, Any]]:
    profile = get_voice_profile_model(voice_profile_id, db)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found")
    ensure_voice_profile_editable(profile, current_user_id)
    slug = slugify_character(character_slug or profile.character_slug or display_name or profile.display_name)
    root = character_voice_model_dir(slug)
    dataset = VoiceReferenceDataset(
        voice_profile_id=voice_profile_id,
        character_slug=slug,
        display_name=display_name or profile.display_name,
        storage_path=str(root),
        status="created",
        created_by_user_id=current_user_id,
    )
    db.add(dataset)
    db.flush()
    profile.character_slug = slug
    profile.reference_dataset_id = dataset.id
    db.commit()
    db.refresh(dataset)
    return get_voice_profile(profile.id, db), serialize_reference_dataset(dataset)


def upload_reference_dataset_clip(
    *,
    voice_profile_id: str,
    reference_dataset_id: int,
    file: UploadFile,
    current_user_id: int,
    authorization_confirmed: bool,
    authorization_note: str | None,
    db: Session,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    dataset = _get_dataset(reference_dataset_id, voice_profile_id, db)
    profile_payload, reference_audio = save_reference_audio_upload(
        file=file,
        voice_profile_id=voice_profile_id,
        current_user_id=current_user_id,
        authorization_confirmed=authorization_confirmed,
        authorization_note=authorization_note,
        db=db,
        reference_dataset_id=dataset.id,
    )
    dataset = _get_dataset(reference_dataset_id, voice_profile_id, db)
    update_reference_dataset_metrics(dataset, db=db)
    profile_payload = get_voice_profile(voice_profile_id, db)
    return profile_payload, serialize_reference_dataset(dataset), reference_audio


def analyze_voice_reference_dataset(
    *,
    voice_profile_id: str,
    reference_dataset_id: int,
    current_user_id: int,
    db: Session,
) -> tuple[dict[str, Any], dict[str, Any]]:
    profile = get_voice_profile_model(voice_profile_id, db)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found")
    ensure_voice_profile_editable(profile, current_user_id)
    dataset = _get_dataset(reference_dataset_id, voice_profile_id, db)
    update_reference_dataset_metrics(dataset, db=db)
    paths = [
        Path(item.processed_storage_path or item.storage_path)
        for item in dataset.reference_audios
        if item.validation_status != "rejected" and (item.processed_storage_path or item.storage_path)
    ]
    prosody_items = [analyze_audio_prosody(path) for path in paths if path.exists()]
    prosody = aggregate_prosody_metrics(prosody_items)
    dataset.prosody_metrics_json = prosody
    dataset.status = "analyzed" if prosody_items else "needs_reference_audio"
    profile.reference_dataset_id = dataset.id
    metadata = dict(profile.provider_metadata_json or {})
    metadata["target_prosody_metrics"] = prosody
    metadata["reference_dataset_metrics"] = dict(dataset.metrics_json or {})
    profile.provider_metadata_json = metadata
    db.commit()
    db.refresh(dataset)
    return get_voice_profile(voice_profile_id, db), serialize_reference_dataset(dataset)


def update_reference_dataset_metrics(dataset: VoiceReferenceDataset, *, db: Session) -> VoiceReferenceDataset:
    db.refresh(dataset)
    accepted = [item for item in dataset.reference_audios if item.validation_status != "rejected"]
    rejected = [item for item in dataset.reference_audios if item.validation_status == "rejected"]
    total_duration = 0.0
    clean_speech_duration = 0.0
    clipping_ratios: list[float] = []
    silence_ratios: list[float] = []
    snr_values: list[float] = []
    for item in accepted:
        validation = dict(item.validation_json or {})
        metrics = dict(validation.get("metrics") or {})
        duration = float(metrics.get("duration_seconds") or (item.duration_ms or 0) / 1000)
        speech = float(metrics.get("speech_duration_seconds") or 0.0)
        speech_ratio = float(metrics.get("speech_ratio") or 0.0)
        clipped = metrics.get("clipped_sample_ratio")
        rms = float(metrics.get("rms_ratio") or 0.0)
        total_duration += duration
        clean_speech_duration += speech
        silence_ratios.append(max(0.0, 1.0 - speech_ratio))
        if clipped is not None:
            clipping_ratios.append(float(clipped))
        snr_values.append(round(20 * math.log10(max(rms, 1e-6) / 1e-4), 3))
    metrics_payload = {
        "total_duration_seconds": round(total_duration, 3),
        "clean_speech_duration_seconds": round(clean_speech_duration, 3),
        "accepted_clip_count": len(accepted),
        "rejected_clip_count": len(rejected),
        "average_snr_db_estimate": round(float(np.mean(snr_values)), 3) if snr_values else None,
        "clipping_ratio": round(float(np.mean(clipping_ratios)), 6) if clipping_ratios else 0.0,
        "silence_ratio": round(float(np.mean(silence_ratios)), 4) if silence_ratios else 0.0,
    }
    dataset.total_duration_seconds = metrics_payload["total_duration_seconds"]
    dataset.clean_speech_duration_seconds = metrics_payload["clean_speech_duration_seconds"]
    dataset.accepted_clip_count = metrics_payload["accepted_clip_count"]
    dataset.rejected_clip_count = metrics_payload["rejected_clip_count"]
    dataset.metrics_json = metrics_payload
    dataset.status = "ready" if accepted else "needs_reference_audio"
    metrics_path = Path(dataset.storage_path) / "metrics.json"
    metrics_path.write_text(_json_dump(metrics_payload), encoding="utf-8")
    db.commit()
    db.refresh(dataset)
    return dataset


def analyze_audio_prosody(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as handle:
        frame_rate = handle.getframerate()
        channels = handle.getnchannels()
        frame_count = handle.getnframes()
        raw = handle.readframes(frame_count)
    if frame_rate <= 0 or not raw:
        return {}
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape((-1, channels)).mean(axis=1)
    duration = float(len(samples) / frame_rate)
    frame_size = max(int(frame_rate * 0.03), 1)
    hop = max(int(frame_rate * 0.015), 1)
    energies: list[float] = []
    pitches: list[float] = []
    voiced_flags: list[bool] = []
    for start in range(0, max(len(samples) - frame_size, 1), hop):
        frame = samples[start : start + frame_size]
        if len(frame) < frame_size:
            break
        rms = float(np.sqrt(np.mean(frame * frame)))
        energies.append(rms)
        threshold = max(0.012, float(np.percentile(np.abs(samples), 35)) * 1.25)
        voiced = rms >= threshold
        voiced_flags.append(voiced)
        pitch = _estimate_pitch_autocorrelation(frame, frame_rate) if voiced else 0.0
        if pitch > 0:
            pitches.append(pitch)
    silence_runs = _count_silence_runs(voiced_flags, hop / frame_rate)
    pitch_arr = np.array(pitches, dtype=np.float32)
    energy_arr = np.array(energies, dtype=np.float32)
    pitch_min = float(np.min(pitch_arr)) if pitch_arr.size else 0.0
    pitch_max = float(np.max(pitch_arr)) if pitch_arr.size else 0.0
    pitch_median = float(np.median(pitch_arr)) if pitch_arr.size else 0.0
    phrase_movement = _phrase_pitch_movement(pitches)
    return {
        "duration_seconds": round(duration, 3),
        "pitch_median_hz": round(pitch_median, 3),
        "pitch_mean_hz": round(float(np.mean(pitch_arr)), 3) if pitch_arr.size else 0.0,
        "pitch_std_hz": round(float(np.std(pitch_arr)), 3) if pitch_arr.size else 0.0,
        "pitch_min_hz": round(pitch_min, 3),
        "pitch_max_hz": round(pitch_max, 3),
        "pitch_range_semitones": round(12 * math.log2(pitch_max / pitch_min), 3) if pitch_min > 0 and pitch_max > pitch_min else 0.0,
        "speaking_rate": round(_speaking_rate_proxy(voiced_flags, duration), 3),
        "pause_count": silence_runs["pause_count"],
        "mean_pause_length_seconds": silence_runs["mean_pause_length_seconds"],
        "silence_ratio": round(1.0 - (sum(1 for item in voiced_flags if item) / len(voiced_flags)), 4) if voiced_flags else 1.0,
        "energy_mean": round(float(np.mean(energy_arr)), 6) if energy_arr.size else 0.0,
        "energy_variance": round(float(np.var(energy_arr)), 8) if energy_arr.size else 0.0,
        "voiced_ratio": round(sum(1 for item in voiced_flags if item) / len(voiced_flags), 4) if voiced_flags else 0.0,
        "phrase_pitch_movement": phrase_movement,
        "sentence_ending_intonation": _sentence_ending_intonation(pitches),
    }


def audio_verification_metrics(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as handle:
        frame_rate = handle.getframerate()
        channels = handle.getnchannels()
        frame_count = handle.getnframes()
        raw = handle.readframes(frame_count)
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0 if raw else np.array([], dtype=np.float32)
    if channels > 1 and samples.size:
        samples = samples.reshape((-1, channels)).mean(axis=1)
    rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0
    loudness_dbfs = 20 * math.log10(max(rms, 1e-9))
    return {
        "path": str(path),
        "exists": path.exists(),
        "duration_seconds": round(float(frame_count / frame_rate), 3) if frame_rate else 0.0,
        "sample_rate": frame_rate,
        "channels": channels,
        "loudness_dbfs": round(loudness_dbfs, 3),
    }


def _estimate_pitch_autocorrelation(frame: np.ndarray, sample_rate: int) -> float:
    frame = frame - np.mean(frame)
    if not np.any(frame):
        return 0.0
    corr = np.correlate(frame, frame, mode="full")[len(frame) - 1 :]
    min_lag = max(int(sample_rate / 450), 1)
    max_lag = min(int(sample_rate / 60), len(corr) - 1)
    if max_lag <= min_lag:
        return 0.0
    lag = int(np.argmax(corr[min_lag:max_lag]) + min_lag)
    confidence = corr[lag] / max(corr[0], 1e-9)
    return float(sample_rate / lag) if confidence > 0.28 else 0.0


def _count_silence_runs(voiced_flags: list[bool], hop_seconds: float) -> dict[str, Any]:
    pauses: list[float] = []
    current = 0
    for voiced in voiced_flags:
        if not voiced:
            current += 1
        elif current:
            duration = current * hop_seconds
            if duration >= 0.12:
                pauses.append(duration)
            current = 0
    if current:
        duration = current * hop_seconds
        if duration >= 0.12:
            pauses.append(duration)
    return {
        "pause_count": len(pauses),
        "mean_pause_length_seconds": round(float(np.mean(pauses)), 3) if pauses else 0.0,
    }


def _speaking_rate_proxy(voiced_flags: list[bool], duration: float) -> float:
    if duration <= 0:
        return 0.0
    transitions = sum(1 for previous, current in zip(voiced_flags, voiced_flags[1:], strict=False) if current and not previous)
    voiced_ratio = sum(1 for item in voiced_flags if item) / len(voiced_flags) if voiced_flags else 0.0
    return max(transitions, 1) * voiced_ratio / duration


def _phrase_pitch_movement(pitches: list[float]) -> dict[str, float]:
    if len(pitches) < 4:
        return {"slope_hz_per_frame": 0.0, "mean_abs_delta_hz": 0.0}
    x = np.arange(len(pitches), dtype=np.float32)
    y = np.array(pitches, dtype=np.float32)
    slope = float(np.polyfit(x, y, 1)[0])
    return {
        "slope_hz_per_frame": round(slope, 4),
        "mean_abs_delta_hz": round(float(np.mean(np.abs(np.diff(y)))), 3),
    }


def _sentence_ending_intonation(pitches: list[float]) -> str:
    if len(pitches) < 6:
        return "flat"
    first = float(np.median(pitches[: max(2, len(pitches) // 3)]))
    last = float(np.median(pitches[-max(2, len(pitches) // 3) :]))
    delta = last - first
    if delta > 8:
        return "rising"
    if delta < -8:
        return "falling"
    return "flat"


def aggregate_prosody_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        return {}
    scalar_keys = [
        "pitch_median_hz",
        "pitch_mean_hz",
        "pitch_std_hz",
        "pitch_min_hz",
        "pitch_max_hz",
        "pitch_range_semitones",
        "speaking_rate",
        "pause_count",
        "mean_pause_length_seconds",
        "silence_ratio",
        "energy_mean",
        "energy_variance",
        "voiced_ratio",
    ]
    aggregate = {
        key: round(float(np.mean([float(item.get(key) or 0.0) for item in items])), 4)
        for key in scalar_keys
    }
    aggregate["phrase_pitch_movement"] = {
        "slope_hz_per_frame": round(float(np.mean([float((item.get("phrase_pitch_movement") or {}).get("slope_hz_per_frame") or 0.0) for item in items])), 4),
        "mean_abs_delta_hz": round(float(np.mean([float((item.get("phrase_pitch_movement") or {}).get("mean_abs_delta_hz") or 0.0) for item in items])), 4),
    }
    endings = [str(item.get("sentence_ending_intonation") or "flat") for item in items]
    aggregate["sentence_ending_intonation"] = max(set(endings), key=endings.count)
    aggregate["source_clip_count"] = len(items)
    return aggregate


def attach_character_voice_model(
    *,
    voice_profile_id: str,
    provider: str,
    character_slug: str | None,
    model_checkpoint_path: str,
    model_index_path: str | None,
    reference_dataset_id: int | None,
    recipe: dict[str, Any],
    current_user_id: int,
    db: Session,
) -> dict[str, Any]:
    profile = get_voice_profile_model(voice_profile_id, db)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found")
    ensure_voice_profile_editable(profile, current_user_id)
    checkpoint = Path(model_checkpoint_path)
    if not checkpoint.exists():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Model/checkpoint path does not exist")
    if reference_dataset_id is not None:
        _get_dataset(reference_dataset_id, voice_profile_id, db)
    if character_slug:
        profile.character_slug = slugify_character(character_slug)
    profile.provider = provider.lower()
    profile.model_checkpoint_path = str(checkpoint)
    profile.reference_dataset_id = reference_dataset_id or profile.reference_dataset_id
    next_recipe = {
        **dict(recipe or {}),
        "provider": provider.lower(),
        "model_checkpoint_path": str(checkpoint),
        "model_index_path": model_index_path,
        "reference_dataset_id": profile.reference_dataset_id,
    }
    profile.selected_recipe_json = next_recipe
    metadata = dict(profile.provider_metadata_json or {})
    metadata["attached_character_model"] = {
        "provider": provider.lower(),
        "model_checkpoint_path": str(checkpoint),
        "model_index_path": model_index_path,
        "reference_dataset_id": profile.reference_dataset_id,
    }
    profile.provider_metadata_json = metadata
    db.commit()
    return get_voice_profile(voice_profile_id, db)


def create_calibration_batch(
    *,
    voice_profile_id: str,
    reference_dataset_id: int | None,
    calibration_script: str,
    candidates: list[VoiceCalibrationCandidateRequest],
    current_user_id: int,
    db: Session,
) -> dict[str, Any]:
    profile = get_voice_profile_model(voice_profile_id, db)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found")
    ensure_voice_profile_editable(profile, current_user_id)
    dataset = _get_dataset(reference_dataset_id, voice_profile_id, db) if reference_dataset_id else (
        _get_dataset(profile.reference_dataset_id, voice_profile_id, db) if profile.reference_dataset_id else None
    )
    target_metrics = dict(dataset.prosody_metrics_json or {}) if dataset else dict((profile.provider_metadata_json or {}).get("target_prosody_metrics") or {})
    if not target_metrics and dataset:
        _, dataset_payload = analyze_voice_reference_dataset(
            voice_profile_id=voice_profile_id,
            reference_dataset_id=dataset.id,
            current_user_id=current_user_id,
            db=db,
        )
        dataset = _get_dataset(dataset_payload["id"], voice_profile_id, db)
        target_metrics = dict(dataset.prosody_metrics_json or {})
    orchestrator = TTSOrchestrator()
    provider_state = orchestrator.provider_state()
    batch = VoiceCalibrationBatch(
        voice_profile_id=voice_profile_id,
        reference_dataset_id=dataset.id if dataset else None,
        status="processing",
        provider_state_json=provider_state,
        created_by_user_id=current_user_id,
    )
    db.add(batch)
    db.flush()
    candidate_payloads = [item.model_dump() for item in candidates] or [dict(item) for item in DEFAULT_CALIBRATION_CANDIDATES]
    results: list[dict[str, Any]] = []
    rankings: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidate_payloads[:12]):
        result = _run_calibration_candidate(
            profile=profile,
            candidate=candidate,
            calibration_script=calibration_script,
            target_metrics=target_metrics,
            orchestrator=orchestrator,
            batch_id=batch.id,
            index=index,
        )
        results.append(result)
        if result.get("status") == "completed":
            rankings.append(result)
    rankings = sorted(rankings, key=lambda item: float(item.get("score") or 0.0), reverse=True)
    batch.candidates_json = results
    batch.rankings_json = rankings
    batch.status = "completed" if rankings else "failed"
    if not rankings:
        batch.error_json = {"code": "no_calibration_candidates_completed", "message": "No calibration candidate produced a usable preview."}
    db.commit()
    db.refresh(batch)
    return serialize_calibration_batch(batch)


def _run_calibration_candidate(
    *,
    profile: VoiceProfile,
    candidate: dict[str, Any],
    calibration_script: str,
    target_metrics: dict[str, Any],
    orchestrator: TTSOrchestrator,
    batch_id: int,
    index: int,
) -> dict[str, Any]:
    provider = str(candidate.get("provider") or profile.provider or "espeak").lower()
    output_path = voice_lab_preview_dir() / f"calibration_batch_{batch_id}_{index:03d}.wav"
    recipe = _candidate_to_recipe(candidate, profile)
    payload = {
        "id": profile.id,
        "display_name": profile.display_name,
        "provider": provider,
        "fallback_provider": profile.fallback_provider,
        "voice": profile.espeak_voice,
        "espeak_voice": profile.espeak_voice,
        "espeak_rate": profile.espeak_rate,
        "espeak_pitch": profile.espeak_pitch,
        "espeak_word_gap": profile.espeak_word_gap,
        "espeak_amplitude": profile.espeak_amplitude,
        "controls": {
            **dict(profile.controls_json or {}),
            "speaking_rate": recipe.get("speaking_rate"),
            "pitch": recipe.get("pitch_shift"),
            "pause_length": recipe.get("pause_scale"),
            "energy": recipe.get("energy_normalization"),
        },
        "style": {
            **dict(profile.style_json or {}),
            "base_speaker": recipe.get("base_speaker"),
            "style_preset": recipe.get("style_preset"),
        },
        "fallback_voice_settings": dict(profile.fallback_voice_settings_json or {}),
        "reference_audios": [
            {
                "id": item.id,
                "storage_path": item.storage_path,
                "processed_storage_path": item.processed_storage_path or item.storage_path,
                "sha256": item.sha256,
                "processed_sha256": item.processed_sha256,
                "validation_status": item.validation_status,
            }
            for item in profile.reference_audios
        ],
        "language": profile.language,
        "model_id": profile.model_id,
        "model_checkpoint_path": recipe.get("model_checkpoint_path") or profile.model_checkpoint_path,
        "embedding_path": profile.embedding_path,
        "provider_metadata": dict(profile.provider_metadata_json or {}),
        "selected_recipe": recipe,
    }
    try:
        result = orchestrator.synthesize_line(
            text=calibration_script,
            voice_profile=payload,
            output_path=output_path,
            requested_provider=provider,
            fallback_allowed=False,
        )
        metrics = analyze_audio_prosody(Path(result.audio_path))
        score_payload = score_calibration_candidate(target_metrics, metrics, timbre_similarity=_timbre_similarity_proxy(profile, candidate))
        return {
            "status": "completed",
            "candidate_index": index,
            "provider": provider,
            "preview_audio_path": result.audio_path,
            "content_url": f"/voice-lab/previews/{Path(result.audio_path).name}",
            "recipe": recipe,
            "metrics": metrics,
            **score_payload,
        }
    except TTSProviderError as exc:
        return {
            "status": "failed",
            "candidate_index": index,
            "provider": provider,
            "recipe": recipe,
            "error": exc.as_dict(),
        }


def _candidate_to_recipe(candidate: dict[str, Any], profile: VoiceProfile) -> dict[str, Any]:
    return {
        "provider": str(candidate.get("provider") or profile.provider or "espeak").lower(),
        "base_speaker": candidate.get("base_speaker"),
        "style_preset": candidate.get("style_preset") or "default",
        "speaking_rate": float(candidate.get("rate") or 1.0),
        "pitch_shift": float(candidate.get("pitch_shift") or 0.0),
        "pause_scale": float(candidate.get("pause_scale") or 1.0),
        "punctuation_pause_bias": float(candidate.get("punctuation_pause_bias") or 1.0),
        "energy_normalization": float(candidate.get("energy_normalization") or 1.0),
        "rvc_pitch_shift": float(candidate.get("rvc_pitch_shift") or 0.0),
        "rvc_index_rate": float(candidate.get("rvc_index_rate") or 0.75),
        "rvc_protect": float(candidate.get("rvc_protect") or 0.33),
        "rvc_filter_radius": int(candidate.get("rvc_filter_radius") or 3),
        "openvoice_tone_color": bool(candidate.get("openvoice_tone_color")),
        "model_checkpoint_path": candidate.get("model_checkpoint_path") or profile.model_checkpoint_path,
        "reference_dataset_id": profile.reference_dataset_id,
    }


def score_calibration_candidate(target: dict[str, Any], generated: dict[str, Any], *, timbre_similarity: float = 0.0) -> dict[str, Any]:
    if not target:
        target = generated
    pitch_median_similarity = _similarity(float(target.get("pitch_median_hz") or 0.0), float(generated.get("pitch_median_hz") or 0.0), 80.0)
    pitch_range_similarity = _similarity(float(target.get("pitch_range_semitones") or 0.0), float(generated.get("pitch_range_semitones") or 0.0), 8.0)
    speaking_rate_similarity = _similarity(float(target.get("speaking_rate") or 0.0), float(generated.get("speaking_rate") or 0.0), 2.0)
    pause_similarity = (
        _similarity(float(target.get("pause_count") or 0.0), float(generated.get("pause_count") or 0.0), 4.0)
        + _similarity(float(target.get("mean_pause_length_seconds") or 0.0), float(generated.get("mean_pause_length_seconds") or 0.0), 0.6)
    ) / 2.0
    energy_similarity = _similarity(float(target.get("energy_mean") or 0.0), float(generated.get("energy_mean") or 0.0), 0.12)
    phrase_similarity = _similarity(
        float((target.get("phrase_pitch_movement") or {}).get("mean_abs_delta_hz") or 0.0),
        float((generated.get("phrase_pitch_movement") or {}).get("mean_abs_delta_hz") or 0.0),
        35.0,
    )
    rhythm_score = (speaking_rate_similarity + pause_similarity + phrase_similarity) / 3.0
    score = (
        0.25 * timbre_similarity
        + 0.20 * pitch_median_similarity
        + 0.20 * pitch_range_similarity
        + 0.15 * speaking_rate_similarity
        + 0.10 * pause_similarity
        + 0.10 * energy_similarity
    )
    return {
        "score": round(score, 4),
        "timbre_score": round(timbre_similarity, 4),
        "pitch_score": round((pitch_median_similarity + pitch_range_similarity) / 2.0, 4),
        "rhythm_score": round(rhythm_score, 4),
        "pause_score": round(pause_similarity, 4),
        "energy_score": round(energy_similarity, 4),
    }


def _similarity(target: float, generated: float, scale: float) -> float:
    if target == generated:
        return 1.0
    return max(0.0, 1.0 - abs(target - generated) / max(scale, 1e-6))


def _timbre_similarity_proxy(profile: VoiceProfile, candidate: dict[str, Any]) -> float:
    provider = str(candidate.get("provider") or profile.provider or "").lower()
    if provider in {"xtts", "rvc"} and (candidate.get("model_checkpoint_path") or profile.model_checkpoint_path):
        return 0.82
    if provider == "openvoice" and profile.embedding_path:
        return 0.68
    return 0.25 if provider == "espeak" else 0.35


def save_best_calibration_recipe(
    *,
    voice_profile_id: str,
    recipe: dict[str, Any],
    current_user_id: int,
    db: Session,
) -> dict[str, Any]:
    profile = get_voice_profile_model(voice_profile_id, db)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found")
    ensure_voice_profile_editable(profile, current_user_id)
    updated = update_voice_profile_calibration_recipe(profile, recipe=recipe, db=db)
    if updated.reference_dataset_id:
        dataset = _get_dataset(updated.reference_dataset_id, voice_profile_id, db)
        dataset.selected_recipe_json = dict(recipe)
        selected_recipe_path = Path(dataset.storage_path) / "selected_recipe.json"
        selected_recipe_path.write_text(_json_dump(recipe), encoding="utf-8")
        db.commit()
    return get_voice_profile(voice_profile_id, db)


def verify_character_voice_render(
    *,
    voice_profile_id: str,
    generation_job_id: int,
    current_user_id: int,
    db: Session,
) -> dict[str, Any]:
    profile = get_voice_profile_model(voice_profile_id, db)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found")
    ensure_voice_profile_editable(profile, current_user_id)
    job = (
        db.query(GenerationJob)
        .filter(GenerationJob.id == generation_job_id)
        .one_or_none()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation job not found")
    tts_result = dict(job.tts_result_json or {})
    segments = [item for item in list(tts_result.get("segments") or []) if item.get("voice_profile_id") == voice_profile_id]
    if not segments:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Render job does not contain this voice profile")
    failures: list[dict[str, Any]] = []
    for segment in segments:
        if segment.get("fallback_used"):
            failures.append({"code": "fallback_used", "message": "Fallback TTS was used for a render-verified character profile."})
        if segment.get("provider_used") != profile.provider:
            failures.append({"code": "provider_mismatch", "message": "Render segment provider does not match the saved voice profile provider."})
        expected_model = profile.model_checkpoint_path or (profile.selected_recipe_json or {}).get("model_checkpoint_path")
        actual_model = (segment.get("voice_profile_settings") or {}).get("model_checkpoint_path") or (segment.get("selected_recipe") or {}).get("model_checkpoint_path")
        if expected_model and actual_model and str(expected_model) != str(actual_model):
            failures.append({"code": "model_path_mismatch", "message": "Render segment model path does not match the saved recipe."})
        audio_path = Path(str(segment.get("audio_path") or ""))
        if not audio_path.exists():
            failures.append({"code": "missing_segment_audio", "message": "Persisted render segment WAV is missing."})
        golden_preview_value = str(segment.get("golden_preview_wav") or "")
        golden_preview = Path(golden_preview_value) if golden_preview_value else None
        if profile.character_slug == "stewie_griffin" and (not golden_preview or not golden_preview.exists()):
            failures.append({"code": "missing_golden_preview", "message": "Stewie render metadata is missing the selected golden preview WAV."})
    assembly = dict(tts_result.get("assembly") or {})
    composite_value = str(assembly.get("composite_audio_path") or "")
    final_audio_value = str(assembly.get("final_video_audio_path") or "")
    composite_path = Path(composite_value) if composite_value else None
    final_audio_path = Path(final_audio_value) if final_audio_value else None
    if not composite_path or not composite_path.exists():
        failures.append({"code": "missing_composite_audio", "message": "Dialogue composite WAV is missing."})
    if not final_audio_path or not final_audio_path.exists():
        failures.append({"code": "missing_final_extracted_audio", "message": "Final extracted video audio is missing."})
    if composite_path and final_audio_path and composite_path.exists() and final_audio_path.exists():
        composite_metrics = analyze_audio_prosody(composite_path)
        final_metrics = analyze_audio_prosody(final_audio_path)
        duration_delta = abs(float(composite_metrics.get("duration_seconds") or 0.0) - float(final_metrics.get("duration_seconds") or 0.0))
        if duration_delta > 0.35:
            failures.append({"code": "duration_mismatch", "message": "Final extracted audio duration differs from the dialogue composite WAV."})
    audio_checks = []
    for segment in segments:
        for label, raw_path in (
            ("golden_preview_wav", segment.get("golden_preview_wav")),
            ("render_segment_wav", segment.get("audio_path")),
        ):
            if not raw_path:
                continue
            path = Path(str(raw_path))
            if path.exists() and path.is_file():
                audio_checks.append({"kind": label, **audio_verification_metrics(path)})
    if composite_path and composite_path.exists():
        audio_checks.append({"kind": "composite_audio_wav", **audio_verification_metrics(composite_path)})
    if final_audio_path and final_audio_path.exists():
        audio_checks.append({"kind": "final_video_extracted_audio", **audio_verification_metrics(final_audio_path)})
    verification = {
        "status": "failed" if failures else "passed",
        "failures": failures,
        "segments_checked": len(segments),
        "golden_preview_wav": segments[0].get("golden_preview_wav"),
        "render_segment_wavs": [item.get("audio_path") for item in segments],
        "composite_audio_path": str(composite_path) if composite_path else None,
        "final_video_audio_path": str(final_audio_path) if final_audio_path else None,
        "recipe_used": segments[0].get("recipe_used") or segments[0].get("selected_recipe") or {},
        "fallback_used": any(bool(item.get("fallback_used")) for item in segments),
        "audio_checks": audio_checks,
    }
    if failures:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=verification)
    profile.last_verified_render_job_id = generation_job_id
    metadata = dict(profile.provider_metadata_json or {})
    metadata["last_render_verification"] = verification
    profile.provider_metadata_json = metadata
    db.commit()
    return {"voice_profile": get_voice_profile(voice_profile_id, db), "verification": verification}


def _json_dump(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=True)
