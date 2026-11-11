# DEPLOY-TREE-HOME: core keeps the test fixture, nightscout-deploy holds the Compose tree

*Contributor-facing measurement record, captured 2026-11-10. Not edited after capture. Both lane
branches are local and unpushed. Implements the 16.0.0 decision
[`deploy-tree-home-now`](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#deploy-tree-home-now).*

## Anchors

| tree | ref | commit |
|---|---|---|
| #8898 head (lane base) | `codex/batch-join-20261110` | `16a1fc2d45e59602eb6ec3e3bf6f506f35bcc5b1` |
| core lane head | `codex/deploy-fixture-20261110` (worktree `externals/work/crm-deploy-fixture-20261110`) | `f3dc10c86aef64ad1ab2e22abde95ef66c737df4` |
| deploy repo base | `docs/operator-readme-20261110` | `9387428` |
| deploy repo lane head | `deploy/compose-sync-20261110` (worktree `../nightscout-deploy-compose-sync-wt`) | `085d88adae2e1732a0810a93cbcf7db313ff9653` |
| deploy repo `main` = `origin/main` | | `cda3826` |
| `official/dev` | | `4a482627bfdafb1fef8dcbe0ac6c484811cae563` |
| alignment `main` at writing | | `615fa0835b937cb1ffa58d81e1efd4c2ac529e72` |

Queue item `DEPLOY-TREE-HOME` was `in-progress` at start.

## Which tests need the fixture (read from the tests)

`grep -rln deploy/multitenant` over core at `16a1fc2d` (excluding `node_modules`, `.git` and the tree
itself) finds six test files, three docs and `.dockerignore`. No workflow under `.github/workflows`, no
`package.json` script and no entry in `tests/tiers.json` names the path. `scripts/test-multitenant.js`
runs the three integration files by name. The tree's own `bootstrap.test.js` and `restore.test.js` are
`node:test` files that no core runner loads (`npm test` globs `tests/*.test.js`).

| test | loads |
|---|---|
| `tests/admin-role.test.js` | `config.js` |
| `tests/compose-deployment-protocol.test.js` | `demo.js` (and through it `restore.js`), `health.js` (also read as source) |
| `tests/compose-ui.test.js` | `ui.js` |
| `tests/admin-role-ownership.integration.test.js` | `config.js` |
| `tests/admin-lifecycle-fit.integration.test.js` | `config.js`, `restore.js` |
| `tests/evaluator-consumer-load.integration.test.js` | nothing: a comment cites `config.js:96-103`; its lab is `tests/fixtures/evaluator-consumers-native` |

## Core: what stayed, what went (`f3dc10c8`)

Path kept as `deploy/multitenant`. The deploy repo's `tools/compose-overlay.sh` places its tree at
that path over a core checkout, and every kept module requires core by `../../lib/...`; a move under
`tests/fixtures/` would change both and break the overlay's byte comparison for no gain. The five kept
JavaScript files are byte-identical to `16a1fc2d`.

| kept | why |
|---|---|
| `config.js` | the plan's layout and grants, loaded by three tests |
| `demo.js` | loaded by `compose-deployment-protocol` |
| `restore.js` | required by `demo.js`; loaded by `admin-lifecycle-fit` |
| `health.js` | loaded and read by `compose-deployment-protocol` |
| `ui.js` | loaded by `compose-ui` |
| `README.md` | rewritten: points operators to nightscout/nightscout-deploy and lists what loads each file |

Removed (16): `.gitignore`, `CREDENTIALS.md`, `Dockerfile`, `Dockerfile.dockerignore`, `UI.md`,
`bootstrap.js`, `bootstrap.test.js`, `build.js`, `check-compose.js`, `compose.yaml`, `demo.sh`,
`entrypoint.js`, `load-env.js`, `nginx.conf`, `prepare.js`, `restore.test.js`.

Docs repointed: `README.md` (the Compose guide link), `docs/internal-service-topology.md` (its
read-derived sources), `lib/tenant-ownership/README.md` (where the identity is defined). The three
`deploy/multitenant/.state`/`.env` lines in the root `.dockerignore` stay: they keep an overlaid
tree's private state out of the root image build.

20 files changed, 30 insertions, 1258 deletions against `16a1fc2d`.

## nightscout-deploy: what was ported (`13f8bfb0`, `085d88ad`)

Based on `docs/operator-readme-20261110` (`9387428`), not `main`: the ownership-operations overlay
(`34417f8`) the brief asks to keep is only on that branch.

1. `13f8bfb0`: `bindings/compose/multitenant` replaced by core's `16a1fc2d:deploy/multitenant`, byte
   for byte (tree `6529d40282ea4589ea75c71712839d4db6e9940b`; 4 files differed from the
   `ed2ced00` import: `bootstrap.js`, `config.js`, `health.js`, `restore.js`). Pin moved to
   `16a1fc2d` in `README.md` and `bindings/compose/SOURCE.md`.
2. `085d88ad`: ownership grants overlay-shaped. The base `config.js` drops `ownership_operator` from
   `layout()` and its block from `grants()`; the delta is recorded as
   `bindings/compose/SOURCE.delta.patch`. `ownership-admin/ownership-grants.js` gains core's
   tenant-phase read (`phaseGrants`, four statements), which core added after `e6f6e248` and the
   first overlay lacked. `tools/compose-identity-check.sh` now applies the delta to core's tree at the
   recorded commit and compares; SOURCE.md records both hashes (here:
   `93a4a972f8cb6c6a974c943388d78783148af9f5`).

The decision between this and a plain byte-identical re-import (the earlier overlay README's plan:
retire `ownership-grants.js` once the import carries the role) sits on the second commit alone;
dropping `085d88ad` gives the byte-identical form.

## Commands and counts

All synthetic. Integration services: one disposable PostgreSQL 16 started and removed by
`scripts/test-multitenant.js` (random loopback port, generated credentials in the child environment
only), plus the containers the suites start for themselves. The local MongoDB 3.6 was not used.

| command (core lane worktree unless noted) | result |
|---|---|
| mocha `admin-role`, `compose-deployment-protocol`, `compose-ui` with `tests/ci.test.env` | 28 passing (9, 14, 5) |
| `node scripts/test-multitenant.js --only admin-role-ownership --only admin-lifecycle-fit --only evaluator-consumer-load` | 19 passing, 0 pending, 0 failing (11, 6, 2); created container and volume verified absent; `docker ps -a --filter label=ns.multitenant.run`: 0 |
| `npm run test:unit` | 241 test files, 3176 passing, 0 failing |
| `node scripts/test-tiers.js check` | `626 test files, 8 tiers: ok` |
| `npx eslint deploy/multitenant/*.js` | 0 errors, 9 warnings (security plugin; the files are unchanged from `16a1fc2d`) |
| deploy repo: `tools/compose-identity-check.sh <core>` | 3 `ok` lines: committed tree, core upstream tree, core plus delta equals this tree |
| deploy repo: `npm test` | `0 targets checked, 0 failing`; committed tree `ok` |
| deploy tree overlaid on core `16a1fc2d` library: `node --test bootstrap.test.js restore.test.js` | 10 tests, 10 pass |
| base `grants()` + overlay statements against core `grants()` | 345 and 345, identical |
| overlay statements against core `grants()` for the identity | 10 and 10, identical |
| roles in core `layout()` absent from base | `ownership_operator` only (16 and 15) |
| base `documents()` against core `documents()`, same synthetic inputs | identical |

The grant and documents comparisons are scratch scripts that load core's plan from the lane worktree
and the deploy repo's base plan and overlay against the same core library, mapping the overlay's
`/opt/app/` requires onto that tree. They are not committed.

Not run: a Compose deployment (`demo.sh up`, the overlays' `up`) on the synced tree; the full core
suite and browser tier. Both are for the coordinator's frozen-candidate acceptance.

## Controls

| break | symptom | restored |
|---|---|---|
| core: `deploy/multitenant/health.js` moved out | 27 passing, 1 failing: `Compose role health uses the lifecycle participant contract`, `Cannot find module '../deploy/multitenant/health'` | 28 passing |
| deploy: the `phaseGrants` line removed from `ownership-grants.js` | identity 10 and 6 `DIFFER`; total 345 and 341 `DIFFER` | identical |
| deploy: empty `SOURCE.delta.patch`, committed in a scratch detached worktree | `FAIL: core tree plus the recorded delta differs from this tree`, exit 1 | scratch worktree removed |

A first attempt at the second control also stripped a comma and went red on a `SyntaxError`, red
for the wrong reason; the row above is the rerun with only the one line removed.

## Left for the maintainer

- The deploy repo now pins `16a1fc2d`, which is on `official/workspace/multitenant-20261102`
  (#8898), so `compose-overlay.sh` and the identity check can fetch it.
- The deploy branch sits on the unpushed `docs/operator-readme-20261110`; pushing
  `deploy/compose-sync-20261110` publishes both.
- `plan/schema/deployment-plan.schema.json` and the Vault Agent overlay README still cite
  `ed2ced00`; they are a draft read and a dated measurement respectively, left as they were.
