# Archived subject-administration acceptance

Contributor-facing synthetic integration gate. It archives the selected CRM
commit's `lib`, `tests` and package metadata into scratch, uses private matching
dependencies through `NODE_PATH`, and runs the committed unit and owned-PG tests.
It never checks out or mutates a shipping worktree. The tests create and remove
their own uniquely named PostgreSQL service; no shared database is accepted.

```bash
node tools/queue/gates/multitenant-subject-admin.js --ref <CRM-commit>
node tools/queue/gates/multitenant-subject-admin.js --ref <CRM-commit> --control current
node tools/queue/gates/multitenant-subject-admin.js --ref <CRM-commit> --control tenant
node tools/queue/gates/multitenant-subject-admin.js --ref <CRM-commit> --control atomic
```

The positive run must pass nonzero tests without pending cases. Scratch-only
controls each must fail a semantic assertion: ignoring current grants permits
an earlier JWT after grant removal; changing tenant binding mutates foreign
metadata; removing the transaction leaves partial changes after audit failure.
Every mutation requires exactly one known source match; missing boundaries are
invalid controls. The registered current-grants control and positive run are
measured by `make queue-vacuity ID=MT-CONFIG-MIN INTEGRATION=1`.

Prerequisites: Node/Git/tar/Docker, `postgres:16`, and privately installed CRM
dependencies. `NS_REST_GATE_REPO` and `NS_REST_GATE_DEPENDENCIES` can select their
locations; the default dependency directory is the November 5 integration lane.
The gate inherits no database endpoint for these tests. Synthetic signing and
management callbacks are explicit fixtures. This proves the bounded dormant
service, not owner HTTP admission, grant ceilings, full provisioning, deployment
policy or production secrets/runtime acceptance.
