# Private management-session issuance focused evidence

Captured 2026-11-12. Product and instrument source:
`b5b7ef57ef50f0d660ba51e64376308372f04e60`, based on
`17bf3a6064d0c9318a17d4c77f0f141f165e0bed`. This is an immutable focused
measurement, not comprehensive integration acceptance. No push or release. Alignment evidence base:
`7d3399ddc731b1719fceee49317476aeb6eec897`.

Captured outputs (terminal blank lines normalized): [native](native.txt), [focused](focused.txt), [tiers](tiers.txt),
[lint](lint.txt).

## Reproduced results

| command | result |
|---|---|
| `NS_MANAGEMENT_SESSIONS_DOCKER_TEST=1 ./node_modules/.bin/mocha tests/management-sessions.test.js tests/management-sessions.integration.test.js --reporter spec` | 20 passing |
| `./node_modules/.bin/mocha tests/management-sessions.test.js tests/admin-role.test.js tests/provisioning-private.test.js tests/tenant-lifecycle.test.js tests/tenant-deployment-operations.test.js --reporter dot` | 83 passing |
| `node scripts/test-tiers.js check` | 682 test files, 8 tiers, okay |
| ESLint affected issuer, admin composition, REST and fixture JavaScript | exit 0, no diagnostics |
| `git diff --check` before source commit | exit 0 |

The native instrument creates uniquely owned PostgreSQL and Vault containers,
anonymous volumes, roles and synthetic tenants, then removes its resources.
It starts two actual API CLI processes, the actual private admin composition
(`admin-preview.boot`) on HTTP, and real private lifecycle transport. Non-API
lifecycle peers are synthetic status/invalidation participants. It does not
exercise the deployment bootstrap or the admin CLI configuration loader; unit
checks exercise the latter parser and the coordinator owns final deployment
acceptance. No quiet-host capacity measurement was run.

## Acceptance and negative controls

- The current fixed management-key name is read and signed through a scoped Vault
  token. Current management JWT verification authenticates the issued credential;
  wrong-tenant use, revoked session and unknown subject refuse.
- Concurrent identical request UUIDs yield the same token, one immutable audit
  record, and `existing` on retry. No plaintext token is stored in request rows.
  The private POST returns integer-second expiry and no-store; DATA listeners
  return 404 for the issuance path. Logs contain operation/outcome/codes only.
- Actual owner and active-key UPDATE writers are observed blocked through
  `pg_blocking_pids` during signing, then complete after issuance commits.
  Subsequent issuance refuses the revoked authority. These use actual PostgreSQL
  row locks rather than a timing-only oracle.
- The actual deletion activity writer is observed blocked on the activity row
  until issuance completes, after which the next issuance refuses. The full
  deletion ceremony is outside this instrument; its transactional activity
  writer is the component exercised here.
- An actual restore suspends A but cannot enter its data callback while the
  shared issuance advisory lease is held. B remains available through the other
  actual API. Releasing signing causes issuance to refuse the suspended phase
  without committing a request, then restore enters and activates.
- A live issuer backend remains open after issuing a session and passes actual
  restore census. Adding clock UPDATE authority makes the same restore refuse
  with `RESTORE_COHORT_UNKNOWN_BACKEND`, before its data callback. Fresh issuer
  attestation also refuses the extra authority. Revoking it restores acceptance.
- Revoking audit-table INSERT after a successful real Vault sign makes issuance
  unavailable and rolls back all credential, session and request inserts.
  Expiry while signing is held similarly refuses without committing authority.
- Real Vault rotation selects version 2 for new requests while retained enabled
  version 1 supports the original retry. Raising the signing minimum retires
  that retry. Changing Vault's minimum during held signing refuses the old
  pinned version and leaves no issuance row. A key without a currently enabled
  registry/access public-key mapping refuses.
- Mutating the pinned authority function body or search path, and granting
  extra user-function EXECUTE, causes fresh issuance to refuse as unsafe.
  Tenant A cannot invoke the wrapper for B; the issuer cannot update owner rows.
- Unit controls reject ambiguous/missing/exportable/retired key mappings,
  deadline an unresolved Vault token callback, sanitize transport failures,
  reject widened configuration and body fields, and pin the existing management
  JWT profile without embedding permissions.

The request ledger is admitted as tenant credential-authority data in the access
family, with FORCE RLS. Current access authority is preserved on logical restore;
no new operational exclusion, restore-authority grant, or RLS exception was added.

## Substantive failed checks and repairs

An earlier actual issuance attempt using FOR SHARE on the window row reproduced
PostgreSQL 42501 through that row's restore-authority RLS dependency. That design
was rejected. The completed implementation retains the existing shared
`tenantPhase` advisory lease and reads phase before and after signing, while
SHARE locking the activity and other authority rows. The actual restore control
above proves exclusion of the data phase independently of those reads.

The initial compatibility run was 73 passing / 7 failing: the new audit table
needed a complete populated synthetic seed and one additional admitted table.
The repaired intermediate runs exposed two preexisting census expectations:
27 candidates rather than 28 and omission of the already-admitted operational
change-feed catalogue. Reading every discovered candidate from the unchanged
base commit proved 28 and no added catalogue files. The exact expectations were
corrected; admission and operational pin rules were preserved. Final counts are
reported above. The captured outputs accompany this report; local worktree/resource attribution
is retained in the coordinator's evolving lane handoff.

## Integration boundary

The coordinator merges this original history with registry, D6, deployment and
other authorization work, then freezes one coherent candidate for full, browser,
enabled-corpus and capacity acceptance. Those campaigns are UNMEASURED here.

Alignment-record checks were attempted in the isolated evidence worktree:
`make queue-status` and `make queue-check` both refused because the queue names
external worktree directories that are absent under this new alignment checkout.
The latter stopped at queue validation before later checks. No queue state or
external gate was changed to mask that local prerequisite failure. The
coordinator owns programme consistency checks in its populated alignment tree.
