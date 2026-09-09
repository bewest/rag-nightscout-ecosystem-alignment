# Nightscout Release Planning (2026-09)

**Purpose:** Structured, methodical review of `cgm-remote-monitor` merge and
release readiness, and a framework for prioritizing release cadence across
three distinct workstreams that are currently competing for the same `dev`
branch and maintainer attention:

1. **Modernization** — dependency/runtime/memory cleanup, currently staged as
   [PR #8605](https://github.com/nightscout/cgm-remote-monitor/pull/8605)
   (`chore/nightscout-modernization` → `dev`).
2. **Bug fixes / security hotfixes** — see the sibling
   [`security-hotfix-eval-2026`](../security-hotfix-eval-2026/) doc set.
3. **New features** — vendor connectivity expansion, MCP/agentic-AI
   connectivity, AID custom-controller registration for agentic delivery
   systems, schema vocabulary/typed-support improvements, and the general
   maintenance backlog.

This doc set does not make unilateral release decisions — release authority
belongs to the `cgm-remote-monitor` maintainers. Its job is to separate
**verified facts** (checked directly against source/CI/history) from
**open questions that need maintainer or team discussion**, so those
discussions can happen with a shared, accurate starting point.

## Documents

| Doc | Scope | Status |
|---|---|---|
| [pr-8605-merge-readiness.md](./pr-8605-merge-readiness.md) | Independent verification of #8605's current mergeability, CI state, scope, and risk — is it ready to merge, and should progress keep splitting across releases or land as one large release? | Live findings, 2026-09-09 |
| [release-cadence-framework.md](./release-cadence-framework.md) | Rubric for sequencing modernization vs. bug-fix/security vs. new-feature work across release cycles | Draft, decisions pending |
| [feature-backlog-prioritization.md](./feature-backlog-prioritization.md) | Structured pass through the named feature areas (vendor connectivity, MCP/agentic connectivity, AID controller registration, schema vocabulary/typed support) against existing proposals and the maintenance backlog | Draft, decisions pending |
| [tooling-evaluation-keyv-mongoose-zod-wasm.md](./tooling-evaluation-keyv-mongoose-zod-wasm.md) | Evaluates keyv, mongoose, zod, and wasm against `cgm-remote-monitor`'s actual current stack (raw `mongodb` driver, hand-rolled API3 validation, no cache library) for the schema-vocabulary/typed-support and data-layer backlog items | Draft, 2026-09-14 |
| [ecosystem-progression-nocturne-trio.md](./ecosystem-progression-nocturne-trio.md) | Dev-vs-shipped progression for Nocturne (server rewrite) and Trio (iOS AID client); corrects `workspace.lock.json` mischaracterizations; surfaces Nocturne's in-progress V4 typed schema and a live Trio timestamp-precision bug relevant to schema consensus | Draft, 2026-09-14 |

## Method

For each topic:
1. **Verify, don't restate.** Check current source, CI, commit history, and
   linked evidence directly rather than trusting a summary (mirrors the
   approach used in `security-hotfix-eval-2026`).
2. **Separate decided from open.** Distinguish what the maintainers/team have
   already agreed (cite the commit/PR/doc) from what still needs discussion.
3. **One rubric per decision axis**, not a single blended score — merge
   readiness, risk, and release-sequencing are different questions with
   different evidence.
4. **Flag prerequisites explicitly.** Several feature areas (MCP, agentic
   controller registration) depend on groundwork (statistics API extraction,
   schema/typed-support work) already proposed elsewhere in this repo —
   link rather than duplicate.
