"""
Dijital Ayak İzi Temizleyici — Asenkron E-posta Arama Motoru

Tüm servis kontrol fonksiyonlarını eşzamanlı olarak çalıştırır
ve sonuçları toplar. Rich progress bar ile ilerleme gösterir.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    MofNCompleteColumn,
    TimeElapsedColumn,
)

from osint.services import ALL_SERVICES
from utils.display import console


# Tarayıcı benzeri User-Agent başlığı
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


async def _run_check(
    name: str,
    check_fn: Any,
    email: str,
    client: httpx.AsyncClient,
    progress: Progress,
    task_id: Any,
) -> dict:
    """Tek bir servis kontrolünü çalıştırır ve ilerleme çubuğunu günceller."""
    try:
        result = await check_fn(email, client)
    except Exception:
        result = {
            "service": name,
            "found": False,
            "status": "unknown",
            "detail": "Beklenmeyen hata",
        }

    progress.update(task_id, advance=1, description=f"[dim]{name}[/dim]")
    return result


async def check_email(email: str) -> list[dict]:
    """
    E-posta adresini tüm tanımlı servislerde eşzamanlı olarak kontrol eder.

    Args:
        email: Kontrol edilecek e-posta adresi.

    Returns:
        Her servis için sonuç dict'lerinin listesi.
    """
    timeout = httpx.Timeout(15.0, connect=10.0)
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/json,*/*",
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    }

    results: list[dict] = []

    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        headers=headers,
        follow_redirects=True,
        http2=False,
    ) as client:

        with Progress(
            SpinnerColumn("dots"),
            TextColumn("[bold cyan]Taranıyor:[/bold cyan]"),
            BarColumn(bar_width=30, complete_style="green", finished_style="bold green"),
            MofNCompleteColumn(),
            TextColumn("│"),
            TimeElapsedColumn(),
            TextColumn("│"),
            TextColumn("{task.description}"),
            console=console,
            transient=False,
        ) as progress:

            task_id = progress.add_task(
                "Başlatılıyor...",
                total=len(ALL_SERVICES),
            )

            tasks = [
                _run_check(name, fn, email, client, progress, task_id)
                for name, fn in ALL_SERVICES
            ]

            completed = await asyncio.gather(*tasks, return_exceptions=True)

            for item in completed:
                if isinstance(item, dict):
                    results.append(item)
                elif isinstance(item, Exception):
                    results.append({
                        "service": "Bilinmeyen",
                        "found": False,
                        "status": "unknown",
                        "detail": f"Hata: {item}",
                    })

    console.print()
    return results


def run_email_check(email: str) -> list[dict]:
    """
    check_email fonksiyonunun senkron sarmalayıcısı.

    Args:
        email: Kontrol edilecek e-posta adresi.

    Returns:
        Servis sonuç listesi.
    """
    return asyncio.run(check_email(email))
