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
    check_email_domain,
)
from osint.request_policy import PoliteAsyncClient
from utils import __version__
from utils.display import console
from utils.profiles import profile_request_policy, select_email_platforms


USER_AGENT = f"Trackher/{__version__}"


async def _run_account_check(
    platform: dict[str, Any],
    email: str,
    client: httpx.AsyncClient,
    progress: Progress,
    task_id: Any,
) -> dict[str, Any]:
    try:
        platform_client = (
            client.for_platform(platform)
            if isinstance(client, PoliteAsyncClient)
            else client
        )
        result = await check_account_platform(email, platform_client, platform)
    except Exception as exc:
        result = {
            "service": platform.get("name", "Bilinmeyen"),
            "category": platform.get("category", "manual"),
            "status": ERROR,
            "found": False,
            "detail": type(exc).__name__,
            "url": platform.get("url", ""),
        }

    description = (
        f"[yellow]BEKLEMEDE: {platform.get('name')} (rate-limit)[/yellow]"
        if result.get("unknown_cause") == "rate_limited"
        else f"[dim]{platform.get('name')}[/dim]"
    )
    progress.update(task_id, advance=1, description=description)
    return result


async def _run_breach_check(
    platform: dict[str, Any],
    email: str,
    client: httpx.AsyncClient,
    progress: Progress,
    task_id: Any,
) -> dict[str, Any]:
    try:
        platform_client = (
            client.for_platform(platform)
            if isinstance(client, PoliteAsyncClient)
            else client
        )
        result = await check_breach_platform(email, platform_client, platform)
    except Exception as exc:
        result = {
            "service": platform.get("name", "Bilinmeyen"),
            "section": "breach",
            "status": ERROR,
            "found": False,
            "detail": type(exc).__name__,
            "breaches": [],
        }

    description = (
        f"[yellow]BEKLEMEDE: {platform.get('name')} (rate-limit)[/yellow]"
        if result.get("unknown_cause") == "rate_limited"
        else f"[dim]{platform.get('name')}[/dim]"
    )
    progress.update(task_id, advance=1, description=description)
    return result


async def _run_domain_check(
    email: str,
    client: httpx.AsyncClient,
    progress: Progress,
    task_id: Any,
) -> dict[str, Any]:
    try:
        domain_client = (
            client.for_platform({"rate_limit_key": "email-domain-dns"})
            if isinstance(client, PoliteAsyncClient)
            else client
        )
        result = await check_email_domain(email, domain_client)
    except Exception as exc:
        result = {
            "domain": email.rsplit("@", 1)[-1].strip().casefold(),
            "status": "UNKNOWN",
            "mail_routable": None,
            "detail": type(exc).__name__,
            "unknown_cause": "detector_error",
            "mx_hosts": [],
        }
    progress.update(task_id, advance=1, description="[dim]Email domain[/dim]")
    return result


async def check_email(
    email: str,
    *,
    profile: str = "standard",
) -> dict[str, Any]:
    """Check an email address without triggering side-effectful account flows."""
    timeout = httpx.Timeout(15.0, connect=10.0)
    request_policy = profile_request_policy(profile)
    max_concurrent = int(request_policy["max_concurrent"])
    limits = httpx.Limits(
        max_connections=max_concurrent,
        max_keepalive_connections=max_concurrent,
    )
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
    ) as raw_client:
        client = PoliteAsyncClient(
            raw_client,
            max_concurrent=max_concurrent,
            origin_interval_seconds=float(request_policy["request_interval_seconds"]),
        )
        account_platforms, breach_platforms = select_email_platforms(
            profile,
            ACCOUNT_PLATFORMS,
            BREACH_PLATFORMS,
        )
        with Progress(
            SpinnerColumn("dots"),
            TextColumn("[bold cyan]Scanning:[/bold cyan]"),
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
                total=len(account_platforms) + len(breach_platforms) + 1,
            )
            account_tasks = [
                _run_account_check(platform, email, client, progress, task_id)
                for platform in account_platforms
            ]
            breach_tasks = [
                _run_breach_check(platform, email, client, progress, task_id)
                for platform in breach_platforms
            ]
            domain_task = _run_domain_check(email, client, progress, task_id)
            accounts, breaches, domain = await asyncio.gather(
                asyncio.gather(*account_tasks),
                asyncio.gather(*breach_tasks),
                domain_task,
            )

    console.print()
    return {
        "domain": domain,
        "accounts": list(accounts),
        "breaches": list(breaches),
        "request_policy": dict(request_policy),
    }


def run_email_check(
    email: str,
    *,
    profile: str = "standard",
) -> dict[str, Any]:
    """Synchronous wrapper for check_email."""
    return asyncio.run(check_email(email, profile=profile))
