# Trackher: 40-site API compatibility review

Reviewed 2026-09-08. Changes are local; no commit, push, or release was made.

## Behavior

Exactly 40 existing API-backed catalog entries now opt into strict response handling. Each pins its API host and its existing platform-specific username path, and uses an explicit API-only detector chain. Schema changes, mismatched identities, authentication failures and service errors remain unknown instead of becoming a negative account result or falling back to a username echoed in HTML. Other 263 entries are unchanged.

Site-specific missing-profile error values are recorded in the catalog where observed. Codeforces no longer treats every HTTP 400 as missing. Keybase distinguishes success code 0, missing-user code 205 and invalid-input code 100. WordPress needs a positive integer site ID plus the requested site URL; this verifies a site, not a personal account. Mastodon instances require the local acct value, preventing remote namesakes from matching. API username comparisons preserve accents and reject non-string identities.

Ask Fedora now uses /u/{username}.json instead of the broken /askfedora/u/ path. Shikimori uses the observed shikimori.io host. Lobsters uses its current /~{username} route with JSON Accept. Kitsu retains application/vnd.api+json.

## Live checks

Public endpoints were queried with at most four sites concurrently, with a pause between the sample and negative-control requests. Negative control: trkhzz987654321. The earlier exploratory control was longer and triggered Keybase's input validation; this was not treated as evidence of absence.

38 sites returned found for the listed sample and not_found for the negative control. Reddit and AniList returned HTTP 403 for both; Reddit blocked access and AniList's JSON error reported a temporary API outage. Their live positive/negative behavior could not be verified, and the detector correctly left both unknown. Their response contracts are covered by offline fixtures, not claimed as live successes.

| Site | Sample | Sample result | Negative control | Checked API |
| --- | --- | --- | --- | --- |
| GitHub | octocat | found | not_found | https://api.github.com/users/{username} |
| Reddit | spez | unknown | unknown | https://www.reddit.com/user/{username}/about.json |
| Dailymotion | dailymotion | found | not_found | https://api.dailymotion.com/user/{username}?fields=id,username,screenname |
| Mixcloud | mixcloud | found | not_found | https://api.mixcloud.com/{username}/ |
| GitLab | gitlab-bot | found | not_found | https://gitlab.com/api/v4/users?username={username} |
| Gitea | lunny | found | not_found | https://gitea.com/api/v1/users/{username} |
| DockerHub | sindresorhus | found | not_found | https://hub.docker.com/v2/users/{username}/ |
| Chess.com | erik | found | not_found | https://api.chess.com/pub/player/{username} |
| Lichess | DrNykterstein | found | not_found | https://lichess.org/api/user/{username} |
| Dev.to | ben | found | not_found | https://dev.to/api/users/by_username?url={username} |
| WordPress | wordpressdotcom | found | not_found | https://public-api.wordpress.com/rest/v1.1/sites/{username}.wordpress.com/ |
| AniList | AniList | unknown | unknown | https://graphql.anilist.co |
| Wikipedia | Example | found | not_found | https://en.wikipedia.org/w/api.php?action=query&list=users&ususers={username}&format=json |
| Arduino Forum | system | found | not_found | https://forum.arduino.cc/u/{username}.json |
| Codeforces | tourist | found | not_found | https://codeforces.com/api/user.info?handles={username} |
| Speedrun.com | darbian | found | not_found | https://www.speedrun.com/api/v1/users?lookup={username} |
| Discogs | discogs | found | not_found | https://api.discogs.com/users/{username} |
| Lobsters | jcs | found | not_found | https://lobste.rs/~{username} |
| Kitsu | Josh | found | not_found | https://kitsu.io/api/edge/users?filter[name]={username} |
| Bangumi | sai | found | not_found | https://api.bgm.tv/v0/users/{username} |
| Shikimori | morr | found | not_found | https://shikimori.io/api/users/{username} |
| Trakt Forums | system | found | not_found | https://forums.trakt.tv/u/{username}.json |
| Codeberg | forgejo | found | not_found | https://codeberg.org/api/v1/users/{username} |
| Codewars | g964 | found | not_found | https://www.codewars.com/api/v1/users/{username} |
| Keybase | max | found | not_found | https://keybase.io/_/api/1.0/user/lookup.json?username={username} |
| Open Collective | webpack | found | not_found | https://opencollective.com/{username}.json |
| Playstrategy | thibault | found | not_found | https://playstrategy.org/api/user/{username} |
| RubyGems | rubygems | found | not_found | https://rubygems.org/api/v1/profiles/{username}.json |
| Ask Fedora | system | found | not_found | https://discussion.fedoraproject.org/u/{username}.json |
| Caddy Community | system | found | not_found | https://caddy.community/u/{username}.json |
| Cfx.re Forum | system | found | not_found | https://forum.cfx.re/u/{username}.json |
| Chaos.social | leah | found | not_found | https://chaos.social/api/v1/accounts/lookup?acct={username} |
| Fosstodon | kev | found | not_found | https://fosstodon.org/api/v1/accounts/lookup?acct={username} |
| Ionic Forum | system | found | not_found | https://forum.ionicframework.com/u/{username}.json |
| Joplin Forum | system | found | not_found | https://discourse.joplinapp.org/u/{username}.json |
| Mamot | laquadrature | found | not_found | https://mamot.fr/api/v1/accounts/lookup?acct={username} |
| n8n Community | system | found | not_found | https://community.n8n.io/u/{username}.json |
| Kayıp Rıhtım Forum | system | found | not_found | https://forum.kayiprihtim.com/u/{username}.json |
| Discourse Meta | system | found | not_found | https://meta.discourse.org/u/{username}.json |
| Python Discuss | system | found | not_found | https://discuss.python.org/u/{username}.json |

## Verification and limits

235 tests passed using the project virtual environment: python -m unittest discover -s tests. New tests pin 40 independent response shapes and cover schema drift, HTML echoes, outages, rate limits, malformed lists, foreign-host responses, browser challenges and special site errors. git diff --check passed.

This is a dated compatibility snapshot, not a guarantee that third-party endpoints will never change. Stricter checks deliberately increase unknown results when evidence is insufficient. WordPress custom-domain mappings may remain unknown. HTTP 404/410 still use the catalog's absence semantics, so future endpoint migrations require another review. Existing reliability labels were not upgraded.

Reference documentation consulted: [GitHub users API](https://docs.github.com/en/rest/users), [GitHub API troubleshooting](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api), [Mastodon accounts lookup](https://docs.joinmastodon.org/methods/accounts/#lookup). Live endpoint observations informed the platform-specific adjustments above.

