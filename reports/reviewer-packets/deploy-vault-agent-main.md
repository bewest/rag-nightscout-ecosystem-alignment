<!--
  ============================================================================
  GENERATED FILE - MUST NOT BE HAND-EDITED.

  Source of truth:  queue/work-queue.yaml
  Generator:        tools/queue/emit_packets.py   (make packets)
  Staleness check:  python3 tools/queue/emit_packets.py --check

  Review NOTES belong on the pull request, not here. This file is a projection
  of the manifest; anything written into it is destroyed by the next run.
  ============================================================================
-->

# Review packet — DEPLOY-VAULT-AGENT

**M6c: Vault Agent sidecar in the Compose binding (auto-auth, sink, renewal)**

| | |
|---|---|
| repository | `nightscout-deploy` |
| branch | `main` |
| base | `main@75f0f61` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=DEPLOY-VAULT-AGENT` is the measurement |
| semver | `n/a` |

## What this changes

bindings/compose: a `vault-agent` service with AppRole auto-auth, a token sink
on a shared read-only volume mounted into api/realtime/evaluator/tenant-admin,
a Transit policy per tenant key; bootstrap issues the AppRole, not per-tenant
root tokens. Probes: renewal after TTL, seal and unseal, AppRole secret
rotation.

## Why that semver

deployment repository

## Who should review this, and why

maintainer

## What was measured

**`cd /home/bewest/src/nightscout-deploy && npm test >/dev/null && test -f bindings/compose/vault-agent/compose.v`** &nbsp;·&nbsp; kind: `static`

nightscout-deploy main cda38265: overlay present, Agent role grants renew-
self/lookup-self (the first run showed re-auth each TTL instead of renewal
without it), imported tree still byte-identical to ed2. The measured Compose
smoke (renewal past a 2-minute TTL, stopped Agent fails closed with env tokens
present, recovery after secret-id reissue, restore demo through the overlay)
is recorded in reports/tenancy/vault-agent-2026-11-09/README.md; re-running
vault-agent.sh is the measured gate.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Blocked on

`MT-VAULT-TOKEN-FILE`

## Evidence

- [`docs/30-design/tenancy/claimed-public-names-and-deploy-companion-2026-11-09.md`](../../docs/30-design/tenancy/claimed-public-names-and-deploy-companion-2026-11-09.md)

## Notes carried on the item

Deploy roadmap wave 3 ("Vault service login") is satisfied by this item; no
service-login adapter is written in core. Open sub-question for the maintainer
(m5-m6-decision-list): one AppRole whose policy is the union of tenant
policies (tenant separation at Vault moves to application authority + RLS)
versus one Agent and sink per tenant (core tokenFile already allows a path per
tenant). UNMEASURED: re-auth after token_max_ttl, seal/unseal, tokenFile in
roles that make no Vault calls at ed2.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=DEPLOY-VAULT-AGENT` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
