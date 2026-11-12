# Tenancy execution archive

*Contributor-facing retained records. The original consolidation captured
alignment `072ef9e37b6643d66d00248308fa6979d75f559b` on 2026-11-06; the batching
journal was captured from `8792fc7a3d62f59629ed94bac168dcad5d9aa3c7` on 2026-11-08;
the three November 6 decision and review packets were captured from
`c53105eeeb04225910e3c6871629fed5c7b78853` on 2026-11-10; the September
multitenancy discussion and deployable-components analysis were captured from
`e1bd75b80d71627a1bd68e9ee8741a02e65c91ad` on 2026-11-10.
These journals preserve the original
narrative, design alternatives, commands, failed predictions, controls and
source-scoped measurements. They are not current plans or lane assignments.*

## Current documents and retained scope

| Retained journal | What it preserves | Current home |
|---|---|---|
| [Production-path assessment](production-path-assessment-2026-11-10.md) | November 8–10 gap table, first-topology/HA recommendations and commit-pinned prior-art survey, captured from alignment `8ae6f4a3729548de0c88cc0ee5b3c0aede9aba61` on 2026-11-12. Old implementation gaps retain their capture scope. | [Production guide](../../30-design/tenancy/production-critical-path.md) for current explanation/closure criteria; queue and release records for current implementation/acceptance |
| [Multitenancy execution and decision journal](nightscout-multitenancy-execution-plan-2026-09-14.md) | September architecture rationale, decision detail, original seam-chain tasks and later decision amendments through this capture. Old task states and release claims describe their named baselines. | [Tenancy decisions](../../30-design/tenancy/multitenancy-decisions.md); current contracts linked from that reference |
| [Current-dev delivery journal](multitenant-delivery-roadmap-2026-11-02.md) | November dispatch packets, lane checkpoints, integration commands, semantic controls, failed experiments and capacity holds. | [Delivery roadmap](../../30-design/tenancy/multitenant-delivery-roadmap.md) for boundaries/criteria; [completion schedule](../../30-design/tenancy/multitenant-integration-batching-plan-2026-11-06.md#5-current-completion-schedule-adopted-2026-11-06) for sequencing |
| [Integration batching journal](multitenant-integration-batching-journal-2026-11-06.md) | Original November 6–7 B1–B7 dispatch, A–C planning matrices, source/CI snapshots, commands, semantic controls, failures and per-lane ownership. Earlier pending claims retain their capture scope. | [Living completion schedule](../../30-design/tenancy/multitenant-integration-batching-plan-2026-11-06.md) for current A/B/C boundaries and coordination; release/integration records for later acceptance |
| [Critical-path decision note](multitenant-open-decisions-2026-11-06.md) | The five November 6 questions (owner mode, M2 bar, numeric budgets, M4 client execution, batch C ownership) as asked, with mechanisms and recommendations. Each has a recorded decision or deferral. | [Release decisions, promotion bars](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#multitenant-promotion-bars-2026-11-06); [M5/M6 decision list](../../30-design/tenancy/m5-m6-decision-list.md) |
| [Owner lifecycle decision packet](owner-lifecycle-decision-packet-2026-11-06.md) | Published-source survey and alternatives for owner identity, sessions, issuer/audience split, existing-grant authority and ownership lifecycle; draft recommended defaults that were not adopted as written. | [Owner authority](../../30-design/tenancy/owner-authority.md); session and ownership rows in release decisions |
| [M0–M3 promotion review](milestone-promotion-review-2026-11-06.md) | Read-derived mapping of M0–M3 acceptance cells to R24–R55, with the ranked gaps of that date. | [Delivery dashboard](../../30-design/tenancy/multitenant-delivery-dashboard.md) and [integration record](../../30-design/remedial/rc-16.0.0-integration-record.md) |
| [September multitenancy discussion](nightscout-multitenancy-discussion-2026-09-09.md) | The 2026-09-09/14 single-tenant assumption map, candidate architectures, storage ladder and EXP-MT experiments, with in-place notes where a later decision contradicts a recommendation. | [Tenancy decisions](../../30-design/tenancy/multitenancy-decisions.md) |
| [Deployable components](nightscout-deployable-components-2026-09-14.md) | The 2026-09-14 entrypoint/program decomposition and its measurements, adopted as D5/D6 and extended by D7, D16 and D21. | [Tenancy decisions](../../30-design/tenancy/multitenancy-decisions.md); [runtime topology](../../30-design/tenancy/runtime-topology.md) |

Use the [tenancy reading guide](../../30-design/tenancy/README.md) for current
work. The [dashboard](../../30-design/tenancy/multitenant-delivery-dashboard.md)
owns recorded milestone claims, the queue owns item state/gates, and the release
integration record and linked reports own later measurements. A journal's
“current,” “next” or “this session” wording belongs to its captured context.

## Retention and use

All source headings remain available for evidence citations. Relocation rewrites
links and adds the archive notice; it does not reinterpret the recorded results
or remove unique content. The [consolidation record](../../../reports/tenancy/tenancy-journal-consolidation-2026-11-06.json)
records source identity and the link-only preservation check.

Do not append new progress here. Correct current rules in their decision/contract
home and put new acceptance in the release integration record or a dated report.
Git supplies intermediate revisions; this index supplies scope and successors
without a commit-by-commit listing.
