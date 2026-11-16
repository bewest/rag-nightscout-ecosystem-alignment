# Raw-route acquisition — local functional evidence, 2026-11-13

**Reproduced:** ordinary raw routes avoid unrelated clinical acquisition and
reuse tenant route trees with request-private mutable state. The coherent change
is fixed on a local branch. Throughput and latency benefit is **UNMEASURED**;
the coordinator owns one subsequent matched LOCAL comparison with host I/O.
Pgstream scale work continued independently.

The clean source candidate is `3c6e5a016c7aa0665b4a5fcc6a3ece4f7632b6a0`
(two commits beginning with `57dd16465544d4b324314464bd671c5120e662f9`) on
frozen baseline `e90ad574ab9cdf1145d8a3841eef6dad23aa7390`. Deployment remains
`883c516bc2b60a66ef5ae8e211cff4955449fea6`. No new image qualification or
joined deployment acceptance is claimed here.

## Coherent capability

The old preview composition installs a preparation hook for every nonmetadata
legacy request. Authorization invokes it after the trusted request bridge.
The resulting full frame reads six clinical domains, several treatment windows
and all configured domain statistics. It constructs another legacy graph for
each request. Source reading identified these dependencies; recording SQL and
the native comparison reproduce the unnecessary acquisition.

| Raw operation | Candidate behavior |
|---|---|
| Entries model/list GET or HEAD | Same shipping framed entries loader/cache; no unrelated domains/statistics |
| Treatment/devicestatus list GET or HEAD | Same shipping loader/cache for that domain only |
| Current/ID entries, profile/food/activity reads | Handler's own storage read; no preliminary clinical frame |
| Raw POST/PUT/DELETE/preview/OPTIONS | No preliminary clinical frame |
| Echo/count/slice/times aliases | Handler's own query; no preliminary clinical frame |
| Raw route construction | Reuse the tenant's immutable route tree |
| Metadata | Common middleware/context without constructing a clinical graph |

A private AsyncLocalStorage context supplies data, cache, bus and purifier to
shared raw handlers. Accessor descriptors remain live when the legacy graph is
constructed. Each request gets its own mutable state; no clinical frame is
retained for another request. Full derived reads retain their complete frame and
fresh graph. Partial raw frames never feed derived properties or evaluation.

Tenant resolution runs once per request, binding lifecycle admission and routing
to the same result; the next request resolves afresh. Existing request-local
authentication promises are reused. Completed raw replies stop before metadata
fallback work; errors still propagate. Current subject membership/permissions,
physical backend, restore/lifecycle and storage commit boundaries remain in their
existing layers. Removing unused acquisitions removes their lower transactions
and repeated admission work. Required lower transactions still perform their
fresh admission; no shared PostgreSQL/window primitive was weakened. No public
trusted-worker path, cross-request data/auth cache or runtime flag was added.

## Focused evidence

- **59 focused checks pass; five existing native opt-ins are skipped.** This
  includes actual HTTP composition, tenant construction/readiness, private
  acquisition, legacy credentials, authority snapshots and tenant resolution.
- **Three native PostgreSQL checks pass.** Actual preview/data-access/shipping
  HTTP handlers use a NOSUPERUSER/NOBYPASSRLS application role and two synthetic
  tenants. Accepted writes are independently checked in the correct tenant.
- For populated entries model reads with count=1, calls to the application's
  **data connection query method fall from 19 to 1**, in both v1/v2. This excludes
  separate authorization/lifetime connections and driver transaction SQL; it is
  not a pg_stat_statements total or a latency measurement. Empty or cache-miss
  controls also execute the handler's own read.
- Native comparisons retain tested v1/v2 payloads, formats, Last-Modified and
  Content-Type for entries list/model/current, count variants, CSV, mixed types,
  stale/future records and explicit date windows. Other raw domains' POST/storage
  and GET results match full acquisition, including header credentials that can
  actually select the shipping treatment/devicestatus cache.
- Concurrent tenant responses remain separate. A same-tenant recording-SQL
  control forces JSON count=1 and CSV count=2 reads to finish in reverse order,
  then checks their distinct payloads, timestamps, formats and frame/cache/bus
  references. Neither frame escapes into the warm graph.
- Role revoke/restore, subject removal, foreign token and storage-close refusals
  pass. Actual HTTP operation-window middleware refuses a restore adapter before
  a write. That adapter is **not native platform fencing evidence**; joined
  restore/backend exclusion remains the coordinator's acceptance boundary.
- Existing raw/full/derived controls remain meaningful: restoring full acquisition
  makes `RAW_ENTRIES_NO_UNRELATED_ACQUISITION` RED; bypassing derived preparation
  makes `DERIVED_REQUIRES_FULL_FRAME` RED; escaping request state makes
  `RAW_REQUEST_FRAME_MUST_NOT_ESCAPE` RED. Applied mutations are confirmed and
  normal source is GREEN. These are correctness controls, not isolated performance
  proofs for each change.

Two pattern-alias requests reproduce the same UnsupportedQueryError refusal with
full and selected acquisition. Those refusals are retained, not counted as
successful query coverage. An additional MongoDB exchange integration attempt
timed out in its before hook because no MongoDB fixture was available; it is not
a passing check. Earlier fixture-only failures (missing verifier consumer, wrong
close API, subject-delete foreign key and temporary init-server readiness race)
are retained with their repairs; no production workaround followed.

The finite native fixture used PostgreSQL image
`sha256:066167ff39c2a612402ce99b734ea1cff92a9d1f2ac52f697a5f0384f0d88d6b`,
one CPU and 512 MiB. Exact owner/image were verified before removal; the subsequent
owner-label inventory is empty. No k6, saturated profiling or cloud resource was
used for this evidence.

## Next local instrument and custody

The REST helper requires explicit positive integer RPS, duration, per-shape
initial/max VUs, core/image/workload and M7 pins. A six-second arrival unit supports
all positive integer RPS while retaining one write for five reads. Preparation,
catch-up and load create unique private attempt directories before verification,
including refusals. Original verification command outputs are retained. Children
inherit an accessible cwd; Compose uses absolute frozen inputs and explicit
project context.

Four offline helper checks pass. Existing oracle controls still reject missing,
foreign and wrong stored outcomes and successful foreign reads, then restore
GREEN. The existing control fixture needed explicit duration/VUs when they became
required; its assertions were retained. Sampler availability in the next REST
pair remains to be measured; deterministic cwd alone does not establish it.

| Next LOCAL pin | Value |
|---|---|
| Workload SHA256 | `64cb3427fca57a78ae155614dfa09a07b9b1ca300973e1a47bfa83649ad6be72` |
| M7 helper commit | `9ad52a3364d9175d5b4ba372766b204753dab14c` |
| M7 content SHA256 | `a135a49f5a40d6cfe0d90cbce2adeb2209301aa40bd2d6b569ce3605c560cdab` |

Use these same pins for both local halves, including the selected host I/O
instrument. Old e325/workload854926, f208/e90 and all remote paired captures remain
unchanged; remote figures are not a local baseline.

Original final-batch logs are retained at
`/mnt/data/nightscout-workspace/artifacts/rest-raw-acquisition-20261113/batch-final/`.
Manifest SHA256:
`464703544cd13c1c94c56da698ce08fcd27d3fa8909dba69c03a4923a68abf82`.
The earlier entries-only stage and its separate manifest remain unchanged.

The integration owner received the exact source freeze and canonical build plan:
committed archive, same deploy883 overlay/Dockerfile/pinned Node base, verified
source/deploy labels and image-source binding. One canonical candidate image and
one matched local batch comparison follow on its schedule. Full application/
browser/enabled-corpus acceptance and final prcheck belong to the joined batch;
this leaf did not run them or push/app-dev merge.
