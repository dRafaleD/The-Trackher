"""
Dijital Ayak İzi Temizleyici — İşletim Sistemi Tespit Modülü

platform.system() tabanlı OS tespiti ve her OS için
standart yol haritaları sağlar.

Desteklenen: Windows, macOS (Darwin), Linux
"""

from __future__ import annotations

import os
import platform
from enum import Enum
from pathlib import Path


class OS(Enum):
    WINDOWS = "Windows"
    MACOS   = "Darwin"
    LINUX   = "Linux"
    UNKNOWN = "Unknown"


def current_os() -> OS:
    """Çalışma zamanı işletim sistemini döndürür."""
    name = platform.system()
    try:
        return OS(name)
    except ValueError:
        return OS.UNKNOWN


def is_windows() -> bool:
    return current_os() == OS.WINDOWS

def is_macos() -> bool:
    return current_os() == OS.MACOS

def is_linux() -> bool:
    return current_os() == OS.LINUX


# ─────────────────────────────────────────────────────────────────
# Standart Dizin Yardımcıları
# ─────────────────────────────────────────────────────────────────

def home() -> Path:
    """Kullanıcının ev dizini."""
    return Path.home()


def temp_dir() -> Path:
    """İşletim sistemine göre geçici dosya dizini."""
    if is_windows():
        # %LOCALAPPDATA%\Temp  veya  %TEMP%
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            p = Path(local) / "Temp"
            if p.is_dir():
                return p
        tmp = os.environ.get("TEMP") or os.environ.get("TMP", "")
        return Path(tmp) if tmp else Path("C:/Windows/Temp")
    if is_macos():
        return Path("/private/var/folders") if Path("/private/var/folders").is_dir() else home() / ".Trash"
    # Linux
    return Path("/tmp")


def cache_dir() -> Path | None:
    """Kullanıcı önbellek dizini."""
    if is_windows():
        local = os.environ.get("LOCALAPPDATA", "")
        return Path(local) if local else None
    if is_macos():
        return home() / "Library" / "Caches"
    return home() / ".cache"


def trash_dir() -> Path | None:
    """Kullanıcı çöp kutusu dizini."""
    if is_windows():
        # Windows: her sürücüde $Recycle.Bin — kullanıcıya özgü değil,
        # bu yüzden None döndürüyoruz (sistem korumalı)
        return None
    if is_macos():
        return home() / ".Trash"
    return home() / ".local" / "share" / "Trash"


def appdata_dir(app: str = "") -> Path | None:
    """Windows %APPDATA% veya macOS ~/Library/Application Support"""
    if is_windows():
        appdata = os.environ.get("APPDATA", "")
        base = Path(appdata) if appdata else None
    elif is_macos():
        base = home() / "Library" / "Application Support"
    else:
        base = home() / ".config"

    if base is None:
        return None
    return base / app if app else base


def localappdata_dir(app: str = "") -> Path | None:
    """Windows %LOCALAPPDATA% veya Linux/macOS XDG_DATA_HOME"""
    if is_windows():
        local = os.environ.get("LOCALAPPDATA", "")
        base = Path(local) if local else None
    elif is_macos():
        base = home() / "Library" / "Application Support"
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "")
        base = Path(xdg) if xdg else home() / ".local" / "share"

    if base is None:
        return None
    return base / app if app else base
