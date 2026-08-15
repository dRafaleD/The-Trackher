# Changelog

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
