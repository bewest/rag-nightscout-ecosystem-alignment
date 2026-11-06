# Bounded native socket DATA controls

Reproduced on committed application12919f5558c9cbac50b0fd15e4bc2ea482af1a24,
instrumentc2fe24bb2d73fa25e75a5375299e72c8d34b0a9f. Three fresh whole-source
archives use matching locked private dependencies, owned PG16 and Mongo8.0.34,
and actual single-mode child Mongo/Socket.IO reference. No application worktree
or product/schema/default policy changed.

| Native invocation | Result | Accepted semantic observation |
|---|---|---|
| early acknowledgement control | 0 pass /1 assertion fail /0 pending | actual callback while held transaction reached its stored row; independent row absent, events unchanged; true versus expected false |
| role authority substitution control | 0 pass /1 assertion fail /0 pending | committed tenant-A row count1 instead0 plus event/callback; tenant B unchanged |
| fresh unmutated restoration | 4 pass /0 fail /0 pending | initial/retry/multiple-match parity, current-authority refusal, held commit and actual post-write rollback |

The early control changes only the product forwarder: callback occurs before
awaiting transport. The role control changes only the product receiver's current
subject authorization assignment into a trusted-role actor. Source mutation must
match exactly once. Case title, ERR_ASSERTION, exact expected/actual values AND
independent physical proof must match; setup, SQL, TypeError, timeout, wrong-case,
green/vacuous and unrelated failures are invalid evidence. No control is forced
red by its command-line label.

The identical archived-test hardening in all three invocations is preserved in
scratch-oracle.js. Role observation races actual refusal with actual callback,
then independently reads both tenants before its callback assertion. Its red is
the committed A-row count, not absence of a refusal signal or a timer. Early-ack
observation waits for actual callback or a150ms no-callback interval after the
actual post-write barrier. Independent missing-row and unchanged-event assertions
precede its exact early-callback assertion. The interval expiring cannot itself
produce a red. Physical proofs and original native JSON reports are retained.

All three single-reference children report own process mode single; the parent
remains multi. Exact child PIDs exited0 and were independently absent. Six owned
containers and nine captured mounted volumes were independently absent; host
volume count remained462. Unknown baseline resources were preserved. Runtime
released2026-11-06T23:06:05Z. Raw private artifacts remain unchanged; public logs
replace only the local alignment worktree prefix. The index covers captured
measurement artifacts; this explanatory file is separate.

This accepts only the fresh-successor-schema/pattern DATA boundary. It is not an
actual Android binary run, full single-app test, populated/import order contract,
production transport/role admission or alarm-ack semantics. The optional successor
catalogue still rejects old-catalogue startup with MIG_UNKNOWN. No rollout or broad
milestone completion is adopted. Earlier1990 and0d628 failed captures and12919
initial positive remain immutable. No initial positive/matrix/evaluator repeat,
full/browser/whole-corpus/prcheck, queue/release mutation or publication ran here.

Instrument-only checks passed for unique source/adaptation needles, strict
classification and exact child lifecycle rejection. Changed-file lint0errors/
33dynamic-filesystem warnings. Native report/proof hashes and exact lifecycle
records are in artifact-index.json, summary.json and final-audit.json.
