"""
Dijital Ayak İzi Temizleyici — Güvenli Dosya Silme (Shredder)
Cross-Platform: Windows, macOS, Linux

- Linux/macOS : shred veya rm -P komutu, Python fallback
- Windows     : Üzerine yazma (Python) — SDelete aracı varsa onu kullan
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from utils.display import print_success, print_warning, print_error, print_info
from utils.helpers import (
    collect_files,
    expand_path,
    get_file_size,
    safe_remove,
    should_exclude,
)
from utils.platform_utils import is_windows, is_macos


def _python_shred(file_path: Path, passes: int = 3) -> bool:
    """
    Sistem komutu yoksa Python ile dosyayı üzerine yazarak imha eder.

    1. N geçiş : rastgele baytlarla üzerine yaz
    2. Son geçiş: sıfır baytlarla üzerine yaz
    3. Dosyayı sil
    """
    try:
        file_size = file_path.stat().st_size

        if file_size == 0:
            file_path.unlink()
            return True

        chunk_size = 1024 * 1024
        for _ in range(passes):
            with open(file_path, "r+b", buffering=0) as file_obj:
                remaining = file_size
                while remaining:
                    write_size = min(chunk_size, remaining)
                    file_obj.write(os.urandom(write_size))
                    remaining -= write_size
                file_obj.flush()
                os.fsync(file_obj.fileno())

        zero_chunk = b"\x00" * min(chunk_size, file_size)
        with open(file_path, "r+b", buffering=0) as file_obj:
            remaining = file_size
            while remaining:
                write_size = min(len(zero_chunk), remaining)
                file_obj.write(zero_chunk[:write_size])
                remaining -= write_size
            file_obj.flush()
            os.fsync(file_obj.fileno())

        file_path.unlink()
        return True

    except (PermissionError, OSError) as exc:
        print_error(f"Python shred başarısız: {exc}")
        return False


def _windows_shred(file_path: Path, passes: int) -> bool:
    """
    Windows'ta SDelete (Sysinternals) aracı varsa kullanır,
    yoksa Python fallback'e geçer.
    """
    # SDelete mevcut mu?
    try:
        result = subprocess.run(
            ["sdelete64.exe", "-accepteula", f"-p", str(passes), str(file_path)],
            capture_output=True, timeout=120,
        )
        if result.returncode == 0:
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass

    try:
        result = subprocess.run(
            ["sdelete.exe", "-accepteula", f"-p", str(passes), str(file_path)],
            capture_output=True, timeout=120,
        )
        if result.returncode == 0:
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass

    # Fallback: Python
    return _python_shred(file_path, passes)


def _macos_shred(file_path: Path, passes: int) -> bool:
    """
    macOS'ta rm -P ile güvenli silme dener, yoksa Python fallback.
    Not: macOS 10.15+ SSD'lerde rm -P etkisizdir ama yapabildiğimiz budur.
    """
    try:
        result = subprocess.run(
            ["rm", "-P", str(file_path)],
            capture_output=True, timeout=120,
        )
        if result.returncode == 0:
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass

    return _python_shred(file_path, passes)


def _linux_shred(file_path: Path, passes: int) -> bool:
    """
    Linux'ta shred komutunu kullanır, yoksa Python fallback.
    """
    try:
        result = subprocess.run(
            ["shred", "-vfz", "-n", str(passes), str(file_path)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            try:
                file_path.unlink()
            except OSError:
                pass
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass

    return _python_shred(file_path, passes)


def shred_file(
    file_path: str,
    passes: int = 3,
    dry_run: bool = False,
) -> bool:
    """
    Tek bir dosyayı cross-platform olarak güvenli biçimde imha eder.

    Sıralama:
        Windows : SDelete → Python fallback
        macOS   : rm -P  → Python fallback
        Linux   : shred  → Python fallback

    Args:
        file_path: Silinecek dosyanın yolu.
        passes   : Üzerine yazma geçiş sayısı (varsayılan: 3).
        dry_run  : True ise silmez, sadece bilgi verir.

    Returns:
        İşlemin başarılı olup olmadığı.
    """
    target = expand_path(file_path)

    if target.is_symlink() or not target.is_file():
        print_error(f"Dosya bulunamadı veya normal bir dosya değil: {target}")
        return False

    if should_exclude(target):
        print_warning(f"Dosya dışlama listesi tarafından korunuyor: {target}")
        return False

    if passes < 1:
        print_error("Üzerine yazma geçiş sayısı en az 1 olmalıdır.")
        return False

    size = get_file_size(target)

    if dry_run:
        print_info(
            f"[bold]SHRED[/bold] edilecek: {target}  "
            f"({size:,} bayt, {passes} geçiş)"
        )
        return True

    success = False
    method = "python"

    if is_windows():
        method = "SDelete/python"
        success = _windows_shred(target, passes)
    elif is_macos():
        method = "rm -P/python"
        success = _macos_shred(target, passes)
    else:
        method = "shred/python"
        success = _linux_shred(target, passes)

    if success:
        print_success(
            f"Güvenli silme tamamlandı ({method}): {target.name}  "
            f"({size:,} bayt, {passes} geçiş)"
        )
    else:
        print_error(f"Güvenli silme başarısız: {target}")

    return success


def shred_directory(
    dir_path: str,
    passes: int = 3,
    dry_run: bool = False,
) -> list[dict]:
    """
    Bir dizindeki tüm dosyaları özyinelemeli olarak güvenli biçimde imha eder.

    Args:
        dir_path: Silinecek dizinin yolu.
        passes  : Üzerine yazma geçiş sayısı.
        dry_run : True ise silmez, sadece bilgi verir.

    Returns:
        İşlenen dosyaların bilgilerini içeren liste.
    """
    target = expand_path(dir_path)

    if not target.is_dir():
        print_error(f"Dizin bulunamadı: {target}")
        return []

    if should_exclude(target):
        print_warning(f"Dizin dışlama listesi tarafından korunuyor: {target}")
        return []

    if passes < 1:
        print_error("Üzerine yazma geçiş sayısı en az 1 olmalıdır.")
        return []

    results: list[dict] = []
    files = collect_files(target)

    if not files:
        print_info(f"Dizinde dosya bulunamadı: {target}")
        if dry_run:
            return results

    print_info(f"Dizinde [bold]{len(files)}[/bold] dosya bulundu: {target}")

    for file_entry in files:
        size = get_file_size(file_entry)
        item = {
            "path": str(file_entry),
            "size": size,
            "type": "Shred edilecek dosya",
        }
        success = shred_file(str(file_entry), passes=passes, dry_run=dry_run)
        if success:
            results.append(item)

    if not dry_run:
        if safe_remove(target):
            print_success(f"Dizin kaldırıldı: {target}")
        elif target.exists():
            print_warning(f"Dizin tamamen kaldırılamadı; korunan veya kilitli öğeler var: {target}")

    return results
