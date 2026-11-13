# Discovery observation repairs: B750 and B1000

**Reproduced instrumentation defects; fixed on alignment branches.** Both
original B runs remain failed/PARTIAL under their executed instrument. Neither
this record nor the prospective classifiers grant capacity acceptance. Captured
originals remain outside Git. The earlier status-body SDK defect and its actual
cached-k6 controls have their own [record](../m7-discovery-fingerprint-2026-11-12/README.md).
This is the single home for the two B observation defects, not a load-curve comparison.

## Original boundaries

Both runs selected application core
`9db0ce94f072c8f34aab889f0181afa4269a6758`, deployment
`d76ef17878edb610cdeae75aeef9c07f94b60753`, image
`sha256:293a5c531faac6c156305159246e39defd2592612c302af275efe807102a6d3e`,
and the feb instrument in the source-history table below.

| Retained run | Observed refusal and scope |
|---|---|
| `discovery-reference-20261112-b750` | Before HTTP load, `M7_EVALUATOR_IDLE_TAIL_OPPORTUNITY` was UNMEASURED but discovery marked it hard. The selected final pending row had job masks **0,0,1**, successful TIME **0,0,0**, legacy bodies **1,1,1**, acquisitions **1,1,1**, failures **0,0,0**. No successful completion was captured for that obligation. This is missing timing/work evidence, not positive unsafe clinical output. |
| `discovery-reference-20261112-b1000` | After load/recovery, `M7_DISCOVERY_WRONG_DATA` arose at exact probe equality: **64** stored probes versus **45** acknowledged, **19** extra single rows, no missing acknowledged probe row. The probe recorded **100** failed responses without per-tenant status/uncertainty. All available k6 per-tenant and domain count bounds passed. That does not establish correctness of the extra probe rows. |

B1000's settings fingerprint had **216** observations, **0** invalid and **0**
mismatched. Its separate evaluator load failure and unavailable recovery proof
remain recorded outcomes. Neither successful process exits nor a valid settings
fingerprint overrides those findings. The original count function threw before
saving its returned oracle; the stored-count capture itself was retained.

## Mechanisms and prospective repairs

**B750 classification (reproduced).** The actual idle guard correctly refused
an unproven tail opportunity. Discovery lacked that typed UNMEASURED boundary in
its observational route and stopped before load. `d21a43804267bef2b74e00477af19400fd5f8289`
allows that specific incomplete observation to remain UNMEASURED while bounded
load proceeds. The same code with verdict FAIL remains hard. It also handles
one/two captured progress rounds only after validating actual phase, identity,
roster, available-round integrity, counter/generation stability, foreign rows,
clock evidence and query/byte bounds. Zero/extra rounds or invalid provenance
remain hard. There is no generic UNMEASURED waiver or strict-assessor change.

**B1000 accounting (reproduced oracle defect; individual responses UNKNOWN).**
The generated probe counted every non-200 response as failed and exported only
acknowledged per-tenant totals. A timed-out response or a 5xx may follow a commit;
exact stored equality is then unsound. The saved B1000 capture lacks the statuses
needed to classify each of its 19 extra rows. A source-derived attempt projection
is corroboration, not a substitute for missing per-request evidence. No original
row is retroactively declared an uncertain commit, a valid effect or corruption.

`3a35d21b074f66d38a62ecae4885af8587be1d79` adds a discovery-only v2 ledger:
attempt recorded before HTTP, exact run/roster, per-tenant accepted (200), uncertain
(0/5xx), refused and pending counts, conserved attempt totals, admission closure
before awaiting writers. A complete proof requires closed admissions and no
pending callbacks. An interrupted/open ledger remains UNMEASURED. Status-0
server work may still finish later: this is an observed SQL count bound, not a
claim of server-side quiescence.

Discovery checks each tenant's probe `ACK <= stored <= ACK + uncertain` alongside
workload/domain and tenant-scope checks. Another tenant's uncertainty grants no
allowance; definite refusals grant none. Missing known ACKs, out-of-bound extras,
foreign rows and malformed metadata still refuse. Legacy ACK-only metadata cannot
supply an upper bound: missing uncertainty yields probe-specific UNMEASURED, never
GREEN or invented zero. Count findings, stored counts and bounded diagnostics are
saved before a hard refusal; existing resource reduction reads captured files on
that path. There is no added count SQL. Invalid source/ownership admission still
prevents querying.

**Counter validation (reproduced).** The shared legacy metric helper defaults
missing count fields to zero and permits nonfinite values. Discovery now uses an
explicit accessor in `af1bd379f4d4345c7c423668b7a6442ff82efeff`: absent row/count,
including `{}` or nested empty `values`, is UNMEASURED. Boolean, fractional,
nonfinite, negative, malformed or unsafe counts refuse before SQL. Valid finite
integral numeric counters are preserved. The shared acceptance helper is unchanged.

The [source contract](../../../tools/mt-bench/m7-joined/README.md) owns the precise
current format and bounds. Implementation and controls:
[count proof](../../../tools/mt-bench/m7-joined/discovery_counts.py),
[probe ledger](../../../tools/mt-bench/m7-joined/probe-accounting.cjs),
[generated adaptation](../../../tools/mt-bench/m7-joined/probe_discovery.py),
[count controls](../../../tools/mt-bench/m7-joined/test_probe_counts.py),
[discovery producer controls](../../../tools/mt-bench/m7-joined/test_discovery.py),
[typed classification controls](../../../tools/mt-bench/m7-joined/test_discovery_classification.py).

## Executed controls and limits

| Control | Result |
|---|---|
| Actual B750 raw through producer seam | Prior feb control exit **1**, candidate/restored **0/0**; load invocation follows only the correctly classified incomplete boundary. No paid run replay. |
| Actual B1000 captures through count functions | Prior d21 throws WRONG_DATA; repaired/restored return **UNMEASURED**, not GREEN. No database queries or recovered per-request statuses. |
| Actual generated HTTP request/callback | Finite Node loopback fixture with in-memory synthetic persistence: committed 503 and delayed response→0 retain uncertainty; 200 retains ACK; 403 is refused with no allowance. Attempt persistence precedes HTTP. Server/agent/connections close in finally. No PostgreSQL/application qualification. |
| Focused source batch | **46** tests passed: count ledger, actual callback, discovery producer, typed classification and source contracts. |
| Five semantic mutations | Misclassifying uncertainty, dropping before-effect persistence, global uncertainty leakage, lost refusal diagnostics and pending promoted to complete each fail (exit **1**); restored accounting suite **7** passed (exit **0**). |
| Counter follow-up | **4** focused tests passed. New missing/invalid-field controls fail on actual 3a35 (exit **1**) and pass after restoration (exit **0**). A direct nonfinite control makes old 3a35 return GREEN with one query; final af refuses COUNTER_INVALID with **0** queries. |

No product/runtime, workload cadence, seed, strict idle policy, strict native
work function or default acceptance oracle was changed. The entire gate remains
`dba87b881dee06e54e7768210bd457ce809607d1f7697614f9b0e287f9103488`.
The count/reduction changes add no SQL. Source controls do not replace native
correctness, physical resource qualification or a future measured load result.

## Source and retained provenance

Instrument hashes below were independently recomputed from committed Git blobs,
including the four reused workload/probe files. They are separate identities.

| Source commit | Instrument SHA-256 | Files |
|---|---|---:|
| `feb9f3f550233f7bac5974b70df722a0cdec215d` | `11343639dab11dadc02c4bf2fbedd37bf47facaf0aae0741f5ffef6591a163f2` | 55 |
| `d21a43804267bef2b74e00477af19400fd5f8289` | `93711afe37c2f1005e65f7e0dcbb2ca9ec3f69abb26d76d9a3bb300fb7f031af` | 56 |
| `af1bd379f4d4345c7c423668b7a6442ff82efeff` | `1a6b990eba18cdfa36df018b9b1000fe94d28577d09cf0e8621f3e5902ba184b` | 60 |

Retained evidence identifiers: the two run names above;
`m7-discovery-tail-opportunity-review-20261112` (producer classifier);
`m7-discovery-count-review-20261112` (captured-only diagnosis);
`m7-probe-counts-controls-20261112` (prospective ledger/count/counter controls).
Selected original hashes identify retained artifacts; full logs, bodies, per-tenant
oracles and raw JSON are intentionally outside Git.

| Retained artifact | SHA-256 |
|---|---|
| B750 / summary | `39691b0c9920b6972600ca1a8f08e438f27ce8ed99ffd60a8c53a339d7139ef8` |
| B750 / idle raw | `800f9f65558d6db307d9a3d0977c84e0d304c65730b0098f68a5b5f737020b65` |
| B1000 / summary | `ae14e8d86ff747ec618353e12901e38eb8c0a287fb22effa9b34a1618f0c0ac4` |
| B1000 / generated probe | `e9e83fcd81d41abf4032c912135010398759b4b3030105aaf5dcaa467f925e11` |
| B1000 / stored counts | `afd982dfa770e9d5377fbea87d116ab585bd9200fd96aa6a48c8f793a7e7203f` |
| B1000 / ACK-only probe counts | `805aea48bcfe4bc3f1835dd5865a11ba9ac2cd3e5b7f342856b8e0f5eca56432` |
| B1000 / k6 summary | `d797c1181d17074150e578026c17fe08e54b0c0920e06b31622b1c5b04c00413` |
| Prospective mutation process record | `fd0e8c53e5b0a7a56fa587591b2c73b7f728c18151966cd96cdab020e1b44c70` |
| Counter old/restored process record | `dc55f74a5c904699c06c4edf8733532feaa06de6f21b75d6b04173df5d95452f` |
| Direct nonfinite counter control | `4aff335a5bbe8f812816add1e5b2d590bb527a3777b76ea31bb6e371004f5bef` |

The coordinator owns the next freeze/dispatch and any separate point-comparison
record. New instrumentation does not rewrite either failed B run, combine mixed
instrument results into a single-identity PASS, or grant capacity acceptance.
