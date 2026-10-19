# Additional unknown-result review - 2026-10-10

This follow-up inspected 18 services using one public reference name and one
synthetic negative control per service. Reference names are probe inputs, not
an assertion that every chosen profile must still exist. Requests were bounded
and no login, CAPTCHA bypass, or TLS-verification bypass was used.

## Corrections

- Crowdin: replace generic visible-username checking with the exact profile
  canonical URL AND a title ending in `(requested_username) – Crowdin`.
  The display name can change without breaking identity matching.
  Captured HTML and a fresh live recheck both returned found for `serge`;
  the synthetic negative returned not_found (HTTP 404).
- Linktree: require the exact Open Graph URL, `og:type=profile`, and exact
  `profile:username`, rather than the display title or echoed text.
  Captured HTML and a fresh live recheck returned found for `linktree`.
  The synthetic negative returned HTTP 406 and remains unknown: this status
  does not prove account absence. Existing deep-scan tier and five-second
  request pacing remain unchanged.

Public profile title and username are distinct, also documented by Linktree:
https://linktr.ee/help/en/articles/5434181-customize-your-profile-title

## Initial live observations before corrections

| Service | Reference input | Reference / synthetic negative | Interpretation |
| --- | --- | --- | --- |
| Reddit | spez | unknown / unknown, HTTP 403 | Access blocked; no speculative rule |
| AniList | AniList | found / not_found | Existing GraphQL rule works again |
| Bitbucket | jespern | unknown / unknown | Reference redirects to workspace repositories; workspace is not proof of a personal account |
| ArtStation | artgerm | unknown / unknown, HTTP 403 | Access denied |
| Sketchfab | alban | unknown / unknown, HTTP 202 | No usable profile evidence |
| SourceHut | sircmpwn | found / not_found | Existing rule worked for these controls |
| NPM | sindresorhus | unknown / unknown, HTTP 403 | Browser challenge |
| LeetCode | lee215 | unknown / unknown, HTTP 403 | Browser challenge |
| CodeChef | tourist | unknown / unknown, HTTP 403 | Browser challenge |
| OpenStreetMap | gravitystorm | not_found / not_found, HTTP 404 | No positive profile verified with this reference input |
| Speaker Deck | simon | found / not_found | Existing rule worked for these controls |
| Crowdin | serge | unknown / not_found | Fixed using title and canonical profile evidence |
| Replit | amasad | not_found / not_found, HTTP 404 | No positive profile verified with this reference input |
| Codepen | chriscoyier | unknown / unknown, HTTP 403 | Browser challenge |
| Hashnode | victor | not_found / not_found, HTTP 200 | Both pages explicitly titled User not found |
| BuyMeACoffee | buymeacoffee | not_found / not_found, HTTP 404 | Redirect to non-www host; no positive profile verified |
| Linktree | linktree | unknown / unknown | Fixed positive detection; negative HTTP 406 remains unknown |
| freeCodeCamp | quincylarson | not_found / not_found, HTTP 404 | No positive profile verified with this reference input |

Blocked or ambiguous services were not marked as working. These observations
are environment-dependent and do not verify all catalog entries in production.

## Verification

- 253 automated tests passed (six new follow-up tests).
- Regression coverage includes wrong identity, missing individual evidence,
  script/comment-only evidence, changed display title, access challenges,
  service errors, foreign redirects, and literal username punctuation.
- Existing 303-entry fixture contracts and reference-site set remain intact.
- Changes are local, on top of the previous uncommitted review. No commit,
  push, version change, or release was performed.
