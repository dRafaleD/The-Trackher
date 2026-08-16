"""Release hardening checks used by tests and CI."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from utils import __version__


_SUPPORTED_SUFFIXES = {
    ".env",
    ".example",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
_IGNORED_PARTS = {".git", ".venv", "__pycache__", "tests"}
_SECRET_PATTERNS = (
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}\b")),
    (
        "assigned_secret",
        re.compile(
            r"(?i)\b([A-Za-z0-9_-]*?(?:api[_-]?key|token|secret|password|authorization))\b"
            r"\s*[:=]\s*['\"][^'\"]{12,}['\"]"
        ),
    ),
    ("hibp_key_literal", re.compile(r"(?i)hibp-api-key\s*[:=]\s*['\"][^'\"]{12,}['\"]")),
)


def get_version() -> str:
    return __version__


def _iter_repo_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _IGNORED_PARTS for part in path.parts):
            continue
        if path.suffix.lower() in _SUPPORTED_SUFFIXES or path.name in {"requirements.txt"}:
            files.append(path)
    return files


def scan_repository_for_secrets(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in _iter_repo_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for name, pattern in _SECRET_PATTERNS:
            for match in pattern.finditer(text):
                findings.append(
                    {
                        "path": str(path.relative_to(root)),
                        "pattern": name,
                        "match": match.group(0)[:80],
                    }
                )
    return findings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m utils.release_checks")
    parser.add_argument("--check-secrets", action="store_true", help="Scan the repository for obvious secret literals.")
    parser.add_argument("--root", type=str, default=".", help="Repository root to scan.")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    if not args.check_secrets:
        parser.print_help()
        return 2

    findings = scan_repository_for_secrets(Path(args.root).resolve())
    if findings:
        print(json.dumps({"ok": False, "findings": findings}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, "findings": []}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
