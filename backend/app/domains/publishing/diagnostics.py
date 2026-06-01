from __future__ import annotations

from app.models import Project, SocialAccount


def account_requires_reconnect(account: SocialAccount) -> bool:
    return account.status == "reconnect_required"


def account_token_is_healthy(account: SocialAccount) -> bool:
    return account.token_status in {"healthy", "unknown"}


def project_is_publishable(project: Project) -> bool:
    return project.status == "approved" and bool(project.approved_at)
