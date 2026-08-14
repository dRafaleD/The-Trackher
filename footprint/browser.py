"""
Dijital Ayak İzi Temizleyici — Tarayıcı Önbellek Temizleme
Cross-Platform: Windows, macOS, Linux

Tarayıcıların önbellek, GPU önbellek ve Shader önbelleklerini
her işletim sistemindeki doğru konumdan temizler.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from utils.display import print_success, print_warning, print_info
from utils.helpers import get_file_size, get_dir_size, safe_remove, should_exclude
from utils.platform_utils import (
    home, appdata_dir, localappdata_dir,
    is_windows, is_macos,
)


# Alt dizinler: Chromium tabanlı tarayıcılar için ortak
_CHROMIUM_CACHE_DIRS = [
    "Cache",
    "Code Cache",
    "GPUCache",
    "Service Worker/CacheStorage",
]

_CHROMIUM_ROOT_CACHE_DIRS = [
    "ShaderCache",
    "GrShaderCache",
    "GraphiteDawnCache",
]

_CHROMIUM_SQLITE_FILES = [
    ("History", ["DELETE FROM urls", "DELETE FROM visits", "DELETE FROM visit_source", "DELETE FROM keyword_search_terms"]),
    ("Cookies", ["DELETE FROM cookies"]),
    ("Network/Cookies", ["DELETE FROM cookies"]),
]

# Firefox için ortak
_FIREFOX_CACHE_DIRS = [
    "cache2",
    "thumbnails",
    "startupCache",
    "shader-cache",
    "OfflineCache",
]

_FIREFOX_SQLITE_FILES = [
    ("cookies.sqlite", ["DELETE FROM moz_cookies"]),
    # Note: moz_places contains bookmarks too. Deleting from moz_historyvisits removes history traces.
    ("places.sqlite", ["DELETE FROM moz_historyvisits"]), 
]


def _browser_targets() -> list[tuple[str, Path, list[str]]]:
    """
    Mevcut işletim sistemine göre tarayıcı hedefleri döndürür.
    Tuple: (tarayıcı_adı, taban_dizin, alt_dizinler)
    """
    h = home()
    targets: list[tuple[str, Path, list[str]]] = []

    if is_windows():
        local = localappdata_dir() or (h / "AppData" / "Local")
        appdata = appdata_dir() or (h / "AppData" / "Roaming")

        targets = [
            ("Firefox",
             appdata / "Mozilla" / "Firefox" / "Profiles",
             _FIREFOX_CACHE_DIRS),
            ("Google Chrome",
             local / "Google" / "Chrome" / "User Data",
             _CHROMIUM_CACHE_DIRS),
            ("Microsoft Edge",
             local / "Microsoft" / "Edge" / "User Data",
             _CHROMIUM_CACHE_DIRS),
            ("Brave Browser",
             local / "BraveSoftware" / "Brave-Browser" / "User Data",
             _CHROMIUM_CACHE_DIRS),
            ("Opera",
             appdata / "Opera Software" / "Opera Stable",
             _CHROMIUM_CACHE_DIRS),
            ("Vivaldi",
             local / "Vivaldi" / "User Data",
             _CHROMIUM_CACHE_DIRS),
            ("Chromium",
             local / "Chromium" / "User Data",
             _CHROMIUM_CACHE_DIRS),
            ("Tor Browser",
             h / "Desktop" / "Tor Browser" / "Browser" / "TorBrowser"
             / "Data" / "Browser" / "profile.default",
             _FIREFOX_CACHE_DIRS),
        ]

    elif is_macos():
        lib = h / "Library"
        app_support = lib / "Application Support"
        caches = lib / "Caches"

        targets = [
            ("Firefox",
             app_support / "Firefox" / "Profiles",
             _FIREFOX_CACHE_DIRS),
            ("Google Chrome",
             app_support / "Google" / "Chrome",
             _CHROMIUM_CACHE_DIRS),
            ("Google Chrome (Cache)",
             caches / "Google" / "Chrome",
             ["Cache", "Code Cache"]),
            ("Microsoft Edge",
             app_support / "Microsoft Edge",
             _CHROMIUM_CACHE_DIRS),
            ("Brave Browser",
             app_support / "BraveSoftware" / "Brave-Browser",
             _CHROMIUM_CACHE_DIRS),
            ("Safari (WebKit önbelleği)",
             caches / "com.apple.Safari",
             ["."]),
            ("Opera",
             app_support / "com.operasoftware.Opera",
             _CHROMIUM_CACHE_DIRS),
            ("Vivaldi",
             app_support / "Vivaldi",
             _CHROMIUM_CACHE_DIRS),
            ("Chromium",
             app_support / "Chromium",
             _CHROMIUM_CACHE_DIRS),
        ]

    else:  # Linux
        config = h / ".config"

        targets = [
            ("Firefox",
             h / ".mozilla" / "firefox",
             _FIREFOX_CACHE_DIRS),
            ("Google Chrome",
             config / "google-chrome",
             _CHROMIUM_CACHE_DIRS),
            ("Microsoft Edge",
             config / "microsoft-edge",
             _CHROMIUM_CACHE_DIRS),
            ("Brave Browser",
             config / "BraveSoftware" / "Brave-Browser",
             _CHROMIUM_CACHE_DIRS),
            ("Opera",
             config / "opera",
             _CHROMIUM_CACHE_DIRS),
            ("Vivaldi",
             config / "vivaldi",
             _CHROMIUM_CACHE_DIRS),
            ("Chromium",
             config / "chromium",
             _CHROMIUM_CACHE_DIRS),
        ]

    return targets


def _iter_profiles(base: Path, is_firefox: bool) -> list[Path]:
    """
    Firefox profil dizinlerini veya Chromium User Data altındaki
    profil dizinlerini döndürür.
    """
    if not base.is_dir():
        return []

    profiles: list[Path] = []
    try:
        for entry in base.iterdir():
            if not entry.is_dir():
                continue
            if is_firefox:
                # Firefox: xxxxxxxx.default, xxxxxxxx.default-release vb.
                if "." in entry.name:
                    profiles.append(entry)
            else:
                # Chromium: Default, Profile 1, Profile 2...
                if entry.name.startswith(("Default", "Profile")):
                    profiles.append(entry)
    except (PermissionError, OSError):
        pass

    return profiles if profiles else [base]


def _clean_sqlite_db(db_path: Path, queries: list[str]) -> tuple[bool, int]:
    """
    Belirtilen SQLite veritabanına bağlanıp ilgili tabloları temizler.
    Silme işleminden önce ve sonra dosya boyutunu karşılaştırarak gerçekten
    boşaltılan disk alanını hesaplar.
    
    Returns: (success_bool, freed_bytes_int)
    """
    if not db_path.is_file() or should_exclude(db_path):
        return False, 0
        
    initial_size = get_file_size(db_path)
    
    conn: sqlite3.Connection | None = None
    cursor: sqlite3.Cursor | None = None
    try:
        conn = sqlite3.connect(db_path, timeout=3.0)
        cursor = conn.cursor()
        successful_queries = 0
        for query in queries:
            try:
                cursor.execute(query)
            except sqlite3.Error:
                continue
            successful_queries += 1

        if successful_queries == 0:
            conn.rollback()
            return False, 0

        conn.commit()
        try:
            cursor.execute("VACUUM")
        except sqlite3.Error:
            pass

        final_size = get_file_size(db_path)
        freed = max(0, initial_size - final_size)
        return True, freed
    except sqlite3.Error:
        return False, 0
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def clean_browser_data(dry_run: bool = False) -> list[dict]:
    """
    Tarayıcı önbellek dizinlerini cross-platform olarak temizler.

    Args:
        dry_run: True ise dosyaları silmez, sadece rapor üretir.

    Returns:
        Silinen/silinecek dizinlerin bilgilerini içeren liste.
    """
    results: list[dict] = []

    for browser_name, base_path, sub_dirs in _browser_targets():
        if not base_path.is_dir():
            continue

        is_firefox = "Firefox" in browser_name or "Tor" in browser_name
        is_chromium = not is_firefox and not browser_name.startswith("Safari")

        # Firefox → profil dizinleri üzerinden, Chromium → direkt veya profil
        if is_firefox:
            search_bases = _iter_profiles(base_path, is_firefox=True)
        elif is_chromium and (base_path / "Default").is_dir():
            # Chromium User Data → birden fazla profil olabilir
            search_bases = _iter_profiles(base_path, is_firefox=False)
        else:
            search_bases = [base_path]

        browser_found = False

        cache_bases = [(profile_base, sub_dirs) for profile_base in search_bases]
        if is_chromium:
            cache_bases.append((base_path, _CHROMIUM_ROOT_CACHE_DIRS))

        # 1. Önbellek dizinlerini temizle
        for cache_base, cache_dirs in cache_bases:
            for sub_dir in cache_dirs:
                if sub_dir == ".":
                    target = cache_base
                else:
                    target = cache_base / sub_dir

                if not target.is_dir():
                    continue

                size = get_dir_size(target)
                if size == 0:
                    continue

                browser_found = True
                cache_name = sub_dir if sub_dir != "." else "Cache"
                label = f"{browser_name} ({cache_base.name}) — {cache_name}"
                item = {"path": str(target), "size": size, "type": label}

                if dry_run:
                    print_info(f"[dim]{label}[/dim]  →  {target}  ({size:,} bayt)")
                    results.append(item)
                else:
                    if safe_remove(target):
                        try:
                            target.mkdir(parents=True, exist_ok=True)
                        except OSError:
                            pass
                        print_success(f"{label} temizlendi  →  {target}")
                        results.append(item)
                    else:
                        print_warning(f"{label} temizlenemedi (İstisna veya İzin Hatası)  →  {target}")

        # 2. SQLite veritabanlarını profil bazında temizle (History, Cookies)
        for profile_base in search_bases:
            sqlite_files = _FIREFOX_SQLITE_FILES if is_firefox else _CHROMIUM_SQLITE_FILES
            for filename, queries in sqlite_files:
                target_file = profile_base / filename
                if not target_file.is_file() or should_exclude(target_file):
                    continue

                browser_found = True
                label = f"{browser_name} ({profile_base.name}) — {filename}"
                size = get_file_size(target_file)
                item = {"path": str(target_file), "size": size, "type": f"{label} (SQLite)"}
                
                if dry_run:
                    item["size"] = 0
                    print_info(
                        f"[dim]{label} (SQLite)[/dim]  →  İçerik temizlenecek  "
                        f"(veritabanı boyutu: {size:,} bayt)"
                    )
                    results.append(item)
                else:
                    success, freed_size = _clean_sqlite_db(target_file, queries)
                    if success:
                        item["size"] = freed_size
                        print_success(f"{label} içerisindeki kayıtlar silindi  →  {target_file}")
                        results.append(item)
                    else:
                        print_warning(f"{label} temizlenemedi (Tarayıcı açık veya kilitli)  →  {target_file}")

        if not browser_found:
            print_info(f"[dim]{browser_name}:[/dim] Temizlenecek önbellek bulunamadı.")

    if not results:
        print_info("Hiçbir tarayıcıda temizlenecek önbellek bulunamadı.")

    return results
