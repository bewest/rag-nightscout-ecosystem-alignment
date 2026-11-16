# Remote joined REST comparison — 2026-11-13

**Reproduced diagnostic: the joined candidate does less SQL work and improves
latency and achieved throughput in this workload.** At 30 offered requests/s,
successful throughput rises 19.9%, API data-role SQL calls normalized to completed
HTTP fall 21.2%, and read/write p95 latency falls 18.2%/15.7%. Both variants still
drop offered work at their declared concurrency bound. Neither meets the full
30 requests/s point; no universal service ceiling or capacity acceptance follows.

## Exact comparison

| Input | Baseline | Joined candidate |
|---|---|---|
| Core | `4a362b72f8e04d99daede9f2e26b2c4ecd84dbce` | `e90ad574ab9cdf1145d8a3841eef6dad23aa7390` |
| Deployment | `883c516bc2b60a66ef5ae8e211cff4955449fea6` | same |
| Image | `sha256:12c93ddd0ce7c4caaac3559c900c16c9d732dd50da3a39e18d7aa767dcc9036d` | `sha256:bfc1a2faa85bef412eb8cbc853376eeb622732cd3d6801bc1b157ead32c3179b` |

Both halves use M7 helper `84595f58d4c164f365721e629e45b3eb9133c131`, content
`27a6cb77f0be0a23146f45f2f57346eb816bb0afb4498bb06752b522772a20bf`, and REST
helper `e3258745c15dad67ab59b9b1c9ec0258bc9e0da3`. Workload SHA256 is unchanged:
`854926eee3a193617e13b70eaa92968d836fcb253f45015dedbcfb0224da8a52`. The REST
runner SHA256 is `25dbc66e06f0367c43be997d685688fa78e72db41e6946ecf80f26d0660b16ad`.

This is one joined batch: request-local legacy credential simplification, trusted
worker SQL, DDL routing, batched bootstrap and runtime wiring. It does not isolate
the throughput contribution of the six-line authentication change. Existing
Codex permission-snapshot/audit-batching reuse is already in the baseline.

The same isolated rig with 8 logical CPUs (Intel Xeon Platinum 8280) runs each half
sequentially, with Docker 29.1.3/overlay2 and host/generator Node 22.23.4. Both
application images declare the same pinned Node 24.22.1 base. Host identity and
settings fingerprint match; exact package/config/image/helper provenance is
retained. Fresh state per half contains two synthetic tenants and 288 SGVs per
tenant at five-minute spacing. Credentials and timestamps are freshly generated,
using the same schema/permissions/data generator. Each half has one API plus normal
evaluator/pgstream/realtime, PostgreSQL and Vault; diagnostics are OFF. No clients,
restarts, fake handlers or clinical-time acceleration are introduced.

A ten-second warmup follows live controls. The unchanged full HTTP/auth/storage
workload offers one SGV write for five latest-SGV reads, for 30 seconds per point.
Both variants pass 6 offered requests/s and fail 30 because iterations drop at the
same limit of 60 virtual users (VUs). Planned 60 requests/s is **NOT RUN** after that refusal. No point
was retried, no VU limit raised, and no instrument changed mid-comparison.

## Measured result

| Offered requests/s | Variant | Successful requests/s | Completed HTTP | Accepted/stored writes | Dropped iterations |
|---:|---|---:|---:|---:|---:|
| 6 | baseline | 6.04 | 182 | 31/31 | 0 |
| 6 | joined | 6.04 | 182 | 31/31 | 0 |
| 30 | baseline | 21.72 | 659 | 107/107 | 242 |
| 30 | joined | 26.04 | 793 | 125/125 | 108 |

| Offered requests/s | Shape | Baseline p50/p95/p99 ms | Joined p50/p95/p99 ms |
|---:|---|---:|---:|
| 6 | read | 104.0/160.0/199.1 | 72.2/105.6/124.9 |
| 6 | write | 147.5/207.1/276.4 | 108.5/137.0/176.2 |
| 30 | read | 2233.2/2734.3/2801.1 | 1900.0/2237.3/2299.5 |
| 30 | write | 2436.1/2926.1/3071.5 | 2200.4/2466.4/2525.4 |

| Offered requests/s | Variant | API data-role SQL calls / completed HTTP | SQL execution ms / completed HTTP | API cgroup mean cores | PostgreSQL cgroup mean cores |
|---:|---|---:|---:|---:|---:|
| 6 | baseline | 249.68 | 36.66 | 0.432 | 0.584 |
| 6 | joined | 195.69 | 28.64 | 0.302 | 0.478 |
| 30 | baseline | 247.85 | 52.11 | 1.082 | 2.352 |
| 30 | joined | 195.20 | 37.15 | 1.009 | 2.247 |

The SQL column is the actual `nsdemo_api` database user. Separate lifetime and
shared activity users remain separate in the retained reduction. SQL execution
time is not PostgreSQL CPU. Resource/SQL bookends are broader than k6 HTTP
intervals; normalized counts are descriptive workload ratios, not exact timing
or causal attribution for each request. Realized read/write mix differs under
overload, so the equal 6-offered point is the cleaner fixed-work comparison.

API audit buckets normalize from 3 verify/2 decrypt/1 sign events to 1 verify/1 decrypt/
0 sign events per completed HTTP at both points. These broader-bookend ratios are
descriptive. Separately, the focused source control reproduced the legacy path
changing from six crypto/audit operations to two without a cross-request cache.
The read-derived mechanism removes an internal token mint/verify round trip while
retaining raw verification, current subject membership and fresh permissions.

## Correctness and limits

Every issued HTTP/content check passes; refused/uncertain writes and failed/
invalid reads are zero. Independent SQL checks match every accepted write's
tenant, timestamp, device, type, glucose and dateString. Each fresh half also
passes invalid/foreign credential refusal, the supported role-admin API control
(A denied 401 while B reads 200, then A restored 200), and actual stored-value
GREEN → RED → GREEN mutation/restoration. After each measured point, separate
observations show stored/observed/completed/output clocks equal and pendingAt
null. Selected BG-now mean/last/mills consistency passes. These are selected
properties, not a connected-client or broad clinical-equivalence claim.

No measured authority/isolation/persistence regression appeared. The coordinator
still owns the joined readiness/full-acceptance boundary; this short diagnostic
does not close it or declare a release ready.

Both server wait/lock samplers are **NO-INSTRUMENT**: their Compose invocation
refuses `stat .: permission denied`, leaving header-only activity/lock files.
Raw empty wait arrays must not be read as zero contention. Driver pool-queue
and API-stage durations are also **NO-INSTRUMENT** with diagnostics OFF.
PostgreSQL per-process CPU is unavailable; cgroup CPU is measured. Docker stats
and component/process bookends remain available. Low sampled k6 CPU does not
establish a generator ceiling; both 30-offered points reach their VU bound.

## Evidence and custody

Retained local root: `data/capacity/rest-api-performance-20261113/remote-results/`.
Original baseline/candidate archives, request ledgers, independent rows/oracles,
audit/SQL/resource bookends and final rig/source/image provenance are returned
unchanged and checksum-verified. The derived comparison is
`comparison-derived.json`; raw credentials and captures remain ignored.

| Retained record | SHA256 |
|---|---|
| Baseline original archive | `ab54476528673cdc776fdadd4c146c15cbb59aec322d3996a5ae4f02a0a77c70` |
| Joined original archive | `28742843004c27a4785616f08b2e3aaa0e8d503d97b904842a627f27b82d431e` |
| Evidence-return manifest | `292b8547c0be47995234306b5ee61a2e2ac5ce94c7063af4be9027e4ebd0b521` |
| Independent file-only audit | `dddf778d466990e9820e040c39f49e943b30d59f11018fae40bad2297136abfe` |

The independent audit found no material count, source/image or oracle mismatch
and confirms the stated sampler/bookend limitations. Both owned runtime projects
are stopped; no remote-only evidence remains. The integration/resource owner
received READY_FOR_PROVIDER_CLEANUP and independently verified deletion of the
owned VM, firewall, SSH key/tag. Its receipt is retained at
`data/acceptance/remote-rest-scope-20261113/cleanup-verified.json`. No new campaign,
remote extension, push, app-dev merge or publication was performed by this lane.
