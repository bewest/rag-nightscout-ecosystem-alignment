# Tenant clock join: frozen-head acceptance on 65bb8456 — 2026-11-06

**Reproduced result (batch B2 of the [integration batching plan](../../docs/30-design/tenancy/multitenant-integration-batching-plan-2026-11-06.md)):** the opt-in transactional PostgreSQL tenant clock, its startup floor correction and the checked-out client connection repair, joined with their lower-port and HTTP proofs onto the accepted cumulative head `35903069`, pass one full nonbrowser campaign, one default browser campaign and the final prcheck with **0 failing**. The three source ablations the focused slot had not run (serialization, readiness, rollback) are each red for their mechanism and green when restored.

This immutable contributor record is synthetic and local. The [machine capture](tenant-clock-join-2026-11-06.json) carries the pins, per-tier counts, log and source hashes and cleanup classification; no credentials, URLs, container identities or host paths are published. It promotes no milestone, enables no default and authorizes no push.

## Anchors

| Scope | Exact commit |
|---|---|
| Frozen join head, branch `codex/clock-join-20261106` (local, unpushed) | `65bb8456618df9816106692a32f0dd5c76e216d1` |
| Base: accepted cumulative head (R54) | `35903069b46974cfbaddd8dce00c994fb2562bc3` |
| Clock product, readiness correction, lower-port proof and client repair (lane branch head) | `11770146b420a2aa1ccad587030bfee50a8ea0b3` |
| Clock HTTP proof and tier registration (lane branch head) | `3532c1a46d6fc3fb2100ed7704544d278f29357b` |
| Merge base of all three | `1c55098a3d4bcf3d871bcd345f159ce444d6e458` |
| `official/dev`, contained | `4a482627bfdafb1fef8dcbe0ac6c484811cae563` |

The join is two merges. Each conflicted only in `tests/tiers.json` (resolved as the union of registrations); no `lib/` file differs between the two clock heads, so no product reconciliation was made, and nothing else was added. The HTTP fixture requires the replica fixture, so the unaccepted replica characterization candidate `714f6c8b` (five test-only cases, no `lib/` change) rides along; its five cases executed in the integration tier below, and nothing is claimed about that candidate's own controls.

Lint on the changed JavaScript: **0 errors in `lib/`**; six pre-existing errors in the HTTP lane's test files (an `AggregateError` global the config does not declare, one unused import), unchanged from `3532c1a4` and left for that lane. The project's lint script covers `lib/` only.

Runtime measured by the canonical runner `tools/lab/multitenant-rest-preview/owned.js` (hash in the capture): Node `v22.23.4`, PostgreSQL 16.15, MongoDB 8.0.34, Vault 2.2.1, seed `41574423920`, owned disposable services per run.

## Campaign

| Run | Result |
|---|---|
| `clock` (unit, lower-port, HTTP) | **28 passing / 1 pending / 0 failing**; the pending case is the opt-in benchmark |
| `all` (every nonbrowser tier) | **7187 passing / 81 pending / 0 failing**: unit 2213, dom 205, dependency 368 (+2 pending), core 319, harness 93, integration 3971 (+79 pending), stress 18 |
| `browser` | **684 passing / 0 pending / 0 failing** |
| final `prcheck.sh` | `already contains official/dev 4a482627`, `OK`; head unchanged |

Against R54 on `35903069` (7144 / 80 / 0) the passing count rises by 43: 22 unit cases (`tenant-commit-clock` 12, `postgres-connection-failure` 10), lower-port 9, HTTP 7 and the five replica ride-along cases; pending rises by one, the benchmark. Counts across runs overlap and are not summed.

## Source ablations, each in a detached control worktree of the frozen head

| Ablation (single source change) | Selected cases | Red result and symptom | Restored |
|---|---|---|---|
| **Serialization**: drop `FOR UPDATE` from the clock-row select (and, in the HTTP test only, skip the redundant `NOWAIT` probe so the overtake assertion is reached) | `--grep holds` | **0 / 3**: lower-port "holds lower allocation through COMMIT" and "allows tenant B … while tenant A holds" both `No actual PostgreSQL clock-row lock wait was observed`; HTTP "holds the tenant clock through a blocked actual data update" `clock-select completed before its required lock wait: HTTP 201` | **3 / 0** |
| **Readiness**: bypass the `missing or stale tenant write clock floor` throw | `--grep provision` | **0 / 2**: lower-port "refuses absent, stale and overprivileged provisioning" `Missing expected rejection`; HTTP "refuses missing, stale or unsafe operator-provisioned clock state before binding" `refused configuration must never bind` (the worker bound) | **2 / 0** |
| **Rollback**: advance the clock in a separate transaction after the data transaction rolls back | `--grep rolls back` | **0 / 3**: lower-port "rolls back actual data" floor advanced by one; HTTP constraint-rejection case `failed data insert must not commit a clock allocation`; the unit source-protocol case also red, for a harness-shaped assertion rather than the mechanism | **3 / 0** |

No control was green. The restored four-file diff against `65bb8456` was empty before each restored run.

## Cleanup

Nine runner runs created 27 owned containers and 45 volumes, plus the fixture-owned replica services named in the logs; each was inspected after its run and returned "no such" (read from the command's output, never inferred). No image was pulled, nothing was pruned, and no resource this lane did not create was touched. Free space on the campaign volume was unchanged between start and end.

## Remaining limits

**UNMEASURED:** contention and fresh-ingestion latency (the benchmark stayed off by design and belongs to its own slot with an explicit workload and no invented budget); the Mongo counterpart of the clock's history behaviour; mixed old writers and raw imports; bulk soft-delete ties; a bound on PostgreSQL backend cleanup after a Node SIGKILL; the replica candidate's own controls; CI on this head, which is local. Durable event delivery between roles is the [durable-delivery contract](../../docs/30-design/tenancy/durable-event-delivery-contract-2026-11-06.md)'s subject, not this record's. The clock remains opt-in and off by default.

## Record validation

`make docs-links` passes with this report staged. Lane logs and private audits stay under the lane scratch directory named in `externals/work/HANDOFF-clock-join-20261106.md`.
