# Security Policy

## Supported Versions

Security fixes are applied to the latest code on the main branch.

## Reporting a Vulnerability

If the repository has GitHub Private Vulnerability Reporting enabled, please use it.
If it is not enabled, do not publish exploit details in a public issue.
Instead, open a minimal issue asking for a private contact path.

When reporting a vulnerability, include:

- affected operating system
- Python version
- reproduction steps
- expected behavior
- actual behavior
- a harmless proof of concept if possible

Do not include:

- real email addresses
- usernames tied to real people
- API keys or tokens
- cookies or session data
- generated reports containing sensitive data

## In Scope

The following are considered security issues:

- deletion behavior that bypasses exclusion rules or critical-path protections
- command injection or path injection
- HTML or JavaScript injection in reports
- network checks that unexpectedly trigger password reset, OTP, or sign-in notifications
- accidental leakage of sensitive data into logs, reports, or repository files
