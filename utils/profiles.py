"""Built-in Trackher scan profiles and selection helpers."""

from __future__ import annotations

from typing import Any


DEFAULT_SCAN_PROFILE = "standard"

SCAN_PROFILES = {
    "quick": {
        "label": "Quick",
        "description": "Verified and high-confidence checks only.",
    },
    "standard": {
        "label": "Standard",
        "description": "Current default Trackher behavior.",
    },
    "deep": {
        "label": "Deep",
        "description": "Currently matches standard behavior; reserved for broader coverage.",
    },
    "username-only": {
        "label": "Username-only",
        "description": "Run username OSINT only.",
    },
    "email-only": {
        "label": "Email-only",
        "description": "Run email OSINT only.",
    },
}

PROFILE_ORDER = tuple(SCAN_PROFILES.keys())


def normalize_scan_profile(value: object | None) -> str:
    """Return a validated built-in profile name."""

    if value is None:
        return DEFAULT_SCAN_PROFILE

    profile = str(value).strip().casefold()
    if not profile:
        return DEFAULT_SCAN_PROFILE
    if profile not in SCAN_PROFILES:
        raise ValueError(f"Unsupported scan profile: {value}")
    return profile


def profile_label(profile: object | None) -> str:
    """Return a human-readable label for a profile."""

    normalized = normalize_scan_profile(profile)
    return SCAN_PROFILES[normalized]["label"]


def profile_description(profile: object | None) -> str:
    """Return a concise profile description."""

    normalized = normalize_scan_profile(profile)
    return SCAN_PROFILES[normalized]["description"]


def profile_allows_email(profile: object | None) -> bool:
    """Return True when the profile can run email OSINT."""

    normalized = normalize_scan_profile(profile)
    return normalized != "username-only"


def profile_allows_username(profile: object | None) -> bool:
    """Return True when the profile can run username OSINT."""

    normalized = normalize_scan_profile(profile)
    return normalized != "email-only"


def _is_verified_email_platform(platform: dict[str, Any]) -> bool:
    return str(platform.get("category", "")).strip().casefold() == "verified"


def _is_verified_username_platform(platform: dict[str, Any]) -> bool:
    return str(platform.get("reliability", "")).strip().casefold() == "verified"


def select_email_platforms(
    profile: object | None,
    account_platforms: list[dict[str, Any]],
    breach_platforms: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return the email and breach platform subsets for a profile."""

    normalized = normalize_scan_profile(profile)
    if normalized == "quick":
        accounts = [item for item in account_platforms if _is_verified_email_platform(item)]
        breaches = [item for item in breach_platforms if _is_verified_email_platform(item)]
        return accounts, breaches

    return list(account_platforms), list(breach_platforms)


def select_username_platforms(
    profile: object | None,
    username_platforms: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the username platform subset for a profile."""

    normalized = normalize_scan_profile(profile)
    if normalized == "quick":
        return [item for item in username_platforms if _is_verified_username_platform(item)]
    return list(username_platforms)
