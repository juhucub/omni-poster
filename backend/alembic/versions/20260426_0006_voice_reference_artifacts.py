"""voice reference artifacts and validation metadata

Revision ID: 20260426_0006
Revises: 20260425_0005
Create Date: 2026-04-26 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260426_0006"
down_revision = "20260425_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("voice_reference_audios", sa.Column("original_storage_path", sa.Text(), nullable=True))
    op.add_column("voice_reference_audios", sa.Column("processed_storage_path", sa.Text(), nullable=True))
    op.add_column("voice_reference_audios", sa.Column("processed_sha256", sa.String(length=64), nullable=True))
    op.add_column("voice_reference_audios", sa.Column("validation_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column(
        "voice_reference_audios",
        sa.Column("validation_status", sa.String(length=32), nullable=False, server_default="not_validated"),
    )
    op.create_index("ix_voice_reference_audios_processed_sha256", "voice_reference_audios", ["processed_sha256"])


def downgrade() -> None:
    op.drop_index("ix_voice_reference_audios_processed_sha256", table_name="voice_reference_audios")
    op.drop_column("voice_reference_audios", "validation_status")
    op.drop_column("voice_reference_audios", "validation_json")
    op.drop_column("voice_reference_audios", "processed_sha256")
    op.drop_column("voice_reference_audios", "processed_storage_path")
    op.drop_column("voice_reference_audios", "original_storage_path")
