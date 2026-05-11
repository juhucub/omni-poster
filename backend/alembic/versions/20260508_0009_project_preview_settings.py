"""project preview settings and render snapshots

Revision ID: 20260508_0009
Revises: 20260427_0008
Create Date: 2026-05-08 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260508_0009"
down_revision = "20260427_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("preview_settings_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "generation_jobs",
        sa.Column("render_settings_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("generation_jobs", "render_settings_json")
    op.drop_column("projects", "preview_settings_json")
