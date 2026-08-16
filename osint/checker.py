"""Async email OSINT runner."""

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

from osint.services import (
    ACCOUNT_PLATFORMS,
    BREACH_PLATFORMS,
    ERROR,
    check_account_platform,
    check_breach_platform,
)
from utils import __version__
from utils.display import console
from utils.profiles import select_email_platforms


USER_AGENT = f"Trackher/{__version__}"


async def _run_account_check(
    platform: dict[str, Any],
    email: str,
    client: httpx.AsyncClient,
    progress: Progress,
    task_id: Any,
) -> dict[str, Any]:
    try:
        result = await check_account_platform(email, client, platform)
    except Exception as exc:
        result = {
            "service": platform.get("name", "Bilinmeyen"),
            "category": platform.get("category", "manual"),
            "status": ERROR,
            "found": False,
            "detail": type(exc).__name__,
            "url": platform.get("url", ""),
        }

    progress.update(task_id, advance=1, description=f"[dim]{platform.get('name')}[/dim]")
    return result


async def _run_breach_check(
    platform: dict[str, Any],
    email: str,
    client: httpx.AsyncClient,
    progress: Progress,
    task_id: Any,
) -> dict[str, Any]:
    try:
        result = await check_breach_platform(email, client, platform)
    except Exception as exc:
        result = {
            "service": platform.get("name", "Bilinmeyen"),
            "section": "breach",
            "status": ERROR,
            "found": False,
            "detail": type(exc).__name__,
            "breaches": [],
        }

    progress.update(task_id, advance=1, description=f"[dim]{platform.get('name')}[/dim]")
    return result


async def check_email(
    email: str,
    *,
    profile: str = "standard",
) -> dict[str, list[dict[str, Any]]]:
    """Check an email address without triggering side-effectful account flows."""
    timeout = httpx.Timeout(15.0, connect=10.0)
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/json,*/*",
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    }

    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        headers=headers,
        follow_redirects=True,
        http2=False,
    ) as client:
        account_platforms, breach_platforms = select_email_platforms(
            profile,
            ACCOUNT_PLATFORMS,
            BREACH_PLATFORMS,
        )
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
            task_id = progress.add_task(
                "Baslatiliyor...",
                total=len(account_platforms) + len(breach_platforms),
            )
            account_tasks = [
                _run_account_check(platform, email, client, progress, task_id)
                for platform in account_platforms
            ]
            breach_tasks = [
                _run_breach_check(platform, email, client, progress, task_id)
                for platform in breach_platforms
            ]
            accounts, breaches = await asyncio.gather(
                asyncio.gather(*account_tasks),
                asyncio.gather(*breach_tasks),
            )

    console.print()
    return {"accounts": list(accounts), "breaches": list(breaches)}


def run_email_check(
    email: str,
    *,
    profile: str = "standard",
) -> dict[str, list[dict[str, Any]]]:
    """Synchronous wrapper for check_email."""
    return asyncio.run(check_email(email, profile=profile))
