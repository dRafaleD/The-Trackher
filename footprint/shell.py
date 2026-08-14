"""
Dijital Ayak İzi Temizleyici — Kabuk ve Terminal Geçmiş Temizleme
Cross-Platform: Windows, macOS, Linux

Windows : PowerShell, Cmder, WSL geçmişleri + araç geçmişleri
macOS   : Zsh (default), Bash, Fish + araç geçmişleri
Linux   : Bash, Zsh, Fish + araç geçmişleri
"""

from __future__ import annotations

from pathlib import Path

from utils.display import print_success, print_warning, print_info
from utils.helpers import get_file_size, should_exclude
from utils.platform_utils import (
    home, appdata_dir, localappdata_dir,
    is_linux, is_macos, is_windows,
)


def _history_targets() -> list[tuple[str, Path]]:
    """
    Mevcut işletim sistemine göre temizlenecek geçmiş
    dosyalarının (açıklama, tam_yol) listesini döndürür.
    """
    h = home()
    targets: list[tuple[str, Path]] = []

    if not (is_windows() or is_macos() or is_linux()):
        return targets

    # ── Ortak (tüm platformlarda aranır) ─────────────────────────
    common: list[tuple[str, Path]] = [
        ("Python REPL geçmişi",    h / ".python_history"),
        ("Node.js REPL geçmişi",   h / ".node_repl_history"),
        ("Vim bilgi dosyası",       h / ".viminfo"),
        ("MySQL geçmişi",           h / ".mysql_history"),
        ("PostgreSQL geçmişi",      h / ".psql_history"),
        ("SQLite geçmişi",          h / ".sqlite_history"),
        ("GDB geçmişi",             h / ".gdb_history"),
        ("IRB (Ruby) geçmişi",      h / ".irb_history"),
        ("Wget HSTS veritabanı",    h / ".wget-hsts"),
    ]
    targets.extend(common)

    # ── Windows ───────────────────────────────────────────────────
    if is_windows():
        appdata = appdata_dir() or (h / "AppData" / "Roaming")
        local   = localappdata_dir() or (h / "AppData" / "Local")

        windows_targets: list[tuple[str, Path]] = [
            # PowerShell (v5 - ConsoleHost)
            ("PowerShell geçmişi",
             appdata / "Microsoft" / "Windows" / "PowerShell"
             / "PSReadLine" / "ConsoleHost_history.txt"),
            # PowerShell 7+ (pwsh)
            ("PowerShell 7 geçmişi",
             local / "Microsoft" / "PowerShell" / "PSReadLine"
             / "ConsoleHost_history.txt"),
            # WSL bash (Windows Subsystem for Linux)
            ("WSL Bash geçmişi",
             local / "Packages" / "CanonicalGroupLimited.Ubuntu"
             / "LocalState" / "rootfs" / "root" / ".bash_history"),
            # Cmder / ConEmu
            ("Cmder geçmişi",
             appdata / "Cmder" / "history"),
            # Git Bash (MSYS2)
            ("Git Bash geçmişi", h / ".bash_history"),
            # Neovim (Windows)
            ("Neovim ShaDa",
             local / "nvim-data" / "shada" / "main.shada"),
            # Python Launcher geçmişi (bazen oluşur)
            ("Python Launcher geçmişi",
             appdata / "Python" / "Python3" / "history"),
        ]
        targets.extend(windows_targets)

    # ── macOS ─────────────────────────────────────────────────────
    elif is_macos():
        macos_targets: list[tuple[str, Path]] = [
            ("Zsh geçmişi",             h / ".zsh_history"),
            ("Bash geçmişi",            h / ".bash_history"),
            ("Fish geçmişi",
             h / ".local" / "share" / "fish" / "fish_history"),
            ("Nano arama geçmişi",      h / ".nano" / "search_history"),
            ("Less geçmişi",            h / ".lesshst"),
            # macOS varsayılan zsh geçmişi (zsh_sessions)
            ("Zsh Oturum geçmişi",
             h / ".zsh_sessions"),
            # Neovim
            ("Neovim ShaDa",
             h / ".local" / "state" / "nvim" / "shada" / "main.shada"),
            # macOS Terminal son komutlar (plist — sadece kesilebilir)
            ("Terminal SavedState",
             h / "Library" / "Saved Application State"
             / "com.apple.Terminal.savedState"),
        ]
        targets.extend(macos_targets)

    # ── Linux ─────────────────────────────────────────────────────
    elif is_linux():
        data_home = localappdata_dir() or (h / ".local" / "share")
        linux_targets: list[tuple[str, Path]] = [
            ("Bash geçmişi",            h / ".bash_history"),
            ("Zsh geçmişi",             h / ".zsh_history"),
            ("Fish geçmişi",
             data_home / "fish" / "fish_history"),
            ("Nano arama geçmişi",      h / ".nano" / "search_history"),
            ("Less geçmişi",            h / ".lesshst"),
            ("Neovim ShaDa",
             h / ".local" / "state" / "nvim" / "shada" / "main.shada"),
        ]
        targets.extend(linux_targets)

    return targets


def clean_shell_history(dry_run: bool = False) -> list[dict]:
    """
    Kabuk ve REPL geçmiş dosyalarını cross-platform olarak temizler.

    Args:
        dry_run: True ise dosyaları silmez, sadece rapor üretir.

    Returns:
        Silinen/silinecek dosyaların bilgilerini içeren liste.
    """
    results: list[dict] = []
    targets = _history_targets()

    for description, file_path in targets:
        if should_exclude(file_path):
            continue

        # Dizin ise (Zsh oturumlar gibi) dizini sıfırla
        if file_path.is_dir():
            from utils.helpers import get_dir_size, safe_remove
            size = get_dir_size(file_path)
            if size == 0:
                continue
            item = {"path": str(file_path), "size": size, "type": description}
            if dry_run:
                print_info(f"[dim]{description}[/dim]  →  {file_path}  ({size:,} bayt)")
                results.append(item)
            else:
                if safe_remove(file_path):
                    print_success(f"{description} temizlendi  →  {file_path}")
                    results.append(item)
                else:
                    print_warning(f"{description} temizlenemedi  →  {file_path}")
            continue

        if not file_path.is_file():
            continue

        size = get_file_size(file_path)
        if size == 0:
            continue

        item = {"path": str(file_path), "size": size, "type": description}

        if dry_run:
            print_info(f"[dim]{description}[/dim]  →  {file_path}  ({size:,} bayt)")
            results.append(item)
        else:
            try:
                file_path.write_text("", encoding="utf-8")
                print_success(f"{description} temizlendi  →  {file_path}")
                results.append(item)
            except (PermissionError, OSError) as exc:
                print_warning(f"{description} temizlenemedi: {exc}")

    if not results:
        print_info("Temizlenecek kabuk geçmişi bulunamadı.")

    return results
