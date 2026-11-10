# Runtime topology reconciliation — 2026-11-10

Contributor-facing capture. Alignment baseline:
`3259787103b8a8d5a6ed4b193422dc868b127602`. Application mechanisms are read-derived
from joined `dc795bd1515f11808a8d0732f2be9925cb2ffcd1`; later application
`692bd5078f2fa26b6e0a31a2bf7429f2dd453aae` changes documentation only.
No application code or deployment was changed or executed by this reconciliation.

## Closed documentation capability

- The [runtime topology](../../docs/30-design/tenancy/runtime-topology.md) is the
  current guide rendered as `runtime-topology.html`. It distinguishes historical
  ed2/c23 acceptance, implemented private APIs at dc795bd1, and proposed private
  listener composition/fixed-roster scaling. Historical figures and measurements
  retain their original attribution.
- A new current-composition SVG/PNG shows actual consumer, application and
  lifecycle listeners. The target plate distinguishes private contract modules
  from socket allocation and exact instance endpoints from service destinations.
  Grid placement and communication ledgers avoid crossing private connectors.
- The [work plan](../../docs/30-design/tenancy/selectable-endpoints-and-api-scaling-plan.md)
  separates carried schemas/clients/parsers/UDS/HTTP implementation from remaining
  listener composition, operational APIs, remote binding and two-API acceptance.
  Superseded living prose is corrected in place; immutable captures are not edited.
- The deployment guide and tenancy reading path use those current homes. Existing
  logical REST/worker anchors are retained. No new architecture plan or duplicate
  runtime queue item was created.

## Work ownership and scope

`MT-ENDPOINT-TRANSPORT` is claimed in-progress because source work exists; its
remaining composition/deployment gates remain explicit no-gate/UNMEASURED.
`MT-API-FIXED-ROSTER`, `MT-SCALE-UNBOUND` and `MT-EVALUATOR-PARTITION` retain their
unmeasured remaining capability scopes. Generated views were refreshed.

The planned evaluator operational module reports configured assignment separately
from observed membership/freshness/eligibility and actual progress. Standalone
covers the configured assignment space without inventing a membership lease;
multiple ordinals own hash buckets, not necessarily contiguous consistent-hash
token ranges or equal computational load. Stable one-owner intent does not erase
the adopted bounded-overlap/idempotent-effect transition policy. The queue oracle
measures duplicate logical effects rather than demanding exactly-once commits.

The ownership inventory also covers per-process notification scheduling and
durable attempts, future connector actors, realtime connections/projection
checkpoints and maintenance claims. It does not impose one ring on every role
or assume infrastructure cost is independent of tenant load.

Direct component JSON calls retain existing authority. Optional gateway decision
integration is response adaptation, not mandatory authentication redesign.
Read-derived `nightscout-roles-gateway`
`90840acee1ec641d881512e91f1728f7ed8f7817` prior art: Warden GET/HEAD chain
(`lib/routes.js:327`), routing headers (`lib/policies/index.js:107–111`) and token
header projection (`lib/exchanged.js:75–78`). No new gateway runtime campaign ran.

## Measured artifact checks

Renderer SHA256 captured from tool output:
`d64183f752cbe3ab529a4d97f8842ac17bf63d6bd510df625093caef2e9d93ff`.
The corresponding renderer and output artifacts accompany this record.

```bash
python3 tools/site/render_tenancy_topologies.py --png
python3 tools/site/render_tenancy_topologies.py --check
python3 tools/site/render_tenancy_topologies.py --check --output-dir tools/site/fixtures/stale-topology
```

**Reproduced:** normal freshness check exits 0, `Topology SVGs current: 3`.
The identical read-only instrument against existing stale fixture content exits
1 with `STALE topology SVG` for each fixture. Restored/current output passes.
This is content drift, not a missing-file or setup failure. Checks do not rewrite
outputs or fixtures. The control is declared in `queue/gate-controls.yaml` and
normal freshness now runs in `make queue-check`.

SVG/PNG rendering and visual inspection passed; the historical accepted SVG/PNG
have no diff. Python compilation and whitespace checks passed. Queue manifest,
coverage and generated-view checks pass. Remaining runtime items report
UNMEASURED rather than deriving runtime acceptance from a diagram check.

`make docs-links` and the final link portion of `make queue-check` report six
existing references to the absent tracked
`claimed-public-names-and-deploy-companion-2026-11-09.md`. Those references exist
in the baseline; the shared checkout has another lane's untracked document.
It was not copied or staged here. This is not reported as a green whole-repository
link check. New diagram/plan paths resolve.

The local HTML build/check command is
`make -o tools/site/.venv/.installed site-check`, using existing dependencies.
Its final result and preview location are in the lane handoff. Site rendering,
noindex/content checks and diagram inspection are documentation verification,
not application runtime, ring-transition, remote deployment or capacity acceptance.

## Integration boundary

Merge the original documentation lane history and resolve any concurrent queue
edits explicitly. The endpoint/composition owner implements its private module
registry and per-operation lifetime rules; the evaluator partition owner owns
the inspection payload and real membership/assignment controls. Their relevant
new code joins the coherent candidate before applicable acceptance is repeated.
No new bearer protocol, mandatory gateway, discovery service or application
authentication redesign is selected here.

Local handoff: `externals/work/HANDOFF-runtime-topology-2026-11-10.md`.
