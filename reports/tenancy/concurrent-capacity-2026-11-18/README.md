# Concurrent capacity candidate and first results — 2026-11-18

The shared helper is fixed on an unpushed branch for bounded discovery. It joins
S2 removal work with R2's supported-schema and source-factory receipt fixes. The
new roster core and matching C2/RD2 deploy have a distinct image. **Source
acceptance is PENDING and capacity acceptance is NOT_GRANTED.** Entered points
keep their original tuple until closure and explicit operator selection.

## Candidate inputs

Reproduced Git/build identities:

| Input | Source / immutable image |
|---|---|
| Shared helper | `b444b97d47c8cf157deb71094eea567f62a3cbfe` |
| R2 application/deploy, reused | `60bdea6b57bedd60d0675fac51d7d139acce0cda` / `221ebb9815f1a51d5f600e1d465d4f099d736b64`; local image `sha256:72d0de1c1607f369fa73c0dc82a38cebaf857898eb8c785f35714c3e2504d469` |
| Roster core / matched C2+RD2 deploy | `9f0d5f6c428136c1458d03651f55617a5551d1e4` / `45e298ed86b57a537d15512a01e61eef48cf1017`; distinct local image `sha256:1a6228bb6bbed23da6a7e291d356b22d21d8d78925228ea0f05c66b85f298feb` |
| Kubernetes image, reused | core `cd05701d47ad99eebbe7a05e48473bd08bb2ac0d`, image deploy `1230617aa3843fdb4b3e01a6de87277ec93b4f3e`; registry digest `sha256:fbd6671da55842ccbe8290fbf36f8634764fbb071b8db6272b716aede5a67a49`; binding `ef64ff3038ca685e7fd70d19d3e5c87856fb3f0e` |

Named runnable tuples, source fields, distinct local/Kubernetes instrument
identities, image receipts, environment **names**, and invoking commands are in
retained evidence `concurrent-capacity-20261118/candidate.json`. The new local
image is not published. The unchanged Kubernetes image can use the shared helper
after a fresh binding preflight and lifecycle capture; this has not repointed its
operator's entered points.

## Simplification and controls

Reproduced:

- Mandatory fixed-target catch-up selects itself for supported outcome-gated
  discovery. Kubernetes uses its existing 120-second drain default when omitted;
  an authored longer observation budget never extends the per-write clinical
  deadline. Missing-selection ablations go red and restoration passes.
- Factory receipts come from the selected image, bind actual evaluator/realtime
  configuration and provisioning, and require exact row contract digests. The
  merge retains the historical native codec check for old captures. Both current
  and older shipping factory controls pass; missing selection, foreign source
  and wrong row contracts refuse.
- Host driver serialization is scoped to the canonical fixture path. Same-fixture
  overlap refuses, independent fixtures can overlap, and removing the lock makes
  the same-fixture control red. Batch custody, finite clocks, declared allocations,
  actual resource checks and owned cleanup remain. Shared-host figures are contended.
- A producer script's recorded source bytes no longer refuse a frozen Compose
  operation. Actual command, image, role environment, ownership, project and
  configuration custody remain. Other source/configuration seals mixed with
  credential or resource custody remain until their property checks are separated.
- The optional batch resource projection accepts the structured allocation already
  supported by prepare; invalid numeric allocations still refuse.
- An explicit clinical stall is classified as **FAIL** whether the worker is busy
  or idle. The independent REST discovery path may collect alongside that failure;
  it cannot grant clinical PASS or capacity acceptance. The actual local-1000
  shape has a red/restored control, with unknown codes, alerts, malformed job flags,
  foreign state, restore and source-binding controls retained.

No performance arm is required to remove obsolete fixed tenant-count ceilings.
The per-tenant advisory-lock bound remains because it protects datastore health.
W/versioned output and changes to xdripjs remain deferred. Paid perf-cloud source
seals were assessed but not changed in this local/Kubernetes join; no paid run
or provider resource was started.

## First population/rate matrix

All operator figures below are **read-derived**, reduced from retained synthetic
records and rehashed by this integration owner. They are separate tuples, with
shared-host load/observer contention. They do not establish a causal cross-tuple
scaling curve or a saturation ceiling.

| Point / original tuple | Phase and offered ordinary HTTP | Issued → responded; dropped / transport failures | Independently stored / clinical / catch-up | Result |
|---|---|---|---|---|
| Local 500, R2 | realistic-v1 1×; 600 s; 6.944 requests/s | 4171 → 4171; 0 / 0; 6.952 completed/s | 2169 ordinary and 126 probe writes; 126/126 selected witnesses within 120 s; 500 fixed native targets caught up | Completed; owned cleanup ABSENT. All-writer WAL/ACK intake UNMEASURED. |
| Local 1,000 A, R2 | Readiness; ordinary traffic NOT_STARTED | UNMEASURED | Explicit `EVALUATOR_CLINICAL_PROGRESS_STALLED` with idle job flags; no ordinary storage or traffic result | Refused; cleanup ABSENT. A pre-traffic refusal establishes no throughput ceiling. |
| Kubernetes 8, original Tiny09 application tuple | 120 s; target 2 requests/s; host native driver through owned port-forward | 242 → 242; 0 / 0; 2.017 responses/s | 66 ordinary and 29 probe writes; 29/29 selected witnesses ready; all 8 fixed targets caught up | Adopted tiny outcome gate PASS; owned namespace/trust cleanup absent. Source acceptance remains PENDING. |

Local 500's operation p95 values are from each operation's own sample population,
not the maximum of shard percentiles:

| HTTP operation | Samples | p95 ms |
|---|---:|---:|
| `w_sgv` | 1001 | 32.790 |
| `w_devicestatus` | 1001 | 33.033 |
| `w_treatments_v3` | 167 | 35.849 |
| `r_sgv` | 1000 | 18.551 |
| `r_devicestatus` | 334 | 26.564 |
| `r_treatments` | 334 | 25.927 |
| `r_status` | 334 | 41.233 |

Kubernetes pooled operation latency is UNMEASURED at this first point. Its 29
clinical witnesses are below the instrument's 30-sample p95 qualification floor.
The SQL completion observation includes SQL/observer delay: the observed maximum
is 76.863 s, while first-frame maximum is 589.476 ms. This is not evaluator service
time and does not establish whole-roster clinical tails.

## Component relationships and attribution limits

Read-derived local-500 counters span 621.152 s of load bookends, including boundary
cost, while ordinary HTTP rate above uses the authored 600 s schedule. Mean CPU
is cgroup CPU delta / those bookends. Memory is the largest Docker sample,
not a simultaneous aggregate peak.

| Local-500 component | CPU allocation, cores | Mean observed cores | Sampled memory max MiB | Throttled seconds |
|---|---:|---:|---:|---:|
| api | 2 | 0.1164 | 174.2 | 0.371 |
| evaluator | 2 | 0.1238 | 168.8 | 0.137 |
| realtime | 1 | 0.0775 | 130.9 | 1.224 |
| postgres | 2 | 0.2381 | 189.3 | 0.813 |
| pgstream | 1 | 0.0047 | 46.8 | 0.000 |
| vault | 0.25 | 0.0438 | 95.6 | 81.629 |

The evaluator completed 2,290 counted work cycles (3.687 cycles/s over these
bookends); realtime delivery rate and producer events/s are UNMEASURED. SQL
statement request-bracket bounds are 343.435–343.550 statements/s for the API
role and 283.451–283.546 statements/s for the evaluator role, excluding their
separately reported lifetime-role statements. Combined role accounting is 69.240
statements per ordinary HTTP request and 89.694 per evaluator cycle. SQL execution
time is not database CPU or pure evaluator latency. No sampled heavyweight-lock
wait was seen in 86 ticks; this neither measures wait duration nor excludes
between-sample waits. Vault throttling is observed, with causal rate impact
UNMEASURED; no single limiting component is established.

Kubernetes's optional observations span setup/drain as well as steady traffic.
The first point's cgroup API/evaluator CPU ceilings read `max`, so the sampled
117.821/133.689 millicpu means are not measurements under a 500m limit. A subsequent
operator point separately selects that ceiling. Its successful-acquisition rate
is 0.289/s over 255.749 s, including setup/drain; PostgreSQL statements/s and
producer events/s remain UNMEASURED. Optional SQL observation consumed 29.545 s
across 10 successful captures. Observer cost is therefore retained separately.

## Acceptance and next boundary

The image-native receipt and source-plan/loader preflight pass. Focused helper
controls pass, including automatic catch-up, ownership, source contracts,
idle-stall classification and malformed-state refusals. The source-only test
instrument `2d9d2728b53348ad61397ec737bdf1ba6e0ad05d` updates the obsolete route-list
assertion while exercising every current internal path and retaining the public
mount ablation; the image remains built from runtime `9f0d5f6c`.

Reproduced non-database default tiers pass: unit 5,121 / 1 pending, DOM 230,
dependency 368 / 2 pending, core 319 and harness 104 (6,142 passing, 3 pending).
The first attempt exposed the obsolete route assertion and absent compiled
assets; the affected tiers were restored with the test-only correction and
owned compiled assets. Database/integration, stress and browser acceptance for
this successor are not run. The completed predecessor's original qualification keeps its own source
scope; it is not transferred to this image. Operators continue their entered
points, then explicitly select a successor where needed. The next useful result
is the fixed-population Kubernetes rate point and a local-1000 point with retained
clinical outcome, followed by measured-fit population/component changes.

Retained evidence identifier: `concurrent-capacity-20261118`. Input checksums are
in its `matrix-evidence.json`; raw local runs remain under that campaign and raw
Kubernetes runs under `kubernetes-capacity-20261118`. Lane detail:
`/mnt/data/nightscout-workspace/artifacts/handoffs/HANDOFF-capacity-candidate-2026-11-18.md`
(local). No Git push or source promotion occurred.

Repository gates (reproduced): queue schema, coverage and generated views pass,
while `make queue-check` and `make docs-links` fail on three inherited raw-evidence
references: the two queue references to the retired `test-all-and-browser.txt`,
and the PostgreSQL report's retired `projection.json`. The newly exposed archived
collector navigation was corrected to its retained Git revision. No gate was
suppressed. The two selected programme queue items remain UNMEASURED; integration
gates were skipped. No manifest or rich-page change required queue regeneration
or a site render.
