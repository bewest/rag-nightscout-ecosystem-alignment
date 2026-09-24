# xdrip-js — Nightscout API use

All findings are **read-derived**. Nothing was run.

- Repo: `externals/xdrip-js`
- Ref analysed: `origin/master` **0cd1c55** (2022-04-30). Also grepped `origin/dev` **e301273**
  (2026-08-10), which is where development continues.
- Local checkout: HEAD 0cd1c55, behind=0, dirty=0.

## Finding: no Nightscout API use on master or dev

xdrip-js is a Bluetooth library for Dexcom G5/G6 transmitters (used by Lookout/Logger, which do
their own Nightscout I/O and are not in this corpus). Its runtime dependencies on master are
`crc`, `debug`, `noble`, `uuid` (`package.json` `"dependencies"`); there is no HTTP client.

**Positive control** (the grep reaches the library code): on `origin/dev`, the same search hits
`lib/bluetooth-manager.js:114-115` and `lib/keks_plugin/ble-packet.js:73-77` (an `_id`-suffixed
constant name and an env var) — code is searched, and none of it is a Nightscout call. On master
the files are `index.js`, `lib/*.js`, `lib/messages/*.js` (listed with `git ls-tree`), and the
network-library grep returns nothing.

Patterns searched (`git grep -n -i -E <pat> <ref> -- . ':!*.md'`, both refs): `api/v1`, `api/v2`,
`api/v3`, `nightscout`, `count=`, `find\[`, `api-secret`, `api_secret`, `verifyauth`, `socket.io`,
`_id`, `require\('(https?|request|axios|node-fetch|socket.io-client)'\)`, `fetch\(`, `http\.request`.
The only `nightscout` hits (dev `lib/keks_plugin/plugin.js:6-8`) are comments crediting xDrip commits.

| S-id | what the client does | anchor | patterns searched |
|---|---|---|---|
| S1–S15 | None found on either ref: no Nightscout request of any kind. | — | as above |

## Worth cross-checking

None. Out of scope for the consumer-impact join (not a Nightscout API consumer).
