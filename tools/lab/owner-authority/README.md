# Owner authority local-verification prototype

Contributor-facing synthetic lab for the adopted [owner authority contract](../../../docs/30-design/tenancy/owner-authority.md).
No shipping module, listener, single-tenant default or legacy token changes.

## Run and predicted outcome

Requires Docker, Node, and an existing CRM worktree with locked dependencies.
Set `CRM_WORKTREE` to that worktree's absolute path. The source must still include
the real secrets component/Transit adapter, PostgreSQL secrets/legacy/authority
adapters and migration runner; missing or changed boundaries fail, never substitute.
All dependencies/keys/data are synthetic, loopback-only and owned by the harness.
Do not point this lab at an existing Vault or database. It creates/removes only
its own randomly named disposable containers and prints no credentials or key bytes.

```bash
CRM_WORKTREE=/absolute/path/to/crm-worktree \
OWNER_AUTH_OUT=/tmp/owner-authority-results.json \
node tools/lab/owner-authority/harness.js

CRM_WORKTREE=/absolute/path/to/crm-worktree \
OWNER_AUTH_CONTROLS_OUT=/tmp/owner-authority-controls.json \
node tools/lab/owner-authority/controls.js
```

`OWNER_AUTH_SAMPLES` optionally changes samples per case (default 120).
Two repeats reverse arm order; each measures read/write authorization at concurrency
1 and 8 using two independently pooled workers. Warmups are excluded. Request
durations include pool wait, crypto, metadata and synchronous audit where used.
This is authorization-pipeline throughput, not HTTP/data-write throughput.

| Arm | Measured operation |
|---|---|
| current | Actual `verifyLegacyCredential` with an HS256 JWT: current legacy metadata, root decrypt and Transit verify with real PostgreSQL synchronous audit. Actual shipping `authorize`; write also reads `subjectSnapshot` as data-access does. |
| local-shipping-authority | New-format local Ed25519 verifier, then the same actual shipping authority calls. Isolates authentication-path removal; this diagnostic arm lacks the combined candidate's session/key policy. |
| local-combined | Local verifier and one current tenant-bound SQL snapshot joining fixed provisioned roles, stable subject and candidate session/tenant/key/generation state. Includes write attribution. |

Predicted call counts per operation: current has two Transit calls, two durable
secret-audit insertions, two legacy metadata reads and one authority snapshot for
read/two for write; local-shipping has no Transit/secret-audit/metadata calls and
the same authority snapshots; local-combined has no Transit/secret-audit/metadata
calls and one combined snapshot. These are instrumented logical calls, not wire
round trips: the existing tenant transaction foundation uses BEGIN, set_config,
SELECT and COMMIT. Management mutation/audit remains outside this benchmark.

## Semantic checks and negative controls

Valid data read/write must pass. Tampered signatures, wrong issuer/audience/tenant/
purpose, unknown key, injected key URL/algorithm, invalid lifetime and noncanonical
encoding must refuse. Revocation committed after an earlier authorization must
refuse the same token's next operation on both pools; uncommitted grant removal
must not appear committed. Session/credential/key retirement and suspension/expiry
must refuse even with a cached public key. Forced RLS must filter an unscoped read.

`controls.js` mutates only a temporary copy of the actual prototype verifier. It
removes signature verification, audience validation, session status enforcement,
or reuses a stale authority snapshot. Each must make its named assertion fail
with ERR_ASSERTION. Setup failure or CONTROL_DID_NOT_FAIL is not accepted as red.

Stopped Vault: new cached-key operations continue with available PostgreSQL,
including current revocation; old verification, new issuance and secret decrypt
refuse. Stopped PostgreSQL: local signature still verifies, but reads/writes refuse.
These are settled outages: idle socket events drain before the next request.
In-flight shutdown races require separate characterization and are not acceptance.

## Boundaries

The candidate state table uses forced RLS and a separate non-owner SELECT-only
application grant; migrations/bootstrap are operator-only. It covers fixed denied
defaults and provisioned roles, not the complete existing defaults/role semantics,
owner ceilings, session issuer/refresh implementation or production key distribution.
Private keys are generated/sign inside actual Vault; raw Ed25519 public bytes are
converted to a public JWK for Node verification. Public keys are provisioned before
the timing window; cold-key fetch, key rotation distribution, provider renewal,
TLS/HA, load/capacity and actual HTTP/client acceptance are outside this lab.
No automatic performance threshold, queue closure or milestone promotion follows.
