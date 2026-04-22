from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import PlatformMetadata, Project, SocialAccount, User
from app.schemas import RoutingSuggestionResponse, SocialAccountSummary
from app.services.platforms import capability_for


def is_account_routing_eligible(account: SocialAccount, *, platform: str) -> bool:
    if account.platform != platform:
        return False
    if account.status != "linked":
        return False
    if account.token_status not in {"healthy", "unknown"}:
        return False
    account_capabilities = set(account.capabilities_json or [])
    required = set(capability_for(platform).default_capabilities)
    return required.issubset(account_capabilities)


def to_social_account_summary(account: SocialAccount) -> SocialAccountSummary:
    return SocialAccountSummary(
        id=account.id,
        platform=account.platform,
        account_type=account.account_type,
        channel_id=account.channel_id,
        channel_title=account.channel_title,
        status=account.status,
        token_status=account.token_status,
        capabilities=account.capabilities_json or [],
        default_preference_rank=account.default_preference_rank,
        routing_eligible=is_account_routing_eligible(account, platform=account.platform),
        last_validated_at=account.last_validated_at,
    )


def choose_social_account(
    project: Project,
    *,
    user: User,
    platform: str,
) -> tuple[SocialAccount | None, list[SocialAccount]]:
    accounts = [account for account in user.social_accounts if is_account_routing_eligible(account, platform=platform)]
    if project.preferred_account_type:
        preferred = [account for account in accounts if account.account_type == project.preferred_account_type]
        if preferred:
            accounts = preferred
    accounts.sort(key=lambda account: (account.default_preference_rank, -account.id))
    selected = next((account for account in accounts if account.id == project.selected_social_account_id), None)
    return selected or (accounts[0] if accounts else None), accounts


def suggest_destination(db: Session, project: Project, user: User) -> RoutingSuggestionResponse:
    allowed_platforms = project.allowed_platforms_json or [project.target_platform]
    recommended_platform = allowed_platforms[0] if allowed_platforms else project.target_platform
    account, eligible_accounts = choose_social_account(project, user=user, platform=recommended_platform)
    metadata = (
        db.query(PlatformMetadata)
        .filter(
            PlatformMetadata.project_id == project.id,
            PlatformMetadata.platform == recommended_platform,
        )
        .order_by(PlatformMetadata.updated_at.desc())
        .first()
    )
    metadata_ready = bool(metadata and not metadata.validation_errors_json)
    output_ready = project.current_output_video_id is not None
    if account and metadata_ready and output_ready:
        reason = "Selected the best linked account that matches the project's routing policy."
    elif not account:
        reason = "No eligible linked account matched the project's platform and account-type policy."
    elif not metadata_ready:
        reason = "A destination account is available, but metadata still needs attention."
    else:
        reason = "A destination account is available, but no approved output is ready yet."

    return RoutingSuggestionResponse(
        project_id=project.id,
        recommended_platform=recommended_platform,
        social_account_id=account.id if account else None,
        reason=reason,
        eligible_accounts=[to_social_account_summary(item) for item in eligible_accounts],
        metadata_ready=metadata_ready,
        output_ready=output_ready,
        automation_mode=project.automation_mode,
    )
