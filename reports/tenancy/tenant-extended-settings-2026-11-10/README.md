# MT-TENANT-EXTENDED-SETTINGS (BF-232): tenant plugin extended settings

*Contributor-facing evidence record, captured 2026-11-10. Not edited after capture.*

| anchor | value |
|---|---|
| base | #8898 head `b70ad83fa4cdaeb7e6023137a05bd811d7db606a` (read from `git ls-remote official refs/pull/8898/head`) |
| branch | `codex/tenant-extended-settings-20261110`, head `2f1ae027ae834131213010e0d3b97fd0651ec28b`, one commit, local, unpushed |
| worktree | `externals/work/crm-tenant-extended-settings-20261110` |
| alignment `main` | `de1643e1b` |
| services | PostgreSQL 16.15 (`postgres@sha256:5db6dac2…ef83a`), MongoDB 7.0.43 (`mongo@sha256:1f995ad6…27a7b`, `--ulimit nofile=1048576:1048576`), Vault owned by the suite (`hashicorp/vault@sha256:962a9287…6fc2`); all removed afterwards |

## 1. Reproduction on the base: **reproduced**

Script: [`repro-base.test.js`](repro-base.test.js) (synthetic tenant, one reading 40 minutes old, the
actual `tenant-projection-evaluator` with a recording SQL double). Run on `b70ad83f`:

```
EVALUATOR_CONFIG refused: invalid explicit evaluator preview configuration
EMITTED []
CONTROL EMITTED [{"level":2,"group":"Time Ago","title":"Stale data, check rig?"}]
```

- **Evaluator process.** An operator evaluator configuration with
  `extendedSettings: {"timeago": {"enableAlerts": true}}` is refused whole
  (`lib/server/serve/evaluator-config.js:53-54` compares the input with the projected environment, which
  had dropped it). The tenant's evaluator does not start.
- **Serving process.** `preview-config.js:149` passes the same field to `environment()`, which silently
  drops it (`environment.js:56-58` on the base): `extendedSettings` is `{}`, nothing is emitted.
- **Harness control.** The same evaluator and reading, with the setting forced into the environment,
  emits the urgent stale-data alarm, so the harness can show the alarm.

The register's read-derived claim stands, and is wider than it says: the evaluator configuration
refuses the setting outright, rather than dropping it.

## 2. Survey: plugins under `lib/plugins/` that read extended settings

Read on `b70ad83f`. "Default" is the single-site value when unset. "Carried" is the state after
`2f1ae027`; on the base only `devicestatus.days` was carried.

| plugin (key) | `file:line` | settings | alert or notification | single-site default | carried |
|---|---|---|---|---|---|
| timeago | `timeago.js:20` | enableAlerts | yes, stale data (urgent/warn by `alarmTimeago*` settings) | off | yes |
| ar2 | `ar2.js:245` | coneFactor | no (forecast cone; the ar2 alarm does not read it) | 2 | yes |
| rawbg | `rawbg.js:16` | display | no | `unsmoothed` | yes |
| bolus | `bolus.js:13-15` | renderFormat, renderOver, notifyOver (read, unused) | no | `default`, 0, 0 | yes, plus renderFormatSmall (client, `README.md:551`) |
| basal | client `renderer.js:1215` | render | no | `none` | yes |
| profile | client `boluscalc.js:40-41` | multiple | no | off | yes |
| iage | `insulinage.js:17-20` | info, warn, urgent, enableAlerts | yes, insulin age | 44, 48, 72 h, off | yes |
| cage | `cannulaage.js:18-22` | info, warn, urgent, display, enableAlerts | yes, site age | 44, 48, 72 h, `hours`, off | yes |
| sage | `sensorage.js:18-21` | info, warn, urgent, enableAlerts | yes, sensor age | 144, 164, 166 h, off | yes |
| bage | `batteryage.js:17-21` | info, warn, urgent, display, enableAlerts | yes, pump battery age | 312, 336, 360 h, `days`, off | yes |
| errorcodes | `errorcodes.js:40,79-81` | info, warn, urgent | yes, CGM error codes (on by default) | `1 2 3 4 5 6 7 8`, none, `9 10` | yes (string or number, as a single site's parser yields) |
| upbat | `upbat.js:18-20` | warn, urgent, enableAlerts | yes, uploader battery | 30, 20 %, off | yes |
| pump | `pump.js:30-56` | fields, retroFields, warnBattQuietNight, warnClock, urgentClock, warnRes, urgentRes, warnBattV, urgentBattV, warnBattP, urgentBattP, warnOnSuspend, enableAlerts | yes, pump clock/reservoir/battery/suspend | 30, 60 min; 10, 5 U; 1.35, 1.3 V; 30, 20 %; off | yes |
| loop | `loop.js:27-29` | warn, urgent, enableAlerts | yes, loop not looping | 30, 60 min, off | yes. apnsKey, apnsKeyId, developerTeamId (`lib/server/loop.js`, `settings.js` secure list) **not carried**: credentials |
| openaps | `openaps.js:38-61` | fields, retroFields, warn, urgent, enableAlerts, predIobColor, predCobColor, predAcobColor, predZtColor, predUamColor, colorPredictionLines | yes, OpenAPS not looping | 30, 60 min, off | yes |
| xdripjs | `xdripjs.js:21-23` | enableAlerts, warnBatV, stateNotifyIntrvl | yes, transmitter state/battery | off, 300, 0.5 h | yes |
| bwp | `boluswizardpreview.js:239-242` | snooze, warn, urgent, snoozeMins | yes, bolus wizard preview | 0.10, 0.50, 1.00 U, 10 min | yes |
| treatmentnotify | `treatmentnotify.js:22,68` | includeBolusesOver, snoozeMins | yes, treatment announcements | 0 U, 10 min | yes |
| dbsize | `dbsize.js:15-19` | warnPercentage, urgentPercentage, max, enableAlerts, inMib | yes, database size | 60, 75 %, 496 MiB, off | **not carried**: `DBSIZE_*` is a D22 "not offered" floor (16.0.0 decisions, first-preview owner surface preamble) |
| pushover | `pushover.js:90-95` | apiToken, userKey, alarmKey, announcementKey | delivery provider | none | **not carried**: credentials; no push provider in the first preview |
| maker | `maker.js:11-15` | key, announcementKey | delivery provider | none | **not carried**: credentials; deferred with Pushover |
| devicestatus | client `receiveddata.js:159`; `dataloader.js:494` | days, advanced | no | 1, `advanced: true` | days yes (as before). **advanced not carried**: see §5 |

Outside `lib/plugins/`, `connect`, `bridge` and `mmconnect` (credentials, integrations) and
`cors.allowOrigin` (`lib/server/app.js:176`, deployment) are not carried.

## 3. Fix

`lib/server/tenant-app/environment.js`: a frozen catalogue `EXTENDED` (plugin → setting → allowed JSON
types: boolean, finite number, or string up to 256 characters). Each tenant's `extendedSettings` is
projected into a fresh object of primitives. The status route shows the projection
(`filteredSettings` recognises the tenant's own extended object), as a single site shows its extended
settings. No owner catalogue entry was added; see §6.

Owner surface reading: the 16.0.0 decision
[owner-settings-projected-catalogue](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#owner-settings-projected-catalogue)
limits owner-writable names to the projected client keys, `enable` and thresholds, and "every other
name is unsupported on the owner surface and refuses by name". The same row records the rest as
"operator-static JSON per tenant". The fix therefore carries plugin extended settings from the operator's
per-tenant configuration only. An owner display change keeps them (`applySettings`, presentation
environment; tested).

## 4. Acceptance (measured on `2f1ae027`)

| check | result |
|---|---|
| `tests/tenant-extended-settings.test.js` (new, unit tier) | 9 passing |
| A fires (urgent, "Stale data, check rig?"), B does not, on the serving and evaluator paths | `EXT_TIMEAGO_A`, `EXT_TIMEAGO_B` green |
| isolation: B carries only its own; distinct objects; mutating A leaves B | `EXT_ISOLATION` green |
| every catalogued setting round-trips: environment, evaluator config, status projection | `EXT_ROUNDTRIP` green |
| credentials, dbsize, cors, unknown keys not carried; each refuses in evaluator config | `EXT_EXCLUDED` green |
| unknown or mistyped values refuse (`madeUp`, `"true"`, unknown plugin, `Infinity`, 257-character string, array, `"160"`) | `EXT_UNKNOWN_REFUSED` green |
| real HTTP status route, PostgreSQL + MongoDB + Vault: A shows `timeago.enableAlerts`, B does not, sentinel never shown | `tests/tenant-rest-context.integration.test.js` 10 passing |
| `tenant-projection-evaluator.integration`, `tenant-rest-derived.integration`, `tenant-current-state-recovery-proof.integration` (with `NS_M5_CURRENT_STATE_PROOF_TEST=1`) | 25 passing |
| `npm run test:unit` | 3115 passing, exit 0 |
| single-site plugin tests (timeago, pump, cannulaage, errorcodes, openaps) | 43 passing |
| `test-tiers.js check` | 615 files, 8 tiers: ok |
| `eslint` on changed files | 0 problems (`npm run lint`: 49 warnings, 0 errors, none in changed files) |

Single site: every importer of `environment.js` is a multitenant module (evaluator, preview and
evaluator config, tenant-app, tenant-settings catalogue). No single-site file changed.

Not run: the full suite, browser tier and `prcheck`. These belong to the batch join's frozen-candidate
acceptance.

## 5. Controls (each red, then restored by file copy; hash verified)

| control | break | symptom |
|---|---|---|
| C1 drop the projection | base devicestatus-only body restored | 7 failing: `EXT_TIMEAGO_A tenant A has stale data and timeago.enableAlerts` (serving); `EXT_ISOLATION`; `EXT_ROUNDTRIP`; evaluator paths `invalid explicit evaluator preview configuration` |
| C2 leak A into B | projection merged into a module-level shared object | 8 failing: `EXT_TIMEAGO_B tenant B left it unset` (B fired A's alarm), `EXT_ISOLATION B carries only its own settings`, `EXT_EXCLUDED` |
| C3 accept unknown keys | unknown keys of a known plugin copied | 2 failing: `Missing expected exception: EXT_UNKNOWN_REFUSED {"timeago":{"enableAlerts":true,"madeUp":1}}`; `EXT_EXCLUDED` (loop APNs credentials carried) |
| C4 status projection removed | `filteredSettings` branch removed | HTTP suite 1 failing: `operator plugin extended settings are shown as a single site shows them (BF-232)` |

## 6. Findings and open points

1. **Owner editing of alert enables is not decided past the first preview.** The documents settle the
   first preview (operator-only), so the lane did not stop. Whether `timeago.enableAlerts` and the other
   plugin alert enables should join the owner surface later is a separate question. On a single site the
   person who runs the site sets them, and in the multitenant preview that is the operator.
2. **The serving process ignores unknown extended keys; the evaluator refuses them.** The serving
   path does not validate tenant `settings` either, so the behaviour is unchanged. An operator's typo is
   visible because the evaluator refuses to load.
3. **`devicestatus.advanced` differs between modes.** A single site defaults it to `true`
   (`lib/server/env.js:396`). A tenant leaves it unset, so the client replaces device status on each update
   instead of merging (`lib/client/receiveddata.js:159`). The merge depends on what the tenant realtime
   frame sends. It is not carried here, and it is a candidate for its own item. Read-derived.
4. **Single-site quirk, not changed:** `ERRORCODES_URGENT=9` (a single code) becomes the number 9, which
   `errorcodes.js:68` ignores. The tenant accepts the same number, with the same effect.
5. **Numeric settings have no bounds beyond finite.** No bound is documented for them, so none was
   invented.

## 7. Operator- and contributor-facing text changed (on the branch)

- cgm-remote-monitor's architecture document `multitenant-api-preview.md`: the per-tenant `extendedSettings` paragraph. It
  explains that the stale-data alarm is off until the operator enables it, as on a single site, and lists
  what is not carried.
- `docs/m5-evaluator-preview.md`: the tenants row and the refusal sentence.
- `lib/server/tenant-app/rest-context.md`: the `environment()` bullet.
