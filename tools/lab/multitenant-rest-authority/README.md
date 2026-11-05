# Bounded multitenant REST authority instrument

Contributor-facing executable instrument. This measures the committed independent
HTTP/current-authority probe, not complete REST compatibility or production readiness.

From the alignment checkout:

```bash
node tools/queue/gates/multitenant-rest-authority.js --ref <crm-commit>
node tools/queue/gates/multitenant-rest-authority.js --ref <crm-commit> --control authority
node tools/queue/gates/multitenant-rest-authority.js --ref <crm-commit> --control audience
```

The positive command must exit zero with executed passing checks and no pending
checks. Both controls must exit nonzero at semantic HTTP assertions: revoked grants
or cross-tenant audience refusal incorrectly succeeds after the corresponding
scratch-only implementation ablation. A setup failure is not a valid control.

The gate uses `git archive` into an owned temporary directory and removes that
scratch afterwards. It never changes a CRM checkout or another session's index.
The committed test starts a uniquely named disposable PostgreSQL container on a
random loopback port, verifies service liveness and removes only that container.
All identities, secrets and readings are synthetic. Signing is a synthetic crypto
provider; this does not measure Vault or production identity/transport.

Prerequisites: Node, Git, tar, Docker access, the available `postgres:16` lab image,
and privately installed CRM dependencies matching the tested tree's lockfile.
Default dependencies are the integration lane's `node_modules`; override with
`NS_REST_GATE_DEPENDENCIES=/absolute/path/to/node_modules`. The gate resolves
runtime packages through `NODE_PATH`; it does not build or write a shared cache.
`NS_REST_GATE_REPO=/absolute/path/to/crm` selects another local object database;
the default is `externals/cgm-remote-monitor-official`.

The archived commit must contain `tests/tenant-rest-authority-review.test.js`.
The command prints its resolved full commit. Missing source/dependencies, zero
executed checks, pending opt-ins and source-control mismatch fail explicitly.
The queue classifies this as an integration gate; default status runs skip it
and never count that skip as a pass. Full provider/runtime/client campaigns remain
separate acceptance, recorded with their exact heads in the release integration record.
