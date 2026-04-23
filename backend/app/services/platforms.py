from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformCapability:
    platform: str
    title_max: int
    description_supported: bool
    tags_supported: bool
    scheduling_supported: bool
    default_capabilities: list[str]


PLATFORM_CAPABILITIES: dict[str, PlatformCapability] = {
    "youtube": PlatformCapability(
        platform="youtube",
        title_max=100,
        description_supported=True,
        tags_supported=True,
        scheduling_supported=True,
        default_capabilities=["upload", "schedule", "metadata"],
    ),
    "instagram": PlatformCapability(
        platform="instagram",
        title_max=100,
        description_supported=True,
        tags_supported=True,
        scheduling_supported=False,
        default_capabilities=["upload", "metadata"],
    ),
    "tiktok": PlatformCapability(
        platform="tiktok",
        title_max=150,
        description_supported=True,
        tags_supported=True,
        scheduling_supported=False,
        default_capabilities=["upload", "metadata"],
    ),
    "facebook": PlatformCapability(
        platform="facebook",
        title_max=100,
        description_supported=True,
        tags_supported=True,
        scheduling_supported=True,
        default_capabilities=["upload", "schedule", "metadata"],
    ),
}


def supported_platforms() -> list[str]:
    return list(PLATFORM_CAPABILITIES.keys())


def capability_for(platform: str) -> PlatformCapability:
    if platform not in PLATFORM_CAPABILITIES:
        raise ValueError(f"Unsupported platform: {platform}")
    return PLATFORM_CAPABILITIES[platform]


def validate_platform_metadata(
    *,
    platform: str,
    title: str,
    description: str,
    tags: list[str],
) -> list[str]:
    capability = capability_for(platform)
    errors: list[str] = []
    if len(title) > capability.title_max:
        errors.append(f"Title exceeds the {platform} limit of {capability.title_max} characters.")
    if description and not capability.description_supported:
        errors.append(f"{platform} does not support descriptions.")
    if tags and not capability.tags_supported:
        errors.append(f"{platform} does not support tags.")
    return errors
