"""Local scan history storage and diffing for Trackher."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.app_logging import get_logger, safe_log
from utils.profiles import DEFAULT_SCAN_PROFILE, normalize_scan_profile


HISTORY_VERSION = 1
LOGGER = get_logger("history")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _hash_value(value: str, *, casefold: bool = False) -> str:
    normalized = value.strip()
    if casefold:
        normalized = normalized.casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def get_history_dir() -> Path:
    override = os.environ.get("TRACKHER_HISTORY_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    home = Path.home()
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return root / "Trackher" / "history"
    if platform.system() == "Darwin":
        return home / "Library" / "Application Support" / "Trackher" / "history"
    root = Path(os.environ.get("XDG_STATE_HOME", home / ".local" / "state"))
    return root / "trackher" / "history"


def _snapshot_file(scope_id: str, history_dir: Path | None = None) -> Path:
    root = history_dir or get_history_dir()
    return root / "snapshots" / f"{scope_id}.jsonl"


def clear_scan_history(history_dir: Path | None = None) -> dict[str, Any]:
    root = history_dir or get_history_dir()
    snapshots_dir = root / "snapshots"
    if not snapshots_dir.exists():
        return {"cleared": True, "removed_files": 0, "path": str(root)}

    removed = 0
    for entry in snapshots_dir.iterdir():
        try:
            if entry.is_file():
                entry.unlink()
                removed += 1
            elif entry.is_dir():
                shutil.rmtree(entry)
                removed += 1
        except OSError as exc:
            safe_log(LOGGER, logging.WARNING, "Failed to clear history entry at %s: %s", entry, exc)
    return {"cleared": True, "removed_files": removed, "path": str(root)}


def _finding_key(category: str, status: str, label: str) -> str:
    return f"{category}|{status}|{label}"


def _normalize_findings(data: dict[str, Any]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    findings: dict[str, dict[str, str]] = {}
    breaches: dict[str, dict[str, str]] = {}

    email_data = data.get("osint_email")
    if isinstance(email_data, dict):
        results = email_data.get("results", {})
        accounts = results.get("accounts", []) if isinstance(results, dict) else []
        for item in accounts:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status", "")).upper()
            if status not in {"FOUND", "POSSIBLE"}:
                continue
            label = str(item.get("service", "")).strip()
            if not label:
                continue
            key = _finding_key("email_account", status, label)
            findings[key] = {
                "key": key,
                "label": label,
                "category": "email_account",
                "status": status,
            }

        breach_items = results.get("breaches", []) if isinstance(results, dict) else []
        for item in breach_items:
            if not isinstance(item, dict) or str(item.get("status", "")).upper() != "FOUND":
                continue
            for breach_name in item.get("breaches", []):
                label = str(breach_name).strip()
                if not label:
                    continue
                key = _finding_key("breach", "FOUND", label)
                breaches[key] = {
                    "key": key,
                    "label": label,
                    "category": "breach",
                    "status": "FOUND",
                }

    username_data = data.get("osint_username")
    if isinstance(username_data, dict):
        for item in username_data.get("results", []):
            if not isinstance(item, dict) or not item.get("found"):
                continue
            label = str(item.get("platform", "")).strip()
            if not label:
                continue
            status = "UNRELIABLE" if item.get("reliability") == "unreliable" else "FOUND"
            key = _finding_key("username_profile", status, label)
            findings[key] = {
                "key": key,
                "label": label,
                "category": "username_profile",
                "status": status,
            }

    return (
        sorted(findings.values(), key=lambda item: item["key"]),
        sorted(breaches.values(), key=lambda item: item["key"]),
    )


def normalize_scan_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    findings, breaches = _normalize_findings(data)
    scope_parts: list[str] = []
    profile = normalize_scan_profile(
        data.get("scan_profile", data.get("profile", DEFAULT_SCAN_PROFILE))
    )

    email_data = data.get("osint_email")
    if isinstance(email_data, dict):
        scope_parts.append(f"email:{_hash_value(str(email_data.get('target', '')), casefold=True)}")

    username_data = data.get("osint_username")
    if isinstance(username_data, dict):
        scope_parts.append(f"username:{_hash_value(str(username_data.get('target', '')))}")

    scope_id = hashlib.sha256("|".join(sorted(scope_parts)).encode("utf-8")).hexdigest()
    risk = data.get("risk", {})
    return {
        "version": HISTORY_VERSION,
        "timestamp": _utc_now(),
        "profile": profile,
        "scope": sorted(scope_parts),
        "scope_id": scope_id,
        "findings": findings,
        "breaches": breaches,
        "risk": {
            "score": int(risk.get("score", 0)),
            "level": str(risk.get("level", "LOW")),
        },
    }


def _read_snapshots(snapshot_path: Path) -> tuple[list[dict[str, Any]], bool]:
    if not snapshot_path.exists():
        return [], False

    snapshots: list[dict[str, Any]] = []
    try:
        with open(snapshot_path, "r", encoding="utf-8") as file_obj:
            for line in file_obj:
                payload = line.strip()
                if not payload:
                    continue
                item = json.loads(payload)
                if not isinstance(item, dict):
                    raise ValueError("Snapshot line must be a JSON object")
                snapshots.append(item)
    except (OSError, ValueError, json.JSONDecodeError):
        return [], True
    return snapshots, False


def _archive_corrupted_file(snapshot_path: Path) -> None:
    if not snapshot_path.exists():
        return
    archived = snapshot_path.with_suffix(f".corrupt-{int(datetime.now().timestamp())}.jsonl")
    snapshot_path.replace(archived)


def _append_snapshot(snapshot_path: Path, snapshot: dict[str, Any], *, replace_corrupted: bool = False) -> None:
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    if replace_corrupted:
        _archive_corrupted_file(snapshot_path)
    with open(snapshot_path, "a", encoding="utf-8") as file_obj:
        file_obj.write(json.dumps(snapshot, ensure_ascii=False, sort_keys=True))
        file_obj.write("\n")


def _diff_entries(
    previous_items: list[dict[str, str]],
    current_items: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    previous_map = {item["key"]: item for item in previous_items}
    current_map = {item["key"]: item for item in current_items}

    new_items = [current_map[key] for key in sorted(current_map.keys() - previous_map.keys())]
    resolved_items = [previous_map[key] for key in sorted(previous_map.keys() - current_map.keys())]
    unchanged_items = [current_map[key] for key in sorted(current_map.keys() & previous_map.keys())]
    return new_items, resolved_items, unchanged_items


def build_scan_diff(
    previous_snapshot: dict[str, Any] | None,
    current_snapshot: dict[str, Any],
) -> dict[str, Any]:
    if previous_snapshot is None:
        return {
            "available": False,
            "status": "first_scan",
            "message": "No previous matching scan in local history.",
        }

    new_findings, resolved_findings, unchanged_findings = _diff_entries(
        list(previous_snapshot.get("findings", [])),
        list(current_snapshot.get("findings", [])),
    )
    new_breaches, removed_breaches, unchanged_breaches = _diff_entries(
        list(previous_snapshot.get("breaches", [])),
        list(current_snapshot.get("breaches", [])),
    )

    previous_risk = previous_snapshot.get("risk", {})
    current_risk = current_snapshot.get("risk", {})
    previous_score = int(previous_risk.get("score", 0))
    current_score = int(current_risk.get("score", 0))
    change = current_score - previous_score
    direction = "up" if change > 0 else "down" if change < 0 else "same"
    previous_profile = str(previous_snapshot.get("profile", DEFAULT_SCAN_PROFILE))
    current_profile = str(current_snapshot.get("profile", DEFAULT_SCAN_PROFILE))
    profile_mismatch = previous_profile != current_profile

    diff = {
        "available": True,
        "status": "ok",
        "previous": {
            "timestamp": previous_snapshot.get("timestamp", ""),
            "profile": previous_profile,
            "risk": {
                "score": previous_score,
                "level": str(previous_risk.get("level", "LOW")),
            },
        },
        "current": {
            "timestamp": current_snapshot.get("timestamp", ""),
            "profile": current_profile,
            "risk": {
                "score": current_score,
                "level": str(current_risk.get("level", "LOW")),
            },
        },
        "risk_change": {
            "value": change,
            "direction": direction,
        },
        "new_findings": new_findings,
        "resolved_findings": resolved_findings,
        "unchanged_findings": unchanged_findings,
        "new_breaches": new_breaches,
        "removed_breaches": removed_breaches,
        "unchanged_breaches": unchanged_breaches,
    }
    if profile_mismatch:
        diff["profile_mismatch"] = True
        diff["coverage_warning"] = (
            "Diff coverage differs because the previous and current scans used different profiles."
        )
    return diff


def save_and_diff_scan(
    data: dict[str, Any],
    *,
    enabled: bool = True,
    history_dir: Path | None = None,
) -> dict[str, Any]:
    if not enabled:
        return {
            "enabled": False,
            "available": False,
            "status": "disabled",
            "message": "Local scan history is disabled for this run.",
        }

    snapshot = normalize_scan_snapshot(data)
    snapshot_path = _snapshot_file(snapshot["scope_id"], history_dir)
    previous_snapshots, corrupted = _read_snapshots(snapshot_path)
    previous_snapshot = previous_snapshots[-1] if previous_snapshots else None
    diff = build_scan_diff(previous_snapshot, snapshot)
    if corrupted:
        diff = {
            "enabled": True,
            "available": False,
            "status": "corrupted",
            "message": "Local scan history was corrupted and has been reset for this target.",
        }

    try:
        _append_snapshot(snapshot_path, snapshot, replace_corrupted=corrupted)
    except OSError as exc:
        safe_log(LOGGER, logging.WARNING, "Failed to write local scan history at %s: %s", snapshot_path, exc)
        return {
            "enabled": True,
            "available": False,
            "status": "storage_error",
            "message": "Local scan history could not be written for this run.",
            "snapshot_path": str(snapshot_path),
        }
    diff["enabled"] = True
    diff["snapshot_path"] = str(snapshot_path)
    return diff
