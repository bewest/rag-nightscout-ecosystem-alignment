# `bf3/mmconnect-deprecation-warning` — the MiniMed CareLink warning says what to set instead

**DRAFT — for maintainer review. Not pushed, not opened.** Branch
`bf3/mmconnect-deprecation-warning`, one commit `5d342ac1` on `origin/dev` `1f9a9d10` (queue
RT-4). No `CHANGELOG.md` edit. **For 15.0.9** (decided 2026-09-23: deprecate and remove the legacy
MiniMed bridge as early as possible; removal itself goes in the release after 15.0.9). Log text
only: no behaviour, setting or data changes.

---

## What changes for you

*Plain-language summary for people using Nightscout. Nightscout is not a medical device and none
of this is medical advice.*

A few words used below:

- **CareLink** — Medtronic's online service, where a MiniMed pump or phone app sends readings.
- **The old MiniMed connection** — Nightscout's older way of fetching readings from CareLink,
  set up with settings that start with `MMCONNECT_`. It is reported not to work, and a later
  release removes it.
- **The built-in connector** — Nightscout Connect, the newer way, set up with settings that start
  with `CONNECT_`.

### What changes

If your site still uses the old MiniMed connection, Nightscout's startup log used to say only
"PLEASE CONSIDER nightscout-connect instead." It now says what to set to move to the built-in
connector: add `connect` to `ENABLE`, set `CONNECT_SOURCE=minimedcarelink`, your CareLink
username, password and region (`CONNECT_CARELINK_USERNAME`, `CONNECT_CARELINK_PASSWORD`,
`CONNECT_CARELINK_REGION`), and `CONNECT_COUNTRY_CODE`, the two-letter country where your CareLink
account was created. Nightscout cannot work the country out from your old settings. Once readings
arrive through the connector, remove the `MMCONNECT_` settings and `mmconnect` from `ENABLE`.

Nothing else changes in this release. The same steps are in the 15.0.9 release notes.

### What you should do

If you use `MMCONNECT_` settings, move to the built-in connector before the release that removes
the old connection. After any change, check that your readings are arriving, and keep a second way
to see them until you are sure. If you rely on Nightscout for alarms, talk to your care team about
what else you use.

---

## Technical detail

- `lib/plugins/mmconnect.js` exports `DEPRECATION_WARNING`, the message above.
- `lib/server/bootevent.js` `setupMMConnect` logs `DEPRECATION WARNING` with that constant, on the
  same path and under the same condition as before (only when `init` returns a runner, i.e.
  `mmconnect` is enabled with a user name and password).
- The Dexcom `setupBridge` path is unchanged; it already names `DEXCOM_BRIDGE_USE_LEGACY`.

### Tests

`tests/mmconnect.test.js` gains one test: the message names `MMCONNECT_`, `ENABLE`,
`CONNECT_SOURCE=minimedcarelink`, the three CareLink settings and `CONNECT_COUNTRY_CODE`. The file
passes 5/5 on Node 20.20.0. **Break-it:** with `CONNECT_COUNTRY_CODE` deleted from the message, the
test fails on exactly that name, 4 passing / 1 failing.

The alignment repo's RT-4 gate (`tools/queue/gates/minimed-deprecation-path.js`), run against this
branch, reports the MiniMed warning naming an actionable setting (1 of 5 `DEPRECATION WARNING`
lines; 0 of 5 on `dev`). Its other check, a migration shim on `dev`, stays red by design: the shim
ships with the removal, not in 15.0.9.

Full suite on Node 20: 2387 passing, 0 failing, 3 pending, which is `dev` `1f9a9d10`'s 2386 plus
the one new test (run by the release session in its own worktree). The `CONNECT_*` names match
what `extendedSettings` camel-cases and what the CareLink source reads (`carelinkUsername`,
`carelinkPassword`, `carelinkRegion`, `countryCode`).

## For the reviewer to decide or verify

1. "Will be removed in a later release" carries no version number, because the release after
   15.0.9 is not numbered yet.
2. The message is one long log line, deliberately, so the whole instruction survives log
   filtering by the `DEPRECATION WARNING` prefix.
