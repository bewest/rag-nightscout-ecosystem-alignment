# Discovery status fingerprint: instrument repair

**Reproduced; fixed in alignment source.** The discovery workload discarded the
response body that its settings fingerprint needed. The repair retains text for
only the existing status GET. It adds no request, changes no application code,
and keeps the projection whitelist, size bound and hard refusal for invalid or
mismatched settings.

## Original boundary and mechanism

The retained `discovery-reference-20261112-a` 500-tenant cell stopped after load
and recovery with `M7_FUNCTIONAL_SETTINGS_FINGERPRINT`. Its summary is PARTIAL:
observations **0**, invalid **510**, mismatch **0**. The workload set
`discardResponseBodies: true`; its status GET did not override that setting, so
k6 supplied a null body to the fingerprint parser. JWT exchange already retained
its own text response.

The original cell also has `oracle: null` and no resource-reduction result. The
fingerprint refusal preceded its intended independent count query and reduction.
The original database was removed during cleanup: those stored counts remain
**UNMEASURED**. This record supplies neither retrospective counts nor a successful
settings comparison for that cell.

## Repair and reproduced controls

| Boundary | Result and limit |
|---|---|
| Status body | The generated GET helper accepts an optional response type; only `r_status` passes `text`. Other response bodies remain discarded. |
| Actual k6 SDK | One iteration on the cached image, using a synthetic loopback HTTP fixture: old generated status body → invalid **1**; repaired valid status → observed **1**, invalid **0**, mismatch **0**. |
| Strong negative controls | Malformed body → invalid **1**; wrong projected settings → mismatch **1**. The unrelated GET body remains null. SDK control exit **0** means these expected outcomes were asserted, not that invalid settings passed. |
| Control cost and cleanup | **5** synthetic loopback GETs total, no application or PostgreSQL workload. The owned temporary container was absent and the loopback server closed after execution. No image pull or paid run. |
| Source regression | **2** focused tests passed. Removing the text override reproduces observed **0** / invalid **1**; restoration passes. The HTTP mock now models global body discard. |
| Independent observations | The existing owned count query and resource-file reduction now precede final fingerprint classification. Invalid and mismatch cases record both, then still hard-refuse. Source/foreign/custody barriers remain before that query. No extra SQL. |
| Ordering control | Both new tests fail against the prior source because counts/reduction are absent. Candidate and restored source pass; direct control-process exits **1 → 0 → 0**. These are recording fixtures, not recovered A data. |

The SDK control used the same k6 image as A and byte-identical old generated
workload. This reproduces the instrumentation mechanism. It does not establish
capacity, clinical correctness, or the actual site's settings fingerprint.

## Exact source and instrument attribution

| Role | Commit or identity |
|---|---|
| A source | `b546dc313dee8e8ce9e9744717d555347799a739` |
| A instrument | `ec01d588441cedb7f7a6eb4b2f711ad948612dbe00f4ef940674afa0247afcf1` / 54 files |
| Status repair | `fb8238c9addca876c9f4093ca6bf9fdcaf335f32` |
| Observation-order repair | `feb9f3f550233f7bac5974b70df722a0cdec215d` |
| Repaired instrument | `11343639dab11dadc02c4bf2fbedd37bf47facaf0aae0741f5ffef6591a163f2` / 55 files |
| Record integration base | `c29db2e03f2ccb9df4c3243bb69d36a7988aba7b` |
| Unchanged application | core `9db0ce94f072c8f34aab889f0181afa4269a6758`; deployment `d76ef17878edb610cdeae75aeef9c07f94b60753` |
| Unchanged application image | `sha256:293a5c531faac6c156305159246e39defd2592612c302af275efe807102a6d3e` |
| A and control k6 image | `sha256:eeb0db19cd8d263aa57346cdbc7ea18e6fcfb2ba9497746a7ae82ceefc8c9fa5` |

The gate bytes remain
`dba87b881dee06e54e7768210bd457ce809607d1f7697614f9b0e287f9103488`.
The unchanged `native_time_witness` function's AST SHA-256 is
`87e84a54e3bff3c490dea2041bfe7c206946d22dad6c09d36d835cbb8d201ce4`.
This is source compatibility evidence, not a new native witness.

Source: [generator](../../../tools/mt-bench/m7-joined/workload.py),
[body regression](../../../tools/mt-bench/m7-joined/test_fingerprint_body.py),
[discovery collector](../../../tools/mt-bench/m7-joined/discovery.py),
[ordering controls](../../../tools/mt-bench/m7-joined/test_discovery.py).

## Retained evidence

Captured originals stay outside Git under evidence identifiers
`discovery-reference-20261112-a` and `m7-fingerprint-body-review-20261112`.
The following SHA-256 values identify selected original artifacts; this compact
record does not include full logs, bodies, per-tenant oracles or archives.

| Evidence identifier / artifact | SHA-256 |
|---|---|
| A / cell summary | `b8561aec46bb4f8766caae7d45ecf98ceb99db71c31618e05644855760943551` |
| A / k6 summary | `2f08395b3061be82a353e62f96b6369a53c0dee64b480a321d419613a9cb7315` |
| A generated workload = SDK old workload | `1439d4ee7e7cc7e9dc23f635e5b3c9ef393368922440707fba3c488b51bb52cb` |
| A / evidence manifest | `0716674916f95c4dc6a7fd122dac03ad1f64a4242428db97e4e05f1d5ab9264b` |
| SDK / fixed generated workload | `dd42d19a47355a5aaf0191cfa9e0f2bc705f7e5527e2ccf6a7e274c708a4678b` |
| SDK / control source | `db75b9ec8bc73207af4185953a4676000882dce71b141d1084c9049fa710926e` |
| SDK / host driver | `e4b64bb3ea459a62a54db3a9813b636182664c86d9dd9638c62fc82ab276ec07` |
| SDK / direct process and cleanup record | `0652a4dca9d6869e2185b3f843e6c093067724751febc6766f6b2a35ac5dbef1` |
| SDK / summary | `18562537c4179474bf1358a962a927820afeb92c299e41dc28ff2b73c27cdff9` |
| Count order / control source | `cd4451468cecd29dcdf2196425681ac8eb0d06e52b543e207fc3f525bcb67a8c` |
| Count order / direct processes | `04bd4295f1bdaf94c7d634d4cdecf4517bcbaee09569d31122c39d8f6a616445` |

The coordinator owns any later 750/1000 discovery dispatch and its records.
A's 500-tenant result retains its old instrument identity. Combining it with
later results does not create a single-instrument PASS or capacity acceptance.
