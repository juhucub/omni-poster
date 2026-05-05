"""voice calibration preview metadata

Revision ID: 20260426_0007
Revises: 20260426_0006
Create Date: 2026-04-26 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260426_0007"
down_revision = "20260426_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("voice_preview_jobs", sa.Column("calibration_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    op.drop_column("voice_preview_jobs", "calibration_json")
