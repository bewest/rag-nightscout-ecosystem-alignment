# Retained placement resource ownership follow-up

Captured 2026-11-12 against core `8f5c5947753c34c66d19dcb9b2f27a610dd7e3d1`,
following `ac8027f912fae9a4e41ed4ac0bbaea2fc7d623f4`. This adds focused resource
lifetime verification to the [original hybrid repair](../README.md); that immutable
capture remains source-specific. [Results and original-log hashes](result.json)
pin this addendum. The integration coordinator owns full repaired-candidate acceptance.

Review found four previously unowned failure paths introduced by retaining an
accepted placement descriptor. Actual local descriptor checks reproduce each:

- Malformed username/password/database percent encoding could throw after operation
  configuration opened placement. Complete URL decoding now precedes acquisition.
  Original source refuses while leaving one descriptor; the late-decoding ablation
  reproduces that failure. All three malformed fields still refuse.
- The CLI could parse operation/realtime placement before a later role, static-mode
  or startup refusal. It now closes successfully parsed resources on those exits.
  Exact prior committed CLI source produces three descriptor failures.
- `serve.start` listener, replicated write-clock, shared-checkpoint, admin-cohort and
  feed-composition checks preceded its cleanup boundary. These pure checks now run
  inside the existing stop-protected try. Exact prior source produces five failures.
- Evaluator settings/activity/feed/registry validation followed consumer placement
  acquisition. Pure validation now precedes acquisition, with cleanup if a later
  result construction refuses. Exact prior source produces one failed-descriptor
  check; invalid pure inputs acquire no descriptor in the repaired module.

Evaluator hot-file reparses also constructed secondary consumer placement readers.
The actual runtime consumer owns the initial transport. Secondary configuration
parses retain the fresh infrastructure hash for restart/refusal checks, close their
own temporary placement, then explicitly borrow `initial.consumers`; they never
cache a seemingly usable closed transport. Downstream `readCurrent` uses only
infrastructure/roster validation and `withSettings`, returning a tenant entry.
The metadata-only notification configuration acquires no placement. Twenty atomic
hot-file replacements retain exactly one descriptor while the initial placement
remains usable; an infrastructure restart refusal retains that same descriptor;
owner close leaves zero. Omitting secondary cleanup fails with two descriptors
instead of one.

Focused acceptance: **126 passing across 13 affected files**. Tier inventory passes
at 700 files / eight tiers. Changed-source ESLint exits zero with one existing
nonliteral `statSync` security warning in evaluator configuration, zero errors.
No warning was suppressed. Original controls remain immutable in the parent record.
This addendum runs final source-derived controls with the committed instrument:

| control | exit / failures | discrimination |
|---|---:|---|
| prior CLI ownership module | 3 / 3 | previously parsed descriptors survive refusal |
| prior serve precheck module | 5 / 5 | supplied descriptor survives early refusal |
| prior evaluator validation order | 1 / 1 | invalid pure configuration leaves a descriptor |
| retain secondary placement | 1 / 1 | hot reparse retains two descriptors instead of one |
| late pool decoding | 1 / 1 | malformed encoding leaves one descriptor instead of zero |

Historical controls load exact modules from committed `ac8027f912fae9a4e41ed4ac0bbaea2fc7d623f4`
through `git show`, into disposable process memory. They override both cached exports
and isolated source wrappers so the mutation reaches the actual test consumer.
No shipping file or other agent's worktree is modified. Normal focused acceptance
uses the source tier runner and the same private minimal environment as the parent
repair record. For these controls use the parent direct-Mocha command and
`M7_CACHE_CONTROL` identifiers `prior-cli-ownership`, `prior-serve-precheck`,
`prior-evaluator-order`, `retain-secondary-placement`, `late-pool-decode`; the last
capture selects `--grep 'PLACEMENT_(CLI|PRECHECK|EVALUATOR|FAILED_CONFIG)'`.

`make queue-check` in the isolated alignment proof worktree **fails** because many
manifest-declared `externals/work/...` gate directories are absent there. Its
original log is retained; it is not reported green or treated as a product failure.
A sandbox-only `spawnSync git EPERM` on tier inventory was retried with permitted
child execution; the captured final tier inventory is the successful actual check.
No full suite, browser/native database campaign, capacity run, cloud action,
prcheck or push occurred. Datastore-constructor snapshot repair remains a separate
source lane; this change does not modify its PostgreSQL census or admission rules.
