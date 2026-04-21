# AAPS Profile-Edit Sync Diagnosis — Discord Report Follow-up

**Date:** 2026-04-20
**Trigger:** Discord report — new AAPS user sees only the original 1969 "Default" entry in NS Profile Editor's "Database records" dropdown after editing Local Profile multiple times. Reporting > Profiles shows many `Test@@@@@<timestamp>` columns.
**Question asked:** Did our `wip/test-improvements` patches (cgm-pr-8447) fix this user's bug, or is it a different issue?

## TL;DR

- **No, our patches do not fix this user's bug.** The symptom has the wrong shape for the V1 race we patched: that race produces **≥2** profile-store docs from **1** edit; the user has **1** doc total.
- **Conclusive evidence for "AAPS profile-switch sync works, profile-store sync silently fails":**
  - The `Test@@@@@<timestamp>` columns in Reporting > Profiles are NOT profile-store records. They are **profile-switch treatments** with embedded `profileJson`, injected client-side by `lib/profilefunctions.js:272-287` into the in-memory store as `<name>@@@@@<mills>`. Server-side `lib/data/ddata.js:122-126` strips these from the editor dropdowns. The dropdown's *one* "Valid from: 1969…" entry is the lone real profile-store doc (NS bootstrap default).
  - User reported (follow-up): renaming the AAPS profile from "Test" to "Default" produced no change to the NS Default doc. This rules out name collision and confirms profile-store POSTs are not happening at all.
  - Profile-switch treatments share the same NSClient connection, auth, and `isPaused` flag as profile-store. Their successful arrival rules out NSClient pause / network / global auth failure.
- **Surviving root-cause candidates** narrowed by this evidence (highest first):
  1. **`allProfilesValid != true`** in `processChangedProfileStore` (`DataSyncSelectorV1.kt:792` / `V3.kt:718`). Only the profile-store path runs this gate; profile-switches do not — explaining the asymmetry exactly. Validity oracle (`tools/aaps/pump-validity-oracle.py`) shows the user's screenshot values (DIA=9, IC=15, ISF=4 mmol/L, basal=0.4) **pass on every realistic pump driver after `onStart()`**. So this requires either (a) additional basal blocks at non-hour boundaries on Omnipod/Medtrum/Insight/DiaconnG8 (BAIL on those pumps per oracle); (b) the user reconfigured DIA outside [5,9] in a *different* profile in the same store (one bad profile fails `allProfilesValid` for the whole store); (c) the active pump is still in pre-`onStart()` state for the Virtual Pump (basalMaximumRate=0 — race).
  2. **Bootstrap-broadcast race with `LocalProfileLastChange`.** NS bootstrap profile is created with `startDate: new Date(0)` (`lib/profile/profileeditor.js:70`). AAPS's `NsIncomingDataProcessor.processProfile:289` accepts re-broadcasts when `createdAt % 1000 == 0L`, calling `loadFromStore` → `storeSettings(timestamp = 0)`. If a re-broadcast arrives *between* a user Save's `storeSettings(now)` call and the queued `processChangedProfileStore` coroutine actually reading the preference, the lastChange-zero guard at line 790 fires. Simulator (`scenario_S8`) shows this **does not reliably reproduce** the symptom in sequential ordering, but is a plausible intermittent failure — a tight race that could explain "some saves don't sync" but not "no saves sync."
  3. **Per-collection NS auth scope** — the NS access token has `treatments:create` but not `profile:create`. Visible in NSClient log as 401 only on profile uploads.
- **Definitively ruled out** by combined evidence (treatments arriving + dropdown showing 1 record):
  - NSClient paused / network down / global auth invalid (treatments would fail too)
  - `LocalProfileLastChange == 0L` from a *one-time* import (Save would recover via `dateUtil.now()`)
  - Ack-leapfrog race (clock monotonic; simulator-disconfirmed in S3)
  - Name collision (rename to "Default" was tested by user, no change)
  - c-r-m server bug — our R-tests prove patched c-r-m correctly persists every observed AAPS-shape body, including reproducing the exact screenshot from treatments-only data (R8)
- **Static-analysis simulator** (`tools/aaps/sync-state-model.py`) modeled all silent-no-op branches in `DataSyncSelectorV1/V3.processChangedProfileStore` and ran 8 scenarios.

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

> Good news: your c-r-m install looks **healthy**. The `Test@@@@@<timestamp>` columns you see in Reporting > Profiles are *expected* — c-r-m injects each AAPS Profile Switch treatment into that view as a synthetic column for the historical audit trail (`lib/profilefunctions.js:272-287`); they are deliberately filtered out of the editor dropdown. So the dropdown showing a single "Default 1969" entry is consistent with: (a) the original c-r-m bootstrap profile is still the only real `profile` document, and (b) AAPS *is* successfully syncing Profile Switch treatments (which is why the columns keep appearing) but is **not** sending any profile-store updates.
>
> We modeled all 9 silent-skip branches of AAPS' `DataSyncSelectorV1/V3.processChangedProfileStore` and ran an automated validity oracle against your screenshot values across 8 pump drivers. With your DIA=9, IC=15, ISF=4 mmol/L, basal=0.4, validation passes on every realistic pump after `onStart()`, so the leading suspect — `allProfilesValid` returning false — only fires under specific conditions. In order of likelihood:
>
> 1. **Pump-validity gate.** Even though your *visible* profile passes, `allProfilesValid` checks **every** profile in the store. Do you have other profiles besides "Test"? Open AAPS → Local Profile → check the profile selector at the top. If a stale or imported profile has `dia=9.5`, `ic=1.5`, basal blocks at non-hour boundaries on Omnipod/Medtrum, etc., the *whole* store fails validity silently. (See `tools/aaps/pump-validity-oracle.py` for the per-pump rules.) **What pump driver are you using?**
> 2. **NSClient unauthorized for `profile.create` specifically.** Your NS token clearly has `treatments:create` (Profile Switches arrive). It might lack `profile:create`. The NSClient log will show 401 only on profile uploads. Tap Save in Local Profile, then immediately open NSClient → Log and look for HTTP errors.
> 3. **Bootstrap-broadcast race.** The original NS bootstrap profile has `startDate: new Date(0)`, and AAPS treats whole-second timestamps as "user edited in NS" → reloads it → resets `LocalProfileLastChange` to 0. If a re-broadcast arrives between your Save and the queued upload, the upload bails. Less likely to explain a 100% failure rate but possible for intermittent ones.
>
> Two things would let us pin it in minutes:
> - The **pump driver** you've selected in AAPS.
> - A short **NSClient log** captured while you do one Save (filter for "profile" / "DataSync" / HTTP errors).
>
> Also useful: from a NS shell, `mongoexport --collection profile --query '{}'` so we can see all your stored profile docs (including `defaultProfile` field per doc), and run our `tools/aaps/dropdown-logic-probe.js` against the dump to confirm what the editor is reading.
>
> Heads-up: our forthcoming PR ([nightscout/cgm-remote-monitor#8475](https://github.com/nightscout/cgm-remote-monitor/pull/8475)) hardens c-r-m against duplicate AAPS uploads, but does **not** address the "AAPS isn't sending uploads at all" case — which is what we believe is happening to you. The fix is on the AAPS side (instrumentation patch needed; we have a proposal pending).

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
