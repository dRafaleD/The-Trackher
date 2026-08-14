from __future__ import annotations

import os
import platform
import plistlib
import shlex
import subprocess
import sys
from pathlib import Path

from utils.display import print_error, print_info, print_success


TASK_LABEL = "com.trackher.cleanup"


def _task_arguments() -> list[str]:
    script_path = Path(__file__).parent.parent.resolve() / "main.py"
    return [
        sys.executable,
        str(script_path),
        "--clean-all",
        "--yes",
        "--no-banner",
    ]


def _schedule_windows(interval: str) -> None:
    task_name = "DigitalAyakIziTemizleyici"
    task_command = subprocess.list2cmdline(_task_arguments())
    schedule = "DAILY" if interval == "daily" else "WEEKLY"
    command = [
        "schtasks", "/create", "/tn", task_name, "/tr", task_command,
        "/sc", schedule, "/st", "14:00", "/f",
    ]
    if schedule == "WEEKLY":
        command.extend(["/d", "SUN"])

    subprocess.run(
        command,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print_success(
        f"Windows Görev Zamanlayıcıya '{task_name}' görevi ({schedule}) eklendi."
    )


def _schedule_linux(interval: str) -> None:
    cron_command = " ".join(shlex.quote(part) for part in _task_arguments())
    cron_time = "0 14 * * *" if interval == "daily" else "0 14 * * 0"
    marker = "# digitalayakizi-cleaner"
    cron_line = f"{cron_time} {cron_command} {marker}\n"

    current_process = subprocess.run(
        ["crontab", "-l"], capture_output=True, text=True
    )
    current_cron = current_process.stdout if current_process.returncode == 0 else ""
    retained_lines = [
        line for line in current_cron.splitlines()
        if marker not in line
    ]
    retained_cron = "\n".join(retained_lines)
    if retained_cron:
        retained_cron += "\n"

    subprocess.run(
        ["crontab", "-"],
        input=retained_cron + cron_line,
        text=True,
        capture_output=True,
        check=True,
    )
    print_success(f"Linux cron görevi ({interval}) eklendi.")


def _schedule_macos(interval: str) -> None:
    launch_agents = Path.home() / "Library" / "LaunchAgents"
    logs_dir = Path.home() / "Library" / "Logs" / "Trackher"
    launch_agents.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    plist_path = launch_agents / f"{TASK_LABEL}.plist"
    payload = {
        "Label": TASK_LABEL,
        "ProgramArguments": _task_arguments(),
        "StartInterval": 86400 if interval == "daily" else 604800,
        "ProcessType": "Background",
        "StandardOutPath": str(logs_dir / "cleanup.log"),
        "StandardErrorPath": str(logs_dir / "cleanup-error.log"),
    }
    with open(plist_path, "wb") as plist_file:
        plistlib.dump(payload, plist_file, sort_keys=True)

    domain = f"gui/{os.getuid()}"
    subprocess.run(
        ["launchctl", "bootout", domain, str(plist_path)],
        capture_output=True,
    )
    subprocess.run(
        ["launchctl", "bootstrap", domain, str(plist_path)],
        capture_output=True,
        check=True,
    )
    print_success(f"macOS launchd görevi ({interval}) eklendi: {plist_path}")


def schedule_task(interval: str = "daily", dry_run: bool = False) -> None:
    """Günlük veya haftalık temizliği işletim sisteminin zamanlayıcısına ekler."""
    interval = interval.lower()
    if interval not in {"daily", "weekly"}:
        print_error("Zamanlama aralığı 'daily' veya 'weekly' olmalıdır.")
        return

    system = platform.system()
    if dry_run:
        if system not in {"Windows", "Linux", "Darwin"}:
            print_error(f"Bu işletim sistemi için zamanlama desteklenmiyor: {system}")
            return
        print_info(
            f"Zamanlama simülasyonu: {system} üzerinde {interval} görev oluşturulacaktı."
        )
        return

    try:
        if system == "Windows":
            _schedule_windows(interval)
        elif system == "Linux":
            _schedule_linux(interval)
        elif system == "Darwin":
            _schedule_macos(interval)
        else:
            print_error(f"Bu işletim sistemi için zamanlama desteklenmiyor: {system}")
    except (OSError, subprocess.SubprocessError) as exc:
        print_error(f"Zamanlanmış görev eklenemedi: {exc}")
