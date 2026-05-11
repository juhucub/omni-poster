"""voice operation jobs

Revision ID: 20260511_0011
Revises: 20260509_0010
Create Date: 2026-05-11 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260511_0011"
down_revision = "20260509_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("voice_calibration_batches", sa.Column("calibration_script", sa.Text(), nullable=True))

    op.create_table(
        "voice_operation_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("voice_profile_id", sa.String(length=64), nullable=False),
        sa.Column("reference_dataset_id", sa.Integer(), nullable=True),
        sa.Column("operation_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("request_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("celery_task_id", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["reference_dataset_id"], ["voice_reference_datasets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["voice_profile_id"], ["voice_profiles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("celery_task_id", name="uq_voice_operation_jobs_celery_task_id"),
    )
    op.create_index("ix_voice_operation_jobs_user_id", "voice_operation_jobs", ["user_id"])
    op.create_index("ix_voice_operation_jobs_voice_profile_id", "voice_operation_jobs", ["voice_profile_id"])
    op.create_index("ix_voice_operation_jobs_reference_dataset_id", "voice_operation_jobs", ["reference_dataset_id"])
    op.create_index("ix_voice_operation_jobs_operation_type", "voice_operation_jobs", ["operation_type"])


def downgrade() -> None:
    op.drop_index("ix_voice_operation_jobs_operation_type", table_name="voice_operation_jobs")
    op.drop_index("ix_voice_operation_jobs_reference_dataset_id", table_name="voice_operation_jobs")
    op.drop_index("ix_voice_operation_jobs_voice_profile_id", table_name="voice_operation_jobs")
    op.drop_index("ix_voice_operation_jobs_user_id", table_name="voice_operation_jobs")
    op.drop_table("voice_operation_jobs")
    op.drop_column("voice_calibration_batches", "calibration_script")
