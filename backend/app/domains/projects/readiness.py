from __future__ import annotations

from app.models import Project


def project_has_background_asset(project: Project) -> bool:
    if project.background_asset_id is not None:
        return True
    return any(
        asset.kind in {"background_video", "background_preset", "background_image"}
        for asset in project.assets
    )


def project_has_script(project: Project) -> bool:
    return project.current_script_revision_id is not None


def project_has_output(project: Project) -> bool:
    return project.current_output_video_id is not None


def project_can_render(project: Project) -> bool:
    return project_has_background_asset(project) and project_has_script(project)
