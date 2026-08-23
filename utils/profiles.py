"""Built-in Trackher scan profiles and selection helpers."""

from __future__ import annotations

from typing import Any


DEFAULT_SCAN_PROFILE = "standard"

SCAN_PROFILES = {
    "quick": {
        "label": "Quick",
        "description": "Verified checks only, using the fastest polite request policy.",
        "max_concurrent": 6,
        "request_interval_seconds": 0.5,
    },
    "standard": {
        "label": "Standard",
        "description": "Balanced coverage with sensitive deep-only sites excluded.",
        "max_concurrent": 4,
        "request_interval_seconds": 1.0,
    },
    "deep": {
        "label": "Deep",
        "description": "Broadest coverage with slower requests to sensitive endpoints.",
        "max_concurrent": 2,
        "request_interval_seconds": 2.0,
    },
    "username-only": {
        "label": "Username-only",
        "description": "Run username OSINT only.",
        "max_concurrent": 4,
        "request_interval_seconds": 1.0,
    },
    "email-only": {
        "label": "Email-only",
        "description": "Run email OSINT only.",
        "max_concurrent": 4,
        "request_interval_seconds": 1.0,
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


def profile_request_policy(profile: object | None) -> dict[str, float | int]:
    """Return bounded network policy values for a built-in scan profile."""

    normalized = normalize_scan_profile(profile)
    config = SCAN_PROFILES[normalized]
    return {
        "max_concurrent": int(config["max_concurrent"]),
        "request_interval_seconds": float(config["request_interval_seconds"]),
    }


def profile_request_policy_description(profile: object | None) -> str:
    """Return a compact user-facing summary of the profile network budget."""

    policy = profile_request_policy(profile)
    return (
        f"up to {policy['max_concurrent']} concurrent requests, "
        f"at least {policy['request_interval_seconds']:g}s per site"
    )


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

    if normalized == "deep":
        accounts = []
        for item in account_platforms:
            expanded = dict(item)
            if "deep_profile_check_limit" in expanded:
                expanded["profile_check_limit"] = expanded["deep_profile_check_limit"]
            accounts.append(expanded)
        return accounts, [dict(item) for item in breach_platforms]

    return list(account_platforms), list(breach_platforms)


def select_username_platforms(
    profile: object | None,
    username_platforms: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the username platform subset for a profile."""

    normalized = normalize_scan_profile(profile)
    if normalized == "quick":
        return [item for item in username_platforms if _is_verified_username_platform(item)]
    if normalized in {"standard", "username-only", "email-only"}:
        return [item for item in username_platforms if item.get("scan_tier") != "deep"]
    return list(username_platforms)
