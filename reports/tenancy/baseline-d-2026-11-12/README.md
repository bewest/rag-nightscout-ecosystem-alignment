# Baseline D partial idle measurement — 2026-11-12

**Captured result: UNMEASURED / M7_EVALUATOR_IDLE_JOB_PENDING.** Readiness passed for the first 500-owner cell, but its sampled idle proof ended with one evaluator job observed running. Load, recovery and the 750/1000-owner cells were **NOT_RUN**. This is neither capacity acceptance nor proof of completed, hung or missed runtime work.

This immutable leaf projects D's primary saved idle proof, resource bookends and cleanup records. It retains the old frozen application identity; newer candidate acceptance and diagnostics are separate. No campaign, native test, application/source change or cloud operation was performed in preparing the leaf.

## Exact attribution

| Identity | Captured value |
|---|---|
| Core | `9db0ce94f072c8f34aab889f0181afa4269a6758` |
| Deployment | `d76ef17878edb610cdeae75aeef9c07f94b60753` |
| Alignment | `c62ecb446cb34649f0e80e0e41ecac0088024bc2` |
| Measurement instrument | `b60704009d490e04b587220f40d789192c530227b31ac4aafe6bdf160c948320` — 45 files |
| Transport | `f9a39f7dbca1efb9787afd61c15443e545717ef2` |
| Application image | `sha256:293a5c531faac6c156305159246e39defd2592612c302af275efe807102a6d3e` |

[Provenance](provenance.json) binds exact source and primary artifact hashes. Archive SHA256: `9f1e9929da47ea332dd741d8e67b0fde33b27efd1515e4a72172e1665ccc434e`. The profile declares 60-second sampler-disabled idle, 120-second sampled idle and a later 300-second load; those configuration durations are not SQL capture timestamps.

## Actual idle discriminator

[Idle evidence](idle-result.json) preserves the three 500-owner rounds:

| Counter | First | Middle | Final |
|---|---:|---:|---:|
| Completed acquisitions | 500 | 500 | 500 |
| Completed TIME cycles | 0 | 0 | 7 |
| Failed completions | 0 | 0 | 0 |
| Owners with nonzero job mask | 0 | 0 | 1 |

The final nonzero mask is 1: `running` is true and the other five sampled clinical job flags are false. That owner's completed TIME counter is still 0 and its declared due is null. There is **no later completion observation**. Null due during an observed running job cannot establish no demand or successful completion. Seven completed TIME cycles for other owners do not settle this job. Runtime cause and any source/instrument change remain with the source owner.

## Captured resource bookends

Unlike C's failed idle capture, D retains **both BEFORE and AFTER** cgroup, PG-role and PG-statement snapshots even though the idle assessor refused. [Resource evidence](resource-bookends.json) retains per-service CPU/memory/RSS, all captured SQL-role counter deltas, sampler observations and bounded statement-snippet fingerprints.

| Window | Cgroup bracket seconds | Approx. PG cores | Approx. evaluator cores | SQL calls delta | SQL execution-ms delta |
|---|---:|---:|---:|---:|---:|
| Sampler disabled | 61.944145 | 7.86968 | 1.29290 | 188574 | 190407.993202 |
| Sampler enabled | 123.969284 | 7.55987 | 1.25514 | 359968 | 367063.615919 |

**The SQL snapshots have no own capture timestamps. SQL intervals, measured QPS and execution-ms/second are UNMEASURED.** The table reports differences of stored counters; neither nominal phase duration nor the cgroup bracket is presented as a measured SQL interval. SQL executor elapsed milliseconds are not CPU or request latency. No request/query p50/p95/p99 is invented.

Cgroup CPU cores are approximate: each global snapshot timestamp follows sequential service reads, rather than timestamping each service counter individually. Display-reader dominates SQL execution deltas: disabled 130479 calls / 148006.820428 ms; enabled 261126 / 285655.814254. Feed-reader records 4047 / 25723.861089 and 7796 / 54759.354086. The retained statement hashes cover only stored top-50, normalized/truncated-500-character snippets; they are not complete query IDs or a complete query inventory. Raw SQL is not published.

`memory.current` and Docker memory are cgroup observations, not JavaScript heap. Summed process RSS can count shared mappings repeatedly, especially PostgreSQL. Sampler/controller/collector/publication accounting is retained, but excludes unmeasured Docker/psql child and database costs. Different phase lengths, sampling methods and TIME activity prevent a causal sampler-overhead claim.

## Limited C comparison

Only like-for-like **sampler-disabled raw bookends** are compared. C and D report the same 16-core Intel Xeon Platinum 8168 model and kernel `6.8.0-147-generic`, but are distinct hosts; reported MemTotal differs by 4 KiB. Approximate PG cores are 7.84330 in C and 7.86968 in D. These are single-run observations, not a historical speedup result. C lacks enabled after-snapshots, so no full enabled C/D comparison is manufactured. Both runs' SQL deltas lack SQL capture intervals.

## Cleanup, verification and handoff

[Cleanup projection](cleanup.json) records verified controller/watchdog cleanup. Independent audit at `2026-11-13T00:27:37.405Z` reported **0 droplets, 0 firewalls and 0 tags**, with **two exact-original temporary key removals**. Key paths and provider/host identities are omitted. UTC audit time follows the repository's November 12 work date.

[Four metadata negatives](projection-controls.json) refuse wrong source, invented final completion, a measured SQL-rate claim from unstamped snapshots and capacity-PASS laundering. These are offline projection controls, not app tests. [The manifest](manifest.json) binds the leaf; original failed D captures remain unchanged.

No raw logs, SQL, environment, clinical data, network addresses, provider IDs or key paths are copied. The root owner owns programme rollup, classification, source implementation and future publication/measurement. No active acceptance-run files or runtimes were accessed.

[Publication verification](publication-verification.json): JSON/hash/local-link/privacy/whitespace and original-anchor checks passed. One static `make queue-check` attempt failed at queue validation on 16 existing absent peer-worktree cwd references; later steps were skipped. [Exact output](queue-check-output.txt) is retained. No peer or queue file was changed.
