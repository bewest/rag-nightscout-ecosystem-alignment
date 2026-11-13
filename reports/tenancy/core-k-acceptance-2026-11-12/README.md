# Core K source execution — 2026-11-12

**FULL_SOURCE_EXECUTION_PASS, source scope only.** K's eight tiers and enabled
corpus completed in the recorded order with actual process return code **0**
for every stage. The worker recorded `passed`, no errors, and
`COORDINATOR_REVIEW_REQUIRED`. This leaf projects that closed execution; it does
not close selected external deployment/image, native/clinical qualification,
capacity acceptance, final prcheck, release or production readiness.

## Executed source and observations

Reproduced remotely; independently read here from the retained command ledger
and terminal log summaries. Core was
`074eab44ee75b9175c951b6a8add3df3e9554af7`, including its tracked
`deploy/multitenant` fixture tree
`fdc9f8dd2644b8789c86abeb030fbc0ad7304780`. The execution-scope sidecar explicitly
records **no external deployment overlay execution**. Deployment
`479affb738e01e8f6fe1a476da63a0260ee08f50` and alignment
`d21a43804267bef2b74e00477af19400fd5f8289` are provenance-only, despite appearing
in the worker's general source fields. They receive no execution credit here.

Node was **v24.22.1**, npm **11.19.1**. Captured source-head matched the core pin;
initial and final source-clean outputs were empty. The recorded lock and worker
hashes matched immutable Git bytes at the pinned core and worker transport
`232be23ed0e42ff3647ce0108026fa0769173d18`. The worker-file hash is reported by
the remote provenance record, not an invented captured worker-file artifact.

| Ordered stage | Passing | Pending | Failing | Actual return code |
|---|---:|---:|---:|---:|
| unit | 3622 | 1 | 0 | 0 |
| dom | 205 | 0 | 0 | 0 |
| dependency | 368 | 2 | 0 | 0 |
| core | 319 | 0 | 0 | 0 |
| harness | 99 | 0 | 0 | 0 |
| integration | 3643 | 836 | 0 | 0 |
| stress | 18 | 0 | 0 | 0 |
| browser | 686 | 0 | 0 | 0 |
| enabled corpus | 839 | 1 | 0 | 0 |

[Selected summary and provenance](summary.json) binds each stage's stdout/stderr
hashes and recorded return code. Absent failing/pending terminal fields become
zero only with a successful command and a positive passing summary. Counts
across tiers/corpus overlap; they are not a distinct-test total.

Pending cases remain pending: unit's optional view-corpus parse, two dependency
ajv-resolution cases, and the integration tier's recorded pending cases. The
subsequent enabled corpus selected **86** unique suites and reported **839**
passing, **1** pending, **0** failing. Its pending case is the optional
end-to-end commit-clock benchmark, gated by
`NS_TENANT_COMMIT_CLOCK_BENCHMARK`. A separate per-file completed-body ledger was
not recorded. Harness stderr's support-only execution rejection belongs to its
expected nested negative control; it does not change the outer harness exit or
supply a failed campaign result.

## Cleanup and retained evidence

The owned Mongo removal and absence checks completed successfully; the worker
recorded verified cleanup and empty owned container/volume residuals. The corpus
created **2** fixtures (PostgreSQL and Vault), removed those same fixtures and
volumes with verified absence, and recorded `remaining: []`.

Independent cleanup observation at **2026-11-13T04:12:54.496Z** recorded verified
controller and watchdog cleanup, **0** remaining droplets, **0** firewalls and
**0** tags, plus removal of the **2** exact original temporary keys. These are
owned-run cleanup observations, not a claim about other services or test
acceptance. UTC execution crossed into the next day; this leaf uses the local
campaign date/run identifier.

Retained evidence identifiers are `core-acceptance-20261112-k`,
`perf-cloud-core-stage-20261112-k` (execution scope),
`perf-cloud-core-observe-20261112-k` (independent cleanup), and
`perf-cloud-core-k-assessment-20261112` (parent's closed-archive assessment).
The selected summary includes hashes for those inputs. The independently
remeasured closed archive is **2,001,368 bytes**, SHA-256
`446d3457d6a12c8903cb84d88101504f60a8d1284780d8dce12ddfd4785dd89c`.
Full logs, captures, fixture state, provider identities, keys and archives remain
outside Git; the JSON here is a small whitelist derivative, not a raw result.

This record was assembled by reading retained evidence and immutable source
objects. No tests, Docker/provider operations or new campaign were run to
publish it. Programme integration and any later acceptance decision remain
with the coordinator.
