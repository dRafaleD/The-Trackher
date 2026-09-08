# Trackher — second 40-site review

Date: 2026-09-08. This batch changes exactly 40 catalog entries outside the first batch. Combined review coverage: 80 distinct sites. The initial 40 catalog entries are unchanged. No commit, push or release was made.

## Results

30/40 public sample profiles were confirmed live; 26/40 sites confirmed both the sample profile and the negative control. Ten sample checks remained unknown. The negative control was trkhzz9817263. At most four sites were queried concurrently with a pause between same-site requests. These are a dated snapshot, not a guarantee against future website changes.

29 entries use strict JSON checks (including 24 Discourse-family forums). Eleven use the new structured-profile detector. Six of those eleven (Bitbucket, HackerRank, ArtStation, Sketchfab, NotABug.org, PyPi) have no verified positive structure: their empty evidence rules deliberately leave results unknown, even for a hypothetical HTTP 200 page. They are not claimed to be functional/verified detectors. Future positive evidence is needed before enabling detection. Other blocked sites retain strict contracts without claiming live success.

Hacker News null, Telegram Contact templates and Twitch generic pages are inconclusive, so the negative control stays unknown. In the final Last.fm run the negative request returned HTTP 600, also unknown; the initial exploratory request returned 404. Pardus had intermittent connectivity. YazBel's existing TLS-related disablement is preserved.

## Site-by-site evidence

| Site | Sample | Sample result | Negative result | Adjustment / observation |
| --- | --- | --- | --- | --- |
| OpenAI Developer Community | system | found | not_found | Pin forum API host and user.username; recognize error_type=not_found; disable weak HTML fallback. |
| Mozilla Discourse | system | found | not_found | Pin forum API host and user.username; recognize error_type=not_found; disable weak HTML fallback. |
| Unreal Engine Forums | system | found | not_found | Pin forum API host and user.username; recognize error_type=not_found; disable weak HTML fallback. |
| Brave Community | system | found | not_found | Followed and pinned new community.brave.app host. |
| Elastic Discuss | system | found | not_found | Pin forum API host and user.username; recognize error_type=not_found; disable weak HTML fallback. |
| Ubuntu Community Hub | system | found | not_found | Pin forum API host and user.username; recognize error_type=not_found; disable weak HTML fallback. |
| Signal Community | system | found | not_found | Pin forum API host and user.username; recognize error_type=not_found; disable weak HTML fallback. |
| Obsidian Forum | system | found | not_found | Pin forum API host and user.username; recognize error_type=not_found; disable weak HTML fallback. |
| Home Assistant Community | system | found | not_found | Pin forum API host and user.username; recognize error_type=not_found; disable weak HTML fallback. |
| Hugging Face Forums | system | found | not_found | Pin forum API host and user.username; recognize error_type=not_found; disable weak HTML fallback. |
| PyTorch Forums | system | found | not_found | Pin forum API host and user.username; recognize error_type=not_found; disable weak HTML fallback. |
| Rust Users Forum | system | found | not_found | Pin forum API host and user.username; recognize error_type=not_found; disable weak HTML fallback. |
| Jupyter Community | system | found | not_found | Pin forum API host and user.username; recognize error_type=not_found; disable weak HTML fallback. |
| Django Forum | system | found | not_found | Pin forum API host and user.username; recognize error_type=not_found; disable weak HTML fallback. |
| KDE Discuss | system | found | not_found | Pin forum API host and user.username; recognize error_type=not_found; disable weak HTML fallback. |
| Godot Forum | system | found | not_found | Pin forum API host and user.username; recognize error_type=not_found; disable weak HTML fallback. |
| YazBel Forum | system | unknown | unknown | Confirmed TLS hostname mismatch; preserve pre-existing disabled reason and certificate verification. |
| Pardus Forumları | system | unknown | not_found | Intermittent connection errors: sample unknown, negative JSON error was observed. |
| Hack The Box Forum | system | found | not_found | Pin forum API host and user.username; recognize error_type=not_found; disable weak HTML fallback. |
| Car Talk Community | system | found | not_found | Pin forum API host and user.username; recognize error_type=not_found; disable weak HTML fallback. |
| Cloudflare Community | system | unknown | unknown | Browser challenge; retain unknown without bypass. |
| Envato Forum | system | unknown | unknown | Observed redirect to help.author.envato.com; forbid interpreting help center as a profile. |
| Icons8 Community | system | found | not_found | Pin forum API host and user.username; recognize error_type=not_found; disable weak HTML fallback. |
| Leasehackr | system | found | not_found | Pin forum API host and user.username; recognize error_type=not_found; disable weak HTML fallback. |
| HackerNews | pg | found | unknown | Official Firebase API id; null remains unknown, since only publicly active users appear in the API. |
| Hugging Face | julien-c | found | not_found | Public overview endpoint user field; no display-name matching. |
| TopCoder | tourist | found | not_found | v5 returned 404 for tourist; v6 returned the actual handle. Switched to v6. |
| Bitbucket | atlassian | unknown | unknown | API and sampled public path could not establish a valid profile contract; conservative unknown. |
| Gravatar | matt | found | not_found | Legacy public JSON entry[0].preferredUsername; exact root string missing error. |
| HackerRank | hacker | unknown | unknown | Old REST route returns 404; public page echoes user/query and yielded no verified profile contract. |
| ArtStation | artgerm | unknown | unknown | HTTP 403 blocks verification; no invented success signature. |
| Sketchfab | alban | unknown | unknown | HTTP 202 / challenge response, not profile evidence. |
| Coderwall | ryanb | found | not_found | Public JSON username field. |
| NotABug.org | dusnm | unknown | unknown | Both sample and control gave 404; that alone does not establish a working lookup route. |
| Telegram | telegram | found | unknown | Requires View title plus populated profile-title element. Contact template is inconclusive. |
| PyPi | pypa | unknown | unknown | Client Challenge for both requests; no challenge bypass or invented positive signature. |
| AtCoder | tourist | found | not_found | Require matching title and og:url, not a username mentioned elsewhere. |
| Steam | gaben | found | not_found | Parse XML profile, 17-digit steamID64 and matching customURL. Recognize explicit missing-profile XML. |
| Twitch | twitch | found | unknown | Requires requested og:url and video.other; generic Person markers and echoed URLs cannot suffice. |
| Last.fm | rj | found | unknown | Require profile og:url and header-title. Negative control became HTTP 600 in final run and stayed unknown. |

## Implementation and tests

Structured HTML checks parse actual elements and attributes, accept attribute-order/quote changes, and ignore script/comment pseudo-markup. Every configured positive condition must match. Steam uses XML parsing with ID plus vanity-name matching; DTD/entity declarations and invalid XML remain unknown. Login/foreign-host redirects, authentication errors, challenge pages and rate limits never verify a profile. For sites without a verified absence contract, an HTTP 404 alone is inconclusive.

245 tests passed with the project virtual environment using `python -m unittest discover -s tests`. The new fixtures independently cover all 40 entries, success/absence/unknown outcomes, API schema changes, status errors, script/comment injection, Twitch's old weak evidence and mismatched Steam identities. Original 40-site fixtures still pass. `git diff --check` passed.

The fixtures for blocked or unreachable APIs exercise their configured response contracts, not evidence that those services currently work. Public-profile finding is not proof that a person owns the account. Existing reliability labels were not upgraded.

References consulted: [official Hacker News API](https://github.com/HackerNews/API) (public-activity limitation), [Bitbucket user API](https://developer.atlassian.com/cloud/bitbucket/rest/api-group-users/), [Gravatar current API authentication](https://docs.gravatar.com/sdk/profiles/). The legacy Gravatar JSON endpoint was separately tested directly; no authentication bypass was attempted.

