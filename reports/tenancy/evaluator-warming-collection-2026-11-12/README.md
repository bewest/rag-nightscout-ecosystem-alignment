# First-release warming collection

**Fixed on an isolated branch; recording-source qualification only.** Collector
source `56f28928a8d0ffed5d0398dccc7b7608c32f9931`, based on alignment
`df18100cf13780cec904a792b2bb1ab8867bfb54`. Application source is unchanged at
`9db0ce94f072c8f34aab889f0181afa4269a6758`; deployment input remains
`d76ef17878edb610cdeae75aeef9c07f94b60753`. No application/deployment source,
workload, progress assessor, budget, cadence or deadline changed. No live
application, database, browser, Docker or cloud run occurred.

The baseline B historical refusal remains **UNCLASSIFIED**: its raw refused rows
were not captured, so this reproduced compatible mechanism does not establish
which predicate failed in that run or retrospectively pass it.

## Reproduced boundary

The owned `evaluator-readiness-fixture.cjs` loads the actual clean, pinned9db
runtime, operation window and inspection modules. It holds the recording
protocol's lifecycle-operation finish UPDATE. Its synthetic selected tenant is
ready with one legacy cycle, zero completed acquisitions/time cycles/failures,
and explicitly null completion age. After releasing the UPDATE, the same runtime
reports one completed acquisition and finite completion age. The fixture uses a
recording database protocol, **not PostgreSQL**, and proves no native locking,
serving, latency or capacity criterion. Its actual typed frames are retained in
`runtime-transition.stdout`; source/environment and instrument hashes are in
`instrument.json`.

The exact immutable df181 collector rejects the held shape as
`M7_EVALUATOR_PROGRESS_CONTRACT`; the repaired collector permits it only with
`warming=True`. The unchanged readiness acquisition guard then returns
`M7_EVALUATOR_PROGRESS_WARMING`, not PASS. Released completion permits readiness
PASS. The old collector is loaded again in scratch and still refuses, without
mutating any old source. Nonwarming collection still rejects the null age.

The exception is limited to a complete, admitted, ready, error-free owner with
all three completion/failure counters zero. Missing age, malformed fields,
nonzero counters with null age, errors and progress requirements still refuse.
Diagnostics contain only fixed predicate/field names, bounded instance/page/row
indices and warming boolean; no tenant IDs, raw rows, clinical values, runtime
codes or alert strings are published. Readiness's bounded observation list
retains the diagnostic and existing query/byte/time counts.

## Focused checks and controls

Commands/exits and original outputs are retained. New warming checks7, existing
progress14, idle12, contract19 and unaccepted-scope9 all pass with no skips.
The actual recording runtime release discriminator and existing actual-source
progress fixture are included. The repaired source passes again after controls.
Syntax compilation and `git diff --check` pass.

| In-memory control | Actual red symptom |
| --- | --- |
| Restore strict age refusal (`old-age`) | 3 errors: `M7_EVALUATOR_PROGRESS_CONTRACT` on valid held release |
| Permit null age without warming/counter scope (`unscoped-age`) | 5 failures: required refusal not raised |
| Omit refused collection diagnostic (`omit-diagnostic`) | 1 failed assertion and1error because required fixed-field diagnostic is absent |

No original source, captured measurement or peer worktree is modified by these
controls. Source-owned bounds and strict phase/load/recovery/native TIME
predicates remain unchanged. The new instrument SHA is distinct; old native
proofs retain their executed instrument attribution and are not relabeled.

## Standalone operation-window path

**Read-derived composition check**, not a new full-stack execution: deployment
d76 `bindings/compose/multitenant/config.js:208` supplies operation config for each
selected service role, including the single evaluator. Core9db
`lib/server/serve/index.js:98–108` constructs its operation window/cohort and
line141 boots through that cohort; `operation-cohort.js:70` passes the actual
window into role boot, and `evaluator-preview.js:97` passes it into runtime.
`evaluator-runtime.js:186–197` credits successful completion only after the fresh
window run releases. Without a window it grants no such completion credit, so
this repair cannot manufacture a ready acquisition or missing-window PASS.
This static chain does not prove a particular deployed instance had its expected
window; source-pinned native qualification remains the coordinator's next gate.

Root owns ordinary-history integration, final instrument freeze, and any new
strict native TIME episode or baseline launch. No acceptance/capacity claim is
created by this report. The gate script is unchanged; exact hashes are retained
in `instrument.json` and the artifact manifest.
