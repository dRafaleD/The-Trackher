# Site settings review - 2026-10-10

Scope: twelve services, with two separate HackerRank routes. Public reference
profiles and a synthetic negative username were requested, with bounded timeouts
and a pause between requests. No authentication, challenge bypass, or account
enumeration beyond these limited checks was used.

## Changes

- HackerRank now uses `/profile/{username}`. Positive evidence requires all of:
  the requested profile's exact Open Graph URL (HTTP or HTTPS), the
  `hackerrank:hacker` profile type, and a nonempty `h1.profile-title`.
  A real public-profile HTML response captured during this review passes the
  updated detector. The negative response redirected to a generic page and
  remains unknown. A subsequent live request returned a browser challenge:
  successful extraction is therefore not guaranteed for every request.
- HackerRank 404 stays unknown: accounts without public activity can also
  produce 404, per the official profile FAQ:
  https://help.hackerrank.com/articles/4472358331-profile-and-preferences-faqs
- PyPI's profile URL now includes its canonical trailing slash. Browser
  challenges still remain unknown; no unverified positive rule was added.
- Generic HTML detectors now recognize visible access challenges before
  interpreting 404/410 as missing profiles. HTTP 429 retains rate-limit priority.

## Observed limitations and unchanged rules

| Service | Observed response / outcome |
| --- | --- |
| Telegram | Reference found; synthetic contact template unknown |
| Pardus Forumları | Reference found; synthetic missing user not_found |
| Twitch | Public HTML varied; final detector run unknown for both inputs |
| PyPI | Client Challenge for both inputs; unknown |
| ArtStation | HTTP 403 for both inputs; no reliable profile evidence |
| Sketchfab | HTTP 202 for both inputs; no reliable profile evidence |
| Bitbucket | API reference and synthetic requests both 404; no positive proof |
| NotABug.org | Both requests 404; no positive proof |
| YazBel Forum | TLS verification failure; existing safety restriction retained |
| Cloudflare Community | HTTP 403; no challenge bypass |
| Envato Forum | Redirect to help.author.envato.com with HTTP 403 |
| HackerRank | New public route verified from captured HTML; REST route 404 |

Blocked services were not relabeled as absent accounts or given speculative
success rules. These observations are time- and environment-dependent, not a
claim that all 303 catalog entries currently work live.

## Verification

- 247 automated tests passed, including all 303 catalog entries' fixture
  contracts and the existing 80-site review sets.
- New regressions cover HackerRank identity mismatch, profile type, missing
  heading, HTTP/HTTPS metadata, lookalike hosts, unsupported schemes, hidden
  profiles returning 404, and challenge responses with 404/410/429.
- The original captured HackerRank positive and generic redirect responses
  were evaluated with the updated parser: found and unknown respectively.
- Final live detector run: Telegram and Pardus confirmed expected outcomes;
  HackerRank/PyPI challenged, and Twitch lacked sufficient evidence.
- No commit, push, release, or version change was performed for this review.
