"""generated script json

Revision ID: 20260513_0012
Revises: 20260511_0011
Create Date: 2026-05-13 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260513_0012"
down_revision = "20260511_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("script_revisions", sa.Column("generated_script_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("script_revisions", "generated_script_json")
