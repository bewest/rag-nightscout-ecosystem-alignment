# New source-pair strict TIME witness

Reproduced 2026-11-12: the exactly-once post-clinical/pre-export observation passes
the CURRENT strict v2 successful TIME checker on the new primary image. The actual
collector process returnCode0 was recorded directly by its owned supervisor.
This is a short native functional witness, not a pilot/capacity/load/restart,
clinical-output or continuous deadline acceptance claim.

## Exact attribution

- Core761e8f19373c4fbbd6fc888b51b35c9b2eb677a1.
- Deployment31565abe437ea84214aa0068f75de1246c06e45e.
- Actual image sha256:2ad267c7fc382597085c369eb838e8e360ec9c17770d7581c2ad4af240a5241d.
- Instrument502b46b05bc9a581d2c371f18f7e0e71852f0578; content
  52c76f7500312bc3ce8006f3783444b04489bdf53cd1f764417f77cf8333ba1d /37 files.
- Fresh source project, nonce1f412947-27e2-4ef3-8e4d-5c71b62792dc;
  owned-marker SHAe93d2eac9d3d346b14be973ca14883769d4e75256137f57c2b2f11378f35924e.
- Actual post-clinical selected spec SHAa3451a879202cf9402352ec6287fe18fb7ba9423f20ba6e19c386968e821c66f.
- Executed driver SHAd91a94e2630c5313e80d4452ac387ed7d542c58341461b47d384cb9adebfda9c;
  supervisor SHA5db259d1bacddeac468ffa2ea1b0eb486d53dc43c05380a4537e79db9009a334;
  unchanged helper SHAc9e0370e8a3ca4d08dfd70b1290a36a0d57f33c34f3a5639a2e6d81b77b707e8.

RT explicitly released a stable no-write pause after its clinical2→3 sequence and
before export. This lane selected current CIDs/StartedAt/image/project/service,
not old startup identities, then made exactly3 snapshots10s apart and9 bounded
private RPCs. Container/runtime identities and ownership generations stayed stable.
No writes, work triggers, public HTTP, settings/membership/lifecycle actions,
retries, extensions or forced cadence occurred. No resource queries followed release.
No quiet/stock/realtime-move observation was repeated by this lane.

## Observed rows and outcome

| Owner | Acquisitions | Successful TIME | Legacy cycles | Failures | Generation |
|---|---|---|---|---|---|
| A/evaluator-2 |1→1|379→399 (+20)|380→400|0→0|10 stable|
| B/evaluator |1→1|379→399 (+20)|380→400|0→0|10 stable|

The observation took21.309256474021822s,9RPCs/20086 response bytes. Parallel-round
collection wall time summed to1.2759905229322612s; this is collector overhead,
not CPU or capacity. All2 synthetic IDs on all3 evaluator instances are retained
in every snapshot:18 rows including12 foreign observations. Foreign counters
remained unchanged, even where earlier ownership left nonzero historical counts.
Both admitted owners were ready/code-null/alert-null; successful TIME delta40,
minimum owner delta20, failure delta0. Captured dueAt/dueReason, helper observedAt
and actual UTC read brackets are unchanged in the evidence. Both owner reasons
were slow:alarm-message. Sparse snapshots do not prove a strict deadline SLO.

The [raw wrapper](strict-time/observation.private.json) SHA is
10398cd98e94799bd71d3b405b883bfc426b3f387de0b1c80fe0b57ecc8a89d0;
deterministic gzip SHA90a601a84e9d8eb45acaa9b6b8b6f1cffedb676420dcece1a06ed628f586da5e.
Decoded gzip equals the raw bytes. The native receipt selects `/proof` in this
wrapper; [native-time-expectation.json](native-time-expectation.json) pins the exact
new source/deploy/image/instrument/two tenants/three services. Its artifact path
is relative to strict-time/. No old399/ff capture was relabelled.

[process-result.private.json](process-result.private.json) records the actual
collector process returnCode0, wall start/end, driver/spec/stdout/raw SHA. This
number comes from subprocess completion, not inferred from a proof/TAP marker.
The supervisor's original stdout is also retained. Every actual RPC command
record separately retains its observed returncode/byte/time/stderr digest.

## Focused controls and boundary

Existing strict verifier and native_time_witness gate independently recompute the
captured result. Nine offline mutations of actual rows/wrapper refuse stalled
owner, hidden failure, foreign work, missing foreign row, runtime reset,
generation reset, invalid due scalar, wrong image and historicalv1 downgrade.
Exact restoration passes after every mutation. The stalled mutation is an offline
captured-row control, not a stopped live worker. No extra live capture ran.
Recording-only driver controls cover positive/zero-work/nonce/exact-once paths;
separate spawned recording controls retain supervisor exits0 and7 and refuse
repeat launches. They supply no native result or accepted application exit.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 controls.py "$EXACT_502_INSTRUMENT_ARCHIVE" strict-time/observation.private.json
```

The archive must contain tools/mt-bench/m7-joined and
 tools/queue/gates/m7_joined_receipt.py from the exact502 commit. All37 current
instrument hashes were checked before collection; its exact owned archive is
retained privately for offline recomputation after the coordinator advances.
Private originals remain0700/files0600. Published evidence has synthetic IDs and
bounded operational metadata only, no credential/config contents. Root owns
full-source/enabled-corpus/prcheck acceptance and policy approval. RT owns image
export and its separate qualification record; this TIME PASS does not close
those criteria or claim new stock/realtime-move execution.
