"""tts voice profiles and speaker bindings

Revision ID: 20260422_0003
Revises: 20260421_0002
Create Date: 2026-04-22 00:00:00
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "20260422_0003"
down_revision = "20260421_0002"
branch_labels = None
depends_on = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _bundled_presets_path() -> Path:
    return _repo_root() / "backend" / "storage" / "character_presets.json"


def _runtime_presets_path() -> Path:
    media_dir = os.getenv("MEDIA_DIR", str(_repo_root() / "backend" / "storage"))
    media_path = Path(media_dir)
    if not media_path.is_absolute():
        media_path = (_repo_root() / media_path).resolve()
    return media_path / "voice_lab" / "character_presets.json"


def _load_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def upgrade() -> None:
    op.create_table(
        "voice_profiles",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="espeak"),
        sa.Column("model_id", sa.String(length=128), nullable=True),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("embedding_path", sa.Text(), nullable=True),
        sa.Column("fallback_provider", sa.String(length=32), nullable=True),
        sa.Column("fallback_voice_settings_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("style_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("controls_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("provider_metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("espeak_voice", sa.String(length=64), nullable=True),
        sa.Column("espeak_rate", sa.Integer(), nullable=True),
        sa.Column("espeak_pitch", sa.Integer(), nullable=True),
        sa.Column("espeak_word_gap", sa.Integer(), nullable=True),
        sa.Column("espeak_amplitude", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_voice_profiles_created_by_user_id", "voice_profiles", ["created_by_user_id"])

    op.create_table(
        "character_presets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("speaker_names_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("portrait_filename", sa.String(length=255), nullable=True),
        sa.Column("voice_profile_id", sa.String(length=64), nullable=False),
        sa.Column("sample_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="runtime"),
        sa.Column("is_seeded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["voice_profile_id"], ["voice_profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_character_presets_display_name", "character_presets", ["display_name"])
    op.create_index("ix_character_presets_voice_profile_id", "character_presets", ["voice_profile_id"])
    op.create_index("ix_character_presets_created_by_user_id", "character_presets", ["created_by_user_id"])

    op.create_table(
        "voice_reference_audios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("voice_profile_id", sa.String(length=64), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("authorization_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("authorization_note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["voice_profile_id"], ["voice_profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_voice_reference_audios_voice_profile_id", "voice_reference_audios", ["voice_profile_id"])
    op.create_index("ix_voice_reference_audios_sha256", "voice_reference_audios", ["sha256"])
    op.create_index("ix_voice_reference_audios_created_by_user_id", "voice_reference_audios", ["created_by_user_id"])

    op.create_table(
        "project_speaker_bindings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("speaker_name", sa.String(length=128), nullable=False),
        sa.Column("character_preset_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["character_preset_id"], ["character_presets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "speaker_name", name="uq_project_speaker_binding"),
    )
    op.create_index("ix_project_speaker_bindings_project_id", "project_speaker_bindings", ["project_id"])
    op.create_index("ix_project_speaker_bindings_character_preset_id", "project_speaker_bindings", ["character_preset_id"])

    connection = op.get_bind()
    seeded_ids: set[str] = set()
    for source, path, is_seeded in (
        ("bundled", _bundled_presets_path(), True),
        ("runtime", _runtime_presets_path(), False),
    ):
        for payload in _load_json_list(path):
            preset_id = str(payload.get("id") or "").strip()
            if not preset_id or preset_id in seeded_ids:
                continue
            voice_profile_id = f"vp_{preset_id}"
            display_name = str(payload.get("display_name") or "Speaker").strip()
            speaker_names = payload.get("speaker_names") or [display_name]
            sample_text = str(payload.get("sample_text") or "")
            notes = str(payload.get("notes") or "")
            controls = {
                "speaking_rate": payload.get("rate"),
                "pitch": payload.get("pitch"),
                "pause_length": payload.get("word_gap"),
                "energy": payload.get("amplitude"),
            }
            fallback_settings = {
                "voice": payload.get("voice"),
                "rate": payload.get("rate"),
                "pitch": payload.get("pitch"),
                "word_gap": payload.get("word_gap"),
                "amplitude": payload.get("amplitude"),
            }
            connection.execute(
                sa.text(
                    """
                    INSERT INTO voice_profiles (
                        id, display_name, provider, model_id, language, embedding_path,
                        fallback_provider, fallback_voice_settings_json, style_json, controls_json,
                        provider_metadata_json, espeak_voice, espeak_rate, espeak_pitch,
                        espeak_word_gap, espeak_amplitude, created_by_user_id, created_at, updated_at
                    ) VALUES (
                        :id, :display_name, :provider, :model_id, :language, :embedding_path,
                        :fallback_provider, :fallback_voice_settings_json, :style_json, :controls_json,
                        :provider_metadata_json, :espeak_voice, :espeak_rate, :espeak_pitch,
                        :espeak_word_gap, :espeak_amplitude, :created_by_user_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "id": voice_profile_id,
                    "display_name": display_name,
                    "provider": str(payload.get("tts_provider") or "espeak"),
                    "model_id": None,
                    "language": str(payload.get("language") or "en"),
                    "embedding_path": None,
                    "fallback_provider": "espeak",
                    "fallback_voice_settings_json": json.dumps(fallback_settings),
                    "style_json": json.dumps({}),
                    "controls_json": json.dumps(controls),
                    "provider_metadata_json": json.dumps({"migrated_from": source}),
                    "espeak_voice": payload.get("voice"),
                    "espeak_rate": payload.get("rate"),
                    "espeak_pitch": payload.get("pitch"),
                    "espeak_word_gap": payload.get("word_gap"),
                    "espeak_amplitude": payload.get("amplitude"),
                    "created_by_user_id": None,
                },
            )
            connection.execute(
                sa.text(
                    """
                    INSERT INTO character_presets (
                        id, display_name, speaker_names_json, portrait_filename, voice_profile_id,
                        sample_text, notes, source, is_seeded, created_by_user_id, created_at, updated_at
                    ) VALUES (
                        :id, :display_name, :speaker_names_json, :portrait_filename, :voice_profile_id,
                        :sample_text, :notes, :source, :is_seeded, :created_by_user_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "id": preset_id,
                    "display_name": display_name,
                    "speaker_names_json": json.dumps(speaker_names),
                    "portrait_filename": payload.get("portrait_filename"),
                    "voice_profile_id": voice_profile_id,
                    "sample_text": sample_text,
                    "notes": notes,
                    "source": source,
                    "is_seeded": is_seeded,
                    "created_by_user_id": None,
                },
            )
            seeded_ids.add(preset_id)


def downgrade() -> None:
    op.drop_index("ix_project_speaker_bindings_character_preset_id", table_name="project_speaker_bindings")
    op.drop_index("ix_project_speaker_bindings_project_id", table_name="project_speaker_bindings")
    op.drop_table("project_speaker_bindings")

    op.drop_index("ix_voice_reference_audios_created_by_user_id", table_name="voice_reference_audios")
    op.drop_index("ix_voice_reference_audios_sha256", table_name="voice_reference_audios")
    op.drop_index("ix_voice_reference_audios_voice_profile_id", table_name="voice_reference_audios")
    op.drop_table("voice_reference_audios")

    op.drop_index("ix_character_presets_created_by_user_id", table_name="character_presets")
    op.drop_index("ix_character_presets_voice_profile_id", table_name="character_presets")
    op.drop_index("ix_character_presets_display_name", table_name="character_presets")
    op.drop_table("character_presets")

    op.drop_index("ix_voice_profiles_created_by_user_id", table_name="voice_profiles")
    op.drop_table("voice_profiles")
