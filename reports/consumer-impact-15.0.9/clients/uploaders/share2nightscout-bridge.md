# share2nightscout-bridge — Nightscout API use

All findings are **read-derived**. Nothing was run.

- Repo: `externals/share2nightscout-bridge` (package `version` 0.2.12 — the version the candidate
  depends on, cgm-remote-monitor ddd9b600 `package.json:147` `^0.2.12`)
- Ref analysed: `origin/master` **518c85c** (2026-03-03) (= `official/master`).
  `origin/dev` 937142b (2026-02-27) is the local HEAD; `git diff --stat origin/master origin/dev -- index.js` is empty.
- Local checkout: HEAD 937142b, 3 behind master, dirty=0.

## How it reaches Nightscout

Two modes. **Embedded in cgm-remote-monitor** (legacy Dexcom path, used only when
`DEXCOM_BRIDGE_USE_LEGACY=true`, because 15.0.8+ routes `BRIDGE_*` to nightscout-connect —
ddd9b600 `lib/server/bootevent.js:118`, `:398`): cgm-remote-monitor passes `opts.callback`, which
calls `entries.create` in-process (ddd9b600 `lib/plugins/bridge.js:14-27`, `:76-79`), and sets
`nightscout: {}`, so the HTTP upload below never runs. **Standalone**: HTTP POST.

## Positive controls

- `share2nightscout-bridge@518c85c index.js:51` — `nightscout_upload: '/api/v1/entries.json'`
- `share2nightscout-bridge@518c85c index.js:259-268` — `report_to_nightscout` POST

Patterns searched (`git grep -n -E <pat> origin/master -- index.js`): `api/v1`, `api/v2`, `api/v3`,
`count`, `find`, `\$`, `api-secret`, `token`, `_id`, `socket`, `devicestatus`, `treatments`,
`profile`, `statusCode`. (`maxCount`/`minutes` hits at `:50`, `:192-196`, `:295`, `:402-403` are
Dexcom Share parameters, not Nightscout.)

| S-id | what the client does | anchor (repo@sha path:line) | patterns searched |
|---|---|---|---|
| S1 | None found toward Nightscout (no reads). | — | `count` |
| S2 | None found. | — | `find`, `\$` |
| S3 | None found. | — | `\$gt`, `\$gte` |
| S4 | None found. | — | `/count/`, `/times/`, `status`, `verifyauth`, `properties` |
| S5 | `api-secret: sha1(API_SECRET)` header on every POST. No token/JWT, no subjects. `rejectUnauthorized: false` on both requests (TLS verification off). No X-Forwarded-For. | `index.js:259-268`, `:272-283` | `api-secret`, `token`, `Authorization` |
| S6 | None found. | — | `socket` |
| S7 | Entries without `_id`: `{sgv, date, dateString, trend, direction, device:'share2', type:'sgv'}`. Relies on the server's entries upsert for re-sent readings. | `index.js:232-255` | `_id`, `identifier` |
| S8 | None found. | — | `treatments` |
| S9 | None found. | — | `food` |
| S10 | None found. | — | `profile` |
| S11 | `nullify_battery_status` would POST `{uploaderBattery: false}` to `/api/v1/devicestatus.json`, but it is guarded by `runs === 0` after `runs++`, so it never runs. | `index.js:272-283`, `:334-350` | `devicestatus`, `battery` |
| S12 | None (POST bodies only). | — | `\[\]` |
| S13 | None found. | — | `api/v3` |
| S14 | None found. | — | `notifications` |
| S15 | The POST callback only logs (`'Nightscout upload', 'error', err, 'status', response.statusCode, body`); a 400 is dropped, not retried, and `response.statusCode` throws if `response` is undefined on a connection error. Later polls fetch only `maxCount` recent readings, so a dropped batch leaves a gap. Embedded mode: `entries.create` errors are logged by cgm-remote-monitor's `bridged` callback. | `index.js:353-356`; ddd9b600 `lib/plugins/bridge.js:27` | `statusCode`, `err` |

## Worth cross-checking

Nothing in the candidate's changed surface is sent (no count, find, `_id`, auth API). None.
