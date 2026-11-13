# Baseline C: credited TIME rejected at the read boundary — 2026-11-12

**Original run failed; complete capacity remains UNMEASURED.** The accepted500-tenant cell passes source/image admission and readiness, completes the sampler-disabled and enabled idle phases, then stops at `M7_EVALUATOR_IDLE_TIME_NOT_OBSERVED` before load or recovery.750 and1000 are not run. [Original lifecycle projection](outcome.json) retains failure, collection and verified controller/watchdog cleanup. Source remains core9db/deploymentd76/image293 with actual alignment9f9ec/instrument1e62. No old result is rewritten.

## Exact reproduced predicate

The immutable [predicate projection](predicate.json) binds the original188539-byte proof by hash. All three snapshots cover500 owners. Successful TIME totals advance0→0→23. All23 observed opportunities have successful TIME progress; no final-only opportunity exists. One tenant, zero-based ordinal22 in the sorted inspection selector, causes the refusal twice: first and midpoint counters are0, final counter1. Acquisition stays1, failures0 and all six job flags are false. The final due is null.

Its already observed due falls352.118ms after the start of the final fetch bracket and598.710ms before its end. The950.828ms bracket covers four RPC pages. The original assessor requires both positive completed work and due-before-global-final-start; only that latter timing clause fails here. This is evidence of an overconservative collector boundary, not missed runtime TIME, a scheduler stall or a need to extend the phase. A separately versioned assessor repair must retain final-only/uncompleted-demand, clock, job, foreign-owner, reset and new-demand refusals. Reassessing historical rounds does not change the original module2 outcome or command exit.

## Useful partial resource observation

[Complete sampler-disabled bookends](partial-resources.json) span62.015437seconds with unchanged container identities. PostgreSQL consumes7.8433 CPU-core equivalents; evaluator1.2806 and realtime0.3253. These are measured container totals, not CPU by SQL role or a steady-state capacity limit.

Between SQL snapshots, display-reader records127271 calls and145172.587 SQLexecution-ms; activity-reader30937 calls and5281.275ms; feed-reader4182 calls and24237.749ms. The SQL snapshots have no own timestamps, so exact QPS is UNMEASURED. Dividing by the nearby cgroup interval would be only a nominal proxy. Execution time is not CPU time.

Enabled idle retains its sampler series and evaluator proof, but the observer refusal prevents the existing AFTER snapshots from being written. Its complete SQL/cgroup deltas and causal sampler overhead are unmeasured. A failure-evidence repair can attempt those existing bookends in `finally` while preserving the original refusal; it must not add metrics, extend the phase or convert failure to PASS.

These partial observations justify investigating evaluator settings-capability lifecycle and background work. They do not establish a bottleneck, HTTP throughput/latency, load recovery,500-tenant acceptance or a performance improvement. The actual maximum planned1000 is not the measured cell size500.

Only bounded synthetic metadata, counts, clock offsets and raw-input hashes are published. Credentials, addresses, full logs, SQL text, private state and tenant IDs remain private. [Manifest](sha256.json).
