"""character voice replication datasets and calibration batches

Revision ID: 20260427_0008
Revises: 20260426_0007
Create Date: 2026-04-27 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260427_0008"
down_revision = "20260426_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_reference_datasets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("voice_profile_id", sa.String(length=64), nullable=False),
        sa.Column("character_slug", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="created"),
        sa.Column("total_duration_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("clean_speech_duration_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("accepted_clip_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_clip_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("prosody_metrics_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("selected_recipe_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["voice_profile_id"], ["voice_profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_voice_reference_datasets_voice_profile_id", "voice_reference_datasets", ["voice_profile_id"])
    op.create_index("ix_voice_reference_datasets_character_slug", "voice_reference_datasets", ["character_slug"])
    op.create_index("ix_voice_reference_datasets_created_by_user_id", "voice_reference_datasets", ["created_by_user_id"])

    op.add_column("voice_profiles", sa.Column("character_slug", sa.String(length=128), nullable=True))
    op.add_column("voice_profiles", sa.Column("reference_dataset_id", sa.Integer(), nullable=True))
    op.add_column("voice_profiles", sa.Column("model_checkpoint_path", sa.Text(), nullable=True))
    op.add_column("voice_profiles", sa.Column("selected_recipe_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("voice_profiles", sa.Column("calibration_score", sa.Float(), nullable=True))
    op.add_column("voice_profiles", sa.Column("last_verified_render_job_id", sa.Integer(), nullable=True))
    op.create_index("ix_voice_profiles_character_slug", "voice_profiles", ["character_slug"])
    op.create_index("ix_voice_profiles_reference_dataset_id", "voice_profiles", ["reference_dataset_id"])
    op.create_foreign_key(
        "fk_voice_profiles_reference_dataset_id",
        "voice_profiles",
        "voice_reference_datasets",
        ["reference_dataset_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("voice_reference_audios", sa.Column("reference_dataset_id", sa.Integer(), nullable=True))
    op.create_index("ix_voice_reference_audios_reference_dataset_id", "voice_reference_audios", ["reference_dataset_id"])
    op.create_foreign_key(
        "fk_voice_reference_audios_reference_dataset_id",
        "voice_reference_audios",
        "voice_reference_datasets",
        ["reference_dataset_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "voice_calibration_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("voice_profile_id", sa.String(length=64), nullable=False),
        sa.Column("reference_dataset_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="created"),
        sa.Column("provider_state_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("candidates_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("rankings_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reference_dataset_id"], ["voice_reference_datasets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["voice_profile_id"], ["voice_profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_voice_calibration_batches_voice_profile_id", "voice_calibration_batches", ["voice_profile_id"])
    op.create_index("ix_voice_calibration_batches_reference_dataset_id", "voice_calibration_batches", ["reference_dataset_id"])
    op.create_index("ix_voice_calibration_batches_created_by_user_id", "voice_calibration_batches", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_voice_calibration_batches_created_by_user_id", table_name="voice_calibration_batches")
    op.drop_index("ix_voice_calibration_batches_reference_dataset_id", table_name="voice_calibration_batches")
    op.drop_index("ix_voice_calibration_batches_voice_profile_id", table_name="voice_calibration_batches")
    op.drop_table("voice_calibration_batches")

    op.drop_constraint("fk_voice_reference_audios_reference_dataset_id", "voice_reference_audios", type_="foreignkey")
    op.drop_index("ix_voice_reference_audios_reference_dataset_id", table_name="voice_reference_audios")
    op.drop_column("voice_reference_audios", "reference_dataset_id")

    op.drop_constraint("fk_voice_profiles_reference_dataset_id", "voice_profiles", type_="foreignkey")
    op.drop_index("ix_voice_profiles_reference_dataset_id", table_name="voice_profiles")
    op.drop_index("ix_voice_profiles_character_slug", table_name="voice_profiles")
    op.drop_column("voice_profiles", "last_verified_render_job_id")
    op.drop_column("voice_profiles", "calibration_score")
    op.drop_column("voice_profiles", "selected_recipe_json")
    op.drop_column("voice_profiles", "model_checkpoint_path")
    op.drop_column("voice_profiles", "reference_dataset_id")
    op.drop_column("voice_profiles", "character_slug")

    op.drop_index("ix_voice_reference_datasets_created_by_user_id", table_name="voice_reference_datasets")
    op.drop_index("ix_voice_reference_datasets_character_slug", table_name="voice_reference_datasets")
    op.drop_index("ix_voice_reference_datasets_voice_profile_id", table_name="voice_reference_datasets")
    op.drop_table("voice_reference_datasets")
