"""generation voice manifest

Revision ID: 20260425_0005
Revises: 20260424_0004
Create Date: 2026-04-25 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260425_0005"
down_revision = "20260424_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("generation_jobs", sa.Column("voice_manifest_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("generation_jobs", sa.Column("tts_result_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("generation_jobs", sa.Column("provider_state_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    op.drop_column("generation_jobs", "provider_state_json")
    op.drop_column("generation_jobs", "tts_result_json")
    op.drop_column("generation_jobs", "voice_manifest_json")
