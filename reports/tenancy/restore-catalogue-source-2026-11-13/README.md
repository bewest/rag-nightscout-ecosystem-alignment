# Restore catalogue admission: bounded source approval

**Reproduced; fixed on a branch, independently approved at source/catalogue
scope.** Exact core `85225269767482498427191d121e5b8b06d6c72b` retains the
accepted recovery/admission history and repairs restore/resume catalogue trust.
It is not merged to application dev or released. The [selected summary](summary.json)
records source attribution, results, limits and artifact hashes; raw captures stay
outside Git.

## What changed and why

Restore/resume adds durable audit and operation-clearance tables. Matching a
migration name does not prove those tables still have the required protection.
The original source accepted unsafe new-table metadata because admission and
epoch checks did not enumerate both tables. The repair screens exact shape,
owner, forced row security, constrained grants, policies and constraints; it
includes both identities in strict lifecycle contracts and lower/lifetime epochs.
Existing column-only operator grants remain constrained.

| Original source boundary | Reproduced finding and final repair |
|---|---|
| `57369af24f1345238b26f992ebd2a39008b91fbc`, inherited from paused `7107` | Both new tables escaped catalogue admission and epoch coverage. Final source enumerates and checks them; lower/lifetime drift controls refuse before tenant body SQL. |
| `3a6af16940eac72938857fc4c0d30ce0b70ff6b3` | Enumeration was repaired, but removing parentheses accepted changed policy grouping. Final comparison preserves structure and precedence. |
| `4cc1ae66c5f7caabeee68c97d4dc159449654af1` and partial `2763` | Operator-shaped strings or quoted/qualified special names could alias syntax. Final parser checks token kinds and context-specific qualification; preserves quoted text/identifiers; distinguishes missing, null and invalid metadata; and refuses unsupported syntax. |

The parser implements a narrow fail-closed catalogue grammar, not general SQL
equivalence. Keywords and special constructs do not arise from string contents.
Selected-schema normalization cannot turn a shadow function/type/relation into
a PostgreSQL builtin. Meaningful grouping and literal bytes remain significant.

## Executed source and PostgreSQL evidence

Owner affected checks: **329 passing, 64 opt-in pending**. Independent authorized
focused replay: **81 passing**, exit zero; its initial sandbox failure is retained.
Fresh immutable-source replay covers original/adjacent cases and **nine** semantic
mutations that fail at the intended symptoms before restoration. These counts
overlap and must not be added.

The successful bounded fixture used the reviewed PostgreSQL **16.15** image,
network none, no published ports or host/shared data, read-only root and owned
tmpfs directories. It checked actual UID/GID and ownership before initialization;
PostgreSQL listened only on its Unix socket. Captured source query text,
arguments and metadata rows bind the exact committed source. The fixture used
**22 execs**, **3,801 ms** and **214,733 bytes** within its approved bounds.

Independent review matched source hashes and replayed these nine actual metadata
snapshots: lower, lifetime and maintenance admission; grouping, literal and
clearance forced-RLS mutations; and fresh restoration after each mutation.
Healthy/restored cases admit and mutated cases refuse. Exact container and nonce
absence were independently verified. No extra fixture was run for missing cases.

Native owner/grant drift on **both** new tables was planned but **UNMEASURED**.
Source-protocol owner/grant checks are separate evidence. This catalogue fixture
does not prove clinical behavior, selected runtime recovery, operator execution,
capacity or the later joined full/browser/corpus campaign and final prcheck.

## Preserved failures and evidence custody

The first fixture stopped before SQL because the planned UID differed from the
image's actual UID. A fresh corrected fixture reached PostgreSQL but stopped on
multiline JSON framing. Both are retained as failures with exact cleanup; neither
is a source verdict. The third fixture used compact captured metadata framing
and the final source; it is not a relabelled earlier attempt.

Earlier owner-side `3a6` mutation logs were overwritten during a later replay.
Those paths are SUPERSEDED/evidence lost, not reconstructed. Original independent
reviewer defect captures remain separate. All final replays use fresh head-bound
paths. An old quoted-ANY instrument did not apply its mutation due to whitespace;
that result is vacuous, not a product failure. Corrected instruments assert the
mutation applied and preserve the original attempts.

The executed third runner lacked an exclusive-output guard. A later resource-free
collision control qualifies a future guard; it is not retroactive native evidence.
No raw captures or credentials are committed here.

## Next boundary

The coordinator released implementation of the reviewed fresh-v2 controller-owned
lifecycle operator. At this accepted checkpoint, the previous owner reported
context pressure and transferred clean worktree custody to a fresh owner. It must charge controlRecovery before
connection/authentication, preserve authority and exact managed-session census,
and retain uncertain physical effects. Existing deployment/image pins remain
unchanged. Actual operator and selected-runtime proofs belong to a later coherent
freeze; no automatic resource-epoch rebinding is claimed.

Local custody: `externals/work/HANDOFF-restore-recovery-join-2026-11-12.md`.
Selected raw evidence identifiers: `restore-recovery-structure-repair-20261113`,
`m7-lifecycle-852-independent-review-20261113`,
`m7-lifecycle-root-native-review-20261113`. Their full captures remain local.
