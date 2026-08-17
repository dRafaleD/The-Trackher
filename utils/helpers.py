"""
Dijital Ayak İzi Temizleyici — Yardımcı Fonksiyonlar

Dosya boyutu formatlama, yol genişletme, izin kontrolleri ve e-posta doğrulama.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Iterator
from pathlib import Path

# Global exclusion list
_EXCLUSIONS: list[Path] = []


def is_critical_path(path: Path, *, allow_temp_root: bool = False) -> bool:
    """Toplu silme için işletim sistemi ve kullanıcı köklerini korur."""
    resolved = Path(path).resolve()
    user_home = Path.home().resolve()
    runtime_temp = Path(tempfile.gettempdir()).resolve()
    is_allowed_temp = allow_temp_root and resolved == runtime_temp
    protected_exact = {user_home, *user_home.parents}
    if not allow_temp_root:
        protected_exact.add(runtime_temp)
    protected_trees: set[Path] = set()

    if os.name == "nt":
        for variable in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
            value = os.environ.get(variable)
            if value:
                protected_trees.add(Path(value).resolve())
    else:
        protected_trees.update(
            Path(item).resolve()
            for item in (
                "/bin", "/boot", "/dev", "/etc", "/lib", "/lib64", "/opt",
                "/proc", "/root", "/run", "/sbin", "/srv", "/sys", "/usr",
                "/var", "/Applications", "/Library", "/System",
            )
        )

    if resolved in protected_exact:
        return True
    if any(root == resolved for root in protected_trees):
        return True
    if not is_allowed_temp and any(root in resolved.parents for root in protected_trees):
        return True

    users_root = user_home.parent
    is_users_root = users_root.name.casefold() in {"home", "users"}
    is_other_user = (
        is_users_root
        and users_root in resolved.parents
        and user_home not in resolved.parents
    )
    return is_other_user


def load_exclusions(config_path: str) -> int:
    """JSON yapılandırmasındaki korunan yolları yükler ve sayısını döndürür."""
    global _EXCLUSIONS

    path = expand_path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"Dışlama dosyası bulunamadı: {path}")

    with open(path, "r", encoding="utf-8") as config_file:
        data = json.load(config_file)

    if not isinstance(data, dict):
        raise ValueError("Dışlama dosyasının kökü bir JSON nesnesi olmalıdır.")

    entries = data.get("exclude", [])
    if not isinstance(entries, list) or not all(
        isinstance(item, str) and item.strip() for item in entries
    ):
        raise ValueError("'exclude' alanı yalnızca yol metinlerinden oluşan bir liste olmalıdır.")

    exclusions = [expand_path(item) for item in entries]
    _EXCLUSIONS = list(dict.fromkeys(exclusions))
    return len(_EXCLUSIONS)


def should_exclude(path: Path) -> bool:
    """Belirtilen yolun exclusion (whitelist) listesinde olup olmadığını kontrol eder."""
    path = Path(path).resolve()
    for exc in _EXCLUSIONS:
        # Check if the path is exactly the excluded path or a child of it
        if path == exc or exc in path.parents:
            return True
    return False


def _contains_exclusion(path: Path) -> bool:
    """Yolun kendisinin veya altındaki bir yolun korunduğunu kontrol eder."""
    resolved = Path(path).resolve()
    return any(resolved == exc or resolved in exc.parents for exc in _EXCLUSIONS)


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


def expand_path(path_str: str, *, resolve_symlinks: bool = True) -> Path:
    """~ ve ortam değişkenlerini genişletip mutlak Path döndürür."""
    expanded = Path(os.path.expandvars(os.path.expanduser(path_str)))
    if resolve_symlinks:
        return expanded.resolve()
    return Path(os.path.abspath(expanded))


def get_dir_size(path: Path) -> int:
    """
    Bir dizinin toplam boyutunu (bayt) hesaplar.
    Erişim hatalarını sessizce atlar.
    """
    if should_exclude(path):
        return 0

    total = 0
    try:
        for root, dir_names, file_names in os.walk(path, topdown=True, followlinks=False):
            root_path = Path(root)
            dir_names[:] = [
                name for name in dir_names
                if not should_exclude(root_path / name)
            ]
            for name in file_names:
                entry = root_path / name
                try:
                    if not should_exclude(entry) and not entry.is_symlink():
                        total += entry.stat().st_size
                except (PermissionError, OSError):
                    continue
    except (PermissionError, OSError):
        pass
    return total


def get_file_size(path: Path) -> int:
    """Tek bir dosyanın boyutunu döndürür; hata durumunda 0."""
    try:
        if not should_exclude(path) and path.is_file():
            return path.stat().st_size
    except (PermissionError, OSError):
        pass
    return 0


def is_valid_email(email: str) -> bool:
    """Temel e-posta formatı doğrulaması."""
    if not 3 <= len(email) <= 254:
        return False
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    return re.fullmatch(pattern, email) is not None


def is_valid_username_query(username: str) -> bool:
    """URL ve terminal çıktısı için makul uzunlukta, yazdırılabilir hedef doğrular."""
    value = username.strip()
    return 1 <= len(value) <= 100 and all(character.isprintable() for character in value)


def safe_remove(path: Path, dry_run: bool = False) -> bool:
    """
    Dosya veya dizini güvenli biçimde siler.
    dry_run=True ise silmez, sadece True döndürür.
    """
    path = Path(path)
    if is_critical_path(path) or should_exclude(path):
        return False

    if dry_run:
        return True

    try:
        if path.is_file() or path.is_symlink():
            path.unlink()
            return True
        elif path.is_dir():
            return _remove_directory(path)
    except (PermissionError, OSError):
        return False

    return False


def _remove_directory(directory: Path) -> bool:
    """Korunan alt yolları atlayarak bir dizindeki silinebilir içeriği kaldırır."""
    removed_any = False
    successful = True

    try:
        for entry in directory.iterdir():
            if should_exclude(entry):
                continue

            try:
                if entry.is_dir() and not entry.is_symlink():
                    child_removed = _remove_directory(entry)
                    removed_any = removed_any or child_removed
                    if entry.exists() and not _contains_exclusion(entry):
                        successful = False
                else:
                    entry.unlink()
                    removed_any = True
            except (PermissionError, OSError):
                successful = False
    except (PermissionError, OSError):
        successful = False

    if not _contains_exclusion(directory):
        try:
            directory.rmdir()
            removed_any = True
        except (PermissionError, OSError):
            successful = False

    return successful and removed_any


def iter_files(directory: Path, pattern: str = "*") -> Iterator[Path]:
    """
    Belirtilen dizinde verilen glob kalıbına uyan dosyaları akış halinde döndürür.
    Erişim hatalarını sessizce atlar.
    """
    try:
        if directory.is_dir() and not should_exclude(directory):
            for root, dir_names, file_names in os.walk(directory, topdown=True, followlinks=False):
                root_path = Path(root)
                dir_names[:] = [
                    name for name in dir_names
                    if not should_exclude(root_path / name)
                ]
                for name in file_names:
                    entry = root_path / name
                    try:
                        if (
                            not should_exclude(entry)
                            and not entry.is_symlink()
                            and entry.match(pattern)
                        ):
                            yield entry
                    except (PermissionError, OSError):
                        continue
    except (PermissionError, OSError):
        return


def collect_files(directory: Path, pattern: str = "*") -> list[Path]:
    """iter_files sonucunu geriye dönük uyumluluk için liste olarak döndürür."""
    return list(iter_files(directory, pattern))
