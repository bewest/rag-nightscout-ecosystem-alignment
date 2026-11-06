# Batch A final acceptance capsule — 2026-11-06

The delegated bounded application acceptance is complete for d89a44e182e771ef84aa99190ec166e6ff0d9772.
The coordinator owns combined R60 allocation, release/queue integration, criterion decisions,
publication and remote CI verification. This lane made no source fix or push.

## Exact execution and reuse scope

| Evidence | Executed application head | Passing | Pending | Failing |
|---|---|---:|---:|---:|
| Full nonbrowser | c0e8ad3c | 7207 | 81 | 0 |
| Browser | c0e8ad3c | 684 | 0 | 0 |
| PgBouncer connection/RLS checks | c0e8ad3c | 9 | 0 | 0 |
| PgBouncer typed-identity checks | c0e8ad3c | 4 | 0 | 0 |
| Final expanded corpus, 34 suites | d89a44e1 | 441 | 1 | 0 |

Full/browser/foundation were not rerun on d89a44e1. Independent comparison proved the only changes
from c0e8ad3c are scripts/test-multitenant.js and docs/multitenant-test-corpus.md. All other paths
are unchanged. Exact lib, tests, bin, package.json and package-lock.json tree/blob identities
are recorded in the JSON companion. Reuse therefore applies to identical serving code, assertions
and dependencies. The private bundle still corresponds to that unchanged source.
Do not relabel the ancestor campaigns as descendant executions or add overlapping totals.

The earlier failed corpus attempt remains preserved: 432 passing, one benchmark pending,
one before-hook failure because the provisioned database name failed the clock fixture's
disposable-test guard. The runner-only fix supplies a consistent test-named database to container
bootstrap, URI and readiness probe, retaining the original guard. The source repair lane's
focused runtime is separate; this lane ran the entire final corpus once.

## Final corpus and last gate

Final corpus ran 21:07:13.446Z–21:10:55.134Z: script and Mocha exit zero,
441 passing, one pending, zero failing; all 34 selected suites ran. The pending case is the
explicitly disabled HTTP performance benchmark and is not counted as passing.

From the application worktree, caller database selectors were removed:

~~~bash
env -u NS_TEST_POSTGRES_ADMIN_URI -u CUSTOMCONNSTR_mongo NS_TENANT_COMMIT_CLOCK_BENCHMARK=0   node scripts/test-multitenant.js --record "$FRESH_RECORD"
~~~

The actual invocation used the resource observer. Syntax, tier registry (512 files/eight tiers),
inventory (34 suites) and whitespace checks passed before final prcheck. Required upstream
fetch/merge completed already up to date before acceptance. The final application gate was:

~~~bash
tools/review/prcheck/prcheck.sh "$APP_WORKTREE"
~~~

It exited zero, reported OK and already contained official/dev
4a482627bfdafb1fef8dcbe0ac6c484811cae563. The final application head stayed unchanged and clean.
No application tests were run after final prcheck.

## Cleanup and release

The final corpus observer recorded 34 new containers and 51 mounted anonymous volumes.
All recorded containers were independently absent; 39 attributable, unattached leftovers were
removed by exact volume ID. All 51 observed mounts were then verified absent. Only positively
attributed current-run resources were touched; unknown/pre-existing volumes were preserved.
Docker volume count returned to its 462 baseline; no global claim is made about older resources.
Runtime released at 21:11:56Z.

## Evidence and limits

- [Original failed attempt](batch-a-acceptance-attempt-c0e8ad3c-2026-11-06.md), including full/browser tier results and original failure.
- [Separate PgBouncer continuation](batch-a-foundation-c0e8ad3c-2026-11-06.md), including meaningful controls and historical DDL limits.
- [Machine capsule](batch-a-acceptance-d89a44e1-2026-11-06.json), including source identity and local artifact hashes.

M4 actual-client evidence and B4a parent controls keep their own reports and source scope;
they are not claimed as repeated by this lane. The coordinator confirmed that client prerequisite
before the final campaign. Node 26 remote CI remains for publication verification.
Performance, arbitrary BSON import fidelity, mixed writers, HA and operations remain outside
this bounded acceptance. No milestone promotion, operator release, default enablement or broader
M0–M6 completion is implied.
