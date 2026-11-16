# Coherent pgstream worker repair and first diagnostic — 2026-11-14

Later source tuples and their limits are recorded in the [November 15 comparable experiments](#comparable-experiments-and-final-image-tiny--2026-11-15-pacific) and [local operating-envelope diagnostics](#local-operating-envelope-diagnostics--2026-11-15-pacific). Earlier captures retain their original attribution.

The coherent worker repair passes source acceptance, canonical image qualification and the first completed local 1,000-tenant/2,000-client discovery window. The window measures demand below an unknown capacity ceiling. Nothing in this record claims a merge to application `dev`, a release or capacity acceptance.

## Frozen inputs and retained evidence

| Input | Exact identity |
|---|---|
| Application | `5d305dd08f006b7956c5c9a647d5e541b307c9f1` |
| Deployment | `0dcde57e1dd3959e3420a6e1e4ff2ef65a40902d` |
| Reference `official/dev` | `4a482627bfdafb1fef8dcbe0ac6c484811cae563` |
| Qualified application image | `sha256:544ab2001b46297aec069f32beacdc7a152711a521f83faea9630de38032472d` |
| Failed C controller | `f2fdbb3caec65106fc8f4c9e5da7d86e5b63c195` |
| Repaired D controller | `7ddfe34ceceedaffbe5d83f6bbc101f11db488a9` |
| Completed local E helper | `02c18aabfe459e6ed673244fffb78a4224e0d102` |
| Local E instrument manifest | `5d1a5661b0a5f28411d6cc643c68a4a007d6a2f4b8e6fdde64926d4171b95fe2` |
| Offline remote firewall/binding repair | helper `4fb721aa9d93ecfe39c26f90f061460463767efe`; controller `4c538d5860cc720b4ce73f70aeee63fa82e8ed4a` |

Retained evidence identifiers are `pgstream-activity-small-pair-20261114/acceptance-idiomatic-04`, `pgstream-activity-small-pair-20261114/build-idiomatic-04` and `pgstream-remote-small-5d305-0dc-20261114-c`, `pgstream-remote-small-5d305-0dc-20261114-d` and `pgstream-remote-small-5d305-0dc-20261114-e`, `pgstream-local1k-5d305-0dc-20261114-b` and `pgstream-local1k-5d305-0dc-20261114-e`. Originals remain outside Git under the workspace artifact store. Earlier failed campaigns 01–03 and prior diagnostic captures retain their original attribution. This record does not replace the [earlier startup repair](../pgstream-startup-repair-2026-11-14/README.md) or the [first repaired 1000-tenant failure](../pgstream-repaired-1000-2026-11-14/README.md).

## Source acceptance — reproduced

The frozen candidate runs `node scripts/test-tiers.js check`, each declared unfiltered tier through `node scripts/test-tiers.js run <tier>`, and the enabled native corpus with the retained PostgreSQL, Vault, MongoDB and pgstream bindings. All stages exit zero. Counts overlap and must not be added.

| Suite | Passing | Pending | Failing |
|---|---:|---:|---:|
| Unit | 4505 | 1 | 0 |
| DOM | 205 | 0 | 0 |
| Dependency | 368 | 2 | 0 |
| Core | 319 | 0 | 0 |
| Harness | 101 | 0 | 0 |
| Integration | 3643 | 920 opt-in | 0 |
| Stress | 18 | 0 | 0 |
| Browser | 686 | 0 | 0 |
| Enabled native corpus | 923 | 1 optional | 0 |

The repair validates API port intent before binding, refuses invalid reader configuration before acquiring registry resources, and inspects delivery metadata once per owned delivery pass. Realtime admission carries the actual registry cohort and refreshes trusted metadata after staged acquisition. Runtime closure fences effects before asynchronous drains. Fresh input generations, clinical pause/suspend and stale-owner guards remain authoritative.

Native evaluator fixtures use the actual CLI, declared manifest, canonical ACL and settings validation, YAML wire configuration, monotonic versions and typed durable observations. A low-level provisioning primitive has its own fully migrated namespace: inserting an unregistered tenant into a live captured cohort correctly fails admission. Six focused evaluator suites pass 31 checks; recorded child processes, ports, owned PostgreSQL volumes and Vault fixtures are absent after cleanup.

Meaningful controls preserve the original unsafe-RLS no-sink rejection, held-close refusal of late output, paused clinical output and cross-tenant continuity, canonical deployment pin refusal, parser selection and provisioning admission failures. Failed controls and restored positives remain in retained lane evidence. No clinical guard was weakened, no stream was re-primed and no adopted test deadline was extended. One direct Mocha run used an inappropriate default timeout for harness inventory; the declared harness runner passes without changing its deadline.

## Canonical image qualification — reproduced

Canonical preparation and build pass. Independent inspection verifies 1178 source files with zero mismatches. Corrupting the expected source hash makes qualification fail with exit 21; restoring it passes. Existing historical image tags are unchanged. The build receipt SHA-256 is `996cada3b87bff4e38d2ca93687f93bdf36cd16e042d8d4a548dbe44ac411dfa`.

The application archive SHA-256 is `27e8b4fb50fb196d340d1d6f70c1cf4164b100811136ee5056b8167d125c4e79`. PostgreSQL is 16.16 with wal2json; its archive SHA-256 is `0b83799732deb1636cc64897278f5cf826bded929616dda4576e64d98ae030f0`. Image qualification alone does not prove whole-system runtime behavior.

The completed-work SQL oracle module is unchanged from its earlier native qualification. Scoped reuse preserves that earlier executed source identity; it does not claim a fresh native pass on this image. Current outer source/image binding controls and actual runtime remain distinct evidence.

## Diagnostic setup and remote closeout — reproduced

Remote C stopped before timed load on strict log-directory initialization order (`FileExistsError`); its copied deletion hook also lacked executable permission (`EACCES`). The independent guard deleted the exact owned resources. The controller repair creates fresh directories before admission logging and checks hook bytes and executable permission before execution; broken/restored controls pass. Remote D passed application bootstrap and exact archive imports, then driver bootstrap rejected a k6 configuration digest used as a registry manifest digest. The corrected linux/amd64 manifest resolves to the same existing image configuration and root filesystem.

Remote E passed both host bootstraps and the corrected k6 pull, then refused firewall admission (`REMOTE_GENERATOR_ONLY_FIREWALL_REQUIRED`) and unbound cleanup (`EXTERNAL_BINDING_CHANGED`). The original host's serialized firewall rules were not captured, so argument order as the historical cause remains read-derived. A separately reproduced serializer-order case and offline semantic-parser controls support the repair; prepared external binding now records the actual port before ingress. The full repaired remote workflow has not run. Each C/D/E root deletion audit confirms zero owned VMs, firewalls, keys, tags and volumes, with temporary keys and guards absent. There is no remote throughput or latency result and no current paid plan or GO.

The final cumulative model covers five closed allocated pairs, including earlier source attempts. Conservative compute upper USD1.991911 plus retained egress and tax/deletion reserves gives USD4.090111 under the original USD6 cap. This is a model, not an invoice or a new allocation allowance. Its home is `pgstream-remote-final-budget-20261114/final-cumulative-model.json`, SHA-256 `4af620143e538cddf8d1ec7fdbeadc226ba9fd8385a516cbd83f4af7bab4e399`. Independent local guards do not survive controller host loss.

Local B completed all eleven canonical startup stages. Its first attachment selected the application root instead of the fixture's owned client dependency tree. A later attachment ignored diagnostics mode; local D then stopped on a valid Linux limits line with trailing spaces. These failures and partial captures remain unchanged. The completed helper uses the actual owned dependency root and diagnostics selection. Its driver qualification accepts the valid limits line and explicitly reports unavailable delegated CPU-set and oversized host-interface fields; hard process, image, namespace, owner, file-limit and memory guards remain.

## Completed local E window — reproduced

The qualified image restarted the preserved B durable fixture without provisioning, migration, re-priming or stream reset. Configuration: 1,000 tenants, two clients each, ordinary cadence (`accel=1`, `hotFactor=1`), 10-second warmup, 30-second idle and 310-second configured load, with no restart campaign. Readiness, idle and load checks pass, the stored-write oracle is GREEN, and hard failures are empty. The pure measurement reduction is complete; capacity acceptance remains `NOT_GRANTED`.

| Observation | Result and scope |
|---|---|
| Ordinary accepted and stored writes | 3,102 each; all 1,000 tenant rows match, zero uncertain writes |
| Separate probe writes | Two accepted and stored; zero pending |
| Connected clients | 2,000 at end; zero observed server disconnects |
| Sampled output and frames | Two selected tenants out of 1,000 pass stored/output/client witnesses; four of four expected frames arrive |
| Sampled write-to-frame latency | Four frames; p95/max 113 ms |
| Sampled evaluation-clock latency | Two samples, 286 and 1,126 ms; no missed selected evaluation within 120 seconds |
| Evaluator progress | 2,238 completed work items; zero failed completions; not an all-write latency distribution |
| Global HTTP | 12,371 requests; 36.390831 requests/s; p50/p95/p99 37.317/84.880/109.225 ms; reported failure rate zero |
| Scenario demand | Seven shapes, configured 36.6667 requests/s; 11,371 scenario requests. Dividing by configured 310 seconds gives **derived** 36.6806 requests/s, not a separately instrumented phase clock |

Global HTTP includes 1,000 setup JWT exchanges. The dropped-iteration counter was not emitted; its absence is not reported as a measured zero. Sampled clinical and frame evidence does not establish all-roster clinical equivalence or per-ordinary-write evaluation latency.

Resource measurements use 344.283-second load bookends that include setup and collection. Mean total service CPU is 2.228676 cores; the matched idle interval averages 0.487723 core. Anonymous memory is not JavaScript heap, and these phase observations do not establish a leak or a tenant-count growth slope.

| Role | Mean load CPU, cores | Anonymous memory after load, MiB | Anonymous change during load, MiB |
|---|---:|---:|---:|
| PostgreSQL | 1.130399 | 160.34 | −20.88 |
| API | 0.451437 | 496.99 | −5.80 |
| Evaluator | 0.166701 | 440.63 | +127.74 |
| Realtime | 0.154649 | 290.53 | +19.52 |

Socket priming separately adds 249.90 MiB API and 165.83 MiB realtime anonymous memory. Load SQL bookends record 1,514,665 calls, 1,084,424 rows and 62,830,100 WAL bytes. They mix reads, writes, setup exchanges, viewers, control and collector work. They are not a causal per-write budget; statement execution time is not PostgreSQL CPU or wall time, and WAL/row counts are not wire bytes or round trips.

Whole-host load I/O wait is 11.20%, with substantial I/O pressure; the shared host prevents attribution of that delay to the application. Pool wait/query/held measurements remain UNMEASURED because retained role-log heads contain no current-interval samples. Realized realtime metadata batch size, qualified driver CPU-set/NIC/ephemeral-port headroom, SQL wire bytes/round trips and higher-count scaling remain UNMEASURED.

Independent cleanup confirms all nine exact-owned B containers stopped, the E guard absent and three durable volumes retained. Originals are unchanged. The result is a complete bounded local discovery point, not a capacity ceiling or a matched comparison with earlier two-tenant REST results.

Retained homes and checksums:

| Retained identifier | SHA-256 |
|---|---|
| `rest-remote-first-analysis-20261114/localE-analysis.json` | `b09193cca917b27bf0df21dfc3a39774b86a720aa2884d4e75bcf7034ce87262` |
| `pgstream-local1k-5d305-0dc-20261114-e/root-local-stop-audit-01.json` | `1e2190488536c713373ef1014ebd105ccc0461758a4432f52ee560249da047af` |
| `pgstream-local1k-5d305-0dc-20261114-e/completion.json` | `ca9bf1e6b73482f463f537f4f42915a4c8bc4e34090bcc764d41491a7d7adcc7` |

The analysis record binds the original input hashes and full/pool reductions. Originals remain outside Git. Source campaign commands are in `acceptance-idiomatic-04/commands.json`; executed local fixture, attachment and window commands remain in the local B/E packets.

## Fixed-cohort request-rate curve — reproduced

The accepted application and image above also ran at 120, 180 and 240 offered scenario requests/s on the same preserved 1,000-tenant fixture with 2,000 polling clients. Tenant count and request rate are independent test axes. A failed or overloaded point remains evidence; these points are not an all-green milestone sequence.

The shared local host has an Intel Core i7-11800H, 16 logical CPUs and 65,683,804 KiB total memory. Each point keeps the seven request shapes and their three-write/eight-read weights, credential mix, ordinary acceleration, 10-second warmup, 30-second idle and 310-second configured load. Each restarts the same durable fixture without provisioning, DDL, re-priming or resetting history. History therefore accumulates across points. The observation helper is `df4dbbf159065ecbd297c5e044a982cf81c9e800`, instrument `752a16da422931e561c17b9628b5ab6d91665fc15b60d686661ae5cf28eb7dfc`; its explicit transition retains the original runtime owner. The successful E driver bytes are unchanged. Startup warming and sustained idle use separate observation files from the canonical load's readiness check.

| Offered scenario requests/s | Scheduled attempts / HTTP responses | Global HTTP failures | Dropped iterations | Global p50 / p95 / p99, ms | Capture status |
|---:|---:|---:|---:|---|---|
| 120 | 37,202 / 37,202 | 0 / 38,202 | UNMEASURED: not emitted | 46.595 / 153.270 / 269.610 | MEASURED |
| 180 | 55,802 / 55,802 | 0 / 56,802 | UNMEASURED: not emitted | 133.538 / 709.555 / 926.214 | MEASURED |
| 240 | 73,828 / 73,828 | 14,610 / 74,828 (19.525%) | 575 | 2,315.327 / 4,723.376 / 5,002.058 | PARTIAL: overload and uncertain writes |

Every point includes 1,000 successful serial JWT setup exchanges in global HTTP. Scenario counters exclude them. Positive HTTP responses include errors; they are not successful-work counts. Transport-failure counters are zero. Counter rates in the raw k6 summary use a clock that includes setup, so they are not scenario-only throughput. Dividing scenario counts by the configured 310 seconds is a derived normalization, not a separately instrumented traffic clock. Per-shape tails also rise sharply: SGV-read p95 increases from 127.642 ms at 120 to 691.834 ms at 180, independently of setup weighting.

| Offered rate | Ordinary accepted / stored / uncertain writes | Client and selected-output observations |
|---:|---|---|
| 120 | 10,146 / 10,146 / 0 | All 1,000 rows reconcile exactly; 2,000 clients connected at end; four selected frames arrive, p95 371 ms |
| 180 | 15,219 / 15,219 / 0 | All 1,000 rows reconcile exactly; 2,000 clients connected at end; four selected frames arrive, p95 1,060 ms; two ping-timeout reasons are retained |
| 240 | 16,106 / 16,148 / 4,047 | All 1,000 rows satisfy conservative uncertainty bounds, not exact reconciliation; 2,000 clients connected at end; four selected frames arrive, p95 85,941 ms; selected evaluation p95 86,312 ms |

Two separate probe writes are accepted and stored at every point. Output witnesses cover two selected tenants, not all-roster clinical equivalence. At 180 the server-disconnect counter is zero while the probe also records two ping-timeout reasons; neither observation is discarded. At 240 the stored-write oracle's conservative bounds do not establish that every uncertain request failed or succeeded. Its exact-write control remains UNMEASURED, which keeps the discovery PARTIAL. Readiness, idle and observed load-progress checks pass; no hard correctness failure is recorded. This does not relabel overload as a healthy capacity pass.

| Offered rate | Mixed load bookend, seconds | Total service CPU, cores | API / PostgreSQL CPU, cores | API / PostgreSQL memory after, MiB |
|---:|---:|---:|---|---|
| 120 | 346.206 | 3.956 | 0.731 / 2.270 | 1,090.85 / 601.39 |
| 180 | 346.929 | 5.314 | 0.984 / 3.181 | 1,125.78 / 804.58 |
| 240 | 349.131 | 5.904 | 1.040 / 3.457 | 1,194.82 / 560.63 |

CPU bookends include setup, stock clients, probes, control and collection. Memory is the container cgroup gauge, not JavaScript heap. The API approaches one core while latency rises and delivered work flattens. This supports an API-process saturation hypothesis; it does not prove a causal bottleneck or a whole-host capacity ceiling. Whole-host I/O remains shared context. Exact current-incarnation pool logs now support observed subwindows; they do not cover a whole phase. At 240 the API load reducer refuses a counter reset and reports UNMEASURED rather than normalizing it away.

The original SQL classification function was recovered and reproduced against the retained E result before reuse, with no category changes. Captured statement totals are 3,131,622 / 3,997,433 / 4,174,817 calls at 120 / 180 / 240. Epoch-proof execution totals are 261.404 / 382.922 / 381.092 seconds; lifecycle register/finish totals are 74.262 / 103.900 / 115.346 seconds. These are mixed-work PostgreSQL statement-execution sums, not wall time, PostgreSQL CPU, round trips or causal per-write costs. Residual statements remain unclassified; guard work is not presumed removable.

The observed transition is sharp between 180 and 240 offered requests/s for this source, mix, client count, history and shared host. No higher baseline point or per-rate tuning was needed. All exact-owned workload containers and guards are stopped; durable state and failed outputs remain retained. Local and remote curves remain separate.

| Retained identifier | SHA-256 |
|---|---|
| `pgstream-rate-analysis-20261114/120-reduction.json` | `0b70bf8ad0be7f0d8f6adb0eda79624f707cdf3b6e7bb6f44333cc7e5a488c8d` |
| `pgstream-rate-analysis-20261114/180-reduction.json` | `927f8a700fbd0999333603f85f4110baebee48e45a7b44c2c6d3be86f4cef790` |
| `pgstream-rate-analysis-20261114/240-reduction.json` | `d24e1722a9e504bc78c943cddf9ee55e6f21c8a4397bdecbf0b4355db649adc6` |

Raw point packets are `pgstream-local1k-rate-20261114/{120,180,240}`. The analysis directory retains separate unchanged-rule SQL classifications, exact inputs, workload bindings, driver observations, pool coverage and cleanup. Originals remain outside Git.

## Separate 3,000-tenant failure and NEXT correction

The separate fresh 3,000-tenant fixture uses the same application commit with deployment `df5362745a1b2d1b02b9186daedef3faccc14e58` and qualified primer image `sha256:153505ae2a2568cd8a081762506a6ca8d6c8eef3b7ad10529ca04c30993f8416`. Priming at concurrency two and independent application-database counts reproduce 3,000 saved and persisted tenants. Original prime-only time and cost remain UNMEASURED. After corrected warming and strict idle passed, serial k6 JWT setup returned 44 successes and then a 503, before any scheduled workload request. The response body was not captured, so its precise refusal cause remains unknown. All roles stopped and durable state remains preserved. Retained home: `primer-database-continuation-20261114/resume-03`; separate partial reduction: `pgstream-3k-partial-analysis-20261114/resume03-partial-analysis.json`.

A controlled source reproduction independently shows that an already registered operation's completion can expire in the lifetime-session queue, poison a healthy shared backend and trigger datastore recovery. NEXT commit `c8a315d38d6a51a3a0e91adbc6d96d1e803014ed` includes the earlier safe numeric catalogue ordering and drains registered completions before new admissions. Unstarted admissions retain their deadline; true backend loss and ambiguous COMMIT replies retain fail-closed behavior. Registered completion has no fixed queue-cancellation deadline; it drains after current SQL and earlier completions under existing transport bounds.

The isolated PostgreSQL 16.16 proof reproduces completion after an admission deadline, zero remaining locks and markers for that case, and preserved refusal/pending-state semantics for real backend loss and lost registration/finish COMMIT replies. Exact cleanup removes the one owned tmpfs fixture. Results are `lifecycle-completion-pressure-20261114/native-02/results.json`, SHA-256 `e43fdaa4bf2ede817097e7b68dafc4bafb68047a6122ee4148103e9359ff4fa1`. This is a component proof, not proof of the historical 3k cause or of a fixed 3k runtime. The joined source completed the acceptance and image qualification below. Its performance and the preserved 3k application diagnostic remain UNMEASURED.


## Joined completion candidate acceptance and image — reproduced

Application `7291af9b9cc48dbe58c488e892e7b34cf367c88e` joins the completion correction, numeric catalogue ordering and pressure-test tier registration. Deployment is `df5362745a1b2d1b02b9186daedef3faccc14e58`. The first acceptance attempt stopped at two unchanged browser-bundle budgets. A copied, untracked nested dependency symlink resolved historical jquery and moment copies. A cache-only rebuild reproduced the failure. Removing only that owned link and rebuilding produced app/all-page gzip sizes of 325,207/415,790 bytes within unchanged budgets; nine focused checks passed. Failed originals and the repair receipt remain retained. No source or budget change was used to pass preparation.

One repaired campaign runs the inventory, all eight unfiltered tiers and enabled native corpus on that exact source. Counts overlap and must not be added; duplicate formatted native totals are counted once.

| Stage | Passing | Pending | Failing |
|---|---:|---:|---:|
| Unit | 4,512 | 1 | 0 |
| DOM | 205 | 0 | 0 |
| Dependency | 368 | 2 | 0 |
| Core | 319 | 0 | 0 |
| Harness | 101 | 0 | 0 |
| Integration | 3,643 | 920 | 0 |
| Stress | 18 | 0 | 0 |
| Browser | 686 | 0 | 0 |
| Enabled native corpus | 923 | 1 optional | 0 |

Inventory and every stage exit zero. Recorded shared PostgreSQL/Vault containers and three volumes, outer MongoDB and same-birth source/guard processes are independently absent. Native corpus remaining resources are empty. Both preserved workload projects remain stopped with durable fixtures retained. Transfer to the fresh integration owner did not repeat acceptance.

Canonical image `sha256:2a4e911fc9d4a06a4a25286c90d8d9fca835d873849eb6974c15bdb498d41ff8`, tag `ns-lifecycle-completion-app:7291af9b9cc4`, passes canonical check-image and independent archived-source verification of 1,179 files, Node 24.22.1, source/deploy labels and the pinned pgstream binary. A deliberately wrong expected source hash fails with exit 21 and exactly the changed path; restoring the expected manifest passes. Prior image tags remain unchanged. Final prcheck exits zero with `OK`; a separate Git read confirms unchanged clean source and `official/dev` `4a482627bfdafb1fef8dcbe0ac6c484811cae563`. Fixed locally; nothing pushed, merged to application dev or released. This verification record has no operator-visible change.

Retained evidence root: `lifecycle-completion-joined-20261114`. Raw logs and originals remain outside Git.

| Retained artifact | SHA-256 |
|---|---|
| `acceptance-02/results.json` | `3cfd6f862d2cf1cd85c423fbb1c775ff3a95541b6a994c1fcf8c6366076fcb62` |
| `acceptance-02/root-final-absence.json` | `0bc23a3cc91fed0fc1b8a77a0762142ccb634ea931616a2f11227111e36a79bb` |
| `build-02/build-receipt.json` | `a5febf13e4938d3e9edc6344f902a261539c5040d05f7aeb59fa755143112497` |
| `build-02/image-byte-control.json` | `72ccff99e4e74cd5924cea15fd9edde0c09c7e344c91e1440a4033dad3516235` |
| `build-02/image-byte-control-restored.json` | `5757f06f9e8aeaa75828d633de0999cbfe9893d55a2480bd80f5fe394978e47e` |
| `build-02/prcheck.log` | `f67538ba898a1d3583441362741188b4bdfebe2967b77e32521c1db15d97b7d4` |

Qualification is a source/image result. It does not establish improved throughput, evaluator execution latency, realtime client tails or the historical 3k refusal cause. The next source-bound diagnostic keeps HTTP, evaluator progress/freshness, realtime catch-up and selected client-frame delays distinct. Missing duration/queue instruments remain UNMEASURED; two-tenant polling observations are not executor latency or an all-write distribution.


## Repaired 3k observations and comparison binding fault — reproduced

The qualified completion candidate above ran on the preserved 3,000-tenant fixture with 6,000 stock polling clients. These are separate questions with separate dispositions; neither establishes a healthy full ordinary 3k workload.

| Question | Captured result | Limit |
|---|---|---|
| Same Node actor, 64 serial exchanges before and after client priming | Both phases return 64 HTTP 200 responses without retries. Stock setup returns 3,000 HTTP 200 responses without retries; all 6,000 clients prime, with zero dark or server-disconnected clients at that bookend. | The probe remains alive after its recorded result. Root stops it through exact-owned cleanup; the run is PARTIAL. This actor and exposure interval do not reproduce the original full serial k6 setup. Missing after-cost bookends remain UNMEASURED. |
| Full ordinary 3k attempt | Canonical readiness and 120-second idle pass. All 6,000 clients prime. Serial k6 JWT setup returns 21 successes, then request 22 returns 503 with allowlisted `AUTHORITY_UNAVAILABLE` after 5,005 ms. k6 exits 107; scheduled traffic does not run. The ordinary probe exits zero. | The run is PARTIAL. The public code masks several internal causes; queue admission expiry is plausible, not established. No completed 310-second workload or ordinary throughput is claimed. |
| Selected output/client proof in the ordinary attempt | One accepted probe write is stored and produces two frames at 173/174 ms and one polled completion at 1,163 ms. The selected retained-output/BG-now witness passes. | One tenant and two frames, with no cold witness. Connected-at-end is 6,000, but recorded transport/connect errors remain visible; it is not proof of healthy client transport. Polling is not evaluator execution latency. |
| Evaluator progress in the ordinary attempt | Two available snapshots cover all 3,000 tenants and show zero completed-work, time-work and failure deltas. | The strict three-round criterion is UNMEASURED. The selected probe completion can precede the first progress snapshot, so zero later delta alone does not establish a stall. Backlog/drain latency lacks the required clock proof. |

The current-marker count oracle reconciles zero ordinary accepted/stored/uncertain writes across all 3,000 tenants, plus the one separately counted probe. That green count result does not establish the unrun workload. Missing dropped-iteration metrics, driver headroom and cached realtime counters remain UNMEASURED. The mixed load-cost bookend spans 74.688 seconds and includes setup, probe and control work; it has no scheduled-traffic denominator. Its role means are API 1.057, PostgreSQL 2.506, nginx 3.605, evaluator 0.151 and realtime 0.574 CPU cores. SQL execution aggregates and observed pool subwindows do not attribute the 503 to a particular query or establish per-write CPU cost.

Both executors and independent guards finish, and exact resource/process absence is independently verified. Volumes and protected fixture files remain retained. The ordinary capture completes as an evidence collection, while its semantic disposition remains PARTIAL. Homes are `pgstream-3k-upgrade-next-20261114/runtime-03` and `runtime-04`; the pure ordinary reduction is `pgstream-ordinary3k-analysis-20261114/compact-summary.json`.

The next 1k candidate comparison has no performance result. Its authored Compose prefix copied the 3k project name while selecting 1k state and owner. It replaced six stopped 3k application container definitions with 1k-bound candidate definitions. Custody capture and normal cleanup refused; root then stopped exact attributable resources, restored the six correct 3k definitions without starting them, and verified both projects stopped. Database volumes were retained, no provisioning or re-priming ran, and protected configuration/provenance files remained unchanged. Container identities changed and require a new custody record. No claim is made that database contents were bitwise unchanged during application startup.

A shared orchestration binding repair is required before another local or paid launch: one canonical project/command binding, actual resolved Compose identity checks before mutation, and original/new container layout epochs plus recorded-ID cleanup. The independent read-only namespace audit reproduces the copied-project fault; the failed inputs and containment/restoration evidence remain immutable. This is a harness boundary, not a reason to repeat application source acceptance or claim the comparison complete. The local handoff names the sole repair writer and the independent audit owner.

| Retained artifact | SHA-256 |
|---|---|
| `pgstream-3k-upgrade-next-20261114/runtime-03/root-final-summary.json` | `f779ac020003e42d6a440e16805183364968e566b263dd9013522b74f1920e6a` |
| `pgstream-ordinary3k-analysis-20261114/compact-summary.json` | `e63e8637fb36cb13cd89f02817bb64fd318c3e4898f6962a3d37ce4b78331fae` |
| `pgstream-1k-candidate-comparison-20261114/integration-180/runtime-01/root-emergency-exact-stop.json` | `5d3d4cf72e7c03d5fa6c4991fda4c261409781679e89a64300bb064631bcdc68` |
| `pgstream-1k-candidate-comparison-20261114/integration-180/runtime-01/root-3k-restoration-receipt.json` | `616473864293cdb677e1e9d5e3fd4a6b6ca65e73deff2e8efd46af3e29c7cd86` |

## Local cold-start costs — reproduced

All eleven canonical startup stages exit zero. After-API to after-prime bookends retain the same source, image, owner and SQL reset identity, with no statement eviction. The measured interval spans 495.589–495.969 seconds and includes interstage collection and concurrent services. It is not exclusive primer work or steady state.

| Observation | Measured value |
|---|---:|
| SQL calls, all captured roles | 604,859 |
| SQL rows | 447,009 |
| WAL bytes | 18,758,032 |
| Same API Node process CPU | 104.32 CPU-seconds |
| API process mean CPU | 0.2104 core |
| API anonymous memory after prime | 381,353,984 bytes |

The memory value is an anonymous-memory gauge, not JavaScript heap or RSS. Database transactions have shared scope. SQL wire bytes and round trips have no instrument. Evaluator and realtime do not appear in the matched prime process roster; their missing measurements are not zeros. Workstation I/O wait and pressure, plus concurrent cloud upload, confound wall time. The pure reducer and original input hashes are retained in `rest-remote-first-analysis-20261114/localB-startup-reduction.json`, SHA-256 `37b0959430aa94397377c667eb08823e4052536aa4f7f86b47945f28550e054e`.

## Remaining boundary and owner

Final `tools/review/prcheck/prcheck.sh` exits zero and ends `OK`; a separate Git read confirms the same clean application head. Retained log: `pgstream-5d305-final-review-20261114/prcheck.log`, SHA-256 `06db2dd8a61978f2b626a31f81995b64bf1a8a036518746d084aef3b049662ca`. `make queue-check` and `make docs-links` pass in the record worktree; logs are retained beside prcheck. Initial sandbox attempts failed at `spawnSync git EPERM`; normal host execution passed without source changes. The separate programme-wide `make queue-status` measurement reports PASS=197, FAIL=67 and UNMEASURED=147; that overall queue result is not green and does not replace this frozen-source evidence. The maintained registry has no operator input for extended plugin settings; retained pure clinical-domain checks do not establish that missing operator capability.

Fresh integration owns source adoption, local resources, finite runtime windows, budget review and cleanup. Capacity preparation owns the concurrent-primer/current-harness rate binding; epoch/lifecycle reduction continues independently with fresh authority proofs preserved. Tenant count and offered request rate remain independent measurement axes. The fixed-cohort rate observations and separate 3k setup failure above guide the next bounded question; neither a tenant count nor an all-green sequence is a capacity definition. Source correction, acceptance and image qualification proceed as one distinct batch before attributing improvements to the new candidate. The historical REST runner binds a different deployment and exactly two tenants; it cannot be reused as a matched current-system curve without a qualified binding change. Local and remote hardware need separate curves. A parked REST memory batch is not automatically part of this join. No paid allocation follows from this record. Evolving local custody is in `externals/work/HANDOFF-pgstream-flow-2026-11-13.md`.


## Qualified candidate fixed-cohort observations — reproduced

The joined completion candidate above completed 180 and 240 offered scenario requests/s on the preserved 1,000-tenant fixture with 2,000 polling clients. Application, image, generated workload and probe bytes stayed fixed between points. The shared helper is `457a3f8d59cf6de54efb50cc7e1d8397ec8831f8`, instrument `cceaf978352a837e4c97317f9f92b2bfbeac3ea29a865c0b7989b19d10705367`. History accumulated; no re-priming, reset or tuning separated the points. Captures closed on November 15 UTC (November 14 Pacific).

| Offered scenario requests/s | Attempts / HTTP responses | Global HTTP failures | Dropped iterations | Accepted / stored / uncertain writes | Global p95, ms | Capture |
|---:|---:|---:|---:|---:|---:|---|
| 180 | 55,802 / 55,802 | 0 / 56,802 | UNMEASURED: not emitted | 15,219 / 15,219 / 0 | 1,018.769 | MEASURED |
| 240 | 73,576 / 73,576 | 13,431 / 74,576 | 827 | 14,914 / 14,914 / 5,187 | 5,090.333 | PARTIAL |

Global HTTP includes 1,000 serial JWT setup exchanges at each point. Scenario counters exclude them; transport-failure counters are zero. The combined ordinary-request percentile is UNMEASURED. Raw counter rates include setup time. At 240, accepted/stored equality does not classify the uncertain requests: the count oracle checks conservative bounds, while its exact-outcome control is `UNMEASURED / M7_DISCOVERY_COUNTS_MISSING`. The result remains PARTIAL. No capacity acceptance is granted.

Both points pass fresh-acquisition readiness, the separate sustained idle check and native load-work progression. At 180, evaluator completed-work delta is 5,693, with a minimum of five per tenant and no failed completions. At 240 those values are 6,833, one and zero. Native TIME delta is zero at both candidate points. Timer opportunity and strict deadline support remain UNMEASURED; a quiet idle result does not establish that timer work was exercised.

Both points prime 2,000 clients and report 2,000 connected at the end. Two separate probe writes produce four selected frames at each point; their maxima are 1,407 ms and 5,765 ms. Selected stored/output/BG-now witnesses pass for two tenants. The probes also retain one and two ping-timeout reasons, despite zero server-disconnect counters. These samples do not establish all-roster clinical equivalence, genuine cold-owner behavior, durable-output-revision-to-frame continuity, or drain/restart/ownership recovery. A separately bounded due-only timer case is the next evaluator criterion; it uses the existing opportunity assessor and clock brackets without new input during the case.

### Descriptive comparison with the retained baseline

The [earlier fixed-cohort curve](#fixed-cohort-request-rate-curve--reproduced) remains the baseline. At 180, global p95 rises from 709.555 to 1,018.769 ms and the four-frame maximum rises from 1,060 to 1,407 ms. There is no demonstrated latency gain. The generated probe, workload, completed-output oracle and progress observer bytes match exactly. The host and cohort match, but accumulated history, order, caches and shared-host CPU/IO remain confounders.

The original SQL classifier reproduces the retained baseline exactly before reuse. Integration independently reran the captured reduction and obtained the same comparison. Load bookends include setup, polling clients, probes and collection; SQL execution sums are neither PostgreSQL CPU nor wall time.

| 180 observation | Baseline | Joined candidate |
|---|---:|---:|
| PostgreSQL mean CPU, cores | 3.181 | 2.927 |
| API / evaluator / realtime mean CPU, cores | 0.984 / 0.395 / 0.234 | 1.009 / 0.498 / 0.270 |
| Captured SQL calls | 3,997,433 | 3,925,724 |
| Summed SQL execution, seconds | 583.562 | 484.322 |
| Epoch-proof execution, seconds | 382.922 | 258.710 |
| Lifecycle register/finish execution, seconds | 103.900 | 107.209 |
| Unclassified execution, seconds | 6.804 | 10.056 |

Bound retained role logs reproduce baseline pool results and provide candidate observations over sampled subwindows. API storage-pool mean wait falls from 1.035 to 0.705 ms; mean held time rises from 6.877 to 7.230 ms. Evaluator and realtime held time also rise. These observations support diagnosis, not a causal attribution or a reason to tune between sealed points. Cached-realtime and driver metrics retain their missing-instrument labels. Source-level epoch-proof reassessment is a separate NEXT capability; these captures remain unchanged.

At 240 both captures remain PARTIAL. Global p95 rises from 4,723.376 to 5,090.333 ms; HTTP failures fall from 14,610 to 13,431, while dropped iterations rise from 575 to 827 and uncertain writes from 4,047 to 5,187. The maximum of four selected frames falls from 85,941 to 5,765 ms; this small sample is not an all-write improvement. Captured SQL calls fall from 4,174,817 to 4,097,565, with summed execution from 621.172 to 553.831 seconds. The baseline records 16 native TIME completions and the candidate zero, with unmatched/unmeasured timer opportunity. This does not establish a candidate timer failure. Baseline API pool diagnostics retain their reproduced counter-reset UNMEASURED result. Integration independently reproduces the captured 240 comparison with the same original rules.

### Harness and evidence custody

A common immutable project/config/source binding replaces the failed copied namespace. Actual expanded Compose checks precede mutation; the journal distinguishes original and newly created container layouts and cleans exact recorded IDs. Wrong namespaces, receipts, source identities and null finite GOs refuse. Interruption, oneoff-container and PID-birth controls use injected effects; the two actual points then verify the adopted path. Independent audit caught a missing runtime receipt before launch; its failed boundary and corrected source-bound receipt remain retained. The 240 point restarts the actual nine stopped candidate IDs without recreation or relabeling.

Both executors and independent guards exit successfully. Separate host audits verify nine stopped workload containers, no live recorded process incarnation, all 48 protected fixture files unchanged, and the restored 3k project stopped. Durable state and failed captures remain retained. No application source campaign was repeated for these harness changes. The source is fixed on local branches, not merged to application `dev` or released.

Raw points are retained under `pgstream-1k-candidate-comparison-20261114/integration-shared/points/{180/attempt-02,240/attempt-01}`. Compact comparison records live under `pgstream-rate-analysis-20261114/`; raw logs, full per-tenant output and source-bound private inputs stay outside Git.

| Retained evidence identifier | SHA-256 |
|---|---|
| `points/180/attempt-02/root-final-summary.json` | `1653abdc7715855c1ec610bb3ef3e60f35ab19bcbc7eb9f251aa2ee946706069` |
| `points/180/attempt-02/root-final-absence.json` | `0cd971feec4ee6f7029ea4e2a7838ca6f402d599280254cc61d45ac780214ab5` |
| `points/240/attempt-01/root-final-summary.json` | `75a17b6adab266b41423430cd311582705c37c00cd384d412acd1efee6531375` |
| `points/240/attempt-01/root-final-absence.json` | `bb75943d6b15c3d1a6057e44a2b3947f2073b9a4a7d9072620feaf7b2530a05e` |
| `candidate7291-180-comparison/compact-comparison.json` | `965207146ffda3bfeb87d1de6c4304bdffe89ae74591ca2eb311246c43e72529` |
| `candidate7291-240-comparison/final-comparison.json` | `65c34f25120d2cd120dfc8ae89bf77c72fd56b07a04e17f5561595658a8227b4` |


## Minimum live fence and timer recipe continuation — 2026-11-15

The next application candidate removes the global epoch/suppression digests from warm operations. First and reconnected physical backends still perform structural and privilege admission. Current principal, tenant, lifecycle, restore generation, backend-loss and COMMIT fences remain required. An already-admitted backend does not promise next-transaction refusal of arbitrary trusted-administrator structural, policy or extra-grant edits; new or reconnected backends refuse incompatible state. This compatibility boundary is intentional. No latency or capacity gain has been measured for this candidate.

Full acceptance exposed stale test fixtures after that boundary changed. The first failure involved mocked constructor admission and cleanup; the next campaign passed its regular tiers but failed two native suite constructors. The local joined source `8aeefaefc88c79c3d548f7683d5651bec9cf5c01` includes test-only repairs for exact cold-reader control-table privileges and a callback variable. The focused native rerun passes 52 checks. Independent cleanup verifies both exact PostgreSQL containers, their anonymous volumes and reapers absent. Earlier failures remain retained. Full acceptance now passes on this unchanged source. The enabled native corpus reports 938 passing, two pending and zero failures. The pending cases are the legacy-only epoch-cost counter bridge and the end-to-end request benchmark; neither is counted as a minimum-path pass. Canonical image `sha256:382e44696c4415e710698ee6135c499ae2d480d9f39a2fb85c59675fdd8d2150` binds that source and deployment `df5362745a1b2d1b02b9186daedef3faccc14e58`. Network-isolated inspection verifies 1,178 source files, Node 24.22.1 and the pinned pgstream binary. A deliberate expected-hash mismatch exits 21; restoration passes. Final prcheck exits zero and ends `OK` on the same clean source. Its first invocation used the wrong tool home and ran no checks; both logs remain retained. Independent cleanup verifies captured native/outer/replica fixture identities, anonymous volumes and recorded actor incarnations absent. The matched rate comparison remains UNMEASURED.


| Unfiltered tier | Passing | Pending | Failure |
|---|---:|---:|---:|
| Unit | 4,518 | 1 | 0 |
| DOM | 205 | 0 | 0 |
| Dependency | 368 | 2 | 0 |
| Core | 319 | 0 | 0 |
| Harness | 101 | 0 | 0 |
| Integration | 3,645 | 934 | 0 |
| Stress | 18 | 0 | 0 |
| Browser | 686 | 0 | 0 |

The enabled corpus separately exercises optional integration suites with their required native backends and opt-ins. Tier pending counts are retained, not added to passing counts.

The separate timer recipe has not yet demonstrated a natural timer completion. The initial unchanged quiet fixture contained no known future opportunity. Subsequent setup attempts exposed registry-mode configuration and diagnostic-retention faults before any clinical write. A bounded authenticated settings GET now reproduces the remaining recipe mismatch: status and enable-list validation pass, `simplealarms` is absent and `errorcodes` is present. The application's actual recency rule accepts simplealarms, errorcodes or ar2. The recipe's narrower gate caused its refusal. That diagnostic makes one GET and zero setup or observation writes; independent checks verify the exact nine containers stopped, protected inputs unchanged and recorded actors absent. The corrected source-faithful recipe then ran once. Its single setup write was accepted, but the exact latest/stored-entry guard failed before any native settling round or observation. It made four bounded DATA requests, did not retry, and preserves the accepted write in the fixture history. Exact container/process cleanup and protected-input checks pass. Independent reduction of the retained responses finds only the ID differs: the requested ID is not 24 hexadecimal characters, the stored ID is, and date/value/device match. Actual API normalization is under focused source qualification; native due reason, future margin, pending clearance and unchanged observation inputs remain required before claiming the timer criterion.

Remote preparation separately reproduces npm's duplicate-config-path failure. Distinct immutable user/global configuration files pass the actual locked install command under the intended unprivileged identity, with unchanged package lock and configuration bytes; this qualifies the installation delta, not the complete remote account/application worker. The subsequent finite remote attempt completed local bundle preparation but transferred no source/image payload and ran no application workload while explicit export approval was pending. Its exact paid resources, temporary keys and guard are independently verified absent. Remote throughput remains UNMEASURED and capacity is not granted.

The fixed two-worker partition and notification transaction fences continue in their own source lane. A catalogue diagnostic reproduces the expected-body delimiter mismatch. One queued point was withdrawn before effects when its declared timeout profile differed from the actual library. A fresh frozen-source component point now passes with four actual physical clients: two shared effect transactions block exclusive membership replacement through their COMMIT/rollback boundaries; stale incarnation, foreign backend, autocommit and expired-incarnation resurrection refuse. Removing the actual old-writer trigger or shared lock makes the respective mandatory control red; restoration passes. Exact container, nonce namespace and recorded runner/reaper absence are independently verified. This is membership/effect protocol proof, not assigned checkpoint SQL, notification, restore or complete two-worker clinical/realtime qualification. Per-process capacity instruments have focused/self-process proof only; actual whole-server PostgreSQL visibility and real driver/edge headroom remain UNMEASURED. No 10,000-tenant acceptance follows from these preparatory results.

Raw evidence remains outside Git under the retained workspace artifact root. These records identify the exact captures; no earlier capture was rewritten.

| Retained evidence identifier | SHA-256 |
|---|---|
| `lifecycle-minimum-joined-20261115/native-fixture-repair-01/native-01/root-final-absence.json` | `c2e9da6acee32be7b6d8359da18a9af8a4ee65ef98c359988327218739cdc32f` |
| `evrt-due-only-20261114/settings-get-diagnostic-v2/runner-v5/points/settings-get/attempt-01/root-final-absence.json` | `ed6b483e415d29b225470d595980ce907c9645768e58fa5ef081f05bd4c71e38` |
| `remote-client-config-20261115/receipt.json` | `568fca0ccc941773892384f647be8362ccaa74e1c758890a6b155e3672989b2b` |
| `remote-npm-fixed-20261115-run01/attempt-final.json` | `ca1ee57f23ccc84016fb5bec868e37082f6d7766611422bb4d6d3886d763d747` |

| Additional retained evidence identifier | SHA-256 |
|---|---|
| `lifecycle-minimum-joined-20261115/acceptance-03/results.json` | `ffedf936f2adf17805291ea0168a5a4cb94904528757b3871da4d34e5544a263` |
| `lifecycle-minimum-joined-20261115/acceptance-03/root-final-absence.json` | `4f3371efc4970008a07af05001211cced9ab42f5976b2a1448b593244bd7fc97` |
| `lifecycle-minimum-joined-20261115/build-01/build-receipt.json` | `9519b13232dcf935997158e25fad02d84981ba026a6f398932991d92989cb656` |
| `lifecycle-minimum-joined-20261115/final-prcheck-02.json` | `8b9d3d4a6ce0074b94123dab64c9badd3a70844a6420d6af2dd493e78c18d23e` |
| `pgstream-evaluator-partition-20261114/native-b-frozen-001b581c8402/results.json` | `2c65497ab96778f833350022904e76ed706cd57cba1aa2460980204e0af91d8b` |
| `pgstream-evaluator-partition-20261114/native-b-frozen-001b581c8402/root-final-absence.json` | `35cd89e871a27795a5f103ca868e5e44c5c1f659560004293162282f22b958e7` |
| `evrt-due-only-20261114/clinical-recency-or-v1/runner-v6/points/due-only/attempt-01/prewindow-setup.json` | `20717812923bd88c773f863fe6a50ba459aaefddd18b2e8cb5c3bfadeb52276e` |
| `evrt-due-only-20261114/clinical-recency-or-v1/runner-v6/points/due-only/attempt-01/root-final-absence.json` | `0869abc3aba3e3d05660bf2965b30248df67b60c23dd08fe87edacfe9fa792db` |


## Minimum-fence fixed-cohort observations — reproduced

The qualified minimum-fence source and image above completed unchanged 180 and 240 offered scenario requests/s on the preserved 1,000-tenant fixture with 2,000 polling clients. Parent source `7291af9b9cc48dbe58c488e892e7b34cf367c88e` and minimum source `8aeefaefc88c79c3d548f7683d5651bec9cf5c01` share deployment `df5362745a1b2d1b02b9186daedef3faccc14e58`, helper `457a3f8d59cf6de54efb50cc7e1d8397ec8831f8` and instrument `cceaf978352a837e4c97317f9f92b2bfbeac3ea29a865c0b7989b19d10705367`. Every application role was upgraded explicitly to the qualified image before 180; 240 resumed those exact stopped IDs. Generated probe, workload, completed-output oracle and progress observer bytes match the parent. No re-prime, reset or tuning separated the new points. The database history includes the retained clinical setup writes below.

At 180, global HTTP p95 and PostgreSQL CPU are lower. At 240, failures and uncertain writes decrease, while p95 remains about five seconds and the result remains PARTIAL. These captures are descriptive: accumulating history, run order, caches and shared-host CPU/IO prevent causal attribution or a capacity ceiling. No operator-visible change, push, application-dev merge or release follows from this verification update.

| Source and offered rate | Global HTTP failures / requests | Dropped iterations | Accepted = stored writes | Uncertain writes | Global p95, ms | Capture |
|---|---:|---:|---:|---:|---:|---|
| Parent, 180 | 0 / 56,802 | Not emitted | 15,219 | 0 | 1,018.769 | MEASURED |
| Minimum, 180 | 0 / 56,802 | Not emitted | 15,219 | 0 | 339.638 | MEASURED |
| Parent, 240 | 13,431 / 74,576 | 827 | 14,914 | 5,187 | 5,090.333 | PARTIAL |
| Minimum, 240 | 5,525 / 74,601 | 802 | 18,064 | 2,038 | 5,054.976 | PARTIAL |

Global HTTP includes 1,000 serial JWT setup exchanges at each point. Minimum scenario attempts/responses are 55,802/55,802 and 73,601/73,601, with zero transport failures. A combined ordinary-request percentile remains UNMEASURED; no percentile averaging or subtraction is used. An absent dropped-iteration metric is not zero. At 240, accepted/stored equality leaves uncertain outcomes unresolved: `oracleControl` remains `UNMEASURED / M7_DISCOVERY_COUNTS_MISSING`, and capacity remains NOT_GRANTED.

| Per-shape p95, ms | Parent 180 | Minimum 180 | Parent 240 | Minimum 240 |
|---|---:|---:|---:|---:|
| Read device status | 1,003.966 | 329.195 | 5,069.766 | 5,040.765 |
| Read SGV | 999.104 | 319.940 | 5,059.224 | 5,037.295 |
| Read status | 1,083.007 | 389.245 | 5,163.927 | 5,125.795 |
| Read treatments | 1,008.412 | 327.841 | 5,063.703 | 5,042.509 |
| Write device status | 1,047.405 | 369.501 | 5,073.044 | 5,054.533 |
| Write SGV | 1,039.142 | 347.464 | 5,075.173 | 5,049.405 |
| Write v3 treatments | 1,059.935 | 376.935 | 5,105.840 | 5,074.192 |

### Work and storage cost

The original SQL classifier exactly reproduces both retained parent classifications before processing the minimum source. Deliberately changing a parent call total makes the mandatory equality check red; restoring it passes. No classifier rule changed. The large remaining authority category maps mainly to the live current-transaction fence. Aggregate statement records do not identify backend births or admission transitions; backend-level exactly-once structural frequency remains UNMEASURED.

| Load-bookend observation | Parent 180 | Minimum 180 | Parent 240 | Minimum 240 |
|---|---:|---:|---:|---:|
| PostgreSQL mean CPU, cores | 2.927 | 1.920 | 3.159 | 2.428 |
| API mean CPU, cores | 1.009 | 0.935 | 1.067 | 1.082 |
| Evaluator mean CPU, cores | 0.498 | 0.510 | 0.612 | 0.727 |
| Realtime mean CPU, cores | 0.270 | 0.275 | 0.307 | 0.341 |
| Tracked SQL calls | 3,925,724 | 4,043,510 | 4,097,565 | 4,589,453 |
| Summed SQL execution, seconds | 484.322 | 251.197 | 553.831 | 302.571 |
| Epoch-proof calls | 386,871 | 0 | 394,433 | 0 |
| Captured SQL rows | 3,522,916 | 4,028,544 | 4,014,301 | 5,064,463 |
| Captured WAL bytes | 337,457,772 | 431,828,658 | 402,162,761 | 573,456,471 |

Total calls, rows and WAL increase. At 180, clinical-document query execution also increases from 13.015 to 31.481 seconds despite equal query-call counts. The cause of those storage-cost differences is UNMEASURED. Load bookends include setup, polling viewers, probes, control and collection; they are not exclusive scheduled-traffic cost. Summed SQL execution is neither CPU nor wall time. Wire bytes and round trips remain `NO-INSTRUMENT`.

### Progress, selected clients and cleanup

Both new points pass fresh-acquisition readiness, sustained idle and native load-work progression. Completed-work deltas are 5,472 and 7,807; the per-tenant minima are five and three, with zero failed completions. TIME delta is zero in these load windows; unmatched opportunity is not interpreted as timer failure. At each point, 2,000 clients remain connected at the end, two probe writes yield four selected frames, and two stored/output/client witnesses pass. Selected frame maxima are 1,176 and 5,951 ms; parent maxima are 1,407 and 5,765 ms. This is not all-write latency, true-cold behavior or durable-output-revision-to-frame proof.

Separate driver observations retain same-process identities and sampled FD/memory maxima. Interface-bound/NIC and delegated headroom metrics remain missing; new pool-log attribution is UNMEASURED. The overload result is retained with those limits. Executors and finite guards exit zero. Independent checks verify nine exact stopped runtime containers, retired IDs absent, all 48 protected files unchanged and recorded process incarnations absent after each point. All native-test labelled fixture namespaces are absent. Durable state and raw captures remain retained.

### Separate natural timer and future capacity instrumentation

The supported-ID clinical case on parent source `7291af9b9cc48dbe58c488e892e7b34cf367c88e`, the same deployment and the [qualified parent image](#joined-completion-candidate-acceptance-and-image--reproduced) passes. Actual API planning preserves the attempt-derived 24-hex storage ID; the runtime exact stored-field guard then passes. One normal setup write precedes new observation input bookends. Native state selects the expected future recency due instant, and the unchanged 900-second collector records one successful TIME credit, pending-work clearance and unchanged durable/RAM input. Root re-reduction gives the same result; exact containers, protected inputs and guard/stage/sampler absence are verified. This closes one selected-tenant no-write timer criterion on that source. It gives no executor duration, cold-owner, frame-revision, recovery or capacity claim, and does not retroactively qualify earlier failed attempts.

A separate source-only capacity adoption records exact minimum source 8ae in the directed manifest on deployment branch `codex/capacity-minimum-source-20261115`, head `5d3b3134db82d5e4056df6d7f658637b97626cf0`. Only that literal record and the required Compose tree identity change. Existing directed checks pass, with absent-record and wrong-pin red/restored controls; root independently passes the 15 focused checks. The read-derived constructor inventory remains 111 requested pooled maxima. This is a future instrument source record; the measured curve keeps the deployment named above. Actual full-server PostgreSQL visibility, driver/edge headroom, partitioned topology and 3k/10k application capacity remain UNMEASURED. Integration owns the next native qualification and source-adoption boundary.

| Retained evidence identifier | SHA-256 |
|---|---|
| `pgstream-minimum-matched-20261115/analysis-01/compact-comparison.json` | `dc9ef06e03af8d91a4ffc3a57d5418982707089296c228baa6c5b45e8142637b` |
| `pgstream-minimum-matched-20261115/analysis-01/full-comparison.json` | `296ae361e7490885e21ed134aea781f06d33e0bc636b496435b1b6bb8559fb10` |
| `pgstream-minimum-matched-20261115/analysis-01/receipt.json` | `1900e211ced46e1057000c455aff3d397d3f6fcd103e9748749fec602ca6195d` |
| `pgstream-minimum-matched-20261115/points/180/attempt-01/root-final-absence.json` | `e04dae38357bd3054db7d9cbdf68a7d27125d8ac935b15661c5a217a8ff19176` |
| `pgstream-minimum-matched-20261115/points/240/attempt-01/root-final-absence.json` | `105be8f218c28830214a072aeaeebac3bb5794e34bb9723d9c62f859ce74c542` |
| `evrt-due-only-20261114/clinical-recency-id-v1/runner-v7/points/due-only/attempt-01/attachment-due-only-01/summary.json` | `c98691a5bf443f3ad5cd79523c64db6bb00b36a0e31aee73f7ddc4745ccbbb1f` |
| `evrt-due-only-20261114/clinical-recency-id-v1/runner-v7/points/due-only/attempt-01/root-final-absence.json` | `f6d6079d6fab08a34cde5a255d15d57350e9779985ad8491489ff75d44eea70b` |
| `capacity-minimum-8ae-audit-20261115/adoption-receipt.json` | `8b56f09e9fd7594ec182c84c17544e4918b44297b6c6cb015a24be67512c595b` |
| `minimum-warm-sql-audit-20261115/receipt.json` | `87a79b292c419c03b35990286a1cfe3e09f9c60c050bd4808597faaf218df88d` |


## Notification component first native failure — reproduced, 2026-11-15

The owned source-adoption branch at `cceee9ccdd5785e543f6101abbf498284c261ce6` fixes foreign-slice preparation and route/store consumer binding. Its optional static namespace contract derives the notification catalogue and forwards it to ACK admission. The affected database-free checks report 105 passing with forwarding and binding controls red then restored. Root independently reproduces the held native runner's 16 pure guard controls. These source checks do not qualify the notification topology.

The first native component exits PARTIAL during synthetic assignment seeding with PostgreSQL `42703`, before selected owner transactions or ACK checks. Actual runtime is Node 24.22.1, pg 8.23.1 and PostgreSQL 16.15. The raw administrator's observed statement/lock timeouts are 3 seconds/500 milliseconds; pooled profiles remain UNMEASURED. The fixture installs the full pool mutation catalogue, which replaces `expected_members` with `applied_members`, but its seed names both fields. That precise column diagnosis is read-derived because the native capture retains the error code without its column text. No production defect or protocol pass follows.

Runner and guardian cleanup both report `ERR_ASSERTION` and do not verify absence. The initial physical PostgreSQL record was captured during startup with UID zero; later UID and command digest were not retained. A startup identity transition is a read-derived hypothesis, not the reproduced assertion cause. Root independently validates the exact container ID, name, nonce, image and PostgreSQL PID birth, then removes only that fixture. Exact container/name, backend, runner, guardian and nonce namespace absence pass before the original absolute deadline; no volumes were recorded. Original failed cleanup and absence captures remain unchanged. Root's initial independent absence parser also rejected Docker's lowercase error prefix; a strict case-insensitive exact-target check then verifies absence. A new source-only fixture revision must correct seeding and capture stable physical identity after readiness before another finite GO. Full notification, restore and two-worker topology qualification remain OPEN.

Retained evidence identifier: `notification-partition-native-20261115`, outside Git under the workspace artifact store.

| Capture | SHA-256 |
|---|---|
| `results.json` | `2f742caa4ec17fa71e662b31a78520fcb97731c1a8a6b22f26ab0c34d4d81066` |
| `cleanup.json` | `2435fe465497c5e39a56b7826159c193583d0db4f417e606ecc6260049a9cc3e` |
| `root-fallback-cleanup.json` | `29133b3e57d34ad10a7c1716e3ed2e30ca109332eb70fb1ad88ec331dd3a8abd` |
| `root-final-absence-02.json` | `3660ea321aa31c12c83ee45390771da54dcde5f8f103ffd5372f84bcef921cb9` |


## Notification native progress and coherent source join — 2026-11-15

The second finite component uses a fresh nonce and corrects only fixture seeding, stable post-readiness identity capture and bounded diagnostics. Root independently reproduces 22 pure controls, including the old seed's mandatory failure. Both actual selected notification stores then complete five fresh transactions each on their held backends: consume, begin, confirmed dispatch, fresh pre-send and finish preserve request identity. The native census is six clients including the administrator. Both held and distinct read-only pool slots observe 3-second statement timeout and zero lock timeout; raw clients observe 3 seconds/500 milliseconds. These are reproduced component observations, not network adapter or topology proof.

The run remains PARTIAL. It reaches the wrong-backend discriminator after foreign-tenant/consumer, ambient-transaction, stale-incarnation and assignment controls, then reports an error at runner line 167. The frozen module exports `open`, but the fixture calls private `create`; that exact API mismatch is read-derived from the retained frame and source. No production export or authority is changed. Runner and guardian now close cleanly without root fallback; independent exact container/name, backend, runner, guardian and nonce namespace absence pass, with no volumes. Original executed captures remain unchanged. A new fixture must use the real public protocol-admission API before continuing the remaining SQL/ACK controls.

The complete notification ancestry is separately joined with qualified minimum `8aeefaefc88c79c3d548f7683d5651bec9cf5c01`. Merge `3e4a51856c2ee0a7838ea368e5b42e4d6de286e1` has that source and `cceee9ccdd5785e543f6101abbf498284c261ce6` as its exact parents. Clean local head `330354ed6b98160c1aa56c8884b9e3cac7ca790d` adds only test-harness normalization and registration. Eight new tests imported Node's test declarations while the repository runs Mocha; their declarations now use Mocha globals, with assertions and bodies unchanged. All eleven new tests are registered in the database-free unit tier. The inventory passes for 775 files/eight tiers; 235 affected checks pass. Removing a registration fails inventory; injecting an assertion into a normalized test makes Mocha report a failure and exit nonzero; restoration passes. The native inventory is unchanged and was listed only. No full/browser/native campaign, image, prcheck or runtime activation has run on this join. Root owns actual runtime wiring and the next coherent qualification boundary.

| Retained evidence identifier | SHA-256 |
|---|---|
| `notification-partition-native-02-20261115/results.json` | `aeb5ac34a6c85f6f49d87ecbe936f6aaaa9e1e38f254a491d370c116813e4e90` |
| `notification-partition-native-02-20261115/cleanup.json` | `2443e43f08445550b6bb128f239756f70f1cd67a2d2d014e7e612af8f48b7fd6` |
| `notification-partition-native-02-20261115/root-final-absence.json` | `c9b8d3c7c1870190d0ffd1930a4ff0dc278c761dea6d96675d177874ba88592a` |
| `notification-partition-joined-20261115/source-stop-receipt.json` | `460c51a85af88761db9c4e2c2caa2f319afe97390c56aa941fe46a4173a1a67a` |


## Notification SQL and ACK component — reproduced, 2026-11-15

Fresh native03, bound to frozen application `cceee9ccdd5785e543f6101abbf498284c261ce6`, passes in 14,119 milliseconds with exit zero. Its fixture uses the real public effect-fence admission API; production source and authority are unchanged. Root independently reproduces all 28 pure preparation controls before GO. The finite native component then qualifies these specific criteria:

| Criterion | Reproduced result |
|---|---|
| Actual selected owners | Both ordinals retain their physical backend and complete five fresh transactions each; request identity survives consume/begin/confirmed dispatch/pre-send/finish. The adapter is a controlled counter, with no network. |
| Admission and authority | Foreign tenant, consumer/request ID, ambient transaction, stale incarnation, changed assignment and wrong physical backend refuse. Missing metadata privileges refuse separately; exact grants restore. |
| Three outbox tables | Missing context, foreign ordinal/backend, stale incarnation and missing physical resource refuse with all three snapshots unchanged. Intended-role positive UPDATE distinguishes fence refusal from insufficient authority. |
| Deferred COMMIT fence | Each real UPDATE passes its BEFORE trigger and completes a 1.25-second delay after a 1-second lease; COMMIT then refuses with `55000`. Removing only the deferred trigger permits a changed-row commit and makes the mandatory refusal oracle red. Exact catalogue/data restoration restores refusal. |
| Old-writer control | Removing both effect/COMMIT triggers permits a changed-row commit on every table and makes the original oracle red. Restoration reestablishes refusal. |
| Generation and backend loss | A synthetic committed generation change in the actual lifecycle catalogue refuses at deferred COMMIT. Terminating the real held backend after its state UPDATE rolls back all three tables, fires owner loss and refuses later admission. |
| Independent ACK admission | Both worker pools and raw probe close; membership rows are removed. Static catalogue admission succeeds with two clients including admin, zero worker metadata queries and 22 ACK statements. The ACK role's deliberate membership read gets `42501`; missing/wrong ledgers refuse, and exact restoration passes. |

Observed SQL client maximum is six including admin. Actual held, distinct read-only and ACK slots observe 3-second statement timeout/zero lock timeout; raw slots observe 3 seconds/500 milliseconds. PostgreSQL is pinned 16.15 with max9/reserved3/other0. The PostgreSQL container has a one-CPU quota, a 1 GiB memory limit and no volumes. The two host Node processes each have a 128 MiB heap ceiling; their RSS and aggregate fixture CPU/memory are UNMEASURED. Runner and guardian verify exact cleanup, and root independently verifies exact container/name, physical backend, runner, guardian and nonce namespace absence before the original absolute deadline. Earlier failed points remain unchanged.

This closes the SQL/ACK component only. Seeded assignment outputs are not clinical evaluation. The generation mutation is not canonical lifetime/restore choreography; no two-process topology, actual intake, HTTP/socket credentials, provider, buffered wire cancellation or genuinely ambiguous network COMMIT is qualified. Runtime `lib` and migration trees are byte-identical between captured `cceee` and joined `330354ed6b98160c1aa56c8884b9e3cac7ca790d`; the capture retains its original source attribution and does not become a full joined-source acceptance result. Runtime wiring and its intake-health/schema-recovery contract remain the next root-owned integration boundary. No workload or paid resource remains active.

A separate read-derived source audit on the clean join finds that sole SQL intake authority is still absent. `lib/pgstream/typed-checkpoint.js:31` sends observations through ordinary pooled transactions without selected intake ownership. `lib/server/serve/evaluator-readiness.js:24` and its privilege checks require shared observation/completion UPDATE authority. Selecting ordinal zero in application code cannot supply the missing SQL capability. A proposed source design must separate intake ownership, narrow observation rights and readiness while preserving worker TIME progress and all assignment/lifecycle fences. No native intake packet is authorized by the notification result.

| Retained evidence identifier | SHA-256 |
|---|---|
| `notification-partition-native-03-20261115/results.json` | `43fb696aa7a85c7ef05d3b671beb44fb96e144046a82b444baeeb854e67d0ebb` |
| `notification-partition-native-03-20261115/cleanup.json` | `f5a38f5e7070fb71ff080cd955c54665f38fd6e0879e24325c8055b5f7bdf81e` |
| `notification-partition-native-03-20261115/root-final-absence.json` | `5116f2b9009f9c6dbeb59eb6b88b4f6cee010a714aa231e6e87aaf4a14d12850` |


## Proposed intake health contract — source checks, 2026-11-15

Clean local source `381d59134a84b558545572d31194a67339e19791` proposes default-off intake-state publication and a worker admission gate. The existing cohort supplies its actual participant/incarnation; the client bootstraps and pins the existing branded peer's lifecycle status, schema and datastore. One private control operation reports state and committed-heartbeat receipt age. Existing transport trust remains required; contract headers do not authenticate callers. Ready admission expires within the stricter explicit source/local stall bound, less retained receipt age and the full local monotonic request duration. Inspecting state does not renew a receipt or create a freshness default.

Independent source review reproduces three gaps in prior candidate `24f2f621fe9ce7865dc6bedc17c38d8094ee3756`: a longer worker bound can outlive the intake bound, temporary binding loss can clear the publisher's terminal state, and an expired terminal response can escape the worker's terminal latch. The repair carries the source bound and preserves terminal state across binding loss and expired/null-age responses. A separate counterexample on interim repair `d9af60d0c1857057f933eb032b8b86520837fdb2` also establishes fixed participant immutability. Only a validated new incarnation of that same participant can reset nonclosed terminal state; closed publishers never reopen. Each counterexample is retained RED before its fix, then passes after restoration. Targeted independent recheck passes on the final head.

The affected 17-file unit selection reports 231 passing; the separate same-process run also reports 231 and is not added to that count. Tier inventory passes for 776 files/eight tiers; the native inventory is listed only and remains unchanged. Default callback/health/boot shapes, routing isolation, local database fences and partition activation refusals retain focused coverage. Earlier recording-model and exact inventory/mutation-anchor failures remain retained; their fixture repairs do not replace the later semantic counterexamples. Source checks qualify the proposed interface only. Actual transport timing, refresh cadence, resource cost, clinical/restore behavior and full two-worker wiring remain UNMEASURED. No full/browser/native campaign, image, prcheck or activation ran on this candidate.

Retained evidence `intake-state-sync-20261115/source-bound-repair-01/source-stop-receipt.json`, SHA-256 `27dce01f5db5094aff7efbed5bfc5fcca8320ddb01c447b4f3e75db898331757`; prior candidate evidence remains unchanged.

## Native PostgreSQL observer qualification — reproduced, 2026-11-15

The existing collector does not qualify its database reader or require foreign-role/WAL-sender presence by itself. A new isolated caller wrapper therefore checks actual reader privileges, independent administrator census, foreign-role visibility, a real WAL-sender backend and an independently captured server epoch before crediting a sample. The frozen collector at alignment instrument `cc295ffd80bddd0e418c234fdf43f0d9a52b4975` remains unchanged. A bounded stdio bridge sends its one fixed SQL request through the already-owned reader; the Python process is a fixture observer, not a qualified load driver.

The first finite point stops during physical replication authentication with `28000`, before any collector sample. Its exact historical reason was not retained. A fresh diagnostic point reproduces a missing physical-replication HBA rule for its exact synthetic role/client. Only after that predicate passes, one role/address-specific SCRAM rule is appended in the owned fixture and independently checked after reload. Actual replication-protocol `IDENTIFY_SYSTEM` then matches the administrator's control-system identity. No slot or WAL-throughput proof follows.

The second point exits zero and passes all eleven native sample cases. Qualified samples observe four physical sessions including the administrator/observer: three ordinary client backends and one real WAL sender. Revoking statistics membership or control-system-function execution refuses caller qualification; the latter reproduces `42501`. The optional collector result being unavailable is an inference from its unchanged code path, because refusal records do not serialize that result. Closing the foreign client or WAL sender refuses the exact census; reopening restores qualification. An intentionally wrong independent epoch makes the existing collector hard-refuse; the true epoch restores success. The wrapper, rather than the optional collector alone, owns the non-epoch qualification refusals. Grant and actor negatives reach the first privilege or exact-census guard. Individual visibility/raw-count guards have separate source controls; they are not isolated native negative cases.

The run executes 64 bounded SQL queries and eleven one-exchange Python children. The PostgreSQL container is limited to one CPU/1 GiB, with no persistent mounts; host Node heap limits and unmeasured host/Python RSS remain separate. Runner/guardian cleanup passes. Root independently verifies exact container/name, physical PostgreSQL backend, runner, guardian, every recorded Python child and nonce namespace absent before the original deadline. Both points and their source/cleanup captures remain unchanged. Caller-wrapper integration into future orchestration, driver/edge headroom, application load, 10,000-tenant scaling and capacity acceptance remain OPEN.

| Retained evidence identifier | SHA-256 |
|---|---|
| `capacity-pg-visibility-native-01-20261115/failure.json` | `30d8e0ac9f6713c2c2a820327582855dbdf840caa202254aa8b3d002f830ef8e` |
| `capacity-pg-visibility-native-01-20261115/root-final-absence.json` | `d81ecf01485f85357f649665f05a1ea729249e767405bd71be21d66995985565` |
| `capacity-pg-visibility-native-02-20261115/observations.json` | `381b248fcf3ce967db85d25def69955da9c4d574c75f53f327cda1e77b6a5f82` |
| `capacity-pg-visibility-native-02-20261115/first-wal-auth.json` | `1e6f9d5cca6272a4deb345eeb7a5cb223b118d253148ee73f7d050783f489bac` |
| `capacity-pg-visibility-native-02-20261115/hba-rule-verification.json` | `700947ff926ec7532d8eee52268b1117a3bb43dd1ec3726f291e8a63fbbead49` |
| `capacity-pg-visibility-native-02-20261115/root-final-absence.json` | `5b209ce02e98b01705d63eba6d5094bb7a63583c42edcef1f1dc093f5da53453` |


## Worker SQL component — partial native evidence, 2026-11-15

Worker-only source is fixed on local branch head `b024f2fa3bd3f3ee940a2f16fe22e0e81fa51511`; it is not merged or released. The candidate narrows selected-worker column rights and roster policies, fences shared pending/delivery mutations and rejects NULL membership in each cohort predicate. The first executed point (`checkpoint-worker-native-02-20261115`) stops during catalogue installation with `42601`. The retained statement shows an unparenthesized CASE in a PL/pgSQL IF expression. A minimal two-expression parentheses repair preserves the predicate and is verified by the next actual installation.

**Reproduced:** native03 installs and admits the candidate. Both actual selected worker owners complete three fresh transactions: completion, delivery acknowledgment and a due-only TIME completion without new input. Revision and generation values above JavaScript's exact integer range retain their decimal precision. The observed maximum is seven physical clients including administrator, lifetime, both two-slot worker pools and one raw probe. Actual private lifetime/backend markers and timeout profiles pass. A pinned predecessor catalogue permits an otherwise unfenced shared pending/delivery mutation, establishing the SQL gap in that programme prototype. This does not establish a defect on the shipping release.

The point remains PARTIAL at the foreign-tenant negative oracle. The old fixture enters tenant A's ambient scope before asking its store to complete tenant B; source-only confirmation reaches the existing tenant-rebinding guard before the intended partition refusal. The actual native exception was not retained, so that exact historical reason stays read-derived. The corrected fixture must enter otherwise-valid scope B, execute once, record a bounded safe error before asserting the exact partition refusal, and retain unchanged rows. Remaining raw-role, deferred/NULL membership, backend-loss and outbox criteria are UNMEASURED on this worker candidate. Both executed points close with independent exact absence before their deadlines. No worker activation or comprehensive acceptance follows.

| Retained evidence identifier | SHA-256 |
|---|---|
| `checkpoint-worker-native-02-20261115/results.json` | `8cb78b0d322ee97f955c0b90bb6bdd4546674c39e924fffb804ae6ca238acf3a` |
| `checkpoint-worker-native-02-20261115/root-final-absence.json` | `ecfec8f444f83d8c3c858e97783a076e521778235b3be74febedab470a379912` |
| `checkpoint-worker-native-03-20261115/results.json` | `eb239b55d3e6bd7637b54e4564a43fc864b2181dd805904f86ec51df21ee52ed` |
| `checkpoint-worker-native-03-20261115/root-final-absence.json` | `b361af819a9f287dba4eb313bb46f82211a5e971f0fddab2d109724e5db6fd3f` |

## Suspended intake ordering — reproduced component comparison, 2026-11-15

On unchanged joined source `330354ed6b98160c1aa56c8884b9e3cac7ca790d`, a bounded PostgreSQL fixture compares the actual public receiver/typed observation path with the same observation wrapped only in the real operation window. Both use the existing consumer-bound metadata grants, real global owner and separate lifetime role. A controlled serial caller stops at its first rejected promise. This characterizes ordering pressure; it does not run the upstream pgstream retry implementation.

The earlier native02 point stops before any ordering trace with `23514 tenant_restore_window_digest`: its synthetic suspension omitted the catalogue's required artifact digest. Native03 retains and hashes a bounded research descriptor before binding that digest, and clears it at synthetic resume. The marker is not a canonical tenant artifact, restore authority or stop proof. No catalogue constraint or grant is weakened.

**Reproduced:** all four native03 traces complete. The default path commits both tenants' receipts during suspension in either order. The proposed window wrapper refuses suspended A: A→B leaves B unattempted; B→A commits B before refusing A. Replaying the entire original sequence after the explicitly synthetic generation-incrementing resume succeeds. Exact acknowledged rows, completion/output/ACK fields and eligibility remain unchanged; pending receipts are durable. Each case observes four physical clients including administrator, held owner, ordinary observation/read and lifetime. PostgreSQL has one CPU/1 GiB limits; host Node heap limits and unmeasured aggregate RSS remain separate. Independent exact cleanup passes before the fixed deadline.

A separate read-derived audit finds that canonical maintenance increments generation at suspension and activates that same generation. The current receiver maps suspension to `2g+1` and activation to `2g`; typed observation ignores nonincreasing tokens before updating eligibility. This differs from the comparison's synthetic resume. Its dedicated native01 diagnostic stops before PostgreSQL starts because the created fixture label differs from the guard intent. Automatic cleanup fails closed; root independently validates the exact never-started container and removes it, then verifies container/name, runner, guardian and nonce absence before deadline. The semantic fault therefore remains UNMEASURED natively. A corrected packet needs a control over the actual create label before a fresh GO. No lifecycle encoding change, intake authority, canonical restore, clinical continuity or full topology is adopted.

| Retained evidence identifier | SHA-256 |
|---|---|
| `intake-lifecycle-ordering-02-20261115/results.json` | `525ebb3fe37833700b939dbc3b3dbe8671cd9ea175419819abb98c6220ca80a7` |
| `intake-lifecycle-ordering-03-20261115/results.json` | `871dad67bddc287aec05b0ed111bc3565ea3b3f9c523e239560c42776d37fd29` |
| `intake-lifecycle-ordering-03-20261115/root-final-absence.json` | `c9e44fda2d75388ca77d5258ec563503ff70ec9bfee6f243ed4ff6a9476de7b9` |
| `lifecycle-eligibility-ordering-01-20261115/results.json` | `c78a83909ff558fd56a9ee2dc21ed5f3cca869dd8975bfc6e443e9a46a70cc8c` |
| `lifecycle-eligibility-ordering-01-20261115/root-final-absence.json` | `41c365d4379fe62240a871e0f0794b669775bac384cce2c633d59f577ad35c6c` |


## Worker SQL criterion and default-off source join — 2026-11-15

**Reproduced:** corrected native04 exits zero with `FIRST_COMPONENT_PASS_NOT_TOPOLOGY` on original worker source `b024f2fa3bd3f3ee940a2f16fe22e0e81fa51511`. The foreign-tenant test now supplies an otherwise-valid target scope and reaches the exact partition refusal. Each unchanged-row negative action executes once; its bounded original rejection is retained before the oracle runs. This closes the earlier fixture mismatch without changing production source.

The point completes both selected owners' completion/ACK/TIME transactions, raw-context and immutable-input refusals, a successful write followed by deferred lease-expiry COMMIT refusal, trigger disablement RED/exact restoration, actual post-write backend-loss rollback and principal-scoped row policies. The restrictive-policy ablation exposes the forbidden foreign-row mutation; restoration refuses it again. Self-NULL and peer-NULL membership each refuse with the exact lease SQL error. Replacing the function with the pinned predecessor allows a changed-row commit and makes the mandatory oracle RED; exact data, function and membership restoration reestablish refusal. The same NULL discriminator closes for every notification table and both membership positions. JavaScript admission refusals are checked separately from raw SQL.

Observed phase censuses are seven clients for the worker phase and five for the later outbox phase, including the administrator and the same lifetime lane. Worker pools and probe close before outbox admission. Captured physical timeout profiles, fixed resource limits and independent exact cleanup pass. These are sampled censuses, not continuous resource peaks. The point does not run clinical algorithms, actual pgstream/two-process topology, HTTP/provider/wire behavior, canonical restore or a genuinely ambiguous network COMMIT. Sole intake authority remains OPEN.

Root assembles a separate clean default-off source join at `cf8e8795ac0b6b72ed66b981152d06ad9a624c95`, with exact parents worker `b024f2fa3bd3f3ee940a2f16fe22e0e81fa51511` and health `381d59134a84b558545572d31194a67339e19791`. Their changed paths do not overlap. Nineteen focused unit files pass 250 tests; the inventory passes for 776 files/eight tiers. Original trees and native attribution remain unchanged. The join creates neither sole-intake SQL authority nor health-to-worker runtime composition. No full/browser/native campaign, image, final prcheck or activation ran on the join.

| Retained evidence identifier | SHA-256 |
|---|---|
| `checkpoint-worker-native-04-20261115/results.json` | `957e03daafd6d235e2f7327c41cd43bfec76c3876e5bdf69bc13e32e0a68cc8b` |
| `checkpoint-worker-native-04-20261115/cleanup.json` | `ebae1b149aba1bcc563f6d24f97ce92234abc3499caad879bd579226502bc0ea` |
| `checkpoint-worker-native-04-20261115/root-final-absence.json` | `ad58d0250a3f67cbe576bbd02e01636e644078b7c3e8937f546be00d62b38cad` |
| `worker-health-joined-20261115/source-join-receipt.json` | `bddcf968bebdd53819aabbde3e7bd32188246d1eee199c57342a15a5b36fddb6` |

## Lifecycle eligibility ordering failure — reproduced component, 2026-11-15

The corrected native02 diagnostic reproduces the lifecycle eligibility failure on original joined source `330354ed6b98160c1aa56c8884b9e3cac7ca790d`. The real receiver and public typed store consume phase rows captured from PostgreSQL after an explicitly synthetic administrator applies the source-defined sequence: increment generation at suspension, then reactivate at that same generation. A real operation window confirms the tenant is active. This does not invoke the canonical maintenance API or certify its complete four-role cohort, export or stop proof.

The activation receipt is ignored because its token is below the retained suspension token. The actual active tenant remains lifecycle-disabled and absent from pending-work discovery. The safety oracle is RED; the successful diagnostic label is `REPRODUCED_ORDERING_FAILURE_NOT_RECOVERY`. Duplicate receipts, existing v2 admission and closing/reopening the actual public store preserve that retained state. A second tenant continues to commit receipts and appears in work scans; this proves receipt discoverability, not clinical completion. Completed/output/ACK fields remain unchanged. Bootstrap and OS process restart are not run.

The packet's only executable repair from failed native01 is the create-label literal. An independent source control executes the actual intent constructor and create callback, checks their complete custody fields, rejects the old label and passes after restoration. Native02 uses four observed physical clients including administrator, real owner/ordinary slot and lifetime; it closes with independent exact absence before the fixed deadline. Original failure and root-targeted cleanup captures remain unchanged. Compatibility research now evaluates monotonic encoding, legacy retained tokens, stale replay and the int8 boundary. No encoding change or lifecycle repair is adopted; actual canonical restore and fresh clinical output remain OPEN. The source file is absent from the fetched shipping `official/dev` anchor, so this finding is scoped to the programme prototype rather than a released defect.

| Retained evidence identifier | SHA-256 |
|---|---|
| `lifecycle-eligibility-ordering-02-20261115/results.json` | `47ac06cd949a66da4a1c840ac0434c9a1ec281e8fc146e7cf7d655456694e901` |
| `lifecycle-eligibility-ordering-02-20261115/measurements.json` | `38818e01e2bdc2fb95ae27cc538f3caca0e08ba8b5504c64d89259a89e34f067` |
| `lifecycle-eligibility-ordering-02-20261115/root-final-absence.json` | `da7ecaeb0a89e8982bc55a95c73acd40469bd690e3c2690274309f75c3acdc05` |


## Lifecycle candidate and intake cutover boundary — proposed, 2026-11-15

An isolated proposed receiver candidate at `f39d35c6e5ff44568ea16503bcf57b1cd7ed0e43` maps suspension to `2g+1` and activation to `2g+2`. It recovers the retained legacy suspension token without a vector reset. Both phases explicitly refuse generations outside the complete supported range before observation. Source tests exercise the actual receiver and typed work transformation through recording SQL interfaces: canonical reactivation, legacy-token recovery, duplicate/stale ordering, exact integers, pending age, numeric completion/output-control ordering and ACK behavior. The original recovery assertions are retained RED, and the candidate passes. Root independently repeats 43 focused tests and the inventory for 777 files/eight tiers. These are source checks, not native clinical or cutover evidence.

The candidate changes the unpartitioned receiver default only on its separate unadopted branch. It does not join the integration tree or qualify runtime activation. Its complete-generation maximum is one below the previous encoding's maximum. The former same-generation suspension input, mixed encoders and downgrade remain explicit unsupported counterexamples. Receiver refusal alone is insufficient: controller/restore preflight and retained-roster checks must prevent an unencodable generation change before database phase mutation. A small native receiver/store repair packet is being prepared separately; no runtime GO follows from source closure.

**Read-derived:** independent cutover review finds that current typed digests bind work kind, namespace and consumer but omit the encoder. Cold catalogue validation can reject old startup; warm observations do not rerun it. An explicitly encoder-bound row contract can reject each old public-store transaction, but legacy SQL privileges could reset an unprotected contract. The proposed capability therefore needs immutable installed profile state, actual SQL mutation checks and retirement of the old writer authority. Source/config/image and intake-health pins do not already prove this boundary. The rollback/HTTP-success counterexample is read-derived, not native evidence.

Root commissions a separate default-off receipt-only SQL prototype from the clean integration join. Its proposed policy permits durable pending metadata for configured active or suspended tenants and while a worker is absent, provided the sole owner, fixed configuration and profile remain valid. Clinical operation windows, real restore generations, worker effect fences and independent alarm ACK remain unchanged. This is a prototype policy, not release adoption or canonical restore qualification. The capability must include a purpose-specific held-backend receipt API, validation-only roster admission, narrow principal/grants, coherent immediate/deferred SQL transitions and warm old-writer refusal; a constructor-only change cannot satisfy it. Existing base-consumer replay rights must remain supported while completed-row contract/version writes remain forbidden. Heartbeat production cannot itself renew observed stream freshness. Source implementation continues in its own lane; runtime/health/deploy composition remains root's later boundary.

| Retained evidence identifier | SHA-256 |
|---|---|
| `checkpoint-worker-native-04-20261115/independent-review.json` | `2061243228dc94baf497c97c0af53fabddddd1f92c07ff95c28b3ea44638d172` |
| `lifecycle-encoding-candidate-20261115/receipt.json` | `4802ad8c6e84faaeb5f72b9ec3b438cf6a0d03eec7023a6e9d5c993552339300` |
| `lifecycle-encoding-candidate-20261115/root-recheck/checks.json` | `f599ea90000cb9e86ed90a374ef41669152f026f5de5140e984839649cb5c2e1` |
| `lifecycle-encoder-cutover-audit-20261115/receipt.json` | `790d8cb81405b53aef498e6ee17d9a5fce2e961cf0dec990a7de666ba18ab4fa` |


## Native receiver eligibility repair — reproduced component, 2026-11-15

**Reproduced:** the finite repair point exits zero on proposed source `f39d35c6e5ff44568ea16503bcf57b1cd7ed0e43`. Byte-exact archived cf8e receiver code first establishes the durable legacy suspension token and reproduces a RED same-generation activation. The fixture then switches only to the candidate's actual public receiver. That receipt advances the retained token exactly once, restores lifecycle/work eligibility and makes A discoverable in the actual pending-work scan. The pending timestamp stays exact and delivery revision advances once. No vector reset, fabricated clinical generation or database output is used to establish recovery.

Duplicate activation, existing v2 admission and closing/reopening the actual public store preserve the recovered rows exactly. B continues to commit receipts and appear in work scans without changing A's checkpoint. Twenty fields are projected; ten completion/due/output/projection/ACK fields have explicit unchanged assertions. This is receipt discoverability, not clinical completion. The point invokes no completion or alarm-ACK API. A real operation window confirms active phase and the same actual generation; the administrator's phase mutations follow the source-defined sequence but do not invoke canonical maintenance or certify a complete restore cohort.

The final observed census is four physical clients including administrator, held owner/ordinary slot and lifetime. Actual server statement/lock timeout profiles match; client connect/query options are source-bound rather than experimentally timed-out. Container limits, host heap/RSS distinctions and fixed cleanup window remain unchanged. Root strictly verifies exact container/name, PostgreSQL/runner/guardian PID births and nonce namespace absent before the original deadline, with no volumes. Independent retained-capture review confirms source seals, legacy RED/candidate GREEN, state invariants and cleanup.

The candidate remains unadopted. This point does not qualify old-writer/profile cutover, downgrade, controller generation preflight, canonical maintenance/restore, OS restart, clinical output or full topology. The intake SQL prototype and durable lifecycle-domain enforcement remain separate integration prerequisites. No full campaign, merge to application dev or release follows.

The original paid scope expires at 16:01 UTC with no active paid resources and no source/image transfer. The mutable budget ledger records its expired zero-resource state and retains the original authorization/reservation snapshot. Actual invoices remain UNMEASURED. A later remote run requires a fresh explicit scope, reviewed payload/destination and finite plan; no old resource, key, GO or unused budget credit is reused. Local source work and the local synthetic fixture are separate from that expired paid scope.

| Retained evidence identifier | SHA-256 |
|---|---|
| `lifecycle-eligibility-repair-01-20261115/results.json` | `7228accd9fe8e14fc061d7f381364cd963e4a9de6f732a167e8b66974b8a75f0` |
| `lifecycle-eligibility-repair-01-20261115/measurements.json` | `55366f96f87c9690d5c8670221f33e833956ef8ec7c9e575778ac06bcac4874f` |
| `lifecycle-eligibility-repair-01-20261115/root-final-absence.json` | `9d8632dbe49965e6e7a11551685c564e2da8f586f918d84e65832a00cbfd0157` |
| `lifecycle-eligibility-repair-review-20261115/NOTE.md` | `bbd6a69b6dc39a7b538b1c57bde9a508561a04a3fbc5e4f4f0257b54cd71071f` |
| `pgstream-remote-8h-scope-20261115-0801/budget-owner.json` at scope closure | `436dd1606f4a5b6df32fd48b29a8acb0f8fb22576a1e7a7b39ac5ebe657b4f6c` |


## Frozen source checkpoint and selected domain proof — 2026-11-15

The clean profile/health base is local `4da6adaef155df84eb2c75b6488f601bbd9d886b`, joining pure profile `0ea2d3bc91cadbe003d6817f6acf357214712dee` and health agreement `a10c44e55a095d15abc41eec6060892dfbbdbad1`. Root independently runs 66 listener-free profile/health/contract checks and the current inventory. A selected publisher reports an explicit immutable profile digest; a selected worker requires its exact configured digest and refuses missing, wrong or unexpected selection. A valid terminal response latches before profile comparison, preserving the existing terminal/freshness rules. This is agreement over the trusted peer, not SQL authority. One helper selection also ran local transport listeners outside its source-only brief. That completed log is retained and excluded from the authorized source-only count. Current scoped process checks find no owned Node actor; original ephemeral endpoint/PID births were not retained, so no backdated exact endpoint-absence claim is made.

The receipt-only SQL source candidate is clean local `9d64b2f8ed1e2725bb3f9339324b8cbded272fd9`. It includes narrow intake grants, immutable profile/typed contract binding, validation-only roster admission, a private held-backend receipt port and append-only SQL transition/COMMIT checks. It preserves worker effect and base-consumer replay rights and independent alarm ACK. The real branded lifecycle window's canonical read-only control metadata admission remains required. The candidate is default off; its SQL behavior has not run natively. It is not runtime wiring or an adopted profile migration.

**Reproduced source/model findings:** root's clean-base check reproduces five old notification-store mock failures. Their incomplete default `own`/`close` interface is repaired in fixtures without weakening production ownership or cleanup. Independent review also reproduces a caller-owned batch changing the post-COMMIT wake-hint tenant, including a `toJSON` variant. An owned normalized batch repairs the hint identity; mutation/getter/callback counterexamples pass after repair. These invoke the actual store export with a synthetic deferred port, not PostgreSQL durability.

A bounded pure cost measurement finds that five validations of an already immutable 10,000-tenant profile rebuild its assignment five times and reprocess 50,000 roster entries; individual samples take about 44–48 ms on this host. Before adding a fast path, another counterexample shows that a side-effect getter can change constructor input after validation. The repair first owns scalar values and indexed roster entries, validates and freezes them, then privately recognizes genuine immutable results. Untrusted JSON, clones, proxies and forged assignment functions still undergo full normalization. Root's repeated measurement records zero rebuilds/entries for the same five known-object validations at both 1,000 and 10,000 tenants, with ordinary binding/digests/owner key exactly unchanged. No database authority, membership, owner or COMMIT check is cached. These pure results establish no application throughput or capacity gain.

**Reproduced selected-domain storage/readiness component:** on clean local `2c64664ae263ef209f4715ed2c9f3a315838f67e`, PostgreSQL accepts the exact selected CHECK/catalogue and admits the three limited SQL roles. An out-of-roster namespace row refuses coverage preflight; bypassing that preflight still makes CHECK validation fail and roll back. This first guard is coverage, not an isolated native generation-preflight result. A preadmitted operator's direct source UPDATE above the supported range gets the exact constraint's `23514` before phase/audit commit. The maximum supported suspension/activation pair commits at the same generation. Removing the CHECK permits a forbidden changed-row COMMIT and makes the mandatory oracle RED; exact rows, empty audit and full ledger are restored before re-adding the CHECK, after which refusal returns. Wrong/unvalidated constraints refuse selected readiness and pass after restoration. Root independently repeats the new source unit selection and packet controls, then verifies strict fixture/PID-birth absence before deadline. The observed census is four including administrator. This is not the public controller API, a genuine four-role cohort, crossnamespace profile adoption or clinical restore proof.

All source lanes stop with clean indexes and no attached runtime. The next integration owner must join these candidates in a new tree, bind the actual selected window/profile to the private receipt port, qualify native intake SQL, and wire selected receiver/worker health before one coherent topology/restore campaign. The research receiver's changed unpartitioned default must not be merged blindly; preserve the original unselected behavior and select the recognized codec explicitly. OID-only cohort metadata does not establish profile agreement. The existing restore fixture simulates three roles and cannot supply the missing genuine four-role proof.

Direct human approval now permits necessary source/test-image transfer to temporary test hosts and renews an aggregate $2/hour, $16 maximum eight-hour scope. The new conservative window is 17:04 UTC on November 15 through 01:04 UTC on November 16, including cleanup. A fresh ledger starts with zero reservations/resources; the expired ledger remains unchanged. A filtered current provider census confirms both prior runs' exact owned resources, key files and guard births absent. The qualified minimum can be measured remotely independently of these guarded prototypes, after fresh plan/source/image attestation and custody acceptance. The old closed bundle contains parent7291/image2a4e; a minimum8ae/image382e plan must be rebuilt and rebound, never revived from an old GO.

| Retained evidence identifier | SHA-256 |
|---|---|
| `sole-intake-sql-20261115/source-receipt.json` | `f0c9272b0e5fd286a0f378b17570a8989af6fd6e60158145b20fcb2af43f75c7` |
| `sole-intake-independent-review-20261115/receipt.json` | `dd8fa364798afd36766a25502e4c2d5372a4c32146144d527a294af69b8524e1` |
| `intake-health-profile-20261115/receipt.json` | `c586db92768a73341195a9a1a446b6df68bcfcf7b87505a3072641aedc50af7e` |
| `intake-profile-cost-20261115/measurement.json` | `f1862000ac6cae852a9a190625ccaef3517d773bdb504b836f0e57d6e14096ef` |
| `intake-profile-cost-20261115/after-01/measurement.json` | `7ddd3e9b5816187f3cc27cd4e493adbc9fc99025a03f2638e6ca31d3a9fe58d6` |
| `lifecycle-domain-native-02-20261115/results.json` | `8cd048dd4e2a5a2bcf6b1606ae0be182c2399fa1d868384cdf992db67742981b` |
| `lifecycle-domain-native-02-20261115/root-final-absence.json` | `038f099b7bb692b981c65c147fe78ba7a9b20e639b77423992e1684caedfaa36` |
| `pgstream-remote-renewed-scope-20261115-1704/budget-owner.json` before transfer | `73a37df7c626cbc8e08d121e3c9f7d5c494b48a07da59afc5cbc70930d6f3928` |
| `pgstream-remote-renewed-scope-20261115-1704/current-prior-resource-absence.json` | `227c0a26e9256183caed69778f017511333584ae3bb082530d553c49f6626168` |

## Selected intake integration and first SQL setup failure — 2026-11-15

The successor accepts integration, source, budget and cleanup custody after the outgoing owner's stop acknowledgement. Local source `703ffba70ba0f7df1cea0cd74f0e75dac8f86a2a` joins the selected lifecycle domain and receipt-only capability, binds the real selected operation window's profile digest to the private receipt port, and selects the recognized receiver codec without changing unselected behavior. The feed factory constructs the narrow receipt store only under that explicit selection. Publication uses the actual store's digest. Its pending-health read uses the original held backend and fresh transaction, owner, window and installed-profile checks. Root runs 88 focused checks successfully. These are source/model results; native feed, worker coexistence and canonical restore remain UNMEASURED.

**Reproduced setup failure:** the finite intake SQL component on frozen `179e4c9cb411049fdcc0715f5e0077ba3bdc25c6` stops with PostgreSQL `42704` while installing the selected checkpoint catalogue, before receipt admission or authority controls. The fixture creates its intake role after the catalogue that grants that role function execution. The source-derived diagnosis is fixture ordering; no production repair or intake SQL pass is claimed. The failed packet remains unchanged in ignored `externals/work/intake-sql-native-02-20261115/`. Its runner and guardian remove the exact fixture; root independently verifies exact container ID/name and runner/guardian/PostgreSQL process births absent before the original deadline, with no volumes. A fresh packet must test corrected orchestration and its failing control before another finite run.

Atomic admin cutover, retained-row contract rebinding with every other durable field preserved, old warm-writer exclusion and genuine cohort/clinical continuity remain OPEN. The current worker identities cannot own heartbeat control under their narrow grants; selected runtime work uses one explicitly bounded control connection rather than expanding receipt or clinical authority. The qualified minimum's remote baseline remains independent. Its exact source/image admission adapters and local image archive are prepared; actual remote import and workload remain UNMEASURED. Integration owns these boundaries and the renewed aggregate budget; local custody remains in `externals/work/HANDOFF-pgstream-flow-2026-11-13.md`.

| Retained evidence identifier | SHA-256 |
|---|---|
| `externals/work/intake-sql-native-02-20261115/results.json` | `4ac80f1eeec1d6d756bd4a9a642827188ad6e3bb90e5eaabe412d643a03d38c0` |
| `externals/work/intake-sql-native-02-20261115/cleanup.json` | `5a4956e3bff9eadbdd62795a58d51a87bed0d96b38633b593edf7c918c648ad5` |
| `externals/work/intake-sql-native-02-20261115/root-independent-absence.json` | `e49ae7ad5756a1b302b5b4607347b289395e319fb0fa8a9c646ba7cf27a06c90` |

**Reproduced subsequent component closure:** fresh `intake-sql-native-03-20261115` exits zero on the same frozen179 source after a control executes the actual fixture orchestration: old role ordering fails and corrected ordering passes. Real PostgreSQL installs the source catalogue and admits the actual branded selected window/private receipt port. Active and suspended tenants commit durable observations while worker membership rows are empty. The no-op state remains exact. A caller batch mutated while COMMIT waits cannot change the committed wake-hint identity. A clock-only observation makes clinical work pending without manufacturing a delivery hint; the corrected shared oracle has wrong-hint and missing-pending red/restored controls.

Actual raw backend, transaction, profile, foreign-roster and owner contexts refuse with their expected source assertions. Pre-admitted raw legacy-column writes on this already-selected fixture refuse; this is not a session admitted before cutover. Disabling the two effect fences allows a forbidden changed-row COMMIT and makes the required state oracle RED. Every row is restored exactly before the fences return, after which refusal returns. Withholding a real server COMMIT's adapter result leaves the receipt owner terminally unavailable and emits no success hint. This tests controlled result withholding, not genuine network ambiguity. Completion, output, ACK and assignment fields remain unchanged.

The observed census is five physical clients including administrator, two intake-role clients, lifetime and legacy probes. Exact container/name and host runner/guardian/PostgreSQL births are independently absent before deadline, with no volumes. The original failed packet is unchanged. The new coherent source join `4de5f537f700df0a8c4eb363bbdd8c224cc3fa13` also includes atomic admin adoption source and selected cohort-digest agreement; root runs 169 focused checks. The native03 capture stays attributed to179, not that later join. Actual atomic cutover, pre-cutover warm-writer exclusion, no-op final-authority loss, worker coexistence, genuine cohort/clinical restore and network ambiguity remain OPEN. No full campaign, image, activation, merge or release follows.

| Retained evidence identifier | SHA-256 |
|---|---|
| `externals/work/intake-sql-native-03-20261115/results.json` | `4cc99d67cff7dfd76f8ded88279bc39cc8af7ff24667483ef8cac5298153bd64` |
| `externals/work/intake-sql-native-03-20261115/measurements.json` | `43b0c1105884a76031cb3d2bd424f116b84d6e85e3b8ce722d5ab39f4a8ff7ab` |
| `externals/work/intake-sql-native-03-20261115/root-independent-absence.json` | `2ba20a5062414ce48f9a2cc1c808c72785244664936558b360aed73ec20a8b8f` |


## Atomic intake adoption component — reproduced, 2026-11-15

**Reproduced:** native04 on frozen `c15ec7c7e5bca23ff5e9447de47578f9508b234e` exits zero. PostgreSQL type controls reproduce name-array decoding as a string and the explicit text-element casts as an array. The actual installer refuses a live legacy owner, foreign roster and effective old-writer authority paths, including LOGIN, NOINHERIT/SETROLE and a connected principal subsequently made NOLOGIN. An injected SQL failure rolls back the adoption. Earlier native02 predicate and native03 fixture-oracle failures remain unchanged.

Successful adoption preserves twelve tables and fourteen rows except the two intended completed-row contract digests. All other captured fields remain exact; several restore/activity/audit tables are empty, so this is not a nonempty-history preservation proof. The same physical pre-cutover prepared writer and a new connection both receive permission refusal afterward, with unchanged snapshots. The actual selected intake connection remains admitted while both workers complete checkpoint/ACK/BASE operations and immediate synthetic TIME recompletion. This point contains no post-adoption receipt and no naturally due scheduler, real clinical evaluation or realtime delivery proof.

The fixture's cleanup completes before its deadline. Root independently confirms exact absence afterward, but that check runs after the deadline and explicitly records `beforeDeadline:false`. This component therefore has no independent-before-deadline cleanup claim. No unchanged run is repeated to improve that wording. The retained audit binds all source inputs and observations.

The joined local candidate `6a31159242825eba54c0d9d6d6b384ea79fefe0c` also includes actual selected runtime/fixed membership, cohort profile wiring, realtime output profile and the lower feed-control privilege correction. Root's focused selection passes 279 checks; inventory reports 783 files across eight tiers. These source/model checks do not qualify a genuine five-participant boot, canonical restore or fresh clinical/realtime continuity. Those remain the next integration criterion before one coherent full/browser/enabled-native/image/final-prcheck campaign.

The qualified minimum baseline proceeds separately. Its actual pinned k6 summary qualification preserves explicit zero counters and rejects omitted metrics and failed HTTP responses. A fresh guarded pair is allocated within the renewed scope at combined $1/hour, with a single $3.50 upper reservation. Deployment and traffic have not started at this checkpoint; runtime GO awaits actual host/configuration review. Fixed cleanup remains inside the approved scope. No capacity, application-dev merge or release claim follows.

| Retained evidence identifier | SHA-256 |
|---|---|
| `externals/work/evidence-intake-atomic-adoption-20261115/native04-retained-audit.json` | `bf447f154425e9f320a72106a8f75e9ff3bbde4f5096f61825e9c6c6d059582b` |
| `externals/work/intake-adoption-native-04-20261115/root-independent-absence.json` | `7e8ef7f78abbecab161afb4f324b05b9533acb8e7919f6820c5ff29fc5943272` |


## Remote baseline attempt closed before deployment — reproduced, 2026-11-15

The finite baseline pair is allocated at 18:51:31 UTC. Actual host identity, private NIC, configuration/source/image seals and live guardian pass review. Before deployment, executing the generated public probe with in-memory public HTTP/socket/files reproduces an unconditional missing accounting declaration. The public-only generator removes that declaration with its SQL/discovery block but retains conditional uses. Root revokes runtime GO; no source/image export, application deployment or traffic occurs.

The repair review deadline passes without a reviewed, sealed replacement runtime packet. Root requests early cleanup at 19:08:18.922 UTC. The original unchanged guardian verifies deletion at 19:08:34.596. Root independently lists provider resources and verifies exact pair/firewall/key/tag absence, local key-file absence and guardian process-birth absence at 19:09:05.081, before the fixed deadline. The actual hourly allocation returns to zero. The single historical $3.50 upper reservation remains recorded; the invoice is UNMEASURED. No performance or capacity result follows from this attempt.

Local source repair `19d74183c775453112052406c60a7b91845f992d` explicitly retains inactive accounting for ordinary public traffic and rejects unsupported discovery before public I/O. Generated-probe source controls exercise normal writes/frame witnesses and rejection of missing frames or failed HTTP. Runtime qualification and a fresh source/image/instrument/host-bound plan remain required; the old packet and revoked GO cannot be reused. All original evidence is retained outside Git. Integration owns the next plan and source acceptance boundary.

| Retained evidence identifier | SHA-256 |
|---|---|
| `remote-minimum-renewed-20261115/execution-02/guard-result.json` | `56f1a8f288db2864154e41c6c2aa82237f7073a42d86fe68a2d293547a965326` |
| `remote-minimum-renewed-20261115/execution-02/root-independent-absence.json` | `d44d8d522617258f310e8db6406c6d42cee470239ec844d98e2ade6bc9825072` |

## Local 3000-tenant point — reproduced partial, 2026-11-15

**Reproduced:** the qualified minimum `8aeefaefc88c79c3d548f7683d5651bec9cf5c01`, deployment
`df5362745a1b2d1b02b9186daedef3faccc14e58` and canonical image382e complete an ordinary
3,000-tenant/6,000-client point at 180 offered scenario requests/s. The retained manifest
reports PARTIAL and instrument `cceaf978352a837e4c97317f9f92b2bfbeac3ea29a865c0b7989b19d10705367`.
This shared-host point has fresh history; it is not a causal comparison with the earlier
1,000-tenant accumulated-history point or an isolated capacity ceiling.

Global HTTP p95 is 3850.760 ms and p99 is 4398.201 ms, including 3,000 setup exchanges.
The point records 55,650 scenario responses, 152 dropped iterations and 14 uncertain
writes. Reconciliation finds 15,183 accepted and 15,183 stored writes within its uncertainty
bounds; that is not exact resolution of every uncertain outcome. All 3,000 tenants earn
successful evaluator work: total work delta 10,562, minimum 2 per tenant and failed-completion delta 0.
Those observation bookends include setup and load; they do not establish a scenario-only
evaluation rate or executor-duration distribution.

All 6,000 sockets prime, but only 2,468 remain connected at the end; the observer records
3,532 server disconnect events. Four selected frame witnesses arrive, with maximum 4.633 s.
The two observations labelled write-to-evaluation have maximum 5.373 s and include polling and the
client gate; they are combined completion/client witnesses, not pure evaluator latency.
Sparse delivery witnesses do not offset the all-client availability loss. The disconnect
cause remains UNMEASURED. The known realtime-cost collector omitted a required empty
request body, and the retained log prefix ends before the failure window. A bounded
collector/recent-log repair and the same diagnostic point precede 5,000 tenants; no
reconnection behavior or workload change is implied. The owned fixture is cleaned up.

## Selected topology fixture startup failure — reproduced, 2026-11-15

**Reproduced:** the first native HOST-witness packet on unchanged joined source 6a31 starts its
exact PostgreSQL/Vault resources, then stops during maintained pgstream initialization,
before the five application roles boot. PostgreSQL 16.16 returns 42501 because wal2json
is absent from its trusted output-plugin setting. The canonical deployment already sets
`output_plugin_libraries=wal2json`; the isolated launcher omitted that setting. This is
a fixture configuration failure, not a clinical or receipt result. The earlier frozen
packet remains unrun after a HOST namespace preflight refusal.

The PostgreSQL cleanup guard also refuses `POSTGRES_PHYSICAL_IDENTITY_MISMATCH`.
The physical capture precedes final TCP-ready postmaster startup: its file timestamp is
19:46:15.464823 UTC, while the final server starts at 19:46:15.631. The preceding Unix-only
bootstrap server was already accepting connections. **Read-derived:** the Unix-default
readiness check admitted that bootstrap stage; the exact changed identity field was not
retained. Preserve the strict physical check and require final TCP/SQL readiness before
capture, with bounded expected/actual diagnostics if another mismatch occurs.

Vault cleanup succeeds. Root verifies the exact owned PostgreSQL CID/name/image/nonce
and removes it at 19:48:19.749948, after the original 19:48:13.554 deadline. Independent
current absence confirms both resources and six recorded process births, but explicitly
reports `beforeDeadline:false`. Cleanup therefore FAILS its deadline. Original captures
remain unchanged; no unchanged run is repeated to improve that result. Integration owns
one repaired fixture batch, then actual clinical continuity and canonical restore before
the held coherent acceptance campaign.

A subsequent remote allocation is refused before provider mutation. Independent checks
find no exact owned resources, local key files or guard, and the unconsumed reservation
is released. It supplies no remote workload result. Fresh remote preparation remains
independent of the selected topology fixture and within the existing aggregate scope.

| Retained evidence identifier | SHA-256 |
|---|---|
| `local-minimum-n3000-20261115/attempt-02/analysis/compact.json` | `3dd7624b92dfaeb8d404b6430cfe541b8f1a0db8846b4f88dfc266dd10d112f3` |
| `externals/work/canonical-cohort-qualification-20261115/root-preflight-refusal.json` | `73b5e02f8e8798920293f8b0db5f1ad4d70cb93d5fdb57efac1bb116e4fa0d56` |
| `externals/work/canonical-cohort-host-witness-20261115/results.json` | `a6041cfc480bfd7572f1c9aa4ee88e153321206de1501d6441ef490da9887a9f` |
| `externals/work/canonical-cohort-host-witness-20261115/root-postgres.private.log` | `9be30fb793fadd722f89ac1354ef534a9aa14a0eb6ac74c2d43498bba848415e` |
| `externals/work/canonical-cohort-host-witness-20261115/startup-timing-audit.json` | `3c09bae55354e9b26d925f159c0f28b98c467dd537707b9fd625148e35fc452f` |
| `externals/work/canonical-cohort-host-witness-20261115/root-final-absence.json` | `d5ef55e0c044928b4e5ee1134827587365db16f13a06c3dfb2aa10f52f4dc871` |
| `externals/work/remote-minimum-execution03-20261115/root-final-absence-01/receipt.json` | `04e976fe1b339b16898eb6427e315c3cd46918a05c4a827368d139702d88f182` |

## Remote known-build commissioning (2026-11-15)

**Reproduced:** execution07 completes the supported ordinary remote diagnostic on the
qualified older build. This is a small functional commissioning result, not capacity,
reconnect qualification or a measurement of the later architecture changes.

| Input | Captured value |
|---|---|
| Product / deployment | `8aeefaefc88c79c3d548f7683d5651bec9cf5c01` / `df5362745a1b2d1b02b9186daedef3faccc14e58` |
| App / PostgreSQL image | `sha256:382e44696c4415e710698ee6135c499ae2d480d9f39a2fb85c59675fdd8d2150` / `sha256:21e7e1665c3dd2fdd80ebd9ce6d36fb160d6a4129683b315b6492a71d87bfda7` |
| Helper / controller | `19d74183c775453112052406c60a7b91845f992d` / `6622c10da7f319ab09bf76f4404164e4c09dbc0f` |
| Profile | 10 tenants, 20 stock clients, serial primer, 310-second ordinary traffic, nominal 0.3667 scenario requests/second; no offered-rate override or restart |
| Physical machines | Separate app and generator hosts, each 16 vCPU / 32 GiB; this does not establish an 8 GiB workload limit |

| Measurement | Result and scope |
|---|---|
| HTTP | 118 scenario attempts/responses; 128 global requests including 10 JWT setup requests. HTTP failure metric value 0; transport failures, refusals and dropped iterations 0. |
| Mixed HTTP timing | Global p95 94.413 ms / p99 110.413 ms, including setup. This small low-rate sample is not a tail-capacity benchmark. |
| Independent stored-data oracle | 33 accepted scenario writes = 33 stored; uncertainty 0. Two additional probe writes = two stored. Marker control GREEN → RED → restored GREEN. |
| Realtime | All 20 clients prime and remain connected; no server disconnect. Two selected tenants produce all four expected frames; maximum request-to-frame 92.373 ms, n=4. No broad delivery-tail or reconnect claim. |
| Evaluator progress | Three-round observation passes all 10 tenants: completed-work delta 29, minimum 2, failed-completion delta 0. The collector wall time is observation cost, not a work-rate denominator. |

Per-write evaluator latency, natural-due opportunity coverage, full clinical output
coverage and capacity remain **UNMEASURED**. The two selected output witnesses do not
qualify every tenant's clinical output. REST, durable work and client delivery are
separate observations; no cross-host timestamp subtraction supplies evaluator latency.

The load-start marker is 23:04:13.354 UTC, before the fixed 23:05 new-point cutoff.
The caller completes exact owned fixture teardown and provider deletion. The guard
reports deletion at 23:10:01.720 UTC. Independent root checks at 23:12:01.926 UTC find
no matching hosts, firewalls, provider key, tag, local keypair or guard birth, before
the 23:55 absence deadline. Earlier approval refusals and their closed packets remain
unchanged; this run did not reset its clock or borrow acceptance from a later source.

Raw originals remain ignored under retained evidence identifier
`externals/work/remote-minimum-execution07-20261115`. Read-only inspection of the retained
archives supplies the figures above. Future performance-candidate admission and matched
1k/3k experiments belong to the fresh experiments owner; local clinical/restore and
final promotion remain separate. Local ownership is recorded in
`externals/work/HANDOFF-pgstream-flow-2026-11-13.md`.

| Retained original | SHA-256 |
|---|---|
| `commissioning-result-summary.json` | `5a4c73c3a4e54f21fda03a6d3b8d9a12e2539bfe96b7b0238f5d73b386c9bd08` |
| `bundle/campaign-result.json` | `b305be9b5b699cdda60f59012363abb351ea363b9de09fc82f34966d8bcf94b5` |
| `bundle/driver-evidence.tar.gz` | `e952bc7793e5bc8e00576b7dbd8af565ca510366b193036705f0930236546299` |
| `bundle/sut-evidence.tar.gz` | `631deadb58812dfe83e84e9f3704f6bba42583e5f25f46a3d4853715530dc7aa` |
| `root-final-absence-01/receipt.json` | `7fdb32e4d77cdd88a778ecd2ededb4295fe7f60b26c25ea1f8f7562b537e9914` |


## Comparable experiments and final-image tiny — 2026-11-15 Pacific

**The final-image two-tenant ordinary witness completed. The new 1k point failed
clinical readiness and socket priming before ordinary traffic; no new capacity
or matched 1k/3k throughput result follows.** All figures in this section are
**reproduced** unless marked read-derived. These are isolated synthetic discovery
observations, separate from final full/browser/native acceptance and operator release.

| Point | Executed tuple: core / deploy / image / helper prefixes | Measured outcome |
|---|---|---|
| Ordinary a01, 2 tenants | `d5ec3998 / bf8327f4 / 0775fcd9 / d2db4d58` | Canonical primer HTTP 503 before traffic; request class/body unavailable. No Vault denial selected. |
| Ordinary a02, 2 tenants | `28a1b360 / 99a9ba59 / d930b956 / b749cf81` | Safe diagnostic identifies `entries-create`, HTTP 503, `UNCLASSIFIED`; no traffic. |
| Ordinary a03, 2 tenants | `86c000e9 / 23e73da7 / 67f982ae / f0b887df` | Readiness/idle/load pass; 216 ordinary responses, zero HTTP failures, 60 accepted/stored writes and zero uncertainty. Four clients remain connected. Its optional observer retained a later frame, not first delivery. |
| 1k a04 | `86c000e9 / 23e73da7 / 67f982ae / 5dc2cb3b` | All 1,000 tenants provisioned and canonically commissioned. Readiness/idle fail; socket setup primes 20/2,000 clients. Work deadline ends the point before an ordinary window. Throughput, durable output and first-delivery window metrics are UNMEASURED. |
| Planned 3k a04 | Same frozen tuple/helper as 1k | **NOT RUN.** Held as a throughput comparison after the 1k readiness failure and measured setup cost. Any later bounded startup diagnostic needs that explicit scope. |
| Final image03 a05, 2 tenants | `8ddcc012 / 23e73da7 / c05744f3 / 5dc2cb3b` | Completed; readiness/idle/load pass. 216 ordinary responses plus two JWT setup exchanges; zero HTTP failures. 60 ordinary accepted writes equal stored writes, with zero uncertainty; one additional probe write is stored. |

Final-image attribution is core `8ddcc01208c11c18145c44c1076ae4c91f79ffa2`,
deploy `23e73da7ad8d57bb0a360c29b3ef2320ed229238`, image
`sha256:c05744f34b0657a32cc974498564a9669b5731f889712d399aca7ce76809ecde`.
The 1k/a03 application is `86c000e98890786e5961551f0a6e9f9dc32ab826`, image
`sha256:67f982aefdbadd2851462c8f716bdc92cd853275c8ee07985e904a2b84a7be19`.
The corrected common helper is `5dc2cb3b6ef313719f2f77c0d000761577ca1fcd`, instrument
`0f6940bff36aef0b61b3da7d5fb6c745cb8215b78d9dca08c87980c9b30002d2`.
Actual image labels, committed source objects, dependency custody and the paired
deployment producer → published core schemas/real loaders passed before services.
Genuine image03 build/check qualification SHA256 is
`a0149c016450c8736ebad1934aa14e4f9c0bbef8a294a0c233e04ddc319cdd8e`;
image qualification alone does not assert runtime acceptance.

### Separate output and client observations

The final tiny retains four connected clients, no server disconnects and two of
two selected frames from one probe write. First stored-ID-matched client callbacks
are **144.902–145.259 ms**; the existing millisecond-clock probe reports 145–146 ms.
The single request-to-durable-output observation is independently bounded by
**[0, 1,113.696] ms**, with one SQL query taking 112.765 ms. This is a polling bound,
not executor duration. Its clinical check covers selected BG-now mean/last consistency;
it does not cover every clinical domain, natural-due behavior or restore. The stored
count control is green → red → green. No Vault outage/denial ran in these points;
initial administrative credential commissioning may legitimately use Vault.

The a03 monotonic observer overwrote each socket's first frame on repeated
broadcasts, producing a later callback near 35.8 seconds while the existing first
frame was 137 ms. Source inspection and an actual generated-probe repeated-frame
control reproduce the overwrite. The minimal helper correction preserves the first
per-socket observation and retains exact stored-ID, content, connection and clinical
checks; 49 focused checks pass. Original a03 bytes remain unchanged. Its later value
is neither first-delivery latency nor evaluator lag. No image or full campaign was
repeated for this observer-only change.

### 1k phase budget and readiness limit

Each point retains 1,500 seconds work **including preparation**, then 300 seconds
cleanup, with container limits totaling at most 4 CPU/8 GiB and admitted host V8
heaps at most 1 GiB. These limits do not reserve the shared host or bound host RSS.
The 1k/3k inputs specify 180 offered requests/s, 310 seconds, 10-second warmup,
30-second idle, serial primer/JWT setup and two clients per tenant. The full
application campaign overlapped on the shared host; namespaces/ports/databases
were separate. The older 1k/3k records above use different helpers/resource budgets,
so no isolated performance-gain ratio is inferred.

The 1k cold deployment stages total **932.249 seconds**: provisioning 285.834,
canonical priming 504.794 and remaining-role startup 105.280 seconds dominate.
JWT setup takes 28.121 seconds; the initial socket attempt takes 300.155 seconds,
retaining 1,980 dark clients, connection timeouts and ping timeouts. The readiness
record contains an admitted evaluator owner with `ready=false`,
`EVALUATOR_CLINICAL_PROGRESS_STALLED` and no completed acquisition; this is not
merely an absent optional counter. Its cause is unmeasured. The clock expires with
no completed ordinary window. **Read-derived:** linear extrapolation of provisioning
and canonical priming alone to 3k exceeds the unchanged work allowance. This is a
scope/budget limit, not a measured universal tenant ceiling or a prescribed fix.

The deadline point reports a Docker cleanup error. Guard teardown nevertheless
removes its exact containers/networks/volumes and recorded process groups; the
initial independent check fails only the stale 99-byte probe heap marker. After
fresh exact absence and a nonblocking exclusive lock prove no active driver, the
owner reconciles that marker. Final independent absence passes at
`2026-11-16T00:18:29.230314+00:00`, before the original cleanup deadline. The original
failure/first absence record is retained. Final-image tiny cleanup independently
passes at `2026-11-16T00:32:00.381834+00:00`; no local actors remain.

### Retained evidence and next boundary

Original synthetic captures remain ignored under retained evidence identifier
`externals/work/comparable-experiments-20261115`. Each point's `reduced-result.json`
binds raw artifact checksums, exact source/configuration, result and absence scope.

| Selected retained reduction | SHA-256 |
|---|---|
| `ordinary-n2-a03-point/reduced-result.json` | `e0780b34ff214c945bc050703f6b5411bd7ada5f8954f86e4411e69b1d693f55` |
| `matched-n1000-a04-point/reduced-result.json` | `d356460abbca8e7e1864353cc5adf4fb482f9d562b5f19fe6d8daff9126dd356` |
| `final-image03-tiny-a05-point/reduced-result.json` | `047e08472c5e35f005986e66f3677976aba53be317bb9d4227ce6714ad6a9436` |

The existing configurable controller is locally fixed at
`81a3a7de56f29075a2f663189cfaed676e56cbe9`: explicit discovery mode/typed authorization,
genuine build/check/dual-label qualification, configured worker arguments and
bounded exact-name/hash result transfer have positive and meaningful refusal controls.
The future remote 1k packet remains **NOT RUN**. Its unchanged minimum one-hour
lifecycle no longer fits the original hard cutoff; no clock was backdated, no
protocol shortened and no paid resource/reservation created. The held offline
packet/control evidence is `externals/work/remote-comparable-execution08-20261115`.
The remote07 record above retains its original small known-build scope.

Next: diagnose the retained 1k evaluator-readiness/socket-setup failure and select
an explicit finite question/resource profile before a larger throughput comparison.
Final full/native/date-only-specific acceptance belongs to the app integrator;
future RT profile source preparation does not qualify its image or runtime.
Local ownership and exact reproduction commands remain in
`externals/work/HANDOFF-comparable-experiments-2026-11-15.md`. No push, operator
release or capacity acceptance follows from this update.

## Remote 100-tenant ordinary point — November 15, 2026

The directly approved remote point produced useful load observations, then failed
report finalization. This is a **reproduced partial diagnostic**, not capacity or
application acceptance. It measures the earlier intermediate build, not the later
independent-service platform candidate.

| Input | Exact binding |
|---|---|
| Core / deployment | `8ddcc01208c11c18145c44c1076ae4c91f79ffa2` / `23e73da7ad8d57bb0a360c29b3ef2320ed229238` |
| App image | `sha256:c05744f34b0657a32cc974498564a9669b5731f889712d399aca7ce76809ecde` |
| Helper / controller | `2ae69048cdb263f9a14c3f4102a36961a09aa97a` / `81a3a7de56f29075a2f663189cfaed676e56cbe9` |
| Workload | 100 tenants, 200 stock clients, 180 offered requests/s, 10-second warmup, 30-second idle, 310-second load; serial primer, ordinary cadence, restart disabled |
| Rig | Two DigitalOcean `c-16` hosts in `sfo3`, each 16 vCPU / 32 GiB; SUT and driver separate |

| Reproduced observation | Result and limit |
|---|---|
| HTTP | 55,903 requests at 179.654 requests/s, reported failure value zero; global p95 393.754 ms / p99 661.175 ms. Includes 100 JWT setup exchanges and 55,803 ordinary scenario iterations. |
| Ordinary scenario counts | SGV reads 25,365; device-status, treatment and status reads 5,073 each; SGV, device-status and treatment writes 5,073 each. |
| Ordinary writes | 15,219 accepted, reported uncertainty zero. **SQL stored-write reconciliation and the count control are UNMEASURED**; accepted does not establish stored. |
| Clinical progress | Successful-work delta 5,601, minimum 51 per tenant, failed-completion delta zero. Final clinical output consistency and per-write evaluation latency remain UNMEASURED. |
| Clients | All 200 primed and connected at window end. Two selected probe writes delivered 4/4 expected matched frames; first-frame observations 112.838–1,346.271 ms. This does not bound a general delivery tail. |
| SUT resources | Nine-role bookends span 315.523 seconds: summed mean CPU 4.0455 cores; summed final `memory.current` 2,512,449,536 bytes. At least 73 discrete samples per role; no CPU counter reset. Evaluator process CPU: Node 171.58 seconds, pgstream 14.22 seconds. |
| SQL work | 2,264,288 statement calls / 174,260.819 ms execution within those bookends. These are aggregate workload costs, not individual clinical execution times. |
| Driver observations | 112 samples, 103 with k6 stats; sampled maximum k6 CPU 41.96% and container memory about 395.5 MB; maximum probe RSS 185,933,824 bytes. |

SUT totals exclude host and separate-driver overhead. Container memory and RSS are
not JavaScript heap. Sampling is discrete. The separately constrained local driver
run uses a different budget and does not provide a causal comparison.

The SUT traceback records `PermissionError` when its UID 1000 report process reads
the imported `generator-result-manifest.json` during the first final-summary hash
capture. The root worker's restrictive manifest ownership is the **read-derived
mechanism**; the permission failure itself is reproduced. k6 and the probe both
exited zero. The generator handshake EOF is secondary. The final SQL count oracle
did not run. Future tooling owns the narrow manifest-ownership repair and focused
permission controls; this point's source and captures remain unchanged.

The guard verified deletion at `2026-11-16T02:18:11.101Z`; independent provider,
local-key and same-birth guard absence passed at `2026-11-16T02:21:58.072832+00:00`.
Current/reserved hourly cost is zero. The ledger retains this allocated run's
USD 3.50 upper once: historical upper USD 10.50, uncommitted upper USD 5.50;
invoice UNMEASURED. No retry or further allocation follows from this result.

Retained evidence identifier: `externals/work/remote-capacity-review-20261115`.
Original archives remain ignored; safe reductions exclude synthetic credential
setup data. The later diagnosis record resolves the initial summary's uncertainty.

| Retained artifact | SHA-256 |
|---|---|
| `result-summary.json` | `cf5e75b47366baf2d8801382b2f440220709b4fa3ae54eb5403fb2412fbd1969` |
| `diagnosis-01.json` | `aa66e9322b81d21693b127f9f7757b06d4eacc6fe4e0ff3e3dc3383c0cf82343` |
| `http-shape-reduction.json` | `e999fa3cd36e8050d140ad2eab804d9a1dd73e868d8d71f29368784e98e8d42b` |
| `bundle/sut-evidence.tar.gz` | `0e7e62181b1838d793c3284971b8ec71f5a3514d673cdb6ada3f676663eb4a9c` |
| `bundle/driver-evidence.tar.gz` | `a639812090de6ef1ba4641f2c513b395588c76f78f262dc94c955f49c5376ed0` |

Resource reductions use the existing helper reducer and retain selected original
input hashes in `resource-reduction-provenance.json`. Lane detail and next source
boundary: `externals/work/HANDOFF-remote-capacity-preparation-2026-11-15.md` (local).

## Local operating-envelope diagnostics — 2026-11-15 Pacific

The local packet measures count, rate, skew, startup and idle behavior on two image-qualified branches, including the updated independent-streaming source. Stored counts match accepted writes where final accounting exists. Some load cells retain drops or pending final clinical opportunities; the higher-rate point has incomplete accounting, and the long-idle updated point exposes a separate client authorization failure. These observations do not qualify capacity, the enabled corpus or final application acceptance. The integration owner owns the final coherent source and campaign.

The earlier-image cells below use application `8ddcc01208c11c18145c44c1076ae4c91f79ffa2`, deployment `23e73da7ad8d57bb0a360c29b3ef2320ed229238`, image `sha256:c05744f34b0657a32cc974498564a9669b5731f889712d399aca7ce76809ecde`, and the unchanged instrument `0f6940bff36aef0b61b3da7d5fb6c745cb8215b78d9dca08c87980c9b30002d2` from helper commit `2ae69048cdb263f9a14c3f4102a36961a09aa97a`. Native image labels, actual Git-archive producer/core loaders, PostgreSQL identity and qualified owned dependencies pass separately for each cell. Each has fresh synthetic history and namespace, serial primer/JWT setup, two stock clients per tenant, ordinary five-minute probe cadence, hot factor one and one API replica. No install, build or pull occurs.

The shared-host upper envelope remains 4 CPU / 8 GiB for declared containers plus 1 GiB admitted host V8 heaps; native RSS and page cache are separate observations. Preparation starts the original 1,500-second work clock; 300 seconds remain for cleanup. The existing canonical runner, native snapshots, host-process observer and independent absence checker are reused. Quota/image admission and explicit snapshots are separate from the observer, which samples owned host-process heap arguments/RSS rather than continuously censusing containers. Peer services remain active and owned elsewhere. The ambient queue-status check overlaps the first tiny setup; later points do not overlap that check.

### Low-rate count axis — reproduced

| Cell | Tenants / requested clients | Offered requests/s; load seconds | Ordinary attempts / responses | Accepted = stored; uncertain | Actual socket prime | Clinical observation | Runner outcome |
|---|---:|---|---:|---|---|---|---|
| `n2-a01` | 2 / 4 | 7; 30 | 216 / 216 | 60 = 60; 0 | 4/4 in 277 ms | Readiness/idle/load pass; two known completed input opportunities | COMPLETED / MEASURED |
| `n32-r7-a02` | 32 / 64 | 7; 60 | 425 / 425 | 117 = 117; 0 | 64/64 in 1,130 ms | All-roster health pass; 32 known completed opportunities | COMPLETED / MEASURED |
| `n128-r7-a03` | 128 / 256 | 7; 60 | 425 / 425 | 117 = 117; 0 | 256/256 in 3,264 ms | All-roster health pass; 39 known completed opportunities and 89 with no known opportunity | COMPLETED_PARTIAL / PARTIAL |

All three have zero observed HTTP failures, transport failures and dropped iterations. The 128-tenant cell writes to 39 tenants; zero ordinary writes for the other tenants do not prove workload progress there. Its native strict count control is correctly UNMEASURED because quiet rows lack accepted writes. A separate file-only control runs the actual discovery count reducer on copied native count/ACK/ledger captures, using the retained oracle roster after credential cleanup. Removing one persisted-entry count produces `M7_DISCOVERY_WRONG_DATA` with workload/domain count-bound failures; restoration returns GREEN. This validates the reducer on that capture, not a native SQL mutation. The two smaller cells retain native count controls GREEN → RED → GREEN. No original capture or source was changed for the file-only control.

| Cell | Deployment stage total seconds | Provision / prime / remaining-role seconds | Probe JWT setup ms | Global HTTP p95 / p99 ms, including JWT exchanges | Selected exact stored-ID first callbacks ms |
|---|---:|---|---:|---|---|
| `n2-a01` | 47.980 | 4.297 / 2.755 / 11.731 | 234 | 80.189 / 185.828 | 51.754–52.117, two callbacks |
| `n32-r7-a02` | 96.241 | 19.731 / 19.539 / 16.357 | 902 | 68.397 / 207.379 | 282.398–282.673, two callbacks |
| `n128-r7-a03` | 180.503 | 47.622 / 70.325 / 23.769 | 2,186 | 90.817 / 191.455 | 77.650–78.979, two callbacks |

Global HTTP timings include the per-tenant JWT setup population; per-shape ordinary REST timings remain separate in canonical summaries. Selected callbacks cover one written tenant in each cell, not all configured clients or an all-client percentile. Their variation is not an optimization result. The short idle windows classify all tenants as future due with no observed time cycle; they do not exercise sustained clinical time demand.

### Earlier large-run refusal — reproduced capture, cause unresolved

The retained earlier 1,000-tenant cell uses different application/image inputs (`86c000e9` / `67f982`), so it is not a causal comparison with these cells. Its idle capture fails `OWNER_READY_REQUIRED` on an admitted `EVALUATOR_STARTING` row with zero completed acquisitions. Its readiness capture separately fails on an admitted `EVALUATOR_CLINICAL_PROGRESS_STALLED` row with zero completed acquisitions/time cycles and null completion age. The helper's explicit discovery route retains such progress failures and continues collecting other observations; later socket setup does not imply readiness passed. Socket prime retains 20 of 2,000 clients and no ordinary throughput window starts. Empty evaluator output and truncated API/realtime tails do not establish cause. No source repair is prescribed from those captures.

Original synthetic inputs/results and exact reproduction commands remain under retained evidence identifier `externals/work/local-operating-envelope-20261115`; local custody and next actions are in `externals/work/HANDOFF-local-operating-envelope-2026-11-15.md`. Every completed cell above passes independent project-label/namespace/process-birth/group/host-heap absence. Further rate, hot-tenant, sustained-idle and matched remote-workload observations will be added at the same report boundary.

### Higher-rate driver refusal — reproduced

Cell `n32-r180-a04` keeps 32 tenants, 64 clients and the same image/helper/resource profile, with 180 offered requests/s for a requested 60-second window. Readiness and short-idle checks pass; all 64 clients prime in 1,636 ms. The generated workload logs its JWT setup boundary and first ordinary iteration for each of seven request shapes. The generator then accumulates request timeouts and produces no final k6 JSON summary. Offered rate is not achieved throughput. Ordinary completed/dropped requests, accepted writes and uncertainty remain UNMEASURED.

An exact-owned native observation finds k6 at 1,073,692,672 bytes of its 1,073,741,824-byte memory limit, with 422,751 memory-max events. Its 500-millicpu quota is throttled in 2,264 of 2,621 observed periods. At that observation OOM/kill counters are zero and Docker OOMKilled is false. A graceful SIGINT is sent only to that generator. It subsequently exits 137 without a summary; retained Docker-event output is empty, so the exit is not attributed to OOM. A later bounded stop attempt finds the container already absent.

The probe process exits zero, but its completed-output proof fails: the first selected witness passes and the second reports `M7_COMPLETION_CLIENT`. Four eventual matching callbacks do not repair the failed bounded output/client observation. The canonical runner closes FAILED_PARTIAL with `M7_COMPLETED_OUTPUT_ORACLE`; independent absence passes. Canonical collection has already removed the fixture before a subsequent SQL read attempt, which refuses at its owned-source check. No fallback query or retrospective accepted-count claim follows.

This point measures a constrained driver and an unsatisfied selected output/client proof, not application capacity or an application-only tail. The causal ordering between application backlog, additional generator work and driver memory pressure is UNMEASURED. A file-only reduction of retained native samples preserves the first requested 60 seconds separately from the later incomplete interval; it supplies no missing request/ACK accounting. It also shows why setup, generator execution, clinical/output checks and final accounting require separate records. The proposed 600-request/s point and local matched 180-request/s remote workload are NOT RUN under this known constrained driver profile. The next independent steps use 60 requests/s and the same finite quotas, with hot factor one and ten as separate cells. Original failure, cgroup sample, intervention record and exact cleanup remain in the same retained evidence packet.

### Smaller rate step — reproduced

Cell `n32-r60-a05` uses the same 32-tenant, 64-client ordinary workload with 60 offered requests/s for 60 seconds. It records 3,601 attempts and HTTP responses, zero transport/HTTP failures, four dropped iterations, and 981 accepted = stored writes with zero uncertainty. Native count control is GREEN → RED → GREEN. Readiness and short-idle safety pass. The runner records COMPLETED / MEASURED, which describes captured observations, not capacity acceptance.

Final clinical opportunity assessment is UNMEASURED (`M7_OPPORTUNITY_NOT_OBSERVED`): all-roster health passes and 430 work completions progress during the observed interval, but all 32 final target revisions remain KNOWN_PENDING. Progress does not prove completion of the final received revision. No oracle is weakened, no original clock extended and no missing completion is credited. The sparse selected stored-ID callbacks are 82.283–82.525 ms for two callbacks; they do not represent all 64 clients or every ordinary write.

| Ordinary request shape | Responses | p95 ms | p99 ms |
|---|---:|---:|---:|
| SGV read | 1,637 | 1,467.004 | 1,665.935 |
| Device-status read | 328 | 2,593.250 | 2,827.731 |
| Treatments read | 328 | 2,485.824 | 2,811.775 |
| Status read | 327 | 2,815.775 | 3,054.775 |
| SGV write | 328 | 2,554.658 | 2,896.066 |
| Device-status write | 328 | 2,614.965 | 2,877.024 |
| v3 treatment write | 325 | 3,592.351 | 3,956.052 |

The global HTTP p95/p99, including 32 JWT exchanges, are 2,163.727 / 2,983.285 ms. The instrument's scenario response rate is 59.011/s over its run clock; response count divided by the nominal 60-second scenario duration is a different denominator. These measurements retain the four drops and incomplete final clinical opportunities. Independent absence passes after canonical cleanup.

### Hot-tenant distribution at the smaller rate — reproduced

Cell `n32-r60-hot10-a06` changes only hot factor from one to ten relative to the 32-tenant 60-request/s cell. The same fixed offered rate is distributed over a weighted tenant wheel. It records 3,605 ordinary attempts/responses, 984 accepted = stored writes, zero uncertainty, zero observed HTTP/transport failures and zero drops. The first tenant accounts for 240 accepted writes; every other tenant has at least 24. Native count control is GREEN → RED → GREEN.

All 64 clients prime in 1,143 ms and remain connected at the end observation. Readiness, short-idle safety, all-roster health and known-opportunity completion pass: 32 known completed final opportunities, zero pending, with 356 observed work completions. The global HTTP p95/p99, including JWT setup, are 381.890 / 596.955 ms; ordinary per-shape p95 ranges from 293.171 to 607.827 ms and p99 from 496.442 to 801.599 ms. Two selected exact stored-ID first callbacks are 262.136–262.395 ms. Independent cleanup/absence passes.

These are single ordered cells on a shared host with different tenant distributions and resulting work. The lower observed tails do not establish a general hot-tenant advantage, an optimization gain or a safe universal offered rate. Each tenant still has one realtime owner. Connection coverage at prime/end is separate from the sparse one-tenant frame witness and does not prove continuously complete connection coverage.

### Sustained idle window and its opportunity limit — reproduced

Cell `n32-idle310-a07` preserves 32 tenants, seven offered requests/s and a 60-second load window, extending only idle from 30 to 310 seconds. It completes with 425 ordinary responses, 117 accepted = stored writes, zero uncertainty, zero HTTP failures/drops and native count control GREEN → RED → GREEN. Readiness, idle safety and known received-input opportunity checks pass; the load observation records 32 known completed final opportunities and 82 work completions. All 64 clients prime in 1,130 ms. Independent absence passes.

The idle result remains TIME_NOT_EXERCISED for all 32 tenants, with zero completed time cycles and no native time witness. Actual inspection declares `sgv-recent-10`: due times are 525.442–542.344 seconds after the first idle observation and still 212.837–229.739 seconds after the final observation. Thus a five-minute idle window does not cross this fixture's measured timer horizon. This is a valid observed quiet/future-due interval, not a passing due-time-work claim. A separate fresh updated-source window is configured for 650 seconds within the unchanged preparation-inclusive deadline; no capture or clock is extended.

### Updated independent-streaming source — separate qualification

The integration owner supplies a genuine intermediate branch image for app `58ddc1274359af9c393c098026f1e25a828dcc41`, deploy `b728749354275e3ba8119a7190cf9489187ff685`, image `sha256:04ae9570987ac13bdc8ca58b3865b10d19fbbbf226b05ecbb1135171dccf0a15`. Its canonical build/check and actual native image labels match; this is not final application or capacity acceptance. Exact source archives, paired producer/published core loaders and qualified dependency custody pass again in each fresh point.

The earlier helper cannot admit this topology: it omits the independent Go startup role, refuses its resource allocation and requires the Go process inside the evaluator. A locally committed compatibility leaf and rehearsal followup produce helper `3b8a47abbc9e9dfd04fdaa8bdc021ef880403e27`, instrument `d7bf0cce183b420adbdf95e039987ccf87e77c6eb09c72465adfcabd4520dd05`. This lane executes it from its own immutable checkout; no running point changes helper. Source capability and experiments remain separate from future batch-runner work.

Fresh configurations explicitly select `external-service-v1` and `local-diagnostic-external-pgstream-4cpu-8g-v1`. Evaluator Node at 125 millicpus / 256 MiB plus Go at 125 millicpus / 256 MiB replace the earlier combined 250 millicpus / 512 MiB. The conservative whole-roster limit remains 3,875 millicpus / 8 GiB containers plus 1 GiB host V8 heaps; no additional resource is omitted or granted. Actual native startup checks prove separate source/image-bound containers at the declared quotas. Workload adequacy is measured, not implied by fitting that envelope. The topology and per-process allocation differ from the earlier image, so cross-image latency differences are not a causal optimization comparison.

Updated tiny `updated-n2-a09` completes with 216 ordinary responses, zero HTTP/transport failures/drops, 60 accepted = stored writes and zero uncertainty. Native count control is GREEN → RED → GREEN. The supported rehearsal's generated-program missing-base control produces `ERR_INVALID_URL` before network I/O, then the unchanged generated program runs. Four clients prime in 526 ms and remain connected at the end; selected completed-output proof passes and two exact stored-ID first callbacks are 59.243–59.591 ms.

Readiness and short-idle safety pass. The final known-opportunity verdict remains UNMEASURED: one tenant completes its final target and one remains pending, despite 41 observed work completions and all-roster health PASS. This is distinct from no completed acquisition or stalled startup. The canonical resource reduction is complete across ten services including separate evaluator Node and Go process counters. Independent exact absence passes. These are supported tiny observations, not broad clinical equivalence or accepted capacity.

The updated 32-tenant cell `updated-n32-r60-a10` completes its 60-second window at 60 offered requests/s with 3,605 ordinary attempts/responses, 984 accepted = stored writes, zero uncertainty, zero HTTP/transport failures and zero drops. Native count control is GREEN → RED → GREEN. All 64 clients prime in 1,387 ms and remain connected at the end; selected completed output passes, with two same-ID first callbacks at 368.054–368.333 ms. Global HTTP p95/p99 including JWT setup are 988.196 / 1,373.167 ms; ordinary per-shape p95 ranges from 844.674 to 1,303.262 ms and p99 ranges from 1,105.020 to 1,596.726 ms. Independent absence passes.

All-roster health passes, but final known-opportunity completion is UNMEASURED: all 32 final targets are KNOWN_PENDING despite 246 observed work completions. The pending final revision is not equated with no-work startup failure or promoted to completion. The separate time-demand experiment observes a quiet interval instead of continuing writes; it retains its own source and original deadline.

Resource attribution includes observer cost. In this updated 32-tenant load cost window, evaluator container CPU averages 0.12289096 cores, while the stable primary Node process averages 0.07235652 cores. An additional MainThread lacks a matched process bookend, so its CPU is UNMEASURED. Inspection collector wall time is 30.266193 seconds; it is neither process CPU nor a number to subtract from container CPU. The container total remains valid but cannot alone identify an application-code bottleneck or quantify the observer's CPU share.

### Updated due-time observation and separate client refusal — reproduced

Fresh `updated-n32-idle650-a11` uses the same updated tuple and resource profile, with a requested 650-second idle followed by seven offered requests/s for 60 seconds. The captured idle cost window is 661.102 seconds. All 32 tenants classify as TIME_EXERCISED with 32 completed time cycles and idle-safety PASS. The canonical `timeWitness` flag remains false: the current assessor assigns false even when time work is observed. This record preserves that flag and the assessor's sampled-idle-safety scope; it does not convert the counter observation into broader native or clinical qualification.

After that quiet interval, only 16 of 64 requested clients prime; 48 remain dark and are disconnected by the server. Priming takes 60,691 ms. The retained bounded server summary records 48 `REALTIME_UNAUTHORIZED_DEADLINE` disconnects. End connection coverage is also 16/64. The realtime capture retains the exact cause line but truncates the general tail: 730,346 observed bytes and 57,459 retained, including 115 cause bytes. It cannot prove absence of another earlier cause.

Read-derived source meaning at this exact app commit, `lib/server/realtime/protocol.js:443–447`: the deadline closes a socket with no authorization answer and no authorization request marked pending; pending authorization re-arms the timer. The generated probe's HTTP agent has unlimited maxSockets and emits authorization on connect. Why an authorization answer is absent remains UNMEASURED. Client behavior, scheduling, data age and lifecycle state remain hypotheses for the existing realtime/performance owner, not explanations or proposed fixes. This observation does not explain the earlier different-image 1,000-tenant failure.

Other observations remain valid: 425 ordinary attempts/responses, 117 accepted = stored writes, zero uncertainty, zero HTTP/transport failures/drops, and native count control GREEN → RED → GREEN. All-roster health and all 32 final known opportunities pass, with 76 observed work completions in the load interval. Selected output proof passes for the exercised tenant, with two same-ID callbacks at 388.330–389.675 ms; those callbacks do not qualify the other clients. Global HTTP p95/p99 including JWT setup are 107.075 / 387.584 ms. Discovery records COMPLETED / MEASURED while retaining incomplete connection coverage. Exact independent absence passes.

### Selected service and SQL costs — reproduced

Each service cell below is **mean cgroup CPU cores / end cgroup memory.current MiB**. These are resource bookends over the listed cost window, which includes observation work and differs from nominal request duration. Memory is charged cgroup memory, not process RSS, JavaScript heap or a peak. Earlier evaluator cgroups contain Node and Go; updated rows separate them. Container totals include inspection processes; stable primary-process counters and missing process births remain separate in the retained packet.

| Cell / phase | Cost window s | API | Evaluator | Go service | Realtime | PostgreSQL |
|---|---:|---:|---:|---|---:|---:|
| `n2-a01` / load | 36.521 | 0.0840 / 103.57 | 0.1072 / 86.57 | inside evaluator | 0.0514 / 83.53 | 0.1014 / 250.73 |
| `n32-r7-a02` / load | 67.490 | 0.0833 / 113.62 | 0.0905 / 97.33 | inside evaluator | 0.0485 / 91.03 | 0.1135 / 310.82 |
| `n128-r7-a03` / load | 70.607 | 0.1057 / 133.97 | 0.0980 / 114.77 | inside evaluator | 0.0570 / 115.67 | 0.1467 / 310.67 |
| `n32-r60-a05` / load | 73.571 | 0.2582 / 133.54 | 0.1957 / 119.39 | inside evaluator | 0.0829 / 99.77 | 0.3865 / 342.17 |
| `n32-r60-hot10-a06` / load | 70.205 | 0.2691 / 127.47 | 0.1798 / 129.39 | inside evaluator | 0.0748 / 99.59 | 0.3750 / 350.11 |
| `n32-idle310-a07` / load | 69.082 | 0.0868 / 105.80 | 0.0891 / 105.27 | inside evaluator | 0.0492 / 70.12 | 0.1150 / 329.70 |
| `updated-n2-a09` / load | 42.815 | 0.0827 / 104.52 | 0.0965 / 66.43 | 0.0025 / 22.62 | 0.0520 / 58.29 | 0.0996 / 246.27 |
| `updated-n32-r60-a10` / load | 84.305 | 0.2493 / 120.89 | 0.1229 / 89.30 | 0.0056 / 34.41 | 0.0665 / 93.97 | 0.3282 / 297.73 |
| `updated-n32-idle650-a11` / idle | 661.102 | 0.0398 / 73.88 | 0.0511 / 82.44 | 0.0009 / 17.59 | 0.0410 / 59.57 | 0.0601 / 218.56 |
| `updated-n32-idle650-a11` / load | 77.091 | 0.0798 / 108.62 | 0.0854 / 71.73 | 0.0036 / 19.95 | 0.0770 / 90.89 | 0.1523 / 245.41 |

SQL calls and execution time below use the canonical role-counter bookends. Statement-attributed WAL uses its separate bounded counter snapshot; it is a sum of per-statement WAL fields, not physical WAL-device volume. The statement sum does not establish physical WAL volume. Collector traffic is included; SQL execution time is not CPU time. Exact bookend bounds, per-role values, sampled waits and missing instruments remain in the packet.

| Cell / phase | SQL calls | SQL execution ms | Sum of statement WAL bytes |
|---|---:|---:|---:|
| `n2-a01` / load | 10,943 | 949.115 | 548,624 |
| `n32-r7-a02` / load | 26,706 | 2,671.221 | 997,641 |
| `n128-r7-a03` / load | 40,591 | 4,368.711 | 1,659,664 |
| `n32-r60-a05` / load | 151,599 | 27,710.876 | 7,686,121 |
| `n32-r60-hot10-a06` / load | 148,333 | 19,913.767 | 7,423,586 |
| `n32-idle310-a07` / load | 26,771 | 2,660.257 | 1,118,796 |
| `updated-n2-a09` / load | 10,817 | 947.764 | 507,966 |
| `updated-n32-r60-a10` / load | 141,495 | 17,839.162 | 6,311,082 |
| `updated-n32-idle650-a11` / idle | 44,141 | 4,138.066 | 280,763 |
| `updated-n32-idle650-a11` / load | 39,894 | 3,506.125 | 1,828,455 |

The interrupted 180-request/s point has no complete canonical cost reduction or final HTTP accounting. Its separately retained pressure receipt and partial native-sample readback remain observations, not zeros. Wire-byte costs and pure evaluator execution lag remain unqualified where the existing instruments do not measure them.

### Packet closure and next owner

Ten fresh local points are closed: eight runner COMPLETED, one COMPLETED_PARTIAL and one FAILED_PARTIAL. Those status counts do not count clinical or capacity passes. Every point has independent project-label/namespace/process-birth/group/host-heap absence PASS; this lane owns no live actor, guard, lease or paid resource. Original inputs/results remain unchanged and ignored.

Retained evidence identifier: `externals/work/local-operating-envelope-20261115`. Its immutable selected readback/index is `local-envelope-packet.json`, SHA-256 `161ac7181015219fcfe4b285f7a034dc656e67239e6c8468585ae365ecc0f044`; it binds selected canonical artifact checksums, exact source/helper/cadence, original clocks, controls, costs, unknowns and independent absence. The evolving local handoff remains `externals/work/HANDOFF-local-operating-envelope-2026-11-15.md`. No raw output is committed.

The existing realtime/performance owner accepts the focused read-only diagnosis of the long-idle authorization-deadline gap. Integration owns the final source, any focused repair and the one coherent final acceptance campaign. A separately discovered future notifier-configuration correction is outside these frozen tuples and does not rewrite their observations. The existing batch-tooling owner owns future bounded experiment reuse. No additional point, source fallback, deadline extension, capacity promotion or comprehensive application campaign is claimed here.


## Single-host low-rate baseline and larger-roster preflight — 2026-11-15 Pacific

The reproduced fixed-v1 point `single-host/n32-r7-02-point` completes readiness, idle and load checks. It uses historical app `7e6b2cf77a66049bb0d88c1605ae7703789f070f`, deployment `16133d9d33993b08fd81a318e8d30be123051ae7`, qualified image `sha256:4d07a97f408ff5dc173557f5255ff94d0babfb11c072f50925e6e9b3eefccfcc`, helper `b2ac402ed6efd8e5f5cddc72787d7a0023d55be9` and instrument `d9034e875fbfc9782746a3181d933085bf0aa436cf3ecadca451c5596c5c6c93`. This historical image predates the realtime late-close repair and heartbeat retirement. It does not qualify the current candidate.

The shared-host window has 32 synthetic tenants, one polling viewer each, one API/evaluator/realtime process, ordinary 7 offered requests/s, 30 configured idle seconds and 60 configured load seconds. All 32 tenants receive ordinary writes during load; there are no ordinary writes during idle. Existing role IPC uses UDS; Go-to-evaluator delivery uses Compose bridge HTTP. The existing external-service resource profile keeps evaluator and Go at 125m CPU/256MiB each, within its aggregate 4CPU/8GiB envelope plus 1024MiB declared host V8 heaps. The original finite clock includes preparation; it is never extended.

| Reproduced observation | Result and limit |
|---|---|
| Ordinary accepted/stored oracle | 117 accepted = 117 stored; zero uncertain; one separately accounted accepted/stored sparse probe |
| Evaluator progress | Load completed-work delta 80, minimum 2 per tenant; no failed completion delta. This is all-roster progress, not a final floor for every ordinary write. |
| Idle | PASS with all 32 classified `FUTURE_DUE` / `TIME_NOT_EXERCISED`; time-work witness false |
| Clients | 32/32 primed and connected at end; zero server disconnects; one expected sparse frame delivered |
| Sparse latency witness | One request-to-client frame at 516ms; durable observation bracket 0–1108.048ms. No population percentile or pure executor-lag claim. |
| Driver | 425 scenario iterations; zero dropped iterations and HTTP failures; k6 sampled mean/max CPU 1.002%/1.37% |
| Cleanup | Runner ABSENT and independent exact project containers/networks/volumes, recorded process births/groups and heap marker all absent |

Captured cost windows include collector work and exceed the configured sleep/load intervals. Memory is end-of-window cgroup usage, not peak heap. SQL statement WAL is collector-inclusive, not network bytes.

| Cost | Idle, 47.889s | Load, 76.837s |
|---|---:|---:|
| Serving-role CPU, mean cores | 0.4585 | 0.5565 |
| Serving-role end memory, bytes | 868634624 | 929505280 |
| Evaluator CPU, mean cores | 0.09829 | 0.09359 |
| Evaluator throttled / counted periods | 354 / 410 | 529 / 636 |
| Go CPU, mean cores | 0.001441 | 0.002545 |
| SQL calls | 3670 | 28446 |
| SQL statement WAL, bytes | 5664 | 1274269 |
| Three progress-collector calls, total seconds | 21.455 | 22.258 |

Aggregate headroom does not establish evaluator-container quota headroom. The container includes its observer. The stable primary Node process records 1.04 CPU seconds during idle (0.02172 mean cores) and 2.58 during load (0.03358); another process lacks a complete identity-matched CPU interval. These observations do not permit causal subtraction of every observer cost. The container frequently throttles while the observer starts Node inside the same quota. This point does not isolate the cause. Retained evaluator/Go log tails contain no heartbeat-stall match; their bounded retention does not prove continuous absence. The earlier preparation refusal `M7_DEPENDENCY_REUSE_TOOL_PROVENANCE` came from ambient Node22 versus the receipt's Node24.22.1/npm11.19.1 paths and hashes. It started no application services and closed with absence PASS. Fresh preparation used the recorded tools without weakening provenance.

Larger-roster preflight is source-only. The archived current app `1ce665d326616be0ee683f75953f65dae150201b` / deployment `b26c415e39fe96b09627977467afc68b3c7836ab` existing configuration generator completes at 32/1000/10000 tenants under a 256MiB V8 cap. At 10000 it produces 796253 document bytes, with maximum RSS 160072KiB. A 10001 selection refuses; restoring 10000 passes. These figures do not measure bootstrap or runtime capacity.

The actual existing observer JavaScript, with recording I/O, emits 79 unique pages covering all 10000 tenants, reads its environment once and creates one client per instance. The existing Python reader accepts full coverage and rejects an omitted final page with `M7_EVALUATOR_PROGRESS_COVERAGE`; restoration passes. One evaluator needs 8/79 pages per round and 24/237 queries per three-round phase at 1000/10000 tenants, below the existing 1024-query bound. Real RPC/Node startup, the unchanged 15s round deadline and effective container/driver FD headroom at these counts remain UNMEASURED. Current host soft/hard open-file limits are 1048576; this does not establish every future container's effective limit. NGINX configuration declares 65536.

At this capture, the producer required at least one viewer per tenant. A larger point can measure that coupled workload honestly; a quiet-roster-only interpretation is unsupported. k6 JWT setup retains its existing serial default, optional bounded concurrency and 300s setup deadline. The probe uses 16 JWT workers, 5ms socket-open staggering and a 600s prime bound. These declared limits are not measured large-count passes. Keep request rate, actual write-active tenants, viewer total, bootstrap/prime time and collector cost explicit. The next native point must use the runnable heartbeat-retired candidate and a meaningful larger cohort; no repeated identical 32-tenant point or extra acceptance campaign is implied.

Retained evidence home: `externals/work/performance-enhancements-20261115/single-host`; evolving handoff: `externals/work/HANDOFF-performance-enhancements-2026-11-15.md`. Canonical summary SHA-256 `69e62a52a03e52ac7abd13af2fc9a8730b09e42fd53de43d57f48fe9f2867059`; independent absence `ccc66ac1c6c9454d70f0e3965bf622ed3e4ee2c0620cd16aa4d931ba95603a8f`; selected cost reduction `78866e89a30fc008de97395648fce357fe47fc032467c57533db84cc693b9c96`. Captures remain unchanged and outside Git. No capacity acceptance, paid allocation, push or release is claimed. Source integration and one final acceptance remain with 51f6; freshness owns heartbeat retirement.

The next helper removes one reproduced observer startup cost: it reads the same existing `lib/pool-membership/config.fromEnvironment` contract directly, rather than loading `serve/evaluator-config` and its clinical/settings graph solely for `partitionFor`. Five alternating cold host-source pairs on the pinned historical source load 526 versus 2 modules, use 234548–261972 versus 6159–7204 microseconds CPU, and peak at 89540–93152 versus 50500–50624KiB RSS. This is source-only module cost, not a native quota or heartbeat-causality result. Seven actual parser cases preserve three valid selections and four refusals. Fifty focused checks pass with the actual product fixture enabled. Restoring the heavy import makes that fixture fail `M7_EVALUATOR_PROGRESS_UNAVAILABLE`; restoration passes. RPC source/endpoint binding, instance checks, paging, byte/query/deadline bounds and health criteria are unchanged. The next native point must independently measure its effect. Documentation links pass; queue-check refuses existing missing ignored gate worktrees (including `externals/work/nc-jitter` and `externals/work/crm-m6b-join-20261110`), so no queue-check pass is claimed.


## Independent tenant roster and viewer total — 2026-11-15 Pacific

The harness now supports sparse and zero viewers through the existing discovery
runner. Tenant roster size and total polling viewers are independent. The
[runner contract](../../../tools/mt-bench/m7-joined/RUNNER.md#configurable-discovery-and-strict-remote-reporting)
defines the single declared total, deterministic mapping, legacy defaults and
zero-frame classification. This helper change needs no application image build.
Strict remote preset admission and source/image/deadline/budget bindings remain.

Reproduced source controls execute the actual generated public JavaScript probe
under Node v22.23.4 with in-memory HTTP, Socket.IO and filesystem ports, then feed
its output to the actual Python reducer. They exercise complete roster parsing,
actual emitted bindings, prime/end counts and per-write frame expectations:

| Synthetic tenants | Declared/emitted/primed/end viewers | Accepted probe writes | Expected/delivered frames | Frame evidence |
|---|---|---|---|---|
| 5 | 2 | 4 | 2 | PASS |
| 5 | 7 | 4 | 6 | PASS |
| 5 | 0 | 4 | 0 | NOT_EXERCISED |
| 3 | 17 | 4 | 23 | PASS |
| 10000 | 1 | 4 | 1 | PASS |

The 10000/1 row is a generated-JavaScript-to-Python reducer round trip. It does
not run a native socket server, database, evaluator, application image or remote
host and establishes no runtime capacity or large-count deadline claim.
Missing, extra, foreign, duplicate and wrong-tenant viewer bindings refuse.
Mutating both reported expected and delivered frame totals to the same wrong
value also refuses. An actual emitter ablation restores the old per-tenant loop:
it emits 10 viewers for the declared 5/7 case and fails `M7_VIEWER_BINDINGS`;
restoring the total-based loop passes. A separate selected clinical fixture
checks durable output with zero connected clients and reports client frames as
`NOT_EXERCISED`; missing or foreign client identities refuse.

Final focused verification: 390 joined-helper tests complete with 4 skips and no failures; 84 remote
helper tests complete with 1 skip and no failures; 27 deployment calibration/topology
tests complete with 2 skips and no failures; the paired worker/helper test passes. Enabled caller-to-worker-to-cell
checks cover independent totals 2, 0 and 53 at 37 tenants. Those checks inspect
the real parser and request/receipt binding but replace `adapter.prepare` before
effects; they do not qualify generator dependency production or native admission.
The selected clinical/database fixtures now declare their actual one-tenant
roster instead of claiming 1000 tenants for one row; incomplete clients fail at
the earlier binding guard. No clinical expectation was weakened.

Retained synthetic evidence uses the existing home
`externals/work/performance-enhancements-20261115/single-host/viewer-load/`.
`generated-runtime-results.json` SHA-256:
`4345b95dfa57269c62daf3d6307a937ca4c7b22ec7a0904556e81492f1b76dcc`.
The full focused logs and the deliberate emitter break/restore remain outside
Git. Queue-check refuses missing ignored gate worktrees, starting with
`externals/work/nc-jitter`; it is not a pass. The first sandbox-only checks also
refused `listen EPERM` and `spawnSync git EPERM`; required loopback checks pass
with native tool access. Existing captures and frozen remote clones are unchanged.
51f6 owns integration and final acceptance; the remote owner owns all allocation,
export, finite custody and cleanup. A later source-matched native point must
measure larger-roster bootstrap, SQL, observer deadlines and actual delivery.
