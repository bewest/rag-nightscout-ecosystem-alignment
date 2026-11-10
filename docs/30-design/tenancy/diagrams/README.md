# Tenancy topology plates

*Contributor-facing architecture figures, 2026-11-10. Interpretation is
read-derived; linked acceptance retains its actual source. Trust zones do not
mean physical hosts, and logical endpoints do not imply additional processes.*

- [Accepted one-host reference — SVG](accepted-one-host-topology.svg) / [PNG](accepted-one-host-topology.png): ed2 cold Compose/UI/restore and c23 native separate-role restart evidence, within the [operation-window acceptance family](../../../../reports/tenancy/operation-window-acceptance-2026-11-07/README.md). Its public-facing synthetic origin uses HTTP; Vault uses TLS. No OIDC, external ingress TLS, capacity or production acceptance is added by the drawing.
- [Current private API composition — SVG](current-internal-api-topology.svg) / [PNG](current-internal-api-topology.png): read-derived current contracts/listeners at application `dc795bd1`. The [joined acceptance](../../../../reports/tenancy/m6a-join-2026-11-09/dc795bd1-acceptance/) retains its executed source and scope. Each current private listener owns one named contract. The reference uses UDS; the shared adapter also accepts explicit HTTP endpoints with deployment-owned network trust. Beyond-loopback HTTP, cluster and multi-host admission remain unmeasured.
- [Proposed private-listener and fixed-roster target — SVG](proposed-fixed-roster-network-topology.svg) / [PNG](proposed-fixed-roster-network-topology.png): the [current implementation plan](../selectable-endpoints-and-api-scaling-plan.md). Explicit private contract modules may share one component listener, separate from consumer/management listeners. REST replica A/B are explicit instances of one REST component. Maintenance still uses every exact instance endpoint, not a load-balanced sample. Private-listener composition, operational APIs and fixed-roster scale acceptance remain open; optional gateway middleware is a separate contract. Evaluator partitioning is separately queued M7 work, not implied by API scale-out.

Start with the [runtime topology guide](../runtime-topology.md), which owns the
current reading path and work boundaries. The historical reference, current
implementation and proposed composition are different views; no acceptance
result transfers between them because their boxes look similar.

Version numbers label internal REST adapters, not services. Replica count and
Compose/Kubernetes placement are separate from that logical component; no new
route coverage or Kubernetes acceptance follows from the label.

The proposed role boxes do not mandate separate deployments: owner REST may
co-locate with API while retaining its audience/listener boundary. Private
maintenance execution remains separate from ordinary request serving. See the
[logical REST/worker map](../runtime-topology.md#logical-rest-cohesion-and-worker-placement).

Public routing alone uses arrows in the structural panel. The communication-plane
ledger states private calls, transport and effective backing-resource grants;
it avoids crossing connectors and implied all-to-all privileges. OWNER and
operator audiences remain separate from public DATA paths. Backing resources
are durable ownership boundaries, not a claim that every role accesses every
resource.

Application calls and lifecycle control are both private APIs. These labels
describe purpose, not network interfaces or different wire protocols. Endpoint
addresses bind contracts to UDS or TCP/HTTP at deployment time. Current service
headers identify contracts, not caller identity. A direct HTTPS adapter is not
implemented by the current HTTP transport; deployment TLS/proxy/mesh choices
retain their own binding and acceptance boundaries.

Re-render from the repository root:

```bash
python3 tools/site/render_tenancy_topologies.py --png
python3 tools/site/render_tenancy_topologies.py --check
```

The [renderer](../../../../tools/site/render_tenancy_topologies.py) uses Python's
standard library for SVG and installed ImageMagick for PNG previews. These are
repo-native vector diagrams. Rendering does not run application services or
establish deployment acceptance.

`--check` is read-only and compares the deterministic SVGs against the renderer's
expected output. It does not assert PNG freshness or runtime correctness; render
with `--png` and visually inspect the previews after a figure change. A changed
contract, binding or topology must update the renderer and its generated SVG/PNG
views together.
