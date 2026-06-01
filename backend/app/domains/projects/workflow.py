from __future__ import annotations

from app.domains.projects.diagnostics import latest_review
from app.domains.projects.readiness import (
    project_has_background_asset,
    project_has_output,
    project_has_script,
)
from app.models import Project


def sync_project_state(project: Project) -> None:
    has_background = project_has_background_asset(project)
    has_script = project_has_script(project)
    has_output = project_has_output(project)
    current_review = latest_review(project)

    if project.archived_at:
        project.status = "archived"
        return
    if project.status in {"render_queued", "rendering", "publish_queued", "scheduled", "publishing", "published"}:
        return
    if current_review and current_review.status == "pending":
        project.status = "in_review"
        return
    if current_review and current_review.status == "changes_requested":
        project.status = "changes_requested"
        return
    if current_review and current_review.status == "approved" and has_output:
        project.status = "approved"
        return
    if project.approved_at and has_output:
        project.status = "approved"
        return
    if has_output:
        project.status = "preview_ready"
        return
    if has_background and has_script:
        project.status = "assets_ready"
        return
    if has_script:
        project.status = "script_ready"
        return
    project.status = "draft"
