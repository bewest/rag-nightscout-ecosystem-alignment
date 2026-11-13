# Joined private admin capability checks

Reproduced 2026-11-12 UTC. Core source and committed native instruments:
`fae4a925abf4acf025e4ee3e3c53f028d2e7b3db`, local branch
`codex/m7-join-20261111`. The management/connector admin parser and handler
conflicts retain both capabilities; combined deployment census includes both
connector tables and management issuance metadata.

The complete selected suites run through the source-owned corpus launcher:

```bash
node scripts/test-multitenant.js --only management-sessions --only connector-sources --record /tmp/m7-admin-joined-native.json
```

[Native log](native.log), [run record](native.json): 21 passing, zero pending,
zero failing. The launcher verifies every container and volume it created is
absent. It provisions PostgreSQL through the local `postgres:16` tag; this
capture does not pin the execution-time image digest. Fixture-owned Vault uses
its source-declared pinned image. Final acceptance must use explicit digest
inputs for the assembled environment.

Checks include actual private admin composition/HTTP, Vault signing and rotation,
current owner/key/session refusal, restore/deletion/owner-write races, atomic
issuance rollback, connector generation/tenant/secret-reference gates and live
backend census. The [issuer leaf record](../management-sessions-2026-11-12/report.md)
and [connector leaf record](../registry-connector-2026-11-12/README.md) retain their
original controls and narrower source anchors. This is not whole-corpus, full
role deployment, browser, capacity or final prcheck acceptance.

[Focused merge checks](focused.log) pass 41 cases for management units,
deployment operations and connector units. The command also named a nonexistent
`tests/admin-role-ownership.test.js`; Mocha warns and runs no such file. No
coverage is claimed for that nonexistent pattern. The focused run was on the
resolved merge content immediately before committing the source above.

## Deployment bootstrap inventory failure and repair

Fresh focused rehearsal of core above with deploy
`9b28fe53ab844f120db4511790608f6415351ced` refuses during bootstrap:
`Product lifecycle catalogue missing evaluator_checkpoint`. The derived base
inventory did not include the independently named evaluator checkpoint or the
explicit notification extensions; entries also already carried their typed
allocator in the base catalogue. Partial setup is not reused.

Deploy repair `512b3fbd7c9131c3fc7adaee8f1211ade49c95ec` uses the actual product
insertion-inventory helper, the base checkpoint for its independent instance,
and explicitly selected notification extensions. Every resulting table set
must exactly match its selected reviewed source catalogue. Actual lifecycle
construction and inventory checks: [six passing](inventory-restored.log).
Removing the source-table equality guard in disposable scratch produces
[Missing expected exception](inventory-guard-red.log) for a deliberately omitted
issuance table. Restored source passes. The test links that expectation to the
actual source guard; it does not establish repaired native bootstrap acceptance.
