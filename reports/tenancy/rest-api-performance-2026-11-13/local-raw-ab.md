# Raw-route batch — intermediate local A/B, 2026-11-13

**Reproduced:** the raw acquisition batch reduces SQL work at the offered 30 requests/s and improves throughput and latency under overload. Both variants fail the offered 120 requests/s at the fixed virtual-user bound. This is an intermediate comparison; the subsequent admission/allocation batch and joined pgstream changes require the owner's final comparison. It does not isolate the original auth simplification.

## Matched inputs

Baseline core `e90ad574ab9cdf1145d8a3841eef6dad23aa7390`, image `sha256:bfc1a2faa85bef412eb8cbc853376eeb622732cd3d6801bc1b157ead32c3179b`; candidate core `3c6e5a016c7aa0665b4a5fcc6a3ece4f7632b6a0`, image `sha256:dc354794a78d92c3d478d33164544be9419fab3cb93e2711d7609be9fccbca5a`. Deployment `883c516bc2b60a66ef5ae8e211cff4955449fea6` is unchanged. [Source evidence](raw-acquisition-local.md) describes the capability.

Both halves ran sequentially on the same local host, in separate fresh two-tenant projects with 288 synthetic SGV records per tenant, normal API/evaluator/pgstream/realtime/PostgreSQL/Vault services, diagnostics off and no socket workload. Workload SHA-256 `64cb3427fca57a78ae155614dfa09a07b9b1ca300973e1a47bfa83649ad6be72` offers one write per five reads. Each half ran controls, ten-second warmup, 30 requests/s for 45 seconds, then 120 requests/s for 60 seconds. Each rate used write initial=max32 and read initial=max128 virtual users. No tuning or reruns followed failure.

REST instrument is alignment `08d96402ff363c2b42f65938b86c9b3d34ac42ad`; M7 instrument is `9ad52a3364d9175d5b4ba372766b204753dab14c`, content `a135a49f5a40d6cfe0d90cbce2adeb2209301aa40bd2d6b569ce3605c560cdab`. Settings fingerprint `ad9ab32b5cf610f91c863e8782a7bf6fdf9e4b2923a72112c4a74ae7572c6262` matches apart from declared core source attribution. Full pins, commands and project ownership are retained in plan/receipt files.

## Measurements

| Offered rate | Metric | Baseline | Candidate |
|---|---|---:|---:|
| 30/s | Completed HTTP requests | 1351 | 1351 |
| 30/s | Realized requests/s | 29.99 | 30.00 |
| 30/s | Dropped iterations | 0 | 0 |
| 30/s | Read p95 ms | 64.66 | 57.00 |
| 30/s | Write p95 ms | 77.72 | 56.98 |
| 30/s | API SQL calls/HTTP | 195.41 | 61.24 |
| 30/s | API SQL execution ms/HTTP | 17.94 | 7.93 |
| 120/s | Completed HTTP requests | 2768 | 5130 |
| 120/s | Realized requests/s | 44.55 | 82.58 |
| 120/s | Dropped iterations | 4434 | 2072 |
| 120/s | Read p95 ms | 3634.69 | 2222.32 |
| 120/s | Write p95 ms | 4755.07 | 2246.92 |
| 120/s | Complete SQL comparison | measured baseline | **NO-INSTRUMENT** |

At 30/s, statement-key deltas for role `nsdemo_api` give 263993→82729 calls: 68.7% fewer per HTTP request. SQL execution time per HTTP falls 55.8%; this is accumulated statement execution time, not PostgreSQL CPU. Under overload, realized throughput increases 85.3%, read p95 falls 38.9% and write p95 falls 52.7%. These are single sequential local pairs, not confidence intervals or remote capacity figures.

The strict SQL reducer refused candidate 120/s: 347 before-snapshot statement keys were absent afterward, including 191 API-role keys. Stable role/query/database identity also loses those rows; this is consistent with statement-store churn from utility names, not merely representative text changes. No missing keys were treated as zero, no partial totals substituted, and the failed zero-byte derived output is preserved. Pool queue and authorization-stage latency are NO-INSTRUMENT. Activity/lock and host-I/O samplers contain observations; host-wide I/O is not attribution to PostgreSQL.

## Correctness and limits

All issued reads passed payload checks. Every accepted write persisted exactly: baseline 226+469, candidate 226+982, with zero uncertain/refused writes. Each cell's subsequent evaluator checkpoint/clock and selected BG-now checks passed. Controls reproduced wrong stored-value refusal, then restoration, invalid/foreign credentials, live role revocation with the other tenant still admitted, and restored authorization. These checks do not prove all clinical, restore, authorization or concurrency behavior; root owns joined acceptance.

Root-owned competing timed stacks were stopped for both halves. An unowned auth stack remained constant; its custody did not permit stopping it. This shared-host limitation remains. Both measured projects are stopped with volumes/logs preserved; no active REST sampler or load remains. A mutable default image tag was changed during candidate build before explicit immutable-image qualification; the prior default tag is unknown. The tested immutable image was independently qualified without rebuilding, and baseline image identity remained unchanged.

## Retained evidence

Private originals: `/mnt/data/nightscout-workspace/artifacts/rest-local-ab-20261113`, including plan, image qualification, identity check, receipts, attempt directories, SQL/resource/I/O samples, controls and stop receipts. Baseline rate attempts: `attempt-pv4xvni0` and `attempt-8n0k_s3z`; candidate: `attempt-wk0pr106` and `attempt-ixmda8sz` under their named rate directories. Keep the captures unchanged outside Git.

Human-approved independent file-only audit: `data/capacity/pgstream-preflight-20261113/rest-local-ab-independent-audit.json`, SHA-256 `bf293ec47a90d5244850ec4f658b4b6c1a2a3125bcd16153d5da68173de0994e`, contains 136 input checksums and independent control, SQL retention and host-I/O accounting. REST independently re-read the source outputs and the audit. Do not combine these local numbers with the [earlier remote pair](remote-joined-ab.md).
