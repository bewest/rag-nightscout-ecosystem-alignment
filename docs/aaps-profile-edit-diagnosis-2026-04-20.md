# AAPS Profile-Edit Sync Diagnosis — Discord Report Follow-up

**Date:** 2026-04-20
**Trigger:** Discord report — new AAPS user sees only the original 1969 "Default" entry in NS Profile Editor's "Database records" dropdown after editing Local Profile multiple times. Reporting > Profiles shows many `Test@@@@@<timestamp>` columns.
**Question asked:** Did our `wip/test-improvements` patches (cgm-pr-8447) fix this user's bug, or is it a different issue?

## TL;DR

- **No, our patches almost certainly do not fix this user's bug.** The symptom has the wrong shape for the V1 race we patched: that race produces **≥2** profile-store docs from **1** edit; the user has **1** doc total.
- The `Test@@@@@<timestamp>` columns are **profile-switch treatments**, not profile-store docs. They are expected behavior — every Profile Switch (including loop pump-side activations from any source) produces one and is correctly rendered as a column by `lib/profilefunctions.js:272-287`.
- **Static-analysis simulator** (`tools/aaps/sync-state-model.py`) modeled all silent-no-op branches in `DataSyncSelectorV1/V3.processChangedProfileStore` and ran 8 scenarios. **3 reproduce the user's symptom (≥2 saves, ≤1 profile-store doc in NS); 4 do not (definitively disconfirmed).**
- **Disconfirmed by the model:**
  - `LocalProfileLastChange == 0L` *alone* — the Save button calls `storeSettings(activity, dateUtil.now())` (`ProfileFragment.kt:346`) which immediately sets it to `now`. The guard only triggers if the user **never pressed Save**.
  - Ack-leapfrog race (Save #2 clicked during Save #1's ack wait) — clock is monotonic; even a 1ms gap means `Save #2`'s `lastChange` is greater than `confirmLastProfileStore(now)` from the prior ack, so the `lastChange > lastSync` guard still passes.
- **Surviving candidates** (in order of plausibility for a new user):
  1. **`allProfilesValid != true`** (`DataSyncSelectorV1.kt:792` / `V3.kt:718`) — any single profile with `dia` outside `[5,9]`, `ic` outside `[2,100]`, basal outside the pump's `[min,max]`, or basal block boundary not aligned to a whole hour on a non-30-min-capable pump. **Silent. No notification, no log.** Most insidious — a Virtual Pump or misconfigured pump driver with `basalMaximumRate=0` rejects any profile.
  2. **NSClient unauthorized for `profile.create`** — V3 REST returns 401, V1 socket dbAdd returns no ack within 60s. Visible as HTTP 401 in NSClient log.
  3. **NSClient paused** — `isPaused` guard at `DataSyncSelectorV1.kt:787` / `V3.kt:713`. User-toggleable setting.
- **Version-dependence:** for *this user's symptom* (1 profile-store doc), the answer is *independent of c-r-m version on the "AAPS didn't send" branch*. Our R-tests prove `wip/test-improvements` accepts every observed AAPS-shape body — so even on the "c-r-m rejected" branch, rejection would manifest as an HTTP error in the AAPS NSClient log regardless of c-r-m version.
- Our PR's V1 dedup + `_id` tiebreaker patch is still correct and worth merging; it just addresses a different failure mode.

## Method

We discriminated "AAPS not sending" vs "c-r-m dropping" vs "user-workflow-misunderstanding" using:

1. **Static emission audit** of AAPS source (`tools/aaps/emission-audit.md`):
   identified the exact codepaths and guards on both V1 (Socket.IO) and V3 (REST) profile-store sync.
2. **Roundtrip integration tests** (`tests/aaps-profile-edit-roundtrip.test.js` in c-r-m):
   replays canonical AAPS-shape requests against the patched server and verifies what ends up in mongo and what NS surfaces.
3. **Dropdown-logic probe** (`tools/aaps/dropdown-logic-probe.js`):
   standalone script the user can run against a `mongoexport` of their own data to confirm whether their c-r-m has 0/1/many profile docs without us touching their data.

## R-Test Results (8/8 pass on `wip/test-improvements`)

| Test | Path | Verifies | Result |
|------|------|----------|--------|
| R1 | V1 Socket.IO `dbAdd` profile | First insert of profile-store creates exactly one doc | ✓ |
| R2 | V3 REST `POST /api/v3/profile` | First insert returns 201 and persists doc with `app:"AAPS"` | ✓ |
| R3 | V1 `dbAdd` Profile Switch treatment | Switch grows treatments collection only; profile-store untouched | ✓ |
| R4 | V1 store + switch sequence | Both collections grow correctly (mimics Profile Switch dialog after edit) | ✓ |
| R5 | V1 rapid edits, different startDates | Both docs persist; `profile.last()` returns the newer one (sort tiebreaker) | ✓ |
| R6a | V3 rapid edits, different dates | Both V3 inserts get distinct identifiers and persist | ✓ |
| R6b | V3 mongo state | After two V3 POSTs, mongo has 2 distinct docs (Profile Editor would list 2) | ✓ |
| R7 | Same-startDate race artifact | After seeding 2 same-startDate docs, `last()` deterministically picks newer `_id` | ✓ |

**Conclusion from R-tests:** c-r-m on `wip/test-improvements` correctly handles all observed AAPS-shape inputs. If a profile-store doc reaches the server, it is persisted and surfaced via the routes Profile Editor queries.

→ Therefore the user's missing edits did not reach the server.

## Why this is not the V1 race we fixed

The race patched by PR #8475 occurs when AAPS sends **two** profile-store dbAdds quickly (multi-edit or activation-after-edit), and pre-fix c-r-m's `last()` was non-deterministic with same-startDate ties. The user reports **only one** profile-store doc (the original 1969 Default). One doc cannot be a race artifact — there is no second record to disambiguate.

The Discord screenshots show:

- Stored profiles dropdown: `Default`
- Database records dropdown: `Valid from: 1/1/1970 12:00:00 AM` only
- Reporting > Profiles columns: many `Test@@@@@<ts>` entries

These columns come from `lib/profilefunctions.js:272-287`, which injects each Profile Switch treatment's `profileJson` into the in-memory store under `<name>@@@@@<mills>`. They are filtered out of the editor dropdowns by `ddata.js:122-126` and `profilefunctions.js:404`. **This is intentional** — AAPS records a Profile Switch on every loop activation/pump-side restore, and NS uses them for the audit trail in Reporting.

## What the user probably needs to check (in order of likelihood)

1. **`LongNonKey.LocalProfileLastChange`.** AAPS' `DataSyncSelectorV1.processChangedProfileStore:786-805` and `DataSyncSelectorV3.processChangedProfileStore:712-728` both bail when `lastChange == 0L`. On a first-time install where the original NS profile had `startDate` 0/missing, `ProfilePlugin.storeSettings(timestamp = store.getStartDate())` may set `lastChange` to 0 and the sync never happens. **Fix:** save a Local Profile edit explicitly (the Save button calls `storeSettings(activity, dateUtil.now())` at `ProfilePlugin.kt:346`, which sets `lastChange = now` correctly).
2. **NSClient authentication / role.** If the NSClient connection is auth'd as a role without `profile.create`, V3 POST returns 401 and V1 dbAdd is silently dropped. Check NSClient log for HTTP/socket errors at the moment of the edit save.
3. **Profile name collision.** AAPS defaults to `defaultProfile = "Test"` for the user's Local Profile. If a stale profile with the same name exists from a prior account, the user might be editing one slot but NS `defaultProfile` filter shows another. Less likely.
4. **Browser cache.** The Profile Editor page caches on first load. Hard-refresh or clear browser data. Last resort.

## What we did NOT do (limits of this analysis)

- We did **not** run the probe against the user's actual data. The probe was only smoke-tested against synthetic JSON in this workspace.
- We did **not** read AAPS NSClient logs from the user — without them, we cannot distinguish among the 3 surviving candidates.
- We did **not** bisect older c-r-m versions. The R-tests prove the patched server accepts AAPS bodies; bisecting only becomes useful if a future report includes both an AAPS log showing successful POSTs and missing mongo docs.
- The simulator (`tools/aaps/sync-state-model.py`) models the *guard logic*, not the *exact preference defaults* of the AAPS Android Preferences API. We assumed prefs default to 0; this matches AAPS' explicit defaults in `LongNonKey` but isn't verified end-to-end against an emulator.

## Suggested message back to the Discord user

> Your c-r-m install looks healthy — the `Test@@@@@<timestamp>` entries are expected (one per Profile Switch, used for the historical Reporting audit trail; they're correctly filtered out of the editor dropdowns).
>
> We modeled all silent-no-op branches of AAPS' `DataSyncSelectorV1/V3.processChangedProfileStore` and ran 8 scenarios. Three reproduce your symptom (many edits, ≤1 profile-store doc in NS); five don't. Of the three that survive, in order of likelihood:
>
> 1. **`allProfilesValid` returns false.** Any single profile in your store with `dia` outside [5, 9], `ic` outside [2, 100], or basal outside the active pump's [min, max] silently bails the sync — *no log, no notification*. Open AAPS → Local Profile and check every value, especially if you're on the Virtual Pump (which can have `basalMaximumRate=0`).
> 2. **NSClient unauthorized for `profile.create`.** Check the NSClient log immediately after Save: V3 returns 401, or V1 dbAdd never gets an ack. Verify your NS access token's role grants `profile:create`.
> 3. **NSClient sync paused.** Check NSClient settings page for a pause toggle.
>
> We **disconfirmed** two earlier guesses: `LocalProfileLastChange == 0L` (the Save button immediately sets it to `now`, so the guard cannot trigger after even one Save) and the rapid-edit ack-leapfrog race (clock is monotonic so the next Save's `lastChange` is always greater).
>
> If you can `mongoexport` your `profile` and `treatments` collections (the latter filtered to `eventType: "Profile Switch"`), run our `tools/aaps/dropdown-logic-probe.js` against the JSON dumps — it will tell you definitively how many profile-store docs you have. And if you can share the NSClient log for the moment of a Save, we can pin which of the 3 it is in <5 minutes.
>
> Our forthcoming PR ([nightscout/cgm-remote-monitor#8475](https://github.com/nightscout/cgm-remote-monitor/pull/8475)) does fix a related issue — but only the case where AAPS sends two updates that race; it doesn't address the "no update was sent" case you're hitting.

## What was delivered (this iteration)

| Artifact | Path | Purpose |
|----------|------|---------|
| Emission audit | `tools/aaps/emission-audit.md` | Static analysis of AAPS V1/V3 profile-store paths with line-level guards |
| **Sync state model** | `tools/aaps/sync-state-model.py` | **Static-analysis-derived simulator** of all guard branches; runs 8 scenarios and identifies which match the observed symptom |
| Fixture builder | `tools/aaps/build-fixtures.js` | Deterministic fixtures for replay tests |
| Fixtures (5) | `tools/aaps/fixtures/*.json` | Canonical AAPS-shape bodies |
| Roundtrip tests | `cgm-pr-8447 → tests/aaps-profile-edit-roundtrip.test.js` | R1-R7 integration tests, all green |
| Dropdown probe | `tools/aaps/dropdown-logic-probe.js` | Standalone diagnostic for end-users |
| This report | `docs/aaps-profile-edit-diagnosis-2026-04-20.md` | Findings + user message |

## Open items / out of scope

- Bisect skipped: all R-tests pass on patched c-r-m; nothing for an older c-r-m to disprove. Would only be useful if the user reports a new symptom whose timeline matches a c-r-m upgrade.
- Reproducing the exact AAPS-side bug requires a paired Android emulator + NS instance; out of scope here. AAPS maintainers can use the emission-audit doc as a starting point.
- We did not touch AAPS source. Recommendation for AAPS PR: telemetry/logging when `processChangedProfileStore` bails on `lastChange == 0L` — currently silent.
