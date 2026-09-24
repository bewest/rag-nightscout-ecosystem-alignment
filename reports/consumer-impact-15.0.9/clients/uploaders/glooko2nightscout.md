# glooko2nightscout — Nightscout API use

All findings are **read-derived**. Nothing was run.

- Repo: `externals/glooko2nightscout`
- Ref analysed: `origin/main` **9ab8c60** (2025-09-01). Only branch.
- Local checkout: HEAD 9ab8c60, behind=0, dirty=0.

## Finding: this client does not call Nightscout at all

At this ref the repo is one script, `glooko-cgm-reader.js`, that logs into Glooko, reads CGM
readings, converts them to Nightscout-*shaped* entries in memory, and writes them to a local JSON
file. There is no HTTP call to a Nightscout site. `deploy.sh` commits with the message "removed
external API calls", consistent with this.

**Positive control** (the same grep reaches this file's network code):
`glooko2nightscout@9ab8c60 glooko-cgm-reader.js:240` (`axios.get(…/api/v3/session/users)`) and `:399`
(`axios.get(graphApiUrl)`) — both are **Glooko's** API. Output: `glooko-cgm-reader.js:742` (`fs.writeFileSync`).

Patterns searched (`git grep -n -E <pat> origin/main -- .`): `api/v1`, `api/v2`, `api/v3`,
`nightscout`, `axios\.(post|put|get)`, `fetch\(`, `https?\.request`, `count`, `find\[`,
`api-secret`, `api_secret`, `token`, `_id`, `socket`, `writeFile`.

| S-id | what the client does | anchor | patterns searched |
|---|---|---|---|
| S1–S15 | None found for every surface: no Nightscout request of any kind. The only `/api/v3/…` URLs are Glooko endpoints on `this.config.apiUrl` (a Glooko host). | `glooko-cgm-reader.js:22`, `:240`, `:389-399`, `:522-564`, `:742` | as above |

## Worth cross-checking

None. Not a Nightscout API consumer at this ref.
