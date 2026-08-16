"""Explainable digital footprint risk scoring."""

from __future__ import annotations

from typing import Any


DISCLAIMER = (
    "This score is only an explainable exposure indicator based on current scan evidence. "
    "It is not a scientific measurement or a security guarantee."
)

WEIGHTS = {
    "email_verified_account": 10,
    "email_verified_account_cap": 30,
    "email_possible_account": 4,
    "email_possible_account_cap": 12,
    "breach_per_record": 18,
    "breach_cap": 54,
    "username_verified_profile": 4,
    "username_verified_profile_cap": 24,
    "username_unreliable_profile": 2,
    "username_unreliable_profile_cap": 8,
}

LEVELS = (
    (70, "CRITICAL"),
    (45, "HIGH"),
    (20, "MEDIUM"),
    (0, "LOW"),
)


def _clamp_score(value: int) -> int:
    return max(0, min(100, value))


def _risk_level(score: int) -> str:
    for minimum, label in LEVELS:
        if score >= minimum:
            return label
    return "LOW"


def _reason(
    category: str,
    points: int,
    summary: str,
    evidence: list[str],
    detail: str,
) -> dict[str, Any]:
    return {
        "category": category,
        "points": points,
        "summary": summary,
        "evidence": evidence,
        "detail": detail,
    }


def _score_email(email_data: dict[str, Any]) -> list[dict[str, Any]]:
    results = email_data.get("results", {})
    accounts = results.get("accounts", []) if isinstance(results, dict) else []
    breaches = results.get("breaches", []) if isinstance(results, dict) else []
    reasons: list[dict[str, Any]] = []

    verified_accounts = [
        item.get("service", "Unknown")
        for item in accounts
        if item.get("status") == "FOUND"
    ]
    if verified_accounts:
        points = min(
            len(verified_accounts) * WEIGHTS["email_verified_account"],
            WEIGHTS["email_verified_account_cap"],
        )
        reasons.append(
            _reason(
                "email_verified_accounts",
                points,
                "Verified email-linked public accounts",
                verified_accounts,
                "Passive public evidence confirmed account exposure.",
            )
        )

    possible_accounts = [
        item.get("service", "Unknown")
        for item in accounts
        if item.get("status") == "POSSIBLE"
    ]
    if possible_accounts:
        points = min(
            len(possible_accounts) * WEIGHTS["email_possible_account"],
            WEIGHTS["email_possible_account_cap"],
        )
        reasons.append(
            _reason(
                "email_possible_accounts",
                points,
                "Possible email-linked public accounts",
                possible_accounts,
                "Heuristic passive signals suggest exposure but do not verify it.",
            )
        )

    breach_names: list[str] = []
    for item in breaches:
        if item.get("status") != "FOUND":
            continue
        names = item.get("breaches", [])
        if isinstance(names, list):
            breach_names.extend(str(name) for name in names if str(name).strip())

    if breach_names:
        points = min(
            len(breach_names) * WEIGHTS["breach_per_record"],
            WEIGHTS["breach_cap"],
        )
        reasons.append(
            _reason(
                "breach_exposure",
                points,
                "Known breach exposure",
                breach_names,
                "Breached-account evidence increases privacy and account-reuse risk.",
            )
        )

    return reasons


def _score_username(username_data: dict[str, Any]) -> list[dict[str, Any]]:
    results = username_data.get("results", [])
    reasons: list[dict[str, Any]] = []

    verified_profiles = [
        item.get("platform", "Unknown")
        for item in results
        if item.get("found") and item.get("reliability") != "unreliable"
    ]
    if verified_profiles:
        points = min(
            len(verified_profiles) * WEIGHTS["username_verified_profile"],
            WEIGHTS["username_verified_profile_cap"],
        )
        reasons.append(
            _reason(
                "username_verified_profiles",
                points,
                "Verified username exposure",
                verified_profiles,
                "Confirmed public profiles increase cross-platform traceability.",
            )
        )

    heuristic_profiles = [
        item.get("platform", "Unknown")
        for item in results
        if item.get("found") and item.get("reliability") == "unreliable"
    ]
    if heuristic_profiles:
        points = min(
            len(heuristic_profiles) * WEIGHTS["username_unreliable_profile"],
            WEIGHTS["username_unreliable_profile_cap"],
        )
        reasons.append(
            _reason(
                "username_heuristic_profiles",
                points,
                "Heuristic username exposure",
                heuristic_profiles,
                "Unreliable profile matches count less than verified public profiles.",
            )
        )

    return reasons


def compute_risk(data: dict[str, Any]) -> dict[str, Any]:
    """Compute an explainable 0-100 exposure score from real scan evidence."""
    reasons: list[dict[str, Any]] = []
    email_data = data.get("osint_email")
    if isinstance(email_data, dict):
        reasons.extend(_score_email(email_data))

    username_data = data.get("osint_username")
    if isinstance(username_data, dict):
        reasons.extend(_score_username(username_data))

    total = _clamp_score(sum(int(reason["points"]) for reason in reasons))
    return {
        "score": total,
        "level": _risk_level(total),
        "reasons": reasons,
        "disclaimer": DISCLAIMER,
    }
