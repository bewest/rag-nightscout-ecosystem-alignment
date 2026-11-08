# Coherent operation-window native acceptance — 2026-11-07

**PASS: all 17 native criteria; independent physical closure passed.** Actual CRM
source `b029f5d81f539a4846e51ab88e540cb4511910fa`, tree
`0071642a5b6875ad822904cd3a9e2512eecd87e7`, executed the complete four-deployment
matrix. [summary.json](summary.json) records the exact criteria and evidence hashes.
This is reproduced application evidence, distinct from the earlier PostgreSQL
primitive/model counterfactual and incomplete native attempts.

The matrix passed actual separate API/realtime/evaluator/tenant-admin startup,
HTTP body/response lifetime draining, logical restore with forward history and
current security/consumer state preservation, tenant B progress, row rollback,
participant restart refusal, real COMMIT acknowledgement loss, invalidation
acknowledgement loss and unresolved-orphan refusal. The killed-backend case and
privileged same-PID/different-birth seed remain separate criteria. Independent
server-side observation confirmed prior backend release. All 17 role process
births were retained; complete actor evidence and zero forbidden egress were
measured. The parent and independent readback confirmed service, volume, process,
process-group, descendant and socket release, with baseline identities unchanged.

## Existing-operation timing observations

These are four single synthetic ordinary-restore samples, in milliseconds rounded
to one decimal. Each artifact contained two entry rows and two profile rows; the
current state had three entry rows and two profile rows. Other clinical tables
were empty. All private fixture inspection/control overhead is included.

| Sample | Call to body | Body to acknowledged effect | Effect to activation | Call to activation |
|---|---:|---:|---:|---:|
| c1-ordinary | 384.6 | 518.9 | 76.1 | 979.6 |
| c2-ordinary | 148.9 | 523.0 | 82.8 | 754.7 |
| c3-ordinary | 131.5 | 578.1 | 105.3 | 814.9 |
| c4-ordinary | 191.9 | 519.7 | 113.5 | 825.1 |

Call-to-body includes preclaim, drain and fixture hooks. Body-to-effect includes
restore work and private inspection; effect-to-activation includes callback
oracles and invalidation. In c1, one requested 75 ms held-body wait occurred
before the call and another inside the call; neither is subtracted from these
observations. Nested private spans are not additive. These samples establish no
capacity, SLO, precise outage onset or earliest recovery time.

Eight existing B HTTP write/read operations were observed without adding requests;
the raw single-round-trip observations are in the summary. The four fault samples
also retain their observed spans, terminal result and null missing anchors there.
A server COMMIT frame with its acknowledgement deliberately suppressed never
creates an acknowledged-effect anchor. Fault/refusal durations include the
fixture's deliberately induced conditions and timeout behavior.

## Acceptance boundary

The result covers the fixed, cooperative, same-host credential/ingress deployment.
It does not establish a database-enforced fence against a later raw private writer,
multihost membership, or B restart/HA. Running B continuity is a separate claim from
restart availability. Earlier captures remain unchanged; the original V8 actor is
still unattributed, and this pass does not prove an earlier failure's cause.

Comprehensive suites, default browser and actual Compose UI acceptance remain
separate records. This report does not promote M6 or establish an operator release.
Only synthetic outcomes/counts and portable hashes are published; raw runtime
identities, roles, backend timestamps, endpoints, credentials and payloads stay out.
