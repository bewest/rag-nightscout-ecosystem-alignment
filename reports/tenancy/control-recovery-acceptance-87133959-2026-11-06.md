# Control/recovery acceptance — 2026-11-06

Reproduced bounded comprehensive acceptance on exact clean application
8713395992e07b4dd2cde61ee972e9a15c8ada8c. All campaigns below were fresh on this head.
The isolated acceptance branch was codex/control-recovery-acceptance-20261106;
the source integration worktree was not changed or repointed. Required official fetch/merge
was already up to date; final prcheck retained official/dev
4a482627bfdafb1fef8dcbe0ac6c484811cae563 and left the head unchanged.

## Results

| Campaign | Passing | Pending | Failing | Exit |
|---|---:|---:|---:|---:|
| Full nonbrowser | 7226 | 99 | 0 | 0 |
| Browser | 684 | 0 | 0 | 0 |
| Complete opt-in corpus, 35 suites | 460 | 1 | 0 | 0 |
| Affected PgBouncer connection/RLS group | 9 | 0 | 0 | 0 |
| PgBouncer typed-identity group | 4 | 0 | 0 | 0 |

Counts overlap and must not be added. Pending cases are not passes. Full-suite pending
counts are two dependency and 97 integration cases. The corpus pending case is its explicitly
disabled HTTP performance benchmark. The corpus includes actual durable-replay, selected
authority and populated-recovery fixtures; synthetic selected-carrier HTTP does not certify
actual selected-mode pinned clients.

| Full tier | Files | Passing | Pending | Failing |
|---|---:|---:|---:|---:|
| unit | 151 | 2247 | 0 | 0 |
| dom | 19 | 205 | 0 | 0 |
| dependency | 32 | 368 | 2 | 0 |
| core | 26 | 319 | 0 | 0 |
| harness | 9 | 93 | 0 | 0 |
| integration | 235 | 3976 | 97 | 0 |
| stress | 1 | 18 | 0 | 0 |

Node v22.23.4; owned runner services PostgreSQL 16.15, MongoDB 8.0.34 and Vault 2.2.1;
shuffle seed 41574423920. Corpus ran 21:59:35.622Z–22:03:23.823Z.
Source preparation passed a tier map of 514 files across eight tiers, a corpus inventory of 35 suites, product lint
zero errors / 27 warnings, syntax/whitespace and private bundle build. A matching-lock physical
dependency copy and private rebuilt cache were used; no peer cache was cleared.

## Affected shared transaction proof

The existing unchanged foundation harness ran once because this batch changes the shared
PostgreSQL connection module. PostgreSQL 16.15/PgBouncer 1.25.2 used two independent application
clients sharing exactly one backend, transaction pooling, default_pool_size=1 and
server_reset_query_always=0. All nine connection/RLS checks and four identity checks passed.
Internal controls observed RLS-disabled foreign rows, unsafe BYPASSRLS startup refusal,
session-binding leakage into another pooled client, and typed-kind flattening collision;
the original comparators restored isolation/identity. Exact source/image hashes and check
names are in the JSON companion. stderr was empty.

The generated DDL remains a historical lab fixture. Its two reported adapterBlockers describe
that fixture, not current operator migrations or complete adapters. This proof covers existing
default transaction/binding behavior; new snapshot semantics are exercised by native replay
cases in the corpus. It does not establish arbitrary BSON import, performance or HA.

## Commands and final gate

From alignment root, selecting the owned frozen application worktree:

~~~bash
CRM_REST_WORKTREE="$APP_WORKTREE" node tools/lab/multitenant-rest-preview/owned.js all
CRM_REST_WORKTREE="$APP_WORKTREE" node tools/lab/multitenant-rest-preview/owned.js browser
~~~

From the application worktree:

~~~bash
env -u NS_TEST_POSTGRES_ADMIN_URI -u CUSTOMCONNSTR_mongo NS_TENANT_COMMIT_CLOCK_BENCHMARK=0 node scripts/test-multitenant.js --record "$FRESH_RECORD"
~~~

The separately authorized affected pooler proof, then final application gate:

~~~bash
WORKTREE="$APP_WORKTREE" node tools/lab/postgres-foundation/harness.js > "$FRESH_JSON" 2> "$FRESH_STDERR"
tools/review/prcheck/prcheck.sh "$APP_WORKTREE"
~~~

Invocations used the read-only resource observer. Final source/inventory/whitespace checks
preceded prcheck; it was the last application gate, exit 0 / OK. No tests ran after it.

## Resource audit and release

| Campaign | Observed containers absent | Mounted volumes absent | Attributed unattached volumes removed |
|---|---:|---:|---:|
| Full | 22 | 32 | 19 |
| Browser | 3 | 5 | 0 |
| Corpus | 36 | 51 | 37 |
| Foundation | 2 | 1 | 0 |

Only positively observed current-run IDs were considered. Containers were verified absent
before exact unattached anonymous volume IDs were removed. The exact unique foundation network
was absent. Unknown/pre-existing resources were preserved; Docker volume count returned to its
462-volume baseline. This is not a global claim about old resources. Runtime released at 22:04:35Z.

## Scope and handoff

The fresh actual-client lane accepted the unselected default gate before runtime release;
that separate capture keeps its source scope. Selected-mode actual-client acceptance remains
unmeasured. Owner clamping stays dormant and subject-only, without retrospective delegator
lineage. Replay is explicit current-state convergence, without every-transition delivery or
exactly-once external effects. Populated recovery is a stopped-write synthetic PostgreSQL
reference with explicit ACL recreation, not production backup/provider-key recovery or
general typed API import certification.

Original integration failures and bounded fixture/oracle repairs remain immutable in their
own captures; this lane made no source repair. No option, default, listener or role was enabled.
No complete M2/M5/M6, clinical-consumer, performance, HA, operations or operator-release claim
follows. Remote CI remains for the coordinator after publication.

The coordinator owns next R allocation after R61, release/queue integration, criterion decisions
and publication. This lane did not push. [Machine capsule](control-recovery-acceptance-87133959-2026-11-06.json) records source hashes,
counts and local artifact hashes. Raw logs and resource identities remain local.
