"""
Async email OSINT runner.

Passive checks are executed concurrently. Catalog entries that could trigger
password resets, OTP flows, or login notifications are skipped locally.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from osint.services import ALL_SERVICES, PASSIVE_SERVICE_FUNCTIONS
from utils import __version__
from utils.display import console


USER_AGENT = f"Trackher/{__version__}"


async def _run_check(
    name: str,
    check_fn: Any,
    email: str,
    client: httpx.AsyncClient,
    progress: Progress,
    task_id: Any,
) -> dict:
    """Run a single service check and update progress."""
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


async def _skip_side_effectful_check(name: str, progress: Progress, task_id: Any) -> dict:
    """Skip a potentially side-effectful check without sending a network request."""
    progress.update(task_id, advance=1, description=f"[dim]{name} (atlandı)[/dim]")
    return {
        "service": name,
        "found": False,
        "status": "skipped",
        "detail": "Yan etkili parola sıfırlama veya OTP isteği güvenlik için gönderilmedi",
    }


async def check_email(email: str) -> list[dict]:
    """Check an email address against passive services and safe catalog rules."""
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
            TextColumn("[bold cyan]Taraniyor:[/bold cyan]"),
            BarColumn(bar_width=30, complete_style="green", finished_style="bold green"),
            MofNCompleteColumn(),
            TextColumn("|"),
            TimeElapsedColumn(),
            TextColumn("|"),
            TextColumn("{task.description}"),
            console=console,
            transient=False,
        ) as progress:
            task_id = progress.add_task("Baslatiliyor...", total=len(ALL_SERVICES))

            tasks = [
                _run_check(name, check_fn, email, client, progress, task_id)
                if check_fn in PASSIVE_SERVICE_FUNCTIONS
                else _skip_side_effectful_check(name, progress, task_id)
                for name, check_fn in ALL_SERVICES
            ]

            completed = await asyncio.gather(*tasks, return_exceptions=True)

            for item in completed:
                if isinstance(item, dict):
                    results.append(item)
                elif isinstance(item, Exception):
                    results.append(
                        {
                            "service": "Bilinmeyen",
                            "found": False,
                            "status": "unknown",
                            "detail": f"Hata: {item}",
                        }
                    )

    console.print()
    return results


def run_email_check(email: str) -> list[dict]:
    """Synchronous wrapper for check_email."""
    return asyncio.run(check_email(email))
