# Final joined REST/pgstream local A/B — 2026-11-13

**Reproduced:** the coherent joined candidate reduces API-role SQL work, improves overload throughput and lowers read/write latency while passing the issued-request correctness checks. Both variants fail to sustain the offered 120 requests/s at the fixed virtual-user bound. This single sequential local pair measures the joined REST and pgstream changes; it does not isolate auth simplification or establish multitenant capacity. Root owns the separate 1000-tenant run and full joined acceptance.

## Source, image and matched envelope

| Input | Baseline | Candidate |
|---|---|---|
| Core | `e90ad574ab9cdf1145d8a3841eef6dad23aa7390` | `311ac50023d95815540cc7e718ebffb6eb933b8f` |
| Immutable app image | `sha256:bfc1a2faa85bef412eb8cbc853376eeb622732cd3d6801bc1b157ead32c3179b` | `sha256:53025be8dcd8cee60a4f0bab9db30665f350c41a23382812b41f4f738b01b7e5` |
| New owned project | `ns-rest-final-baseline-20261113` | `ns-rest-final-candidate-20261113` |

Deployment is `883c516bc2b60a66ef5ae8e211cff4955449fea6`. The sole canonical candidate image was qualified against committed source and deployment bytes; image labels/binding, Node24.22.1 and the pinned pgstream checksum were checked. Existing images/tags were preserved. The [REST functional capture](admission-batch-functional.md) describes that source capability; root joins it with the pgstream changes.

The runtime owner released one whole sequential local timing window after builds/native checks stopped. Each fresh fixture has two tenants, 288 synthetic SGV records per tenant at five-minute spacing, one API and normal evaluator/pgstream/realtime/PostgreSQL/Vault roles. Diagnostics are off. Controls precede ten-second warmup, then 30 requests/s for 45 seconds and 120 requests/s for 60 seconds. Writes have initial=max32 virtual users; reads initial=max128. Offered mix is one write per five reads. No sockets, restart, acceleration, retuning or retry was added. Baseline was stopped before candidate allocation.

REST helper source remains `08d96402ff363c2b42f65938b86c9b3d34ac42ad`; later alignment commits record evidence only. Workload SHA-256 `64cb3427fca57a78ae155614dfa09a07b9b1ca300973e1a47bfa83649ad6be72`. M7 helper `9ad52a3364d9175d5b4ba372766b204753dab14c`, content `a135a49f5a40d6cfe0d90cbce2adeb2209301aa40bd2d6b569ce3605c560cdab`, includes host I/O. PostgreSQL image `sha256:21e7e1665c3dd2fdd80ebd9ce6d36fb160d6a4129683b315b6492a71d87bfda7`; k6 image `sha256:eeb0db19cd8d263aa57346cdbc7ea18e6fcfb2ba9497746a7ae82ceefc8c9fa5`.

Same host, cadence, diagnostics, PostgreSQL and settings SHA `ad9ab32b5cf610f91c863e8782a7bf6fdf9e4b2923a72112c4a74ae7572c6262` are verified. Fingerprint provenance differs only in the declared source commit and `lib/server/tenant-app/rest-context.js` source blob, which the candidate changes. These differences are recorded, not removed from captured metadata. Root's acceptance Mongo fixture and the unowned auth stack remain constant neighbors. This is a shared-host comparison, not quiet-host capacity acceptance.

## Result

| Offered rate | Metric | Baseline | Candidate |
|---|---|---:|---:|
| 30/s | Completed HTTP requests | 1352 | 1351 |
| 30/s | Realized requests/s | 30.01 | 29.99 |
| 30/s | Dropped iterations | 0 | 0 |
| 30/s | Read p95 ms | 63.84 | 51.69 |
| 30/s | Write p95 ms | 78.93 | 53.38 |
| 30/s | API SQL calls/HTTP | 195.40 | 46.06 |
| 30/s | API SQL execution ms/HTTP | 17.10 | 6.41 |
| 120/s | Completed HTTP requests | 2782 | 6516 |
| 120/s | Realized requests/s | 45.03 | 105.48 |
| 120/s | Dropped iterations | 4419 | 685 |
| 120/s | Read p95 ms | 3746.17 | 1762.14 |
| 120/s | Write p95 ms | 4823.74 | 1769.57 |
| 120/s | API SQL calls/HTTP | 195.05 | 45.83 |
| 120/s | API SQL execution ms/HTTP | 24.47 | 9.97 |

At 30/s, API-role SQL calls/HTTP fall **76.4%**, SQL execution ms/HTTP **62.5%**, read p95 **19.0%** and write p95 **32.4%**. At offered 120/s, realized throughput rises **134.3%**, read p95 falls **53.0%**, write p95 **63.3%**, SQL calls/HTTP **76.5%** and SQL execution ms/HTTP **59.2%**. Dropped iterations make both 120/s outcomes failures against offered load. The realized mix differs because drops are per shape: writes are 478/2782 baseline and 1167/6516 candidate.

SQL figures sum statement deltas for role `nsdemo_api`; they exclude other database roles and are not total PostgreSQL CPU. The unchanged frozen reducer passes all four cells' retention/reset checks. Before→after statement-key counts are 3066→3522 and 3522→4481 for baseline, 1898→1903 and 1903→1905 for candidate; every before key remains. The [intermediate pair](local-raw-ab.md)'s missing-key SQL cell stays NO-INSTRUMENT; these new captures do not repair it. Pool queue and auth-stage latency remain NO-INSTRUMENT.

API cgroup CPU ms/HTTP falls 21.51→12.57 at 30/s and 23.37→11.08 at 120/s. PostgreSQL cgroup CPU ms/HTTP falls 48.49→26.41 and 65.32→31.98. These bookend deltas include background work. At120/s the candidate uses more absolute PostgreSQL CPU (mean 2.87→3.29 cores) while completing more requests; per-request cost and absolute resource use answer different questions.

## Correctness, I/O and practical limits

Every issued read passed its content checks. Accepted writes were exactly stored: baseline 226+478, candidate 226+1167; no uncertain/refused writes or invalid/failed reads occurred. Each cell's subsequent evaluator observed/completed/input checkpoint matched its write clock with no pending state, and selected BG-now checks passed. Live controls exercised invalid/foreign credentials, next-request role revocation, the other tenant's continued access, restoration, and a wrong stored value that made the oracle red before restoration. Per-write oracles use retained acknowledgements and actual stored synthetic documents. Native source controls cover private request state and current authority; broader authorization/clinical/lifecycle/browser acceptance remains root-owned.

Activity/lock and host-I/O samples are populated in every cell. At120/s, host iowait is 8.87→7.97%; I/O pressure some/full is 29.22/19.34→23.95/14.25% over first-to-last sampler intervals of about 64 seconds. Device `nvme1n1` writes increase 4.40→8.86MB/s and `io_ms` accounting 17.24→34.44% of elapsed time. These are whole-host counters with 512-byte sectors, not PostgreSQL attribution, device capacity or database I/O latency. The 30/s sampler intervals differ: 46 versus 48 seconds. Background contention, order effects, short durations, different realized overload mix and lack of repeated pairs limit causal/capacity claims.

Both measured projects are **STOPPED_PRESERVED**, each with exactly nine containers at PID0. Volumes, state and logs remain outside Git. Timing was released to root before the 1000-tenant work; this lane performs file-only reduction afterward.

## Retained originals

Private evidence identifier/path: `/mnt/data/nightscout-workspace/artifacts/rest-final-local-ab-20261113`. The immutable selected-input manifest has 216 files and SHA-256 `7f804b1644ed127c5b935903749ff6a3937b196f4fd7dc556ccc5bb77c8832ee`. Full private command directories, source fixtures and state are retained too. `comparison-derived.json` SHA-256 is `905630d221ae521f05e7d05feb70eceb705e6cd44f73678352887f4e333d9652`; `host-io-derived.json` is `3b41be3a28f28daa1307a1a43a575d5173302cd5f9a7e956df7806a27564a040`.

Rate attempts are baseline 30/s `attempt-35o4lxr5`, baseline 120/s `attempt-jps46dc8`, candidate 30/s `attempt-ib7exn77`, candidate 120/s `attempt-bw67vj9k`, each under its named rate directory. Preserve failed overload attempt records and invocation outputs unchanged. Plans, image qualification, pair identity, live controls, raw k6/SQL/cgroup/I/O captures, separate catchup observations and exact stop receipts allow resumption/audit without runtime access. Do not mix these measurements with the [earlier remote pair](remote-joined-ab.md).
