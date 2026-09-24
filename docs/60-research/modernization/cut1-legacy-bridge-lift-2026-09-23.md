# Lifting the legacy CGM bridge removal onto cut 1

> **Snapshot, 2026-09-23, on local branch `rh/cut1-retire-legacy` (tip `c043fb2d`, from `rh/cut1` `c77797e0`; not pushed), Node 22.23.2 and 24.20.0, MongoDB 7.0.43. Current: the latest word on the legacy bridge removal; cut 1 is not yet rebased onto `dev`, so the branch is a rehearsal. Contributor-facing, except §8, which is for operators. Current decisions: [backfix register](../../30-design/remedial/nightscout-backfix-register.md) BF-61, BF-62, BF-64; item state in queue items RT-1 and RT-5.**

## 1. What was decided

On 2026-09-23 the maintainer decided that:

- **BF-61 (option A).** Leftover `MMCONNECT_*` or `BRIDGE_*` settings that cannot be migrated
  should stop the site with a page that says what to fix. These settings are usually the
  site's primary data source.
- **BF-64.** mmconnect is deprecated and removed as early as possible, because it does not
  work and carries deprecated dependencies. The removal moves from cut 4 onto cut 1.

15.0.9 is the deprecation release. Its release notes describe the move to the connector, and
local branch `bf3/mmconnect-deprecation-warning` (`5d342ac1`, on dev) makes the boot log name
the replacement settings.

## 2. What was lifted

Cut 4 (`chore/mime-exposure-review`) removes both legacy bridges in eight commits. All eight
were cherry-picked onto `rh/cut1`, oldest first, and nothing else was taken from cut 4. The
other cut 4 work was left out: trusted proxies (`06c83f2f`), DOMPurify, Moment Timezone, MIME,
webpack and ESLint.

| cut 4 | lifted as | what it does | conflicts and how they were resolved |
|---|---|---|---|
| `16776eea` | `43df8603` | removes `lib/plugins/bridge.js` and `share2nightscout-bridge` | `bootevent.js`: kept cut 1's `require('bootevent')` chain and dropped `setupBridge`. `package.json`: kept cut 1's `env-cmd` scripts and removed `bridge` from the unit list. `docs/runtime-upgrade.md`: kept both sides. `docs/plans/legacy-bridge-review.md`: left deleted, because it does not exist on cut 1 |
| `bdc1ed96` | `64d30feb` | Dexcom TLS and database cutover tests | none |
| `33115480` | `631f69b7` | Dexcom session-expiry fixture | none |
| `84cc34be` | `1c11e788` | Dexcom logging-fix pin and tests | `package.json` and the lock: kept cut 1's pin (see below) |
| `8eed5337` | `f6a1f6d0` | keeps the legacy Dexcom US region selector | none |
| `78e7b818` | `36dad5ef` | removes `lib/plugins/mmconnect.js` and `minimed-connect-to-nightscout`, and adds `mmconnect-connect-compat.js` | `bootevent.js`: kept both requires and cut 1's chain, and dropped `setupMMConnect`. `package.json`: kept cut 1's scripts and pins, swapped `mmconnect` for `mmconnect-connect-compat` in the unit list, and dropped the `minimed-connect-to-nightscout` dependency and the `minimed-connect-to-nightscout` and `request` overrides. Lock regenerated with `npm install --package-lock-only`. `docs/plans`: kept cut 1's. `tests/dependency-{ajv6,qs}.test.js`: left deleted, because they do not exist on cut 1 |
| `0f7cf5fb` | `b22ae03d` | MiniMed HTTPS session fixtures | `docs/plans`: kept cut 1's (the other side is cut 2 to cut 5 plan history) |
| `23649d3f` | `2787bd5e` | MiniMed cutover fixtures | `package.json` and the lock: kept cut 1's pin. `docs/plans`: kept cut 1's |

**The connector pin stays at `0.1.0-dev.1`** (`rh/cut1`'s pin). Cut 4 moves the pin through
three connector commits: `9fa2c3c1`, `5349d479` and `c962a13f`. In `externals/nightscout-connect`,
`git merge-base --is-ancestor` shows all three are contained in both `v0.1.0-dev.1` and
`v0.1.0-dev.2`, so keeping `0.1.0-dev.1` does not move the pin backwards. Moving it to
`0.1.0-dev.2`, which dev pins since #8752, is a separate one-line change. [2026-09-24: `dev` now pins
exactly `0.1.0` (#8762), which also contains all three commits.]

Checks after the lift:

- The legacy files match cut 4's. There is no diff between `rh/cut4` and the new tip on the
  removed plugins, the MiniMed and Dexcom test files or their fixtures.
- The two shims differ from cut 4's only by the fixes in §3.
- `minimed-connect-to-nightscout`, `share2nightscout-bridge` and `request` are gone from the
  lock, along with 30 packages that only they pulled in.

## 3. The fixes decision A still needed

All of these are in commit `c043fb2d`.

| fix | change | regression test | break-it (reverted on the committed tree, then restored with `git checkout`) |
|---|---|---|---|
| **a. The named fix must boot** | Every boot error names each setting that fixes it. The MiniMed message says to add `connect` to `ENABLE` *and* set `CONNECT_COUNTRY_CODE`, because `CONNECT_*` settings are read only for plugins in `ENABLE`. The two conflict messages name a fix for each choice ("To keep X, remove … To use Y instead, …") | `tests/legacy-bridge-boot-errors.test.js`: resolves settings from environment variables through the real `lib/server/env.js`, runs the real `setupConnect` stage with the connector stubbed, and checks that applying each named fix boots with the right source | Dropping "connect to ENABLE" from the MiniMed message: **2 failing**, "boot error does not name connect to ENABLE" |
| **b. No release number** | "retired in Nightscout 15.0.9" → "has been removed", in both shims and both `bootevent.js` log lines. The README and `docs/runtime-upgrade.md` headings and anchors lose the number, and those docs now say to add `connect` to `ENABLE` | same file, plus the updated `bridge-connect-compat` and `connect-lifecycle` assertions | Putting "retired in Nightscout 15.0.9" back into the Dexcom message: **1 failing**, "boot error names a release number" |
| **c. BF-63 renderer guard** | already present (it came from the 15.0.9 candidate); no change | `tests/booterror.test.js` (existing) | Removing the `obj.err == null` branch: **2 failing**, the page renders `TypeError: Cannot convert undefined or null to object` |
| **d. BF-62** | `DEXCOM_BRIDGE_USE_LEGACY` (setting, prefixed form or `CUSTOMCONNSTR_`) is detected and logged: "DEXCOM_BRIDGE_USE_LEGACY is no longer supported and is ignored … Remove DEXCOM_BRIDGE_USE_LEGACY from your settings." Dexcom still migrates to the connector | same file: logs the line when set, and not when unset | Removing the log call from `bootevent.js`: **1 failing**, "no log line says the override is ignored" |

After restoring: 10 of 10 pass in those two files, and 36 of 36 across the five legacy test
files.

## 4. Boot matrix

`lib/server/server.js` was booted from the worktree on Node 24.15.0 against MongoDB 7.0.43
(`--ulimit nofile=64000:64000`), once per shape. Settings:

- `AUTH_DEFAULT_ROLES=denied`
- dummy credentials
- all outbound HTTP and HTTPS sent to a dead local proxy

The columns are the status codes of `GET /`, `/api/v1/status.json` and
`/api/v1/entries.json`. 401 on the API means the API is up and the request was unauthenticated.

| shape | codes | page |
|---|---|---|
| R1 control, no legacy settings | 200 / 401 / 401 | — |
| R2 `mmconnect` in `ENABLE`, `MMCONNECT_*`, no country | **500 / 500 / 500** | MiniMed message: add `connect` to `ENABLE`, set `CONNECT_COUNTRY_CODE` |
| R3 R2 plus `CONNECT_COUNTRY_CODE` only | **500 / 500 / 500** | same (the `ENABLE` rule, which is why the message names it) |
| R4 R2 plus the page's fix (`connect` in `ENABLE`, country) | 200 / 401 / 401 | — |
| R5 `bridge mmconnect`, `BRIDGE_*` + `MMCONNECT_*` + country | **500 / 500 / 500** | MiniMed conflict message |
| R6 R5 with `connect` in `ENABLE` | **500 / 500 / 500** | MiniMed conflict message |
| R7 R6 plus fix 1 (remove `MMCONNECT_*` and `mmconnect`) | 200 / 401 / 401 | — |
| R8 R6 plus fix 2 (remove `BRIDGE_*`, `CONNECT_SOURCE=minimedcarelink`) | 200 / 401 / 401 | — |
| R9 `bridge`, `BRIDGE_*` | 200 / 401 / 401 | — |
| R10 R9 plus `DEXCOM_BRIDGE_USE_LEGACY=true` | 200 / 401 / 401 | — (the "ignored" line logged once) |
| R11 `bridge connect`, `BRIDGE_*`, `CONNECT_SOURCE=glooko` with dummy Glooko credentials | **500 / 500 / 500** | Dexcom conflict message |
| R12 R11 plus fix 1 (remove `BRIDGE_*` and `bridge`) | 200 / 401 / 401 | — |
| R13 R11 plus fix 2 (`CONNECT_SOURCE=dexcomshare`) | 200 / 401 / 401 | — |

The first R12 run had no Glooko credentials. It gave 500, but from the connector's own "Glooko
User Login Email is required" check, not from the removal, so R11 and R12 were re-run with dummy
Glooko credentials.

For reference, on the 15.0.9 candidate `rc/15.0.9-additions-e` (`1b1977e0`), which still carries
both legacy plugins, R2 and R5 boot 200 / 401 / 401. The stop is new with this branch, as
decided.

Compared with `rh/cut4` in the 15.0.9-rc rehearsal (§4.5 of
[the rehearsal](../../30-design/modernization/cut-rehearsal-on-15.0.9-rc-2026-09-23.md)):

- The shapes that stop the site are the same.
- What changed is that each page now names a fix, and applying it boots (R4, R7, R8, R12, R13).
- On `rh/cut4`, R4's equivalent booted, but R3's fix ("set `CONNECT_COUNTRY_CODE`") did not,
  and the page did not say so.

## 5. Suites and audit

The full suite was run as in the rehearsal:

- `npm test` (`tests/*.test.js`), from a `git archive` of the tip
- `npm ci` under each Node version
- `my.test.env` = `tests/ci.test.env`, pointed at a dedicated `*_test` database

| tree | Node 22.23.2 · Mongo 7 | Node 24.20.0 · Mongo 7 |
|---|---|---|
| `rh/cut1` (`c77797e0`), recorded | 2104 / 0 / 1 | 2104 / 0 / 1 |
| `rh/cut1` (`c77797e0`), re-run here | 2104 / 0 / 1 | not run |
| `rh/cut1-retire-legacy` (`c043fb2d`) | 2121 / 0 / 1 | 2121 / 0 / 1 |

The re-run baseline matches the recorded figure. The delta is 2104 − 14 + 31 = 2121, by
passing test title, and Node 22 and 24 pass the identical set:

- **14 leave**, all testing the removed code:
  - 6 in `bridge.test.js` and 4 in `mmconnect.test.js`, the deleted plugins;
  - 2 in `dependency-axios.test.js`, mmconnect's axios cookie wrapper;
  - 1 in `bridge-connect-compat.test.js` and 1 in `connect-lifecycle.test.js`, both checking
    that the removed `DEXCOM_BRIDGE_USE_LEGACY` escape hatch still selects the legacy bridge.
- **31 arrive**:
  - 25 from the lifted cut 4 commits: `mmconnect-connect-compat` 7, `connect-minimed-cutover` 6,
    `bridge-connect-compat` 4, `connect-lifecycle` 4, `connect-minimed-transport` 1,
    `connect-dexcom-transport` 1, `api.entries` 1 and `dependency-axios` 1;
  - 6 from `legacy-bridge-boot-errors.test.js` (§3).

`npm audit --omit=dev --package-lock-only` (npm 11.12.1, advisory data as of 2026-09-23):

| tree | findings | high | moderate | low |
|---|---|---|---|---|
| `rh/cut1` | 15 | 3 | 11 | 1 |
| `rh/cut1-retire-legacy` | 9 | 1 | 7 | 1 |

Cleared: `request` (high), `form-data` (high), `har-validator`, `uuid`,
`minimed-connect-to-nightscout` and `share2nightscout-bridge`. What remains is build tooling
(`browserslist`, `ajv`, `ajv-errors`, `ajv-keywords`, `schema-utils`, `style-loader`,
`baseline-browser-mapping`, `postcss-selector-parser`) and `sanitize-html`.

This is the payoff the 15.0.9 audit predicted. Removing mmconnect alone clears only its own
finding, because `request` is also pulled in by the Dexcom bridge. Removing both clears six.

## 6. The RT-5 gate, rewritten

`tools/queue/gates/cut4-total-outage.js` now passes under decision A. For each shape an
operator can hold today:

- a shape that stops the site must name a fix, name no release number and expose no credential;
- applying the first fix the message names, as written, must boot with a connector source
  selected.

It models the `ENABLE` rule directly, because a gate reads git objects and cannot load
`env.js`. The branch's own test checks the same thing through the real `env.js`. It also checks
the BF-62 detector, plus a control with no legacy settings. `QUEUE_GATE_REF` selects the tree,
and the default is `rh/cut1-retire-legacy`.

| ref | result |
|---|---|
| `rh/cut1-retire-legacy` | 8 checked, 0 failing |
| `rh/cut4` | 8 checked, **5 failing**: both MiniMed no-country shapes (the named fix still stops, and the message names 15.0.9), both conflict shapes (no fix the gate can apply, and 15.0.9), BF-62 |
| dangling commit `6eb888b2` (the new tip with "connect to ENABLE" removed from the MiniMed message; on no branch) | 8 checked, **2 failing**: the two MiniMed rows, "named fix [set CONNECT_COUNTRY_CODE] STILL STOPS" |

## 7. What remains of cut 4, and BF-64

A trial `git merge-tree --write-tree` of later rehearsal tips into `rh/cut1-retire-legacy`
(merge base `c77797e0` in each case). Nothing was resolved.

| merged in | conflicted files | files |
|---|---|---|
| `rh/cut2` | 4 | `docs/runtime-upgrade.md` (2 hunks), `lib/server/bootevent.js` (1: cut 2's boot-sequence list still names `setupBridge` and `setupMMConnect`), `package.json` (2), `package-lock.json` (11) |
| `rh/cut3` | 4 | the same four |
| `rh/cut4` | 11 | the same four, plus README, the two shims, the two compat and lifecycle tests, `docs/plans`, and the MiniMed test spec: the lifted legacy content, now with the §3 fixes |
| `rh/cut35` | 11 | the same eleven as `rh/cut4` |

Every conflicted file is legacy-bridge content or a manifest. None of cut 4's other files
conflicts: trusted proxies, DOMPurify, Moment, MIME, webpack and ESLint.

When cuts 2 to 5 are rebased onto this cut 1:

- Each conflict resolves to this branch's side for the legacy files.
- Cut 2's boot-sequence list loses `setupBridge` and `setupMMConnect`.
- The lock is regenerated.

That was not done here.

**Consequence for BF-64.** BF-64 is that the adopted train ships cut 5 as a "dependency
release" while holding cut 4 back behind a deprecation release, although cut 5 contains cut 4.
With the removal on cut 1:

- 15.0.9 is the deprecation release.
- Cut 4's remainder no longer removes a CGM path. It is trusted proxies, DOMPurify, Moment,
  MIME, webpack and ESLint, so the reason for holding it back is gone.

What does still need a decision in cut 4 is the trusted-proxy change (`06c83f2f`): BF-88 and
the 15.0.9 `TRUST_PROXY` design already differ from it. That is outside this lift. (BF-88 was
decided on 2026-09-23: the cuts keep 15.0.9's unset default.)

## 8. For operators (plain language)

*This is not medical advice. Talk to your care team about what you rely on Nightscout for.*

Nightscout has had two old built-in ways to fetch CGM readings: one for MiniMed CareLink
(settings starting `MMCONNECT_`) and one for Dexcom Share (settings starting `BRIDGE_`). The
MiniMed one is reported not to work. Both are now replaced by the built-in connector (settings
starting `CONNECT_`). The release after 15.0.9 is planned to remove the old ones.

- **If you use `BRIDGE_` settings for Dexcom Share:**
  - They keep working through the connector, as they already have since 15.0.8.
  - If you also set `DEXCOM_BRIDGE_USE_LEGACY=true`, Nightscout now writes in its log that the
    setting is ignored. You can remove it.
- **If you still have `MMCONNECT_` settings:**
  - Nightscout will not start normally. It shows an error page that names what to add: put
    `connect` in your `ENABLE` setting, and set `CONNECT_COUNTRY_CODE` to the two-letter
    country where your CareLink account was created.
  - Doing both is enough for the site to start.
  - You can make the change now, on 15.0.9, using the steps in the 15.0.9 release notes.
- **If you have both `BRIDGE_` and `MMCONNECT_` settings:**
  - The connector reads one source per site, so the page asks you to choose.
  - Either remove the `MMCONNECT_` settings (and `mmconnect` from `ENABLE`) to keep Dexcom, or
    remove the `BRIDGE_` settings and set `CONNECT_SOURCE=minimedcarelink` with your country
    to use CareLink.

After any change, check that new readings are arriving. **Keep a second way to see your
readings** until you are sure, because while the error page shows, Nightscout has no readings to
show you.

## 9. Not measured

- **Live services.** Whether the connector reaches Dexcom or CareLink. Outbound traffic was
  blocked, and no real account was used.
- **Browser suite.** The browser suite on this tip (`rh/cut1`: 463 / 0).
- **Docker image.** An image build of this tip.
- **Mongo 4.4.** The suite against MongoDB 4.4.
- **Real rebase.** Rebasing cuts 2 to 5 onto this branch (§7 is a trial merge only).
- **Operator counts.** How many operators hold each shape.

## Reproduce

```sh
R=externals/cgm-remote-monitor-official
git -C $R log --oneline rh/cut1..rh/cut1-retire-legacy
git -C externals/nightscout-connect merge-base --is-ancestor c962a13f v0.1.0-dev.1   # exits 0
node tools/queue/gates/cut4-total-outage.js                                          # default ref
QUEUE_GATE_REF=rh/cut4 node tools/queue/gates/cut4-total-outage.js                   # red, 5
git -C $R merge-tree --write-tree --name-only rh/cut1-retire-legacy rh/cut4
# tests: tests/legacy-bridge-boot-errors.test.js on the branch (NODE_ENV=test, own *_test DB)
# suites: git archive <tip> | tar -x; n exec <ver> npm ci; n exec <ver> npm test
```
