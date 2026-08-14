"""
Dijital Ayak İzi Temizleyici — İşletim Sistemi Tespit Modülü

platform.system() tabanlı OS tespiti ve her OS için
standart yol haritaları sağlar.

Desteklenen: Windows, macOS (Darwin), Linux
"""

from __future__ import annotations

import os
import platform
import tempfile
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
    """Python'ın mevcut kullanıcı için seçtiği geçici dosya dizini."""
    return Path(tempfile.gettempdir()).resolve()


def cache_dir() -> Path | None:
    """Kullanıcı önbellek dizini."""
    if is_windows():
        local = os.environ.get("LOCALAPPDATA", "")
        return Path(local) if local else None
    if is_macos():
        return home() / "Library" / "Caches"
    if is_linux():
        xdg = os.environ.get("XDG_CACHE_HOME", "")
        return Path(xdg) if xdg else home() / ".cache"
    return None


def trash_dir() -> Path | None:
    """Kullanıcı çöp kutusu dizini."""
    if is_windows():
        # Windows: her sürücüde $Recycle.Bin — kullanıcıya özgü değil,
        # bu yüzden None döndürüyoruz (sistem korumalı)
        return None
    if is_macos():
        return home() / ".Trash"
    if is_linux():
        return home() / ".local" / "share" / "Trash"
    return None


def appdata_dir(app: str = "") -> Path | None:
    """Windows %APPDATA% veya macOS ~/Library/Application Support"""
    if is_windows():
        appdata = os.environ.get("APPDATA", "")
        base = Path(appdata) if appdata else None
    elif is_macos():
        base = home() / "Library" / "Application Support"
    elif is_linux():
        xdg = os.environ.get("XDG_CONFIG_HOME", "")
        base = Path(xdg) if xdg else home() / ".config"
    else:
        base = None

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
    elif is_linux():
        xdg = os.environ.get("XDG_DATA_HOME", "")
        base = Path(xdg) if xdg else home() / ".local" / "share"
    else:
        base = None

    if base is None:
        return None
    return base / app if app else base
