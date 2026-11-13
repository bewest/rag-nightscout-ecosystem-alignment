# Core L2 acceptance failure — 2026-11-13

**Captured campaign: FAILED. Cleanup: verified.** All eight ordinary tiers returned 0.
The enabled corpus returned 1 (nested Mocha status 10): **846 passing, 1 pending,
10 failing**. These are reproduced remote execution results, transcribed from the
unchanged saved capture. This publication performed no runtime rerun.

[Machine-readable summary](summary.json) retains selected provenance, stage results,
the ten original failure symptoms and source locations, exit receipts, cleanup facts
and SHA256 bindings to privately retained evidence. Raw logs, provider identities,
addresses, environment contents and credentials are excluded.

## Exact executed boundary

| Identity | Captured value |
|---|---|
| Executed core | `b06106eb8748e975cbe651f6ab51a2b664bd34a1` |
| Tracked `deploy/multitenant` tree | `adbf30ac5c9fbde59df454dcf0b1bb3c00bae43f` |
| Transport | `9a21239fc6b295444846ab5ea8c60a2470686071` |
| Actual Node / npm | `v24.22.1` / `11.19.1` |

The source was captured clean. The campaign executed the core's tracked fixture;
**no external deployment overlay was applied**. Deployment and alignment commits in
the summary are metadata-only provenance, not additional executed sources. Node
binary, lock, CI environment and worker hashes remain in the summary.

## Original execution

| Stage | Passing | Pending | Failing | Return code |
|---|---:|---:|---:|---:|
| unit | 3730 | 1 | 0 | 0 |
| dom | 205 | 0 | 0 | 0 |
| dependency | 368 | 2 | 0 | 0 |
| core | 319 | 0 | 0 | 0 |
| harness | 99 | 0 | 0 | 0 |
| integration | 3643 | 853 | 0 | 0 |
| stress | 18 | 0 | 0 | 0 |
| browser | 686 | 0 | 0 | 0 |
| enabled-corpus | 846 | 1 | 10 | 1 |

Ordinary tiers and enabled corpus are separate executions; pending bodies are not
passes. The enabled corpus selected 88 suites; selection does not supply an
independent per-file execution ledger. Its sole pending case is the optional
end-to-end successful-request latency/throughput workload, requiring
`NS_TENANT_COMMIT_CLOCK_BENCHMARK=1`; it supplies no capacity result.

## Original failure categories

| Category | Failed cases | Captured symptoms |
|---|---:|---|
| D6 metadata feed | 1 | Settings reader remained degraded where the test expected false. |
| Diagnostics, default off / enabled | 2 | Held response aborted or a held-response exclusion assertion failed. |
| Operation-lifetime discriminator | 6 | Registration/orphan error mismatch; restore entered while responses were held; response aborts; control prerequisite did not become ready; backend-death result lacked the expected drain-timeout code. |
| Fixed roster, two API CLI processes | 1 | Restore entered while a post-commit response was held. |

The summary lists all ten test locations and exact bounded symptoms. The test
named “control: early lifetime completion” failed its readiness prerequisite
before reaching its intended negative assertion; this is an actual failed test,
not successful expected-red output. Expected nested red-control diagnostics in
passing tiers do not cancel these failures.

Nine cases concern response lifetime and restore exclusion; focused source
diagnosis owns their cause. The D6 case remains separate. Later standalone D6
results do not establish why its full-corpus execution failed. The
capture alone does not establish a product-only, fixture-only or timing-only cause.
Isolation and restore guarantees remain required.

## Exit, evidence custody and cleanup

The contemporaneous direct controller-subprocess receipt records **rc1**, with
start/finish timestamps and log hash; it is not inferred from the worker outcome.
The unchanged collected archive is **1,993,472 bytes**, SHA256
`2f75893b5c48b143b195f061338bb15f4d6a9a47a9ae359256271d7203241c76`.
Selected original members, controller receipt/log, independent cleanup and
account inventories are hash-bound in the summary. Bulk evidence stays private.

Worker-owned Mongo cleanup was verified with no fixture-container or volume
residuals. The corpus separately verified removal of its two shared fixtures and
volumes, with no remaining fixtures. Controller and watchdog cleanup records both
say verified. Independent inventory found zero owned droplets, firewalls or tags;
both exact original temporary SSH keys were removed. All twelve account inventory
categories had unchanged pre/post resource identity sets. Existing services and
storage were preserved. A watchdog process return code remains **UNMEASURED**;
verified cleanup is not a process-exit receipt.

This record preserves the original **FAILED** verdict through later diagnosis or
repairs. It provides no external-overlay, serving-image, native, capacity,
final-prcheck, release or production acceptance. The coordinator owns review and
joining this record into one programme batch; no queue state or release contents
were changed here, and no additional paid test was launched.
