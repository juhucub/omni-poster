"""script generation settings

Revision ID: 20260519_0013
Revises: 20260513_0012
Create Date: 2026-05-19 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260519_0013"
down_revision = "20260513_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("script_generation_settings_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("projects", "script_generation_settings_json")
