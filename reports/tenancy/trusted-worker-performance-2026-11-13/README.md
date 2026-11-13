# Trusted worker performance batch — 2026-11-13

**Independent review accepts the source for runtime commissioning and measurement;
full native operator/runtime and CPU/capacity acceptance remain open.** This batch gives trusted evaluator/realtime
roles ordinary cross-tenant metadata SELECT, replaces procedural tenant switching
with set-based discovery, retains unchanged settings/effective realtime entries,
and moves operational inspection outside tenant jobs. Public routed identities
receive no new grants. Clinical/output/restore transactions retain their existing
contracts. Connection-driven realtime and API authorization are separate work.

[Selected results and source/evidence hashes](summary.json) bind the exact scope.
Raw captures remain unchanged in the ignored retained-evidence directory named
in the summary. Synthetic data only. Figures below are **reproduced** unless
explicitly labelled otherwise.

## Source and review

Core 4b13bf8bbfe578416441d7322837ec5aabeba1ea is the narrow realtime recovery/publication child of
bbbb6e79fe38d4ba116725a487cf00a910eee568, itself the repaired child of
092b947042f59958e1fcb68eb3a5fb699894ddf1, based on e1f130ec. Deployment
84accb33c3daccebfdf886300c3ba6c638e003c6 is based on abe3e82d. Both are local,
unpushed branches, not merged into application dev or released.

The first core candidate failed independent review: added metadata read policies
broke logical-restore/ensure exactly-one-policy assumptions; metadata failure
could leave in-flight/cached output current; recovery could share an obsolete
settings promise; an older verification could undo invalidation; namespace/cadence
configuration was incomplete. Original actual-module restore refusal was
reproduced as LIFECYCLE_LOGICAL_CLOCK_SCHEMA_UNSUPPORTED.

The repaired source also reacquires quiet realtime cells once after worker recovery
and checks the captured runtime epoch after protocol fanout awaits, before any
synchronous socket emission. These paths use in-memory checks, not new SQL.

The repaired source retains the canonical PUBLIC tenant ALL policy and admits
only nonapplicable, explicit-role, permissive SELECT USING(true) policies without
WITH CHECK in restricted caller checks. It validates that caller's isolation,
not a universal whitelist for every login. Worker generations fence publication,
cached eligibility and staged activation; reconciliation failures retry feed
hints. Verification and settings promises are fenced across invalidation/version
changes. Trusted namespaces match authoritative configuration, and the settings
safety-net interval is configurable with a ten-minute default.

Independent re-review accepts the exact final core/deployment pair for runtime
commissioning and measurement. Its unchanged external quiet-recovery and
protocol-fanout reproducers now pass. This is source acceptance; it does not
promote the narrower metadata lab into full operator or runtime acceptance.

## Focused evidence

- Affected checks: **492 passing, zero pending/failing**. New capability
  regressions: **15 passing**. Touched-source lint: zero errors. Tier inventory:
  **729 files, eight tiers**. These are focused checks, not the full campaign.
- **Eleven source controls** fail with named assertions and restore green: cache
  SQL, operational scope, recovery generation, runtime settings reuse, checkpoint
  comparison, verifier invalidation, settings-version race, publication epoch and
  feed dirty arrival, quiet realtime recovery and protocol emission after an
  asynchronous configuration read.
- Copied deployment overlay against first core candidate: **12 registry-plan
  tests pass**, no skips. Repaired core deployment commissioning remains open.
- One bounded PostgreSQL 16.15 episode on bbbb6e79 executes the actual metadata reader and
  registered connection. Worker A/B visibility, unchanged settings zero SQL,
  version refresh, denied writes/DDL/secrets and public A-to-B denial pass.
- Actual policy-contract SQL accepts canonical plus unrelated worker reads and
  refuses PUBLIC/current-role/ALL/inherited-worker additions. Three additional
  live missing-policy/widened-public-policy/worker-write-grant controls fail and
  restore. This does not qualify a full native logical-history restore.

## Metadata query cost by selected roster

The database holds 10,000 synthetic rows per metadata table throughout. Each
cell is two end-to-end call observations on one shared host, not a confidence
interval or CPU measurement. The source-extracted procedural function reads
clock rows only; the new SELECT joins four metadata tables, so these arms differ
in projected work. No causal capacity ratio follows.

| Selected tenants | Procedural clock-only milliseconds | Set-based metadata milliseconds |
|---|---:|---:|
| 10 | 2.34–3.59 | 2.47–2.48 |
| 1,000 | 9.73–11.62 | 5.40–5.71 |
| 10,000 | 71.54–73.50 | 20.74–22.41 |

The SELECT still does work proportional to its selected roster. Normal idle cost
also includes the configured healthy sweep, periodic settings safety reloads and
actual due clinical/delivery work. With the default sweep disabled, a full page
is checked every second; a page cap bounds throughput by increasing detection
latency, not by proving constant per-tenant cost. Actual runtime idle scaling,
clinical completed/due demand, SQL-family CPU and joined performance remain
**UNMEASURED** here.

## Capture limits and next boundary

Two native setup failures used Unix-socket readiness and accepted PostgreSQL's
temporary initialization server; TCP readiness repaired the fixture. Those
failures are preserved. The initial successful native capture file was
accidentally overwritten by the next attempt; only its tool transcript remains,
and it is excluded from final evidence and figures. Later captures have unique
identifiers and are preserved separately.

The final native container is removed and its exact absence is verified. No paid
resources were created. The sole integration owner reviews/joins the exact pair,
then coordinates matched runtime measurement. The metadata/policy modules tested
natively on bbbb6e79 are byte-identical in the final realtime-only child. Full/browser/enabled-corpus and
final prcheck belong to its coherent candidate. The implementation lane maintains its source-custody handoff. Prospective local
N measurement belongs to the separate measurement owner and its evolving
HANDOFF-idle-scaling-measurement-2026-11-13.md. That preparation has no runtime
resources or results in this capture.
