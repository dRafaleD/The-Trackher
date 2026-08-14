"""
Dijital Ayak İzi Temizleyici — Yardımcı Fonksiyonlar

Dosya boyutu formatlama, yol genişletme, izin kontrolleri ve e-posta doğrulama.
"""

from __future__ import annotations

import os
import re
import json
from pathlib import Path

# Global exclusion list
_EXCLUSIONS = []

def load_exclusions(config_path: str) -> None:
    """Belirtilen JSON dosyasından hariç tutulacak (whitelist) yolları yükler."""
    global _EXCLUSIONS
    try:
        path = expand_path(config_path)
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                _EXCLUSIONS = [expand_path(p) for p in data.get("exclude", [])]
    except Exception:
        pass

def should_exclude(path: Path) -> bool:
    """Belirtilen yolun exclusion (whitelist) listesinde olup olmadığını kontrol eder."""
    path = path.resolve()
    for exc in _EXCLUSIONS:
        # Check if the path is exactly the excluded path or a child of it
        if path == exc or exc in path.parents:
            return True
    return False


def format_size(size_bytes: int) -> str:
    """
    Bayt cinsinden boyutu okunabilir birime çevirir.

    >>> format_size(1536)
    '1.50 KB'
    >>> format_size(0)
    '0 B'
    """
    if size_bytes <= 0:
        return "0 B"

    units = ("B", "KB", "MB", "GB", "TB")
    unit_index = 0
    size = float(size_bytes)

    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} B"
    return f"{size:.2f} {units[unit_index]}"


def expand_path(path_str: str) -> Path:
    """~ ve ortam değişkenlerini genişletip mutlak Path döndürür."""
    return Path(os.path.expandvars(os.path.expanduser(path_str))).resolve()


def get_dir_size(path: Path) -> int:
    """
    Bir dizinin toplam boyutunu (bayt) hesaplar.
    Erişim hatalarını sessizce atlar.
    """
    total = 0
    try:
        for entry in path.rglob("*"):
            try:
                if entry.is_file() and not entry.is_symlink():
                    total += entry.stat().st_size
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass
    return total


def get_file_size(path: Path) -> int:
    """Tek bir dosyanın boyutunu döndürür; hata durumunda 0."""
    try:
        if path.is_file():
            return path.stat().st_size
    except (PermissionError, OSError):
        pass
    return 0


def is_valid_email(email: str) -> bool:
    """Temel e-posta formatı doğrulaması."""
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def safe_remove(path: Path, dry_run: bool = False) -> bool:
    """
    Dosya veya dizini güvenli biçimde siler.
    dry_run=True ise silmez, sadece True döndürür.
    """
    if dry_run:
        return True

    if should_exclude(path):
        return False

    try:
        if path.is_file() or path.is_symlink():
            path.unlink()
            return True
        elif path.is_dir():
            import shutil
            shutil.rmtree(path, ignore_errors=True)
            return True
    except (PermissionError, OSError):
        return False

    return False


def collect_files(directory: Path, pattern: str = "*") -> list[Path]:
    """
    Belirtilen dizinde verilen glob kalıbına uyan dosyaları toplar.
    Erişim hatalarını sessizce atlar.
    """
    results: list[Path] = []
    try:
        if directory.is_dir():
            for entry in directory.rglob(pattern):
                try:
                    if entry.is_file():
                        results.append(entry)
                except (PermissionError, OSError):
                    continue
    except (PermissionError, OSError):
        pass
    return results
