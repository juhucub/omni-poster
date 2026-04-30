from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import joinedload

from app.db import SessionLocal
from app.models import VoicePreviewJob, VoiceProfile
from app.services.voice_profiles import get_voice_profile_model


def _path_exists(path: str | None) -> bool:
    return bool(path and Path(path).exists())


def build_voice_profile_diagnostics(voice_profile_id: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        profile = get_voice_profile_model(voice_profile_id, db)
        if not profile:
            raise SystemExit(f"Voice profile not found: {voice_profile_id}")
        profile = (
            db.query(VoiceProfile)
            .options(joinedload(VoiceProfile.reference_audios))
            .filter(VoiceProfile.id == voice_profile_id)
            .one()
        )
        metadata = dict(profile.provider_metadata_json or {})
        latest_preview = (
            db.query(VoicePreviewJob)
            .filter(VoicePreviewJob.voice_profile_id == voice_profile_id)
            .order_by(VoicePreviewJob.id.desc())
            .first()
        )
        processed_chunks = list(metadata.get("processed_reference_chunks") or [])
        if not processed_chunks:
            for payload in dict(metadata.get("processed_reference_audio") or {}).values():
                if isinstance(payload, dict):
                    processed_chunks.extend(list(payload.get("chunks") or []))

        return {
            "voice_profile_id": profile.id,
            "display_name": profile.display_name,
            "provider": profile.provider,
            "preparation_status": metadata.get("embedding_status"),
            "reference_audio_path": [item.storage_path for item in profile.reference_audios],
            "reference_audio_sha256": metadata.get("reference_audio_sha256") or metadata.get("last_reference_audio_sha256"),
            "normalized_audio_path": metadata.get("last_reference_audio_path"),
            "normalized_audio_exists": _path_exists(metadata.get("last_reference_audio_path")),
            "processed_chunk_paths": [chunk.get("path") for chunk in processed_chunks if isinstance(chunk, dict)],
            "processed_chunk_exists": [_path_exists(chunk.get("path")) for chunk in processed_chunks if isinstance(chunk, dict)],
            "selected_chunk_durations": [
                float(chunk.get("duration_seconds") or 0)
                for chunk in processed_chunks
                if isinstance(chunk, dict)
            ],
            "target_embedding_path": metadata.get("embedding_artifact_path") or profile.embedding_path,
            "target_embedding_exists": _path_exists(metadata.get("embedding_artifact_path") or profile.embedding_path),
            "target_embedding_hash": metadata.get("target_embedding_hash"),
            "last_error": metadata.get("last_error"),
            "last_preview_output_path": latest_preview.preview_audio_path if latest_preview else None,
            "openvoice_conversion_applied": bool(latest_preview and latest_preview.provider_used == "openvoice" and not latest_preview.fallback_used),
        }
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Print Voice Lab/OpenVoice diagnostics for a voice profile.")
    parser.add_argument("voice_profile_id")
    args = parser.parse_args()
    print(json.dumps(build_voice_profile_diagnostics(args.voice_profile_id), indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
