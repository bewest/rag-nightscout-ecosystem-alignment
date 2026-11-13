# Explicit pre-acceptance baseline collection

This opt-in admission permits measurement while functional acceptance is pending.
It never grants functional or capacity acceptance. The existing accepted path
remains the default. The selected profile is still `remote-pilot`: unchanged
500/750/1000 counts, API1/RT1/EV1, Vault Server, diagnostics OFF/5000, HOT10,
two sockets/tenant, 120s idle and 300s load. Source ownership, exact image,
quiet-host, settings, stock clients, SQL accepted-write oracle, clinical/output,
strict recovery, cleanup and failed-level stop predicates remain unchanged.
The fresh-image diagnostic's <=10 tenant boundary is unchanged.

A coordinator supplies exactly:

```
version: 1
kind: joined-measurement-authorization
status: AUTHORIZED_UNACCEPTED_MEASUREMENT
pair: {core: <full source commit>, deploy: <full deployment commit>}
instrument: <exact current content SHA256>
imageId: <actual qualified sha256 image ID>
runId: <exact controller run identity>
functionalAcceptanceAtAuthorization: PENDING
purpose: PRE_ACCEPTANCE_BASELINE_ONLY
limits:
  tenantCounts: [500, 750, 1000]
  apiReplicas: 1
  realtimeReplicas: 1
  evaluatorReplicas: 1
  maximumRunMinutes: 180
```

Extra fields, acceptance claims or an acceptance evidence digest refuse. This is
not a manufactured joined-acceptance PASS. The controller retains its existing
global run deadline/fleet ownership and resource accounting; the source binds
run/image/180-minute limit in each manifest and verifies actual image identity
before deployment. This receipt contains no independent expiry timestamp; it
does not authorize bypassing the controller's existing run deadline.

Prepare adds these explicit flags to the normal source command:

```
--profile remote-pilot --measurement-mode unaccepted
--run-id <controller-run> --image-id <actual-qualified-ID>
--maximum-run-minutes 180 --tenants 500 --replicas 1
```

Repeat only the prescribed count with the same immutable receipt/pair/image/
instrument/run identity. `build`, `deploy` and `run` commands are unchanged.
`campaign.py pilot` accepts the same measurement/run/image/minute flags; `all`
and replica ladders cannot select this admission. Parent transport uses its own
existing ownership/deadline orchestration; no new shipping sequence is added.
`adapter.py measurement-capabilities` returns a separate explicit version-1
support descriptor. The existing cap4 `capabilities.json` remains byte-identical.

A cell is `m7-joined-unaccepted-measurement-cell`; an aggregate is
`m7-joined-unaccepted-measurement`. Both carry measurementMode `unaccepted`,
functionalAcceptance `UNACCEPTED`, functionalAcceptanceAtAuthorization `PENDING`,
capacityAcceptance `NOT_GRANTED`, runId and maximumRunMinutes. `collectionStatus`
COMPLETE/FAILED is separate from the original correctness verdict PASS/FAIL.
A completed measurement with a failed correctness predicate still fails and
stops progression. Early failure retains raw artifacts plus a bounded typed
`unaccepted-collection-failure.json`; it never rewrites existing summary data or
invents successful work. No raw credentials/commands are added to public errors.

`check-unaccepted-measurement` uses the same pilot cell predicates and validates
only complete bounded collection. Its success string explicitly says NOT_ACCEPTANCE.
Accepted `check-pilot`, `check-campaign` and the actual receipt gate reject this
scope, including otherwise valid unaccepted cells wrapped in an accepted-shaped
record. Gate acceptance-only validation stays self-contained; its marker refusal
does not import a missing capacity module in a standalone copied-validator control.
Later same-candidate acceptance requires a separately reviewed qualification;
never overwrite or relabel the original unaccepted captures.

Focused tests use recording-only fixtures and no Docker/cloud/application run.
`control_unaccepted.py image` removes the receipt's image-equality guard in memory;
`control_unaccepted.py accepted-gate` removes actual cell-gate scope refusal.
Each must turn its named test red, then untouched source must pass. No source
file or production authorization is modified by those controls.
