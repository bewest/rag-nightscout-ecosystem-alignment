# Backfix 2 integration record, 2026-09-23

*Contributor-facing. Snapshot, 2026-09-23, on local scratch branch `rc/backfix-2` (not pushed),
against cgm-remote-monitor `origin/dev` `74fc6619` and `origin/chore/nightscout-modernization`
`b1bdaca0`. Superseded: the latest combined run is
[rc-15.0.9-combined-010](rc-15.0.9-combined-010-2026-09-24.md); item state is in
`queue/work-queue.yaml` (`RT-0`, `BF2-AUTH`). Plan: [backfix-2 plan](backfix-2-plan-2026-09-22.md).*

Two of the three units fix defects that are live on the shipping release
(15.0.8). This record describes mechanisms only.

## Branch

`rc/backfix-2`, created from `74fc6619` by SHA. Tip `e9a4ef62`. Each unit is one
`git merge --no-ff` commit. No unit was dropped.

| first-parent | commit | unit (tip) |
|---|---|---|
| 3 | `e9a4ef62` | `bf2/auth-hardening` (`29e6430e`) |
| 2 | `658ed8bf` | `bf2/backports` (`b5038500`) |
| 1 | `505c5169` | `bf2/ops` (`e6a50e9a`) |
| 0 | `74fc6619` | `origin/dev` |

Pairwise `git merge-tree` of the three units: all three pairs clean. Each merge
onto the integration branch was clean. `bf2/auth-hardening` and `bf2/backports`
both edit `lib/api3/alarmSocket.js`; the merged file carries both changes (the
client-address resolver and the redacted failure log lines).

## Full suite (`npm test`, own MongoDB 7 container)

| step | tree | Node | passing | failing | pending | delta |
|---|---|---|---|---|---|---|
| 0 | `74fc6619` | 20.20.0 | 2386 | 0 | 3 | |
| 1 | + `bf2/ops` | 20.20.0 | 2392 | 0 | 3 | +6 |
| 2 | + `bf2/backports` | 20.20.0 | 2404 | 0 | 3 | +12 |
| 3 | + `bf2/auth-hardening` | 20.20.0 | 2480 | 0 | 3 | +76 |
| 3 | + `bf2/auth-hardening` | 22.23.2 | 2480 | 0 | 3 | |

The final figure equals the additive expectation (2386 + 6 + 12 + 76). No test
was added, lost or changed state by integration.

## Targeted tests and break-its on the integrated tree

A break-it reverts the unit's library file(s) on the integrated tree, runs the
unit's own tests, and restores. It counts only when the failures reproduce the
defect the unit fixes.

| unit | targeted | result | break-it | failing | reproduces the defect |
|---|---|---|---|---|---|
| ops | `api.alexa`, `booterror`, `plugins` | 23/23 | `lib/plugins/index.js` from dev | 1 of 14 | yes: the enabled-check answers yes for a disabled plugin |
| ops | | | `lib/api/alexa/index.js` from dev | 1 of 5 | yes: an unhandled request type gets no answer (timeout) |
| ops | | | `lib/server/booterror.js` from dev | 2 of 4 | yes: the two no-error cases fail, the two controls pass |
| backports | `api3.alarm-logging`, `storage-read-permissions` | 12/12 (before and after step 3) | `lib/api3/alarmSocket.js` + `lib/api/entries/index.js` from dev | 7 of 12 | yes: credentials reach the log (6); a read is allowed where it should be refused (1) |
| backports | | | reverse-apply only this unit's library hunks, keeping step 3's changes | 7 of 12 | yes, same 7 |
| auth-hardening | `client-ip` / `authdelay` / `authsubjects` / `env` | 48 / 19 / 8 / 28 | `lib/server/client-ip.js` from `395f3207` | 7 of 48 | yes: address resolution differs from dev's with `TRUST_PROXY` unset |
| auth-hardening | | | `lib/authorization/storage.js` from dev | 6 of 8 | yes: an access token is written to the collection in plaintext |
| auth-hardening | | | `lib/authorization/delaylist.js` from dev | 19 of 19 | **no**: all 19 time out because dev's module lacks a function the new caller uses. Not a valid control. |

## `git merge-tree` against other lines (not merged)

| other side | result | conflicting paths |
|---|---|---|
| `origin/chore/nightscout-modernization` `b1bdaca0` | conflicts | 12 |
| (for comparison) `bf2/auth-hardening` alone | conflicts | 10 |
| (for comparison) `origin/dev`, `bf2/ops` alone | conflicts | 1 (`lib/server/bootevent.js`) |
| (for comparison) `bf2/backports` alone | conflicts | 3 |
| `bf/count-zero-empty` `7b32d9ab` | clean | none (both touch `lib/api/index.js`, textually disjoint) |
| `bf/connect-pin-0.1.0` `338deb7f` | clean | none (both touch `package.json`, `package-lock.json`) |
| both 15.0.9 units combined | clean | none |

Integration against modernization adds two paths to auth-hardening's ten, both
add/add conflicts from `bf2/backports`: `tests/api3.alarm-logging.test.js` and
`tests/storage-read-permissions.test.js`, which the modernization branch also
adds. It removes none. `bf2/ops` adds none beyond dev's own `bootevent.js`.

Backfix 2 does not need a rebase for textual conflicts after the two 15.0.9
units land on dev. The combined suite with those units has not been run; it
must be measured on the re-cut branch, since `bf/count-zero-empty` and
`bf2/auth-hardening` both edit `lib/api/index.js`.
