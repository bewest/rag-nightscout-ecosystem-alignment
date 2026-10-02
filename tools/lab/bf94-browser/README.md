# bf94-browser — BF-94 in a real browser

*Contributor-facing.* Measures whether an open Nightscout page keeps showing a temp basal that
has been shortened or cancelled (register BF-94, queue `BFQ-94`). Synthetic data only.

- `probe.js` boots one cgm-remote-monitor tree on a fresh database, seeds a 1.0 U/h profile and
  CGM readings, uploads a 2.0 U/h temp, opens the page in Chromium (Playwright), makes one
  scenario's change over REST as the client does, then samples the open page every 2 s: the
  basal pill's text and the basal line's value at "now" read from the rendered SVG. A fresh page
  in a new browser context and a reload of the open page are the control. The header comment
  describes the options.
- `run-all.sh <label> <tree> <port> <outdir>` runs every scenario with and without earlier temps
  on the chart. It needs `NODE_PATH` pointing at a `node_modules` with `playwright`, and a
  MongoDB 7 at `127.0.0.1:27941` started with `--ulimit nofile=64000:64000`.

Scenarios: `loop-new` (a new temp), `trio-reupload-new` (the old temp re-uploaded shortened, then a
new one), `aaps-v3` (PATCH the old temp shorter, POST a new one), `cancel-trio`, `cancel-aaps-v3`,
`cancel-oref` (a zero-length temp).

## Results, 2026-10-02

`results/run2/` is the measurement on `dev` `ca6fcfaf`, `v15.0.8` `92d08342` and the fix branch
`bf/profile-temp-cache` `2a64c500`, one tree at a time (Node 22.23.2, MongoDB 7.0.43): one JSON per
tree, scenario and history setting, the server log, and screenshots named
`<tree>-<scenario>[-h]-{0-before,1-live,2-live-end,3-fresh,4-reloaded}.png`. `results/persist/`
times how long the stale value lasts after a cancel on `dev` and `v15.0.8`.

| scenario | `dev` and `v15.0.8` (identical) | fix branch |
|---|---|---|
| `loop-new`, `cancel-oref` | correct | correct |
| `trio-reupload-new`, `aaps-v3` | pill and line wrong for about 14 s | correct |
| `cancel-trio`, `cancel-aaps-v3` | pill and line keep the cancelled rate until the temp's original end when it is the only temp on the chart; about 6 to 15 s with earlier temps | correct |

A fresh page and a reload were correct in every case. The edited record arrives as an update and
replaces the stored object, while `prevBasalTreatment` (module scope in `lib/profilefunctions.js`)
keeps the old one with its original end.
