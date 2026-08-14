"""
Dijital Ayak İzi Temizleyici — Sistem İzleri Temizleme
Cross-Platform: Windows, macOS, Linux

Windows : %TEMP%, %LOCALAPPDATA%/Temp, Son Kullanılan Dosyalar,
          Windows Prefetch, Thumbnail DB, Recycle Bin (kullanıcı)
macOS   : ~/Library/Caches, ~/.Trash, /private/tmp (kullanıcı dosyaları),
          QuickLook Thumbnail önbelleği
Linux   : ~/.cache, /tmp (kullanıcı dosyaları), Çöp Kutusu,
          ~/.local/share/recently-used.xbel, Thumbnail önbelleği
"""

from __future__ import annotations

import os
import ctypes
import sys
from pathlib import Path

from utils.display import print_success, print_warning, print_info
from utils.helpers import get_dir_size, get_file_size, safe_remove
from utils.platform_utils import (
    home, cache_dir, trash_dir, temp_dir,
    localappdata_dir, appdata_dir,
    is_windows, is_macos, is_linux,
)


# ─────────────────────────────────────────────────────────────────
# Platform'a Göre Hedef Listesi
# ─────────────────────────────────────────────────────────────────

def _system_targets() -> list[tuple[str, Path, str]]:
    """
    Mevcut OS'a göre (açıklama, yol, tür) listesi döndürür.
    tür: 'dir'  → dizini boşalt ve yeniden oluştur
         'file' → dosyayı sil
    """
    h = home()
    targets: list[tuple[str, Path, str]] = []

    if is_windows():
        local = localappdata_dir() or (h / "AppData" / "Local")
        appdata = appdata_dir() or (h / "AppData" / "Roaming")

        targets = [
            # Geçici dosyalar
            ("Kullanıcı Temp (%LOCALAPPDATA%\\Temp)",
             local / "Temp",                                     "dir"),
            # Thumbnail veritabanı
            ("Thumbnail Önbelleği",
             local / "Microsoft" / "Windows" / "Explorer",       "dir"),
            # Son kullanılan dosyalar (Recent)
            ("Son Kullanılan Dosyalar (Recent)",
             appdata / "Microsoft" / "Windows" / "Recent",       "dir"),
            # Windows Prefetch (yönetici gerekmez, ama genelde gerekmez)
            ("Prefetch Önbelleği",
             Path("C:/Windows/Prefetch"),                        "dir"),
            # Windows Update önbelleği (kullanıcı erişimi varsa)
            ("Windows Update Önbelleği",
             Path("C:/Windows/SoftwareDistribution/Download"),   "dir"),
            # İnternet Explorer / Edge (Legacy) Önbelleği
            ("IE/Edge (Legacy) Önbelleği",
             local / "Microsoft" / "Windows" / "INetCache",      "dir"),
            # Font önbelleği
            ("Windows Font Önbelleği",
             local / "Microsoft" / "Windows" / "Fonts",          "dir"),
            # Crash dumps
            ("Kullanıcı Crash Dump'ları",
             local / "CrashDumps",                               "dir"),
            # Teams önbelleği
            ("Microsoft Teams Önbelleği",
             appdata / "Microsoft" / "Teams" / "Cache",          "dir"),
            # Discord önbelleği
            ("Discord Önbelleği",
             appdata / "discord" / "Cache",                      "dir"),
            # Spotify önbelleği
            ("Spotify Önbelleği",
             local / "Spotify" / "Storage",                      "dir"),
        ]

    elif is_macos():
        lib = h / "Library"

        targets = [
            # Ana kullanıcı önbelleği
            ("Kullanıcı Önbelleği (~/Library/Caches)",
             lib / "Caches",                                      "dir"),
            # Çöp Kutusu
            ("Çöp Kutusu (~/.Trash)",
             h / ".Trash",                                        "dir"),
            # QuickLook Thumbnail önbelleği
            ("QuickLook Thumbnail Önbelleği",
             Path("/private/var/folders"),                        "ql_cache"),
            # Uygulama geçici dosyaları
            ("Uygulama Geçici Dosyaları (~/Library/Application Support/.Trash)",
             lib / "Application Support" / ".Trash",             "dir"),
            # Son kullanılan dosyalar (plist)
            ("Son Kullanılan Belgelere Yönelik Plist",
             lib / "Application Support" / "com.apple.sharedfilelist",
             "dir"),
            # Crash raporları
            ("Crash Raporları",
             lib / "Logs" / "DiagnosticReports",                 "dir"),
            # Xcode DerivedData (varsa)
            ("Xcode DerivedData",
             lib / "Developer" / "Xcode" / "DerivedData",        "dir"),
            # Simülatör önbelleği
            ("iOS Simülatör Önbelleği",
             lib / "Developer" / "CoreSimulator" / "Caches",     "dir"),
        ]

    else:  # Linux
        targets = [
            ("Kullanıcı Önbelleği (~/.cache)",
             h / ".cache",                                        "dir"),
            ("Küçük Resim Önbelleği (Thumbnails)",
             h / ".cache" / "thumbnails",                        "dir"),
            ("Son Kullanılan Dosyalar (recently-used)",
             h / ".local" / "share" / "recently-used.xbel",     "file"),
            ("Çöp Kutusu (~/.local/share/Trash)",
             h / ".local" / "share" / "Trash",                  "dir"),
            # Flatpak var cache
            ("Flatpak Var Önbelleği",
             h / ".var" / "app",                                 "flatpak"),
            # Snap önbelleği
            ("Snap Önbelleği",
             h / "snap",                                         "snap"),
        ]

    return targets


# ─────────────────────────────────────────────────────────────────
# /tmp veya %TEMP% Temizliği
# ─────────────────────────────────────────────────────────────────

def _clean_temp_files(dry_run: bool = False) -> list[dict]:
    """
    Geçici dosya dizininde yalnızca mevcut kullanıcıya
    ait dosyaları temizler.
    """
    results: list[dict] = []
    tmp_path = temp_dir()

    if not tmp_path.is_dir():
        return results

    # Windows'ta UID kavramı farklı — TEMP klasörü zaten kullanıcıya özel
    if is_windows():
        # Windows Temp zaten kullanıcıya özel olduğu için direkt temizle
        label = "Windows Kullanıcı Temp"
        size = get_dir_size(tmp_path)
        if size == 0:
            return results
        item = {"path": str(tmp_path), "size": size, "type": label}
        if dry_run:
            print_info(f"[dim]{label}[/dim]  →  {tmp_path}  ({size:,} bayt)")
            results.append(item)
        else:
            # Tüm alt dosyaları teker teker sil (dizinin kendisini değil)
            deleted = 0
            for entry in tmp_path.iterdir():
                try:
                    if safe_remove(entry):
                        deleted += 1
                except Exception:
                    pass
            if deleted:
                print_success(f"{label} temizlendi — {deleted} öğe kaldırıldı")
                results.append(item)
        return results

    # Unix/macOS: sadece kullanıcıya ait dosyaları sil
    try:
        current_uid = os.getuid()  # type: ignore[attr-defined]
    except AttributeError:
        return results

    try:
        for entry in tmp_path.iterdir():
            try:
                stat = entry.lstat()
                if stat.st_uid != current_uid:
                    continue

                size = stat.st_size if (entry.is_file() or entry.is_symlink()) \
                    else get_dir_size(entry)

                item = {"path": str(entry), "size": size,
                        "type": "Kullanıcı geçici dosyası"}

                if dry_run:
                    print_info(f"[dim]tmp[/dim]  →  {entry.name}  ({size:,} bayt)")
                    results.append(item)
                else:
                    if safe_remove(entry):
                        print_success(f"tmp temizlendi  →  {entry.name}")
                        results.append(item)
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass

    return results


def _clean_flatpak_cache(base: Path, dry_run: bool) -> list[dict]:
    """Flatpak uygulama veri önbelleklerini temizler."""
    results: list[dict] = []
    if not base.is_dir():
        return results
    try:
        for app_dir in base.iterdir():
            cache = app_dir / "data" / ".cache"
            if cache.is_dir():
                size = get_dir_size(cache)
                if size == 0:
                    continue
                label = f"Flatpak Cache ({app_dir.name})"
                item = {"path": str(cache), "size": size, "type": label}
                if dry_run:
                    print_info(f"[dim]{label}[/dim]  →  {cache}  ({size:,} bayt)")
                    results.append(item)
                else:
                    if safe_remove(cache):
                        cache.mkdir(parents=True, exist_ok=True)
                        print_success(f"{label} temizlendi")
                        results.append(item)
    except (PermissionError, OSError):
        pass
    return results


def clean_system_traces(dry_run: bool = False) -> list[dict]:
    """
    Sistem düzeyindeki dijital ayak izlerini cross-platform olarak temizler.

    Args:
        dry_run: True ise dosyaları silmez, sadece rapor üretir.

    Returns:
        Silinen/silinecek öğelerin bilgilerini içeren liste.
    """
    results: list[dict] = []
    processed_paths: set[str] = set()

    for description, target, target_type in _system_targets():

        target_str = str(target)
        # Zaten üst dizin temizlendiyse alt dizini atla
        if any(target_str.startswith(p) and p != target_str
               for p in processed_paths):
            continue

        # Özel tipler
        if target_type == "flatpak":
            results.extend(_clean_flatpak_cache(target, dry_run))
            continue
        if target_type == "snap":
            # Snap dizininde sadece "current" symlink'ler değil, eski rev'leri sil
            # Bu basit implementasyonda sadece boyutu raporluyoruz
            if target.is_dir():
                size = get_dir_size(target)
                if size > 0 and dry_run:
                    print_info(f"[dim]Snap:[/dim]  {target}  ({size:,} bayt) — elle temizlenmeli")
            continue
        if target_type == "ql_cache":
            # QuickLook önbelleği: kullanıcı klasörlerinde gömülü
            try:
                import subprocess
                if not dry_run:
                    subprocess.run(
                        ["qlmanage", "-r", "cache"],
                        capture_output=True, timeout=15,
                    )
                    print_success("QuickLook Thumbnail Önbelleği temizlendi")
                else:
                    print_info("[dim]QuickLook Cache:[/dim] temizlenecek (qlmanage -r cache)")
            except Exception:
                pass
            continue

        # Normal dir / file işleme
        if target_type == "dir":
            if not target.is_dir():
                continue
            size = get_dir_size(target)
            if size == 0:
                continue
            item = {"path": target_str, "size": size, "type": description}
            if dry_run:
                print_info(f"[dim]{description}[/dim]  →  {target}  ({size:,} bayt)")
                results.append(item)
            else:
                if safe_remove(target):
                    try:
                        target.mkdir(parents=True, exist_ok=True)
                    except OSError:
                        pass
                    print_success(f"{description} temizlendi  →  {target}")
                    results.append(item)
                else:
                    print_warning(f"{description} temizlenemedi  →  {target}")
            processed_paths.add(target_str)

        elif target_type == "file":
            if not target.is_file():
                continue
            size = get_file_size(target)
            if size == 0:
                continue
            item = {"path": target_str, "size": size, "type": description}
            if dry_run:
                print_info(f"[dim]{description}[/dim]  →  {target}  ({size:,} bayt)")
                results.append(item)
            else:
                if safe_remove(target):
                    print_success(f"{description} temizlendi  →  {target}")
                    results.append(item)
                else:
                    print_warning(f"{description} temizlenemedi  →  {target}")

    # Geçici dosya temizliği
    results.extend(_clean_temp_files(dry_run=dry_run))

    if not results:
        print_info("Temizlenecek sistem izi bulunamadı.")

    return results
