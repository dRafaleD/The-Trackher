# Changelog

## 1.2.0-rc8 - 2026-09-08

- hardened 80 username platform checks with site-specific API and profile evidence rules
- added structured profile validation for HTML and Steam XML responses
- preserved unknown results for rate limits, challenges, redirects, schema drift, and blocked sites
- corrected changed endpoints for TopCoder, Brave Community, Ask Fedora, Shikimori, and Lobsters
- added independent regression coverage and documented both live observations and limitations

## 1.2.0-rc7 - 2026-08-23

- added profile-aware request pacing for quick, standard, deep, username-only, and email-only scans
- added site and domain rate-limit handling with explicit paused/skipped states and Retry-After support
- added site-specific pacing and deep-scan limits for sensitive platforms
- expanded username and email verification coverage while preserving evidence-based unknown results
- translated CLI, GUI, cleanup output, reports, and search-dork labels to English
- documented profile usage and pacing examples in `--help`

## 1.2.0 - 2026-08-15

- tightened GUI terminal queue handling and long-session memory behavior
- improved directory shredding to stream files instead of collecting everything first
- added reporting hooks for directory shredding without retaining large result lists
- clarified email and username scan summaries for unknown and skipped results
- refreshed the HTML report layout and safer invalid-link rendering
- polished repository documentation for open-source release readiness

## 1.1.0 - 2026-08-14

- removed risky and false-positive-prone email checks
- added explicit skipped status for side-effectful catalog entries
- improved cross-platform temp, cache, and browser cleanup paths
- added protections for critical directories, symbolic links, and non-interactive destructive actions
- introduced CI coverage for Windows, macOS, and Linux
