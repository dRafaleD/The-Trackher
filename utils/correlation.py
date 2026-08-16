"""Conservative identity correlation for public Trackher findings."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from itertools import combinations
from typing import Any
from urllib.parse import urlparse


WEIGHTS = {
    "same_username": {"points": 26, "strength": "strong", "label": "same username"},
    "same_display_name": {"points": 18, "strength": "medium", "label": "same public display name"},
    "similar_display_name": {"points": 8, "strength": "weak", "label": "similar public display name"},
    "same_avatar_hash": {"points": 30, "strength": "strong", "label": "same public avatar hash"},
    "same_website_domain": {"points": 26, "strength": "strong", "label": "same linked website"},
    "same_profile_domain": {"points": 6, "strength": "weak", "label": "same profile domain"},
}

PENALTIES = {
    "conflicting_display_name": {"points": -14, "label": "conflicting public display name"},
}

QUALITY_FACTORS = {
    "verified": 1.0,
    "heuristic": 0.65,
}

LEVELS = (
    (55, "HIGH"),
    (32, "MEDIUM"),
    (20, "LOW"),
    (0, "NONE"),
)


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().casefold()


def _normalize_handle(value: object) -> str:
    text = _normalize_text(value)
    return re.sub(r"[^a-z0-9._-]+", "", text)


def _normalize_name(value: object) -> str:
    text = _normalize_text(value)
    return re.sub(r"[^a-z0-9 ]+", " ", text).strip()


def _extract_domain(value: object) -> str:
    text = str(value).strip()
    if not text:
        return ""
    if "://" not in text and "." in text and " " not in text:
        text = f"https://{text}"
    parsed = urlparse(text)
    host = parsed.hostname or ""
    host = host.casefold()
    if host.startswith("www."):
        host = host[4:]
    return host


def _extract_avatar_hash(metadata: dict[str, Any]) -> str:
    explicit = _normalize_text(metadata.get("avatar_hash", ""))
    if re.fullmatch(r"[a-f0-9]{32}", explicit):
        return explicit

    avatar_url = str(metadata.get("avatar_url", "")).strip().casefold()
    if not avatar_url:
        return ""
    match = re.search(r"([a-f0-9]{32})", avatar_url)
    return match.group(1) if match else ""


def _name_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _confidence_level(score: int) -> str:
    for minimum, label in LEVELS:
        if score >= minimum:
            return label
    return "NONE"


def _node_quality(node: dict[str, Any]) -> float:
    return QUALITY_FACTORS.get(str(node.get("quality", "heuristic")), 0.65)


def _build_nodes(report_data: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    username_data = report_data.get("osint_username")
    if isinstance(username_data, dict):
        target_username = str(username_data.get("target", "")).strip()
        for result in username_data.get("results", []):
            if not isinstance(result, dict) or not result.get("found"):
                continue
            metadata = dict(result.get("public_metadata", {}))
            if target_username:
                metadata.setdefault("username", target_username)
            nodes.append(
                {
                    "source": "username",
                    "platform": str(result.get("platform", "Unknown")),
                    "status": str(result.get("status", "FOUND")).upper(),
                    "quality": "heuristic" if result.get("reliability") == "unreliable" else "verified",
                    "metadata": metadata,
                    "url": str(result.get("url", "")),
                }
            )

    email_data = report_data.get("osint_email")
    if isinstance(email_data, dict):
        results = email_data.get("results", {})
        if isinstance(results, dict):
            for result in results.get("accounts", []):
                if not isinstance(result, dict):
                    continue
                status = str(result.get("status", "")).upper()
                if status not in {"FOUND", "POSSIBLE"}:
                    continue
                nodes.append(
                    {
                        "source": "email",
                        "platform": str(result.get("service", "Unknown")),
                        "status": status,
                        "quality": "verified" if status == "FOUND" else "heuristic",
                        "metadata": dict(result.get("public_metadata", {})),
                        "url": str(result.get("url", "")),
                    }
                )

    return nodes


def _signal(signal_id: str, points: int, value: str = "") -> dict[str, Any]:
    config = WEIGHTS[signal_id]
    payload = {
        "signal": signal_id,
        "label": config["label"],
        "strength": config["strength"],
        "points": points,
    }
    if value:
        payload["value"] = value
    return payload


def _penalty(signal_id: str, points: int) -> dict[str, Any]:
    config = PENALTIES[signal_id]
    return {
        "signal": signal_id,
        "label": config["label"],
        "points": points,
    }


def _pairwise_evidence(left: dict[str, Any], right: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    penalties: list[dict[str, Any]] = []
    multiplier = min(_node_quality(left), _node_quality(right))

    left_meta = dict(left.get("metadata", {}))
    right_meta = dict(right.get("metadata", {}))

    left_username = _normalize_handle(left_meta.get("username", ""))
    right_username = _normalize_handle(right_meta.get("username", ""))
    if left_username and right_username and left_username == right_username:
        points = round(WEIGHTS["same_username"]["points"] * multiplier)
        evidence.append(_signal("same_username", points, left_username))

    left_name = _normalize_name(left_meta.get("display_name", ""))
    right_name = _normalize_name(right_meta.get("display_name", ""))
    if left_name and right_name:
        if left_name == right_name:
            points = round(WEIGHTS["same_display_name"]["points"] * multiplier)
            evidence.append(_signal("same_display_name", points, left_name))
        else:
            similarity = _name_similarity(left_name, right_name)
            left_tokens = set(left_name.split())
            right_tokens = set(right_name.split())
            overlap = left_tokens & right_tokens
            if similarity >= 0.84 or (len(overlap) >= 2 and overlap):
                points = round(WEIGHTS["similar_display_name"]["points"] * multiplier)
                evidence.append(_signal("similar_display_name", points, f"{left_name} ~ {right_name}"))
            elif similarity <= 0.4:
                penalties.append(_penalty("conflicting_display_name", PENALTIES["conflicting_display_name"]["points"]))

    left_avatar = _extract_avatar_hash(left_meta)
    right_avatar = _extract_avatar_hash(right_meta)
    if left_avatar and right_avatar and left_avatar == right_avatar:
        points = round(WEIGHTS["same_avatar_hash"]["points"] * multiplier)
        evidence.append(_signal("same_avatar_hash", points, left_avatar))

    left_website = _extract_domain(left_meta.get("website", ""))
    right_website = _extract_domain(right_meta.get("website", ""))
    if left_website and right_website and left_website == right_website:
        points = round(WEIGHTS["same_website_domain"]["points"] * multiplier)
        evidence.append(_signal("same_website_domain", points, left_website))

    left_profile_domain = _extract_domain(left_meta.get("profile_url", left.get("url", "")))
    right_profile_domain = _extract_domain(right_meta.get("profile_url", right.get("url", "")))
    if (
        left_profile_domain
        and right_profile_domain
        and left_profile_domain == right_profile_domain
        and left["platform"] == right["platform"]
    ):
        points = round(WEIGHTS["same_profile_domain"]["points"] * multiplier)
        evidence.append(_signal("same_profile_domain", points, left_profile_domain))

    return evidence, penalties


def _accepted(score: int, evidence: list[dict[str, Any]]) -> bool:
    strong_count = sum(1 for item in evidence if item.get("strength") == "strong")
    if len(evidence) < 2:
        return False
    if strong_count == 0 and score < 32:
        return False
    return score >= 20


def _summary_label(level: str) -> str:
    if level == "HIGH":
        return "Likely Same Identity"
    if level == "MEDIUM":
        return "Possible Same Identity"
    if level == "LOW":
        return "Weak Correlation"
    return "No Reliable Correlation"


def build_identity_correlation(report_data: dict[str, Any]) -> dict[str, Any]:
    """Correlate public findings conservatively without changing detection logic."""
    nodes = _build_nodes(report_data)
    items: list[dict[str, Any]] = []

    for left, right in combinations(nodes, 2):
        evidence, penalties = _pairwise_evidence(left, right)
        raw_score = sum(int(item["points"]) for item in evidence) + sum(int(item["points"]) for item in penalties)
        score = max(0, min(100, raw_score))
        level = _confidence_level(score)

        if not _accepted(score, evidence):
            continue

        items.append(
            {
                "summary": f"{left['platform']} ↔ {right['platform']}",
                "label": _summary_label(level),
                "confidence_score": score,
                "confidence": level,
                "left": {
                    "platform": left["platform"],
                    "source": left["source"],
                    "status": left["status"],
                },
                "right": {
                    "platform": right["platform"],
                    "source": right["source"],
                    "status": right["status"],
                },
                "evidence": sorted(evidence, key=lambda item: (-int(item["points"]), str(item["label"]))),
                "penalties": penalties,
            }
        )

    items.sort(key=lambda item: (-int(item["confidence_score"]), item["summary"]))
    return {
        "available": bool(items),
        "count": len(items),
        "items": items,
        "disclaimer": (
            "Identity correlation is probabilistic and based only on public scan evidence. "
            "It does not prove that two accounts belong to the same person."
        ),
    }
