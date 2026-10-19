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
from osint.evidence import email_evidence_view, evidence_card
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

    result['evidence_card'] = evidence_card(result)
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

    result['evidence_card'] = evidence_card(result)
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
    control=None,
    on_result=None,
    only_platforms: set[str] | None = None,
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
            if only_platforms is not None:
                account_platforms = [p for p in account_platforms if p['name'] in only_platforms]
                breach_platforms = [p for p in breach_platforms if p['name'] in only_platforms]
            if control is not None:
                control.register([p['name'] for p in account_platforms + breach_platforms] + ['Email domain'])
            semaphore = asyncio.Semaphore(max_concurrent)

            async def controlled(platform, factory, section):
                from osint.scan_control import ScanStopped, interrupted_result
                try:
                    result = await control.run(platform['name'], factory, semaphore) if control is not None else await factory()
                except ScanStopped:
                    result = interrupted_result(platform, email=True)
                    result['section'] = section
                result.setdefault('section', section)
                if on_result is not None:
                    try:
                        on_result(dict(result))
                    except Exception:
                        pass
                return result

            accounts, breaches, domain = await asyncio.gather(
                asyncio.gather(*(controlled(p, lambda p=p: _run_account_check(p, email, client, progress, task_id), 'account') for p in account_platforms)),
                asyncio.gather(*(controlled(p, lambda p=p: _run_breach_check(p, email, client, progress, task_id), 'breach') for p in breach_platforms)),
                controlled({'name': 'Email domain'}, lambda: _run_domain_check(email, client, progress, task_id), 'domain'),
            )

    console.print()
    return {
        "domain": domain,
        "accounts": list(accounts),
        "breaches": list(breaches),
        "request_policy": dict(request_policy),
        "evidence_summary": email_evidence_view(accounts, breaches, domain),
    }


def run_email_check(
    email: str,
    *,
    profile: str = "standard",
) -> dict[str, Any]:
    """Synchronous wrapper for check_email."""
    return asyncio.run(check_email(email, profile=profile))
