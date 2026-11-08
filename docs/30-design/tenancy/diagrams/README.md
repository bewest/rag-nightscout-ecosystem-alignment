# Tenancy topology plates

*Contributor-facing architecture figures, 2026-11-08. Interpretation is
read-derived; linked acceptance retains its actual source. Trust zones do not
mean physical hosts, and logical endpoints do not imply additional processes.*

- [Accepted one-host reference — SVG](accepted-one-host-topology.svg) / [PNG](accepted-one-host-topology.png): ed2 cold Compose/UI/restore and c23 native separate-role restart evidence, within the [operation-window acceptance family](../../../../reports/tenancy/operation-window-acceptance-2026-11-07/README.md). Its public-facing synthetic origin uses HTTP; Vault uses TLS. No OIDC, external ingress TLS, capacity or production acceptance is added by the drawing.
- [Proposed fixed-roster network target — SVG](proposed-fixed-roster-network-topology.svg) / [PNG](proposed-fixed-roster-network-topology.png): the [configurable transport/API-scale proposal](../deployment-bindings-and-public-names.md#configurable-transports-and-independently-scaled-api). REST replica A/B are explicit instances of one stateless REST APIs (v1/v2/v3) component, realtime owns connections, evaluator remains one producer, and maintenance uses per-instance endpoints plus platform/config-supplied roster input. No custom membership service, evaluator scheduler, dynamic roster or Kubernetes resource design is selected. Network transport, remote trust and scale acceptance remain open.

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

Re-render from the repository root:

```bash
python3 tools/site/render_tenancy_topologies.py --png
```

The [renderer](../../../../tools/site/render_tenancy_topologies.py) uses Python's
standard library for SVG and installed ImageMagick for PNG previews. These are
repo-native vector diagrams. Rendering does not run application services or
establish deployment acceptance.
