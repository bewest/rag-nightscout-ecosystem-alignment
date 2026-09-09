# Feature Backlog Prioritization: Vendor Connectivity, MCP/Agentic Connectivity, AID Controller Registration, Schema/Typed Support

**Status:** Draft — structured pass through named feature areas, distinguishing
existing prior art from genuinely new proposals still needing scoping.

## 1. Vendor connectivity (more connectors, fetching data across systems)

**Existing prior art (not starting from zero):**
- [`nightscout-connect-vendor-interop.md`](../../sdqctl-proposals/nightscout-connect-vendor-interop.md)
  (2026-01-29) — recommends enhancements to `nightscout-connect` based on
  comparing it against `tconnectsync` and `nightscout-librelink-up`'s more
  complete implementations.
- [`nightscout-connect-architecture-review-2026-07-07.md`](../../10-domain/nightscout-connect-architecture-review-2026-07-07.md)
  and [`nightscout-connect-connector-triage-2026-07-07.md`](../../10-domain/nightscout-connect-connector-triage-2026-07-07.md)
  — later, more detailed connector-by-connector triage (referenced directly
  in the 2026-09-09 modernization discussion doc, §10–11).
- **Directly relevant scheduling fact**: the modernization discussion doc
  (`../../60-research/nightscout-modernization-next-steps-2026-09-09.md` §3)
  proposes bringing `nightscout-connect` **in-tree** into `cgm-remote-monitor`
  after the #8605 baseline is accepted — i.e., vendor-connectivity work is
  already sequenced as **dependent on** modernization-baseline acceptance,
  not independent of it. This is a real prerequisite, not just a nice-to-have
  ordering.

**Needs discussion:** which additional vendors/connectors are actually
requested (the user's "fetching data across different systems" wasn't
enumerated) — recommend enumerating target vendors explicitly before scoping
further, since the existing docs already cover Dexcom/Libre/tconnect/Tandem
paths in depth.

## 2. MCP connectivity for AI / agentic workflows

**Existing prior art:**
- [`statistics-api-proposal.md`](../../sdqctl-proposals/statistics-api-proposal.md)
  §REQ-STATS-005 already specifies an MCP resource provider **layered on top
  of** a proposed server-side Statistics API — this is the most concrete
  existing MCP proposal in the repo, not a new idea.
- The 2026-09-09 modernization discussion doc independently arrives at the
  same prerequisite from a different angle (§8: "Make statistics reproducible
  and reusable through an API... Extract a pure calculation pipeline...
  then expose documented, authorized, bounded endpoints").

**Key structural finding**: both the existing MCP proposal and the
modernization discussion converge on the **same prerequisite** — a
server-side statistics/calculation API must exist before MCP resource
exposure is meaningful (an MCP layer over ad-hoc client-side calculations
would just re-expose the same drift/parity problems the statistics-API
proposal was written to fix). **This means "MCP connectivity" is not an
independently schedulable feature — it is phase 3 of the statistics-API
proposal's own phased plan** (`statistics-api-proposal.md` "Phase 3: MCP
Integration (Effort: Small)"), which itself depends on the modernization
baseline being accepted per the discussion doc's dependency table (§12: "Statistics
API | ... | Extracted module").

**Needs discussion:** confirm this dependency chain (modernization baseline →
statistics extraction → statistics API → MCP resources) is the intended
sequencing, since it means MCP work cannot meaningfully start until at least
the statistics-extraction milestone lands, regardless of #8605's own timeline.

## 3. AID custom controller registration for "full agentic delivery systems"

**Important distinction — do not conflate with existing prior art:**
[`aid-controller-conflict-detection-proposal.md`](../../sdqctl-proposals/aid-controller-conflict-detection-proposal.md)
exists in this repo but addresses a **different problem**: detecting when a
patient has *multiple human-installed* AID apps (Loop, AAPS, Trio)
simultaneously fighting over the same BLE peripheral — a safety/conflict
problem between existing human-operated apps.

The user's request — a **registration mechanism for agentic/AI-driven
custom controllers** to participate in AID delivery — is a **different,
currently unscoped concept**: it implies Nightscout (or an adjacent service)
maintaining a registry of authorized automated agents that can issue
delivery-affecting commands, with associated authorization/audit/safety
requirements distinct from passive data-viewing API consumers.

**No existing proposal covers this.** Before scoping, this needs at minimum:
- Clarification of what "full agentic delivery" means operationally — is
  this about an AI agent recommending doses for human confirmation, or an
  agent directly issuing commands to a pump/AID controller?
- A safety-classification pass, likely starting from the same P1
  patient-safety lens as the (differently-scoped) conflict-detection
  proposal above, given direct-delivery authorization is a much higher-stakes
  surface than the read-only MCP/statistics work in §2.
- An explicit decision on whether this belongs in `cgm-remote-monitor` at
  all, versus a separate authorization/gateway service (there is prior
  precedent for a separate service pattern: `nightscout-roles-gateway` in
  `workspace.lock.json`'s tracked externals).

**Recommend treating this as its own dedicated proposal document**, not a
subsection here, given the safety stakes — flagging it in this backlog doc
only to surface that it is currently unscoped, not to scope it here.

## 4. Schema vocabulary / typed support improvements

**Existing prior art, partial:**
- [`profile-model-evolution-proposal.md`](../../60-research/profile-model-evolution-proposal.md)
  touches schema evolution for the profile model specifically.
- The modernization plan's M-series milestones on the `chore/nightscout-modernization`
  branch focus on dependency/runtime, not schema typing — this is a gap, not
  an overlap, per source-checked scope in `pr-8605-merge-readiness.md` §2.
- This repo's own `specs/openapi/aid-*-2025.yaml` specs and `x-aid-*`
  extensions are the closest existing "schema vocabulary" artifact, but they
  document behavior for cross-project alignment purposes, not for
  runtime type-checking inside `cgm-remote-monitor` itself.

**Needs discussion:** "improving schema vocabulary and typed support" is
broad enough to mean several different things — TypeScript adoption inside
`cgm-remote-monitor` (a runtime/tooling question, arguably in-scope for a
*future* modernization phase), JSON Schema formalization of the Mongo
collection shapes (a documentation/validation question, closer to this
repo's existing `specs/openapi/` work), or GraphQL/typed-API-contract work
for MCP consumers (an extension of §2's statistics API). Recommend narrowing
to one of these before scoping further — they have different owners,
different dependency chains, and different urgency.

**Progress since the above was written (2026-09-14):** cross-project
research into Nocturne, Trio, Loop, and AndroidAPS's dev-branch schema
handling (`ecosystem-progression-nocturne-trio.md`,
`ecosystem-progression-loop-aaps.md`) surfaced one concrete, narrowly-scoped,
actionable item that doesn't require resolving the broader
TypeScript/JSON-Schema/GraphQL question above first: all four projects
independently split into the same two camps for handling vendor-specific
fields (typed extension-bag vs. attribute-flattening). This is now drafted
as a standalone proposal —
[`x-aid-extensions-convention-proposal.md`](../../sdqctl-proposals/x-aid-extensions-convention-proposal.md)
— a spec-only, non-breaking addition to `specs/openapi/aid-*-2025.yaml`
that doesn't depend on picking a runtime validation mechanism (zod vs. JSON
Schema vs. TS) first; that mechanism question (see
`tooling-evaluation-keyv-mongoose-zod-wasm.md` §2) can be layered on later
once/if runtime enforcement is wanted. This is "progress to integrate," not
an open question — recommend reviewing and merging that proposal
independently of the broader typed-support scoping decision above, which
remains open.

## 5. General maintenance backlog

Not enumerated by the user in this pass. The existing
[`ECOSYSTEM-BACKLOG.md`](../../sdqctl-proposals/ECOSYSTEM-BACKLOG.md) and its
domain-specific backlogs (`backlogs/nightscout-api.md`, etc.) are the
existing tracked mechanism for this — recommend triaging new items into that
existing structure rather than creating a parallel one here, to avoid two
backlogs drifting out of sync.

## 6. Summary: dependency ordering across these four areas

```
#8605 modernization baseline acceptance (pr-8605-merge-readiness.md)
        │
        ├──> nightscout-connect in-tree import ──> vendor connectivity expansion (§1)
        │
        └──> statistics extraction ──> statistics API ──> MCP resource exposure (§2)

AID controller registration (§3): unscoped, safety-critical, likely independent
   of the above chain but needs its own proposal before any ordering can be assigned.

Schema vocabulary / typed support (§4): needs narrowing before it can be
   placed in this ordering at all — currently too broad to sequence.
```

**This ordering is a structural observation from reading the existing docs
and PR, not a maintainer-ratified roadmap.** It should be checked against
maintainer intent before being treated as a plan.
