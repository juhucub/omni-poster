"""voice preview jobs

Revision ID: 20260424_0004
Revises: 20260422_0003
Create Date: 2026-04-24 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260424_0004"
down_revision = "20260422_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_preview_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("preset_id", sa.String(length=64), nullable=False),
        sa.Column("voice_profile_id", sa.String(length=64), nullable=False),
        sa.Column("requested_provider", sa.String(length=32), nullable=False, server_default="auto"),
        sa.Column("fallback_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sample_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("celery_task_id", sa.String(length=128), nullable=True),
        sa.Column("voice", sa.String(length=128), nullable=True),
        sa.Column("provider_used", sa.String(length=32), nullable=True),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("controls_applied_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("provider_state_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("reference_audio_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("preview_audio_path", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["preset_id"], ["character_presets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["voice_profile_id"], ["voice_profiles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("celery_task_id", name="uq_voice_preview_jobs_celery_task_id"),
    )
    op.create_index("ix_voice_preview_jobs_user_id", "voice_preview_jobs", ["user_id"])
    op.create_index("ix_voice_preview_jobs_preset_id", "voice_preview_jobs", ["preset_id"])
    op.create_index("ix_voice_preview_jobs_voice_profile_id", "voice_preview_jobs", ["voice_profile_id"])


def downgrade() -> None:
    op.drop_index("ix_voice_preview_jobs_voice_profile_id", table_name="voice_preview_jobs")
    op.drop_index("ix_voice_preview_jobs_preset_id", table_name="voice_preview_jobs")
    op.drop_index("ix_voice_preview_jobs_user_id", table_name="voice_preview_jobs")
    op.drop_table("voice_preview_jobs")
