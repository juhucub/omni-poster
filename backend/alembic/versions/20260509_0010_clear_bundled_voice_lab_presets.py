"""clear bundled Voice Lab presets

Revision ID: 20260509_0010
Revises: 20260508_0009
Create Date: 2026-05-09 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260509_0010"
down_revision = "20260508_0009"
branch_labels = None
depends_on = None


REMOVED_BUNDLED_PRESET_IDS = (
    "host_calm_v1",
    "guest_sharp_v1",
    "peter_griffin_character_v1",
    "stewie_griffin_character_v1",
)
REMOVED_BUNDLED_PROFILE_IDS = tuple(f"vp_{preset_id}" for preset_id in REMOVED_BUNDLED_PRESET_IDS)


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            DELETE FROM character_presets
            WHERE is_seeded = true
              AND source = 'bundled'
              AND id IN :preset_ids
            """
        ).bindparams(sa.bindparam("preset_ids", expanding=True)),
        {"preset_ids": REMOVED_BUNDLED_PRESET_IDS},
    )
    connection.execute(
        sa.text(
            """
            DELETE FROM voice_profiles
            WHERE created_by_user_id IS NULL
              AND id IN :profile_ids
            """
        ).bindparams(sa.bindparam("profile_ids", expanding=True)),
        {"profile_ids": REMOVED_BUNDLED_PROFILE_IDS},
    )


def downgrade() -> None:
    pass
