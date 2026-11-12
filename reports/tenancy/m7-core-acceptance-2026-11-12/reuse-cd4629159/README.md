# Affected-input reuse review for cd4629159

**Read-derived verdict:** retain the existing D505 algorithm/memory-projection
proof and 195 native identity/client proof for their original narrow criteria,
with their original executed-source, environment and coverage limits. This is
**not a cd462 clinical or identity execution**, nor whole-program equivalence.
The repaired unavailable-model/notification-repeat handoff still requires its
separate current-source native proof.

Candidate `cd4629159809fb3cffbc6f57626f98f3ffdbdda7` was independently reconfirmed
clean. [review.json](review.json) retains the original affected-input review and
full clinical blob map; [verification.json](verification.json) records the
subsequent Git-object reconfirmation and the review's SHA-256. No product,
queue, original capture or acceptance instrument changed. No runtime campaign,
capacity workload or resource operation was performed for this review.

## Clinical algorithm and memory projection

Executed source remains `d50502bb6126bda2bb0af384569e1d95de114f2f`; its immutable
[clinical report](../../m7-clinical-equivalence-2026-11-12/final-d50502bb/README.md)
was captured in alignment `89b5900a9b6395279458d897bcfb7353a33133c0`.
All **128 local dependency blobs**, plus package and lock blobs, remain identical
D505→cd462. The closure follows literal local `require`/`req` imports from the
instrument's component/scope/environment/language/clock roots, with the explicit
server-plugin eval-require webhook edge included conservatively. It is a static
source-input review, not runtime code coverage.

The actual `trace.cjs:110–114` supplies a memory replay, explicit statistics,
10,000-row and 16-MiB bounds; `trace.cjs:124` directly calls component
`evaluate`/`evaluateTime` at a pinned instant. The projection evaluator, views,
plugins, due calculator, projection reader, safe environment and clock remain
unchanged. The changed notification producer is outside this clinical closure.

Retain the report's full-message cross-schedule DIFF, memory-only/zero-Pool
clinical path, no same-checkpoint deletion or ordering-tie discrimination, and
no ingestion, SQL projection/RLS/authority/restore, notification delivery,
sockets, runtime scheduling or capacity claim. Original Node22/UTC execution
is not relabelled as a new Node24 or repaired-source run.

## Native identity and client criterion

Executed source remains `195c932293f3abc648da8fbe4356bf7360acd002` and evidence
alignment `d7a65425764eb2a0c17ed33237f73e9636ef30db`:
[nine-stage matrix and three original semantic controls](../oidc-195c9322/README.md).
All **20 harness files** and **11 selected constructor/native/control/package
files** independently retain their Git blobs; harness SHA-256s match too.
Package/lock are unchanged. No assertion, stage, control or recorded environment
was altered to support reuse.

The only product-file difference from 195 is
`lib/tenant-notifications/producer-state.js`: repeat deadline selection inside
`reduce`. Original blob `b9a06f9fc1bfb6ca09f7a965d99e2b84cfb986f8` changes to
`c3531858748799bc09fc8390612cdf31a6d6c31e`. Export shape, `armed`, module
initialization and all other product files are unchanged.

Reuse is grounded in the actual instrument's selected constructors:

- `stage.cjs:45–75` selects Vault sign/verify, native Mongo/PG sessions and
  signed-HTTPS fixtures with single/owner extensions, not the multitenant role CLI.
- `consumer-journey.cjs:237–244` constructs `evaluator-runtime` and the projection
  evaluator directly; it supplies neither notification coordinator nor
  `onRevision` delivery callback.
- `owner-extension.cjs:104–134` constructs subject/settings/access/credential
  services and HTTP routes. It does not construct notification delivery.
- The changed reducer is invoked by the separate producer/coordinator path
  (`evaluator-consumers.js:45–48`), which these identity scenarios do not construct.

A conservative native static import graph **does include** producer-state via
lazy diagnostics→roles→evaluator-preview registrations. Consequently this review
must not be described as a disjoint whole-program closure. The narrow reuse
inference rests on the actual harness role/constructor selection and uninvoked
changed reducer logic. Prior identity output does not test the repaired
unavailable-model repeat behavior. Keep actual 195 source, Node22, browser,
synthetic-provider/pinned-client and provider-image attribution; no real-IdP,
device, live-provider or general-interoperability claim is added.

Record consistency: review SHA-256 and all quoted Git-object comparisons were
reconfirmed; staged whitespace passes. `make docs-links` passes (27 checked,
zero failing). `make queue-check` stops on absent historical external gate
working directories in this isolated evidence checkout: local setup UNMEASURED,
not a product failure. No gate definition or queue state was changed.
