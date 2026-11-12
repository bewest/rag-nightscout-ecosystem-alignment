# Exact API readiness before restore measurement — 2026-11-12

**Fixed on a branch; native acceptance NOT_RUN.** This host-fixture repair addresses
an independently reproduced readiness-precondition gap. It does not classify or
clear the [original native continuity failure](../original/README.md).

The fixture commit is `8f92e63c3bb4041325428763b4caccba62f4c404` (original history
`dcc4a70` → `91781fe` → `85cc173` → `3235c28` → `8f92e63`). The actual-source carrier control
uses `ff5156b984424f1ef34bcef22d5bfa0071354cfa`. These are instrument/source inputs,
not new labels for the retained native image. See [captured identity](captures/identity.json).

## Boundary and mechanism

Global process health and one successful public-edge request cannot establish that
every API replica has initialized both tenants. The fixture now performs protected
status GETs on each exact API service and seed tenant before any sockets, JWT
exchange or strict HTTP work. Only typed `503/TENANT_WARMING` is pending within one
shared 20-second request-phase readiness budget; all other refusals and transport/parse failures
fail setup. HTTP200 must be an object with `status: 'ok'` and no error field.
Late success after the monotonic deadline also fails.

A disposable image client joins only the owned backend network. It receives three
read-only mounts (two helpers and one mode-0600 credential input), no operator,
database, Vault or IPC configuration, and an explicit host UID/GID. The
host verifies exact container/project/service/workdir/image/source identities and
requires the complete readiness matrix. After helper cleanup, it checks the same
roster again and refuses changed/lost container IDs, boot times, images or labels.
These are bounded observations, not a promise against future replacement. Metadata
inspection and cleanup have separately bounded commands outside the request phase. The credential file is removed afterwards;
a leftover client is removed only after exact operation-label/image checks.

The original four eager B settings readers still use the public edge with the
original request timeout/cadence. Every worker must succeed before restore spawns.
Any error during measurement remains a failure, including warming. The fixture
retains its 120-second total timeout and stock/frame/session/restore assertions.
Bounded sanitized metadata records request start/end, worker, stage, typed response,
first successes and restore child spawn/exit. Public-edge upstream identity remains
explicitly unknown. No production proxy or application behavior changes.

## Reproduced checks and controls

[Captured checks](captures/checks.json) record 24 focused readiness checks plus five
existing selected-overlay checks passing, without skips. The separately invoked
native suite has **zero passed / one skipped** because it was not selected.

The source-backed carrier test uses actual secrets derivation, credential
extraction, tenant middleware, permission middleware and status handler, replacing
only synthetic store/provider/authority ports. It observes cold warming before
credential verification, initialized success using the opaque DATA token in
`api-secret` (no bearer/JWT prerequisite), and invalid/wrong-tenant/revoked refusal.
Its HTTP listeners are disposable. This is not PostgreSQL or Compose acceptance.

Five isolated ablations went red for the intended assertion:

| Removed boundary | Observed red symptom |
|---|---|
| Post-read shared deadline | Late success incorrectly passed (`true != false`). |
| Invalid-200 refusal | Malformed/error-bearing result incorrectly passed. |
| Complete exact tuple matrix | Missing expected rejection for omitted tuple. |
| Strict measured warming refusal | Missing expected exception in continuity. |
| Await readiness before application setup | Barrier not reached (`0 != 1`). |

The unchanged tree passed the focused checks. The red logs are retained under
[captures](captures/), and [control.py](control.py) recreates mutations only in
scratch copies. All captures are synthetic; no tokens, URLs or response bodies are
retained. [sha256.json](sha256.json) pins the capture bytes.


Independent review found two failed-repair boundaries in the first implementation.
Original917 client bytes accepted arbitrary valid HTTP200 JSON despite the engine's
fake invalid-response test; the new actual read→engine six-body check goes red on
those original bytes and green on85cc. Original85 host bytes returned an old API
identity after a successful probe could replace/restart the target; five current
replacement/restart/image/project/loss checks all go red with missing expected
rejections on those bytes and green on3235. The final roster check follows all
awaited helper cleanup, immediately before synchronous success. The final checks
and captured original-byte controls describe those exact scopes; neither clears
the historical native failure. A final observability-only control found that 3235
strictly failed rejected reads but omitted their individual trace rows. The
original bytes go red with `MISSING_TYPED_MEASURED_REQUEST`; 8f92 records exactly
one sanitized status-null attempt for transport refusal and still only one for
each already-recorded HTTP non200. Workload and strict refusal behavior are unchanged.

## Next integration boundary

The coordinator joins this fixture with the already recorded source assertion fix,
refreshes deployment pins, and authorizes one new image/state/project. No retained
state was warmed, reset or retried here. The original native failure remains
unclassified: missing original request timestamps/upstream identity prevent a
causal claim, even though the source-level precondition mechanism is reproduced.
