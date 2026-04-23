"""review platform backbone

Revision ID: 20260421_0002
Revises: 20260421_0001
Create Date: 2026-04-21 01:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260421_0002"
down_revision = "20260421_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_preferences", sa.Column("automation_mode", sa.String(length=32), nullable=False, server_default="assisted"))
    op.add_column("user_preferences", sa.Column("preferred_account_type", sa.String(length=32), nullable=True))
    op.add_column("user_preferences", sa.Column("allowed_platforms_json", sa.JSON(), nullable=False, server_default=sa.text("'[\"youtube\"]'")))
    op.add_column("user_preferences", sa.Column("publish_windows_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))

    op.add_column("social_accounts", sa.Column("account_type", sa.String(length=32), nullable=False, server_default="owned_channel"))
    op.add_column("social_accounts", sa.Column("capabilities_json", sa.JSON(), nullable=False, server_default=sa.text("'[\"upload\",\"schedule\",\"metadata\"]'")))
    op.add_column("social_accounts", sa.Column("token_status", sa.String(length=32), nullable=False, server_default="healthy"))
    op.add_column("social_accounts", sa.Column("default_preference_rank", sa.Integer(), nullable=False, server_default="100"))

    op.add_column("projects", sa.Column("background_source_type", sa.String(length=32), nullable=False, server_default="upload"))
    op.add_column("projects", sa.Column("background_asset_id", sa.Integer(), nullable=True))
    op.add_column("projects", sa.Column("automation_mode", sa.String(length=32), nullable=False, server_default="assisted"))
    op.add_column("projects", sa.Column("preferred_account_type", sa.String(length=32), nullable=True))
    op.add_column("projects", sa.Column("allowed_platforms_json", sa.JSON(), nullable=False, server_default=sa.text("'[\"youtube\"]'")))
    op.add_column("projects", sa.Column("publish_windows_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    with op.batch_alter_table("projects") as batch_op:
        batch_op.create_foreign_key(
            "fk_projects_background_asset_id",
            "assets",
            ["background_asset_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.add_column("assets", sa.Column("source_type", sa.String(length=32), nullable=False, server_default="upload"))
    op.add_column("assets", sa.Column("preset_key", sa.String(length=64), nullable=True))
    op.add_column("assets", sa.Column("provider_name", sa.String(length=64), nullable=True))
    op.add_column("assets", sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))

    op.add_column("script_revisions", sa.Column("parent_revision_id", sa.Integer(), nullable=True))
    op.add_column("script_revisions", sa.Column("generation_provider", sa.String(length=64), nullable=True))
    with op.batch_alter_table("script_revisions") as batch_op:
        batch_op.create_foreign_key(
            "fk_script_revisions_parent_revision_id",
            "script_revisions",
            ["parent_revision_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "script_line_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("revision_id", sa.Integer(), nullable=False),
        sa.Column("line_order", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.String(length=128), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["revision_id"], ["script_revisions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_script_line_items_revision_id", "script_line_items", ["revision_id"])

    op.add_column("generation_jobs", sa.Column("output_kind", sa.String(length=32), nullable=False, server_default="preview"))
    op.add_column("generation_jobs", sa.Column("provider_name", sa.String(length=64), nullable=False, server_default="local-compositor"))

    op.add_column("output_videos", sa.Column("output_kind", sa.String(length=32), nullable=False, server_default="preview"))
    op.add_column("output_videos", sa.Column("provider_name", sa.String(length=64), nullable=False, server_default="local-compositor"))

    op.create_table(
        "review_queue_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("output_video_id", sa.Integer(), nullable=False),
        sa.Column("submitted_by_user_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("decision_summary", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["output_video_id"], ["output_videos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_review_queue_items_project_id", "review_queue_items", ["project_id"])

    op.create_table(
        "review_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("review_queue_item_id", sa.Integer(), nullable=False),
        sa.Column("author_user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="note"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["review_queue_item_id"], ["review_queue_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_review_comments_review_queue_item_id", "review_comments", ["review_queue_item_id"])

    op.add_column("platform_metadata", sa.Column("extras_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("platform_metadata", sa.Column("validation_errors_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))

    op.add_column("publish_jobs", sa.Column("routing_platform", sa.String(length=32), nullable=False, server_default="youtube"))
    op.add_column("publish_jobs", sa.Column("automation_mode", sa.String(length=32), nullable=False, server_default="assisted"))
    op.add_column("publish_jobs", sa.Column("idempotency_key", sa.String(length=128), nullable=True))

    op.create_table(
        "notification_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_notification_events_user_id", "notification_events", ["user_id"])
    op.create_index("ix_notification_events_project_id", "notification_events", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_notification_events_project_id", table_name="notification_events")
    op.drop_index("ix_notification_events_user_id", table_name="notification_events")
    op.drop_table("notification_events")

    op.drop_column("publish_jobs", "idempotency_key")
    op.drop_column("publish_jobs", "automation_mode")
    op.drop_column("publish_jobs", "routing_platform")

    op.drop_column("platform_metadata", "validation_errors_json")
    op.drop_column("platform_metadata", "extras_json")

    op.drop_index("ix_review_comments_review_queue_item_id", table_name="review_comments")
    op.drop_table("review_comments")

    op.drop_index("ix_review_queue_items_project_id", table_name="review_queue_items")
    op.drop_table("review_queue_items")

    op.drop_column("output_videos", "provider_name")
    op.drop_column("output_videos", "output_kind")

    op.drop_column("generation_jobs", "provider_name")
    op.drop_column("generation_jobs", "output_kind")

    op.drop_index("ix_script_line_items_revision_id", table_name="script_line_items")
    op.drop_table("script_line_items")

    op.drop_constraint("fk_script_revisions_parent_revision_id", "script_revisions", type_="foreignkey")
    op.drop_column("script_revisions", "generation_provider")
    op.drop_column("script_revisions", "parent_revision_id")

    op.drop_column("assets", "metadata_json")
    op.drop_column("assets", "provider_name")
    op.drop_column("assets", "preset_key")
    op.drop_column("assets", "source_type")

    op.drop_constraint("fk_projects_background_asset_id", "projects", type_="foreignkey")
    op.drop_column("projects", "publish_windows_json")
    op.drop_column("projects", "allowed_platforms_json")
    op.drop_column("projects", "preferred_account_type")
    op.drop_column("projects", "automation_mode")
    op.drop_column("projects", "background_asset_id")
    op.drop_column("projects", "background_source_type")

    op.drop_column("social_accounts", "default_preference_rank")
    op.drop_column("social_accounts", "token_status")
    op.drop_column("social_accounts", "capabilities_json")
    op.drop_column("social_accounts", "account_type")

    op.drop_column("user_preferences", "publish_windows_json")
    op.drop_column("user_preferences", "allowed_platforms_json")
    op.drop_column("user_preferences", "preferred_account_type")
    op.drop_column("user_preferences", "automation_mode")
