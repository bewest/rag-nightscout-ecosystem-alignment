# Selected owner proposed-grant verification — 2026-11-06

The existing subject-management PostgreSQL update transaction now has a verified,
explicit owner-policy option. Proposed effective grants must fit the code catalogue,
current operator ceiling and matching management actor's explicit delegation. Current
authority is locked through mutation and final audit. Default subject management
remains compatible. This is local branch acceptance of a bounded store option;
production listener admission and complete owner management remain separate.

## Source and evidence anchors

- Accepted application parent: `1c55098a3d4bcf3d871bcd345f159ce444d6e458`.
- Final application: `17f9a4577e649208ada6b0aa8f83c51026459875`, branch
  `codex/owner-enforcement-20261105`, clean after final prcheck.
- Fresh upstream `official/dev`: `4a482627bfdafb1fef8dcbe0ac6c484811cae563`.
- Guard-control application: `3106f14d5b718e27e2a179e2d637f0d06c0642c8`.
  The only change to final 17f9 is the existing upgrade-test assertion; all `lib/`
  production source and selected owner integration cases are byte-identical.
- Canonical campaign runner: alignment
  `4f3c0b12502d5650595ec6b48cb59e338b46f6ac`, private byte-identical copy,
  SHA256 `385e424c2cb2ae91af78fbb41200c3804e6a809ed05eb9e25f4e7cab6407bc03`.
- Nested audit helper source:
  `37242d950e79972fa512db8ff72fa1a049ad6d87`.

[Final machine capture](../tools/lab/owner-subject-policy/results/17f9a457-acceptance.json)
records totals, source pins, versions, body execution, sanitized cleanup evidence
and full original-output hashes. Original full/browser outputs and exact runtime
resource identities remain in private lane scratch; synthetic data only.

## Reproduced checks

| Final 17f9 check | Passing | Pending | Failing |
|---|---:|---:|---:|
| Existing subject/unit/PostgreSQL/management HTTP corpus | 26 | 0 | 0 |
| Fresh immutable owner-policy database corpus | 22 | 0 | 0 |
| Complete nonbrowser suite | 7,127 | 80 | 0 |
| Complete browser suite | 684 | 0 | 0 |

Nonbrowser tier counts: unit 2,186; DOM 205; dependency 368 with 2 pending; core
319; harness 93; integration 3,938 with 78 pending; stress 18. The actual full run
explicitly enabled `NS_OWNER_SUBJECT_POLICY_DOCKER_TEST=1` and executed every one of
the 22 owner test bodies. These scopes overlap and must not be added together.
The catalogue corpus has 29 positive cases and the existing subject unit corpus
has 3; those are 32 positive static/unit cases, not 36. Four guard controls are
separate negative evidence, not additional passing tests. Tier registration checks
504 files in 8 tiers. Changed JavaScript lint and application diff-check passed.

The private web bundle was rebuilt in the owned application worktree before the
campaigns. Build passed with three webpack performance warnings. Final prcheck was
last: it freshly fetched upstream, reported the tested branch already contains
`official/dev 4a482627`, ended `OK`, and left final HEAD unchanged and clean.
No application commit, branch or PR update was pushed by this lane.

Actual campaign versions: Node v22.23.4, PostgreSQL 16.15, MongoDB 8.0.34,
Vault 2.2.1; UTC shuffle seed `41574423920`. The full run also executed seven
new-format token HTTP checks through the actual executable API, including same-token
revocation and continued data operations through Vault outage with refusal when
current PostgreSQL authority is unavailable. This is functional acceptance, not an
HTTP throughput or tenant-capacity benchmark.

## Controls and revocation boundary

The [immutable database capture](../tools/lab/owner-subject-policy/results/database-capture-2026-11-06.md)
records two 22-case positive archives on 3106, four independent one-guard source
mutations, and a fresh restored 22-case archive. Removing code catalogue, current
operator ceiling, explicit actor delegation or current active/update actor checks
individually caused HTTP 200 instead of 403, with independently observed persisted
state changed. Every intended control failed for that assertion; no setup, hook or
timeout error counted as semantic evidence.

The suite exercises real PostgreSQL locking in both orderings for configuration,
policy, actor and role changes. A narrowing committed before proposal locks is
observed before mutation. A proposal already holding authority locks may finish
before a waiting revoker commits; the next proposal sees the narrowing. It also
checks exact SQL column privileges, forced RLS, tenant isolation, copied proposals,
unknown roles/defaults, provider and current-database outages, recovery, final-audit
rollback and legacy/default compatibility. No stale authority fallback is used.

The earlier [catalogue/Shiro capture](../tools/lab/owner-subject-policy/results/capture-2026-11-05.md)
records 29 passing, one semantic namespace-prefix failure under a membership
mutation, then 29 restored passing. Independent source review resolved Shiro prefix
implication by requiring a reviewed current REST operation universe and checking
actual installed-Shiro implication identity inside that universe. It does not
project arbitrary wildcard permissions into a finite allowlist.

## Resource ownership and the corrected regression

The [nested audit controls](../tools/lab/owner-subject-policy/results/docker-audit-fake-capture-2026-11-06.md)
were followed by a real Docker smoke: exact returned container ownership, private
0700/0600 audit, immutable-ID removal and absence of its one recorded anonymous
volume were verified. No database process was started for that smoke.

The final full campaign recorded 18 created containers and 26 volume references;
the final browser campaign recorded 3 containers and 5 volume references. Every
recorded resource was independently confirmed absent after cleanup. The final
owner archive and existing affected corpus similarly confirmed their 1 and 2
containers/volumes absent. The helper never issues a direct volume delete or global
prune; it augments only positively owned current container IDs and uses Docker's
anonymous-volume cleanup flag. No named volume was authored by these runs, and no
unrelated resource was selected for cleanup. This is bounded audit evidence, not a
global leak-free claim for other sessions or unsupported failed-create outcomes.

An initial post-run verifier rejected lowercase Docker missing-container text;
only exact-message case normalization was corrected and the same captured resource
IDs were verified absent. The application corpus on 3106 then exposed a genuine
stale test expectation: only migration 0003 was expected pending although the
candidate appends 0004. The first run, 25 passing/1 failing, and cleanup were
preserved. Fixture-only 17f9 now explicitly applies 0003 before 0004 and proves all
three prior stored checksums, historical null metadata and readiness behavior are
preserved. The affected corpus then passed all 26. No production guard or readiness
assertion was weakened to make the check pass.

## Scope retained for integration

- The option is dormant unless explicitly supplied to the existing store. The
  separately authenticated JSON factory gains no automatic listener or identity
  issuer. Data/root credentials are not management authority.
- Current selected grants are restricted to 37 reviewed REST operations. Shiro
  still implies descendants outside this universe; future endpoint permissions
  require review. Wildcard roles and the `readable` default refuse in this subset.
- Complete catalogue/default semantics, role CRUD, existing-grant clamping, selected
  removal/ownership lifecycle, human identity/session/renewal and durable stream
  revocation remain separate work. Selected removal explicitly refuses.
- Reverse-order operator transactions may deadlock and roll back. Arbitrary lock
  ordering, a total transaction deadline and client-cancellation guarantees are not
  established by these checks.
- The earlier authorization-pipeline benchmark remains a separately scoped
  measurement. No production capacity, milestone promotion, RC admission or
  production enablement follows from this source acceptance.

The coordinator owns cumulative integration into PR #8898, canonical owner-authority
links and release/queue/dashboard/map records. Cumulative composition requires its
own measured regression; this record does not relabel the independent 17f9 result
onto a combined application head. Publication remains a maintainer action.
