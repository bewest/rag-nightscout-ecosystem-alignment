# Multitenant decisions in force

*Generated-by-review index, dated 2026-11-18, of the 214 anchored rows in [multitenancy-decisions.md](multitenancy-decisions.md) at alignment source commit `a0a8c3956d`; unanchored table rows are not indexed.*
*Each row is classed as in force, superseded or unclear from its text, citing the later row behind the judgement; the classification is read-derived.*
*Each row's text in multitenancy-decisions.md remains the authority. This page restates no detail: follow the link before acting on a row.*

## In force

Rows marked **deferred** or **proposed** record a direction that is not yet adopted behavior.

### Data model, storage and isolation

- [d1](multitenancy-decisions.md#d1) — Multitenant service is the design target; self-hosted single-tenant stays first-class permanently.
- [d2](multitenancy-decisions.md#d2) — Shared logical storage with a tenant discriminator, not a database per tenant.
- [d3](multitenancy-decisions.md#d3) — PostgreSQL with RLS; serving connections never own tables or bypass RLS; binding is transaction-local.
- [d4](multitenancy-decisions.md#d4) — MongoDB stays permanent for single-tenant sites; adapter changes preserve single-tenant behavior.
- [d8](multitenancy-decisions.md#d8) — API v3's closed operator set is the query contract; `mingo` is a differential oracle.
- [d11](multitenancy-decisions.md#d11) — Devicestatus: generated columns for indexed fields only; body kept as JSONB.
- [d18](multitenancy-decisions.md#d18) — Well-known and controller-owned typed declarations; the hub records and observes, never derives dosing state.
- [d19](multitenancy-decisions.md#d19) — Content-addressed definitions separate from leased instances; one device source of record per channel role.
- [d20](multitenancy-decisions.md#d20) — `identifier` is client sync identity; `_id` is the hub key; quirks are version-scoped.
- [exclusive-application-postgres-ownership](multitenancy-decisions.md#exclusive-application-postgres-ownership) — Nightscout owns its PostgreSQL namespaces; other direct database writers are unsupported.
- [view-reads-total-order](multitenancy-decisions.md#view-reads-total-order) — Sort-key ties break on the per-tenant insertion ordinal, in SQL and in process.
- [write-clock-history-arms](multitenancy-decisions.md#write-clock-history-arms) — The write clock serves only v3 history no-missed-write; competing arms replace the row lock.
- [stream-native-coverage-direction](multitenancy-decisions.md#stream-native-coverage-direction) — Evaluate committed-stream transaction coverage instead of the clock seal; replacement is proposed, unqualified.

### Roles, listeners and horizontal shape

- [d5](multitenancy-decisions.md#d5) — One core; stateless `api`, change-driven `evaluator`, fan-out `realtime`, connector `vcpool`; `single` keeps its server.
- [d16](multitenancy-decisions.md#d16) — Separate data, owner and operator sockets, multiplexed by tenant, not duplicated per tenant.
- [d21](multitenancy-decisions.md#d21) — One executable: `single`, `multitenant <role>[,<role>…]` and operator tools.
- [d23](multitenancy-decisions.md#d23) — Realtime is a reader; every socket write and alarm ack is forwarded to `api`.
- [d7](multitenancy-decisions.md#d7) — Operator plane is credential-free and secured by unreachability (narrowed by [admin-plane-same-address-different-port](multitenancy-decisions.md#admin-plane-same-address-different-port)).
- [admin-plane-same-address-different-port](multitenancy-decisions.md#admin-plane-same-address-different-port) — Admin listener may share the API address on another port; never all interfaces.
- [internal-service-contracts](multitenancy-decisions.md#internal-service-contracts) — Internal APIs: separate service contracts per listener; no new bearer authentication (narrowed by [internal-listener-ory-pattern](multitenancy-decisions.md#internal-listener-ory-pattern)).
- [internal-listener-ory-pattern](multitenancy-decisions.md#internal-listener-ory-pattern) — One private `serve.internal` listener per role, Ory-style (narrowed by [k1-per-role-deployments](multitenancy-decisions.md#k1-per-role-deployments)).
- [internal-listener-graceful-shutdown](multitenancy-decisions.md#internal-listener-graceful-shutdown) — On SIGTERM the internal listener drains in-flight calls up to a deadline.
- [static-hash-ownership](multitenancy-decisions.md#static-hash-ownership) — Evaluator and realtime processes own `slice(hash(tenant), K)`; proxy routes match; changing K is a restart.
- [legacy-topology-retirement](multitenancy-decisions.md#legacy-topology-retirement) — One evaluator topology: native stream plus assigned-worker seam; other pool and lease topologies retire.
- [pool-primitive-shared](multitenancy-decisions.md#pool-primitive-shared) — One pool-membership primitive, kinds kept separate (narrowed by [legacy-topology-retirement](multitenancy-decisions.md#legacy-topology-retirement): kept for connectors).
- [census-operational-list](multitenancy-decisions.md#census-operational-list) — Operational catalogues are listed explicitly and excluded from per-tenant restore, export and deletion.
- [pool-member-hygiene](multitenancy-decisions.md#pool-member-hygiene) — Pool members reclaim stale sockets and wait-and-alert instead of exiting.
- [cohort-pod-not-scaled](multitenancy-decisions.md#cohort-pod-not-scaled) — Never scale the all-roles monolith horizontally (narrowed by [k1-per-role-deployments](multitenancy-decisions.md#k1-per-role-deployments)).
- [vcpool-egress-capacity](multitenancy-decisions.md#vcpool-egress-capacity) — Connector pools are sized against upstream quotas; core reports upstream refusals per member.
- [evaluator-scale-direction](multitenancy-decisions.md#evaluator-scale-direction) — Profile first, then K evaluator processes; no coalescing window (narrowed by [static-hash-ownership](multitenancy-decisions.md#static-hash-ownership): not urgent).
- [private-stream-router](multitenancy-decisions.md#private-stream-router) — **Deferred**: for K > 1, preferred shape is a private body-reading router with stock pgstream.

### Platform/application boundary, startup and simplification

- [platform-application-boundary](multitenancy-decisions.md#platform-application-boundary) — Application assumes a verified platform and fails closed; it never re-verifies the platform while serving.
- [brittle-check-removal](multitenancy-decisions.md#brittle-check-removal) — Checks that refuse for anything other than a product property are removed; run identity is image digest plus run configuration.
- [architecture-justified-removal](multitenancy-decisions.md#architecture-justified-removal) — Machinery from an obsolete design is removed on architecture grounds with correctness controls, no measurement.
- [serial-machinery-retirement](multitenancy-decisions.md#serial-machinery-retirement) — Remove serial machinery the streaming design no longer needs, rather than tune it.
- [operable-architecture-first](multitenancy-decisions.md#operable-architecture-first) — Simplified, runnable, operable architecture first; performance work is lower priority meanwhile.
- [boot-independent-of-tenants](multitenancy-decisions.md#boot-independent-of-tenants) — Serving boot is independent of tenant count; expensive platform verification runs on `admin`.
- [catalogue-verification-admin-owned](multitenancy-decisions.md#catalogue-verification-admin-owned) — Admin verifies the catalogue once per deployment; serving keeps one cheap fail-closed check.
- [vcpool-proof-role](multitenancy-decisions.md#vcpool-proof-role) — `vcpool` checks the platform proof at start like the other serving roles.
- [stable-evaluator-runtime](multitenancy-decisions.md#stable-evaluator-runtime) — Evaluator runs on a stable schema; relevant DDL after startup stops it with a typed code.
- [migration-rehearsal-separate](multitenancy-decisions.md#migration-rehearsal-separate) — Migrations are rehearsed as scheduled maintenance, separate from performance and acceptance runs.
- [multitenant-upgrade-shape](multitenancy-decisions.md#multitenant-upgrade-shape) — Platform rolls processes; core supplies two-step migrations and checks (narrowed by [stable-evaluator-runtime](multitenancy-decisions.md#stable-evaluator-runtime)).
- [tenant-local-startup-admission](multitenancy-decisions.md#tenant-local-startup-admission) — A suspended tenant never prevents other tenants becoming ready after a restart.
- [tenant-defect-tenant-scoped](multitenancy-decisions.md#tenant-defect-tenant-scoped) — A defect in one tenant's state refuses that tenant only; deployment defects refuse startup.
- [readiness-serve-then-warm](multitenancy-decisions.md#readiness-serve-then-warm) — A role is ready when its own dependencies are up; tenants warm in the background.
- [datastore-loss-recover-in-place](multitenancy-decisions.md#datastore-loss-recover-in-place) — On PostgreSQL loss a role reports unhealthy, reconnects and rebuilds; exits only past a bound.
- [datastore-loss-before-window-retirement](multitenancy-decisions.md#datastore-loss-before-window-retirement) — Move datastore-loss recovery to a connection probe before retiring the operation window.
- [lane-failure-recover-in-place](multitenancy-decisions.md#lane-failure-recover-in-place) — A failed session lane is replaced in place, never hiding an uncertain completion.
- [compose-restart-on-failure](multitenancy-decisions.md#compose-restart-on-failure) — Compose production default is `restart: on-failure`; tests may disable restart.
- [pg-connection-budget](multitenancy-decisions.md#pg-connection-budget) — Deploy sizes `max_connections` from the declared per-role connection budget.

### Deployment repository and Kubernetes

- [d12](multitenancy-decisions.md#d12) — Alignment holds tooling and evidence; shipping code and tests live in `cgm-remote-monitor`.
- [platform-home-nightscout-deploy](multitenancy-decisions.md#platform-home-nightscout-deploy) — Platform concerns without a core home move to `nightscout-deploy`.
- [deploy-tree-home-now](multitenancy-decisions.md#deploy-tree-home-now) — `nightscout-deploy` holds the Compose tree now (narrowed by [deployment-plan-contract](multitenancy-decisions.md#deployment-plan-contract)).
- [deployment-plan-contract](multitenancy-decisions.md#deployment-plan-contract) — One deployment plan in deploy, checked against a contract core publishes.
- [core-static-plan-retired](multitenancy-decisions.md#core-static-plan-retired) — Core's static Compose plan retires; core tests use a small registry-mode fixture plan.
- [deploy-repo-readme](multitenancy-decisions.md#deploy-repo-readme) — The deploy README addresses operators: what runs, how to run it, the pinned core commit.
- [k1-per-role-deployments](multitenancy-decisions.md#k1-per-role-deployments) — Kubernetes: one Deployment per role, `Recreate`, per-role Services; migrations as Jobs before serving.
- [kubernetes-idiomatic-operations](multitenancy-decisions.md#kubernetes-idiomatic-operations) — Use Kubernetes ordering, digests, quotas, probes and in-cluster Jobs instead of re-proving guarantees.
- [k8s-platform-proofs-to-deploy](multitenancy-decisions.md#k8s-platform-proofs-to-deploy) — Kubernetes runs stop selecting opt-in platform proofs; one fit check and image publication move to deploy.
- [tanka-binding-parallel](multitenancy-decisions.md#tanka-binding-parallel) — The Kubernetes binding is a Tanka-style Jsonnet environment in `nightscout-deploy`.

### Tenant registry, resolution, ingress and provisioning

- [d10](multitenancy-decisions.md#d10) — Slug is a unique host label; trusted resolution maps host to label to stable tenant id.
- [d15](multitenancy-decisions.md#d15) — `single` reads the environment; multitenant per-tenant values come from storage under policy.
- [tenant-registry](multitenancy-decisions.md#tenant-registry) — Tenants and aliases live in a PostgreSQL registry (narrowed by [event-driven-reset](multitenancy-decisions.md#event-driven-reset): refresh signal).
- [provisioning-split](multitenancy-decisions.md#provisioning-split) — Provisioning is an `admin` operation every caller uses; no caller writes provisioning rows directly.
- [operator-rest-api](multitenancy-decisions.md#operator-rest-api) — Operator operations are a versioned REST API on `admin`; reachability, not core, controls callers.
- [static-mode-lab-flag](multitenancy-decisions.md#static-mode-lab-flag) — A role refuses a `tenants` list unless `MULTITENANT_STATIC_TENANTS=lab`; static mode then retires.
- [tenant-live-add](multitenancy-decisions.md#tenant-live-add) — Running evaluator and realtime pick up newly provisioned tenants without restart (separate lane).
- [registry-connector-definitions](multitenancy-decisions.md#registry-connector-definitions) — Connector definitions are durable tenant configuration; endpoint and credential values stay in tenant secrets.
- [tenant-ensure-and-factory-reset](multitenancy-decisions.md#tenant-ensure-and-factory-reset) — Audited `ensure` and `factory reset` operations; reset never erases clinical data or credentials.
- [deployment-ingress-peer-list-trust](multitenancy-decisions.md#deployment-ingress-peer-list-trust) — One explicit peer list serves tenant selection and `TRUST_PROXY`; empty refuses startup.
- [edge-forwarded-headers-left](multitenancy-decisions.md#edge-forwarded-headers-left) — The edge keeps forwarding its headers; core's selector refusal is the control.
- [failed-login-delay-core](multitenancy-decisions.md#failed-login-delay-core) — Failed authentication delays the next request as on a single site, keyed on the real client address.
- [deployment-admission-probes-and-trust-record](multitenancy-decisions.md#deployment-admission-probes-and-trust-record) — Production admission needs a written trust record plus spoof, conflict and outage probes.

### Identity, credentials and secrets

- [d13](multitenancy-decisions.md#d13) — No deployment-wide secret on any multitenant interface; each tenant keeps its own root credential.
- [d14](multitenancy-decisions.md#d14) — Per-tenant signing authority; resolve the tenant before examining a credential.
- [d17](multitenancy-decisions.md#d17) — Devices keep native tenant credentials; humans use shared optional OIDC (narrowed by [deployment-identity-generic-adapter-authentik-reference](multitenancy-decisions.md#deployment-identity-generic-adapter-authentik-reference)).
- [d22](multitenancy-decisions.md#d22) — Effective settings layer code, operator, owner and pins under project floors; secrets are a separate component.
- [shared-oidc-provider-renewal](multitenancy-decisions.md#shared-oidc-provider-renewal) — One optional OIDC integration for both modes, provider-backed renewal first, `ENABLE=oidc`.
- [oidc-provider-outage-existing-access](multitenancy-decisions.md#oidc-provider-outage-existing-access) — During provider outage, existing access lasts until expiry; no new login or renewal.
- [human-session-outage-and-logout](multitenancy-decisions.md#human-session-outage-and-logout) — Pointer anchor; the policy lives in the provider-outage row above.
- [human-session-idle-scope-management-only](multitenancy-decisions.md#human-session-idle-scope-management-only) — Idle and absolute lifetimes apply to management sessions only; data viewing is unchanged.
- [human-session-logout-local-first](multitenancy-decisions.md#human-session-logout-local-first) — Logout invalidates the Nightscout session first, then the browser credential, then the provider.
- [human-session-renewal-fenced](multitenancy-decisions.md#human-session-renewal-fenced) — Concurrent renewal is fenced and idempotent per session; never resurrects revoked state.
- [human-session-transport-cookie-default](multitenancy-decisions.md#human-session-transport-cookie-default) — HttpOnly cookie is the default browser transport under OIDC; direct-token mode remains.
- [deployment-identity-generic-adapter-authentik-reference](multitenancy-decisions.md#deployment-identity-generic-adapter-authentik-reference) — Generic OIDC adapter; Authentik intended reference if it passes the proof; Kratos fallback.
- [oidc-browser-discovery-opt-in](multitenancy-decisions.md#oidc-browser-discovery-opt-in) — The browser looks for a human session only on pages marked OIDC-enabled.
- [single-site-oidc-identity-list](multitenancy-decisions.md#single-site-oidc-identity-list) — Single-site OIDC: an operator list maps identities to existing roles, with a fallback role.
- [single-site-oidc-list-authoritative](multitenancy-decisions.md#single-site-oidc-list-authoritative) — The single-site identity list is re-applied at each start and removes delisted people.
- [registry-oidc-origins](multitenancy-decisions.md#registry-oidc-origins) — In registry mode OIDC derives each tenant's origin from its resolved alias.
- [deployment-secrets-ladder-vault-all-stages](multitenancy-decisions.md#deployment-secrets-ladder-vault-all-stages) — Vault Transit at every stage (narrowed by [vault-agent-sidecar](multitenancy-decisions.md#vault-agent-sidecar): no login adapter in core).
- [vault-agent-sidecar](multitenancy-decisions.md#vault-agent-sidecar) — Vault Agent sidecar handles auth and renewal; the app reads the token file at call time.
- [vault-one-approle-per-deployment](multitenancy-decisions.md#vault-one-approle-per-deployment) — One AppRole per deployment; tenant separation comes from application authority and RLS.
- [vault-approle-lockout-off](multitenancy-decisions.md#vault-approle-lockout-off) — Vault user lockout is disabled for the deployment's single AppRole login.
- [integration-credential-parts](multitenancy-decisions.md#integration-credential-parts) — Integration credentials split into operator-owned and owner-owned parts; neither reads the other's.
- [tenant-root-secret-owner-control](multitenancy-decisions.md#tenant-root-secret-owner-control) — Owners can reveal (after re-authentication), audit, rotate and set the tenant root secret.
- [authorize-cost-first](multitenancy-decisions.md#authorize-cost-first) — Cut per-authorization cost before API scale-out (narrowed by [authority-recheck-deferred](multitenancy-decisions.md#authority-recheck-deferred)).
- [legacy-decision-reuse-60s](multitenancy-decisions.md#legacy-decision-reuse-60s) — Optional legacy-credential decision reuse, 60 s default, off by default (narrowed by [authority-recheck-deferred](multitenancy-decisions.md#authority-recheck-deferred)).
- [authority-recheck-deferred](multitenancy-decisions.md#authority-recheck-deferred) — **Deferred**: no authority cache or epoch machinery this round; revocation stays immediate.

### Owner, root and subject authority

- [authority-split-diagram](multitenancy-decisions.md#authority-split-diagram) — Figure: root, owner and operator authorities as decided 2026-11-10.
- [tenant-root-single-site-parity](multitenancy-decisions.md#tenant-root-single-site-parity) — Tenant `API_SECRET` has single-site authority; never owner or operator authority.
- [root-may-edit-owner-subjects](multitenancy-decisions.md#root-may-edit-owner-subjects) — Root may edit or delete any subject; removing the last usable owner is refused.
- [root-role-edit-delete](multitenancy-decisions.md#root-role-edit-delete) — Root may edit role permissions; renaming, or deleting a held role, is refused.
- [root-grant-ceiling-default-all](multitenancy-decisions.md#root-grant-ceiling-default-all) — Root may grant any tenant data permission unless the operator narrows the list.
- [admin-role-subjects-use-admin-tools](multitenancy-decisions.md#admin-role-subjects-use-admin-tools) — Subjects granted `admin:api:subjects:*` use the admin tools with their own token.
- [owner-credentials-single-tenant-equivalent](multitenancy-decisions.md#owner-credentials-single-tenant-equivalent) — Owners manage subjects and roles with any single-tenant Shiro string, wildcards included.
- [permission-tightening-applies-to-both](multitenancy-decisions.md#permission-tightening-applies-to-both) — Any permission tightening is a separate proposal applying to single and multitenant alike.
- [owner-may-revoke-subjects](multitenancy-decisions.md#owner-may-revoke-subjects) — An owner may revoke subjects on their own site.
- [preview-operator-assisted-ownership](multitenancy-decisions.md#preview-operator-assisted-ownership) — First-preview ownership changes are operator-assisted; self-service comes later.
- [owner-settings-projected-catalogue](multitenancy-decisions.md#owner-settings-projected-catalogue) — Owner-writable settings are the projected display catalogue plus plugin `enable`; others refuse.
- [owner-alarm-thresholds](multitenancy-decisions.md#owner-alarm-thresholds) — Glucose thresholds and alarm enables are owner-writable, bounded 30–600 mg/dL.
- [owner-integrations-none-first-preview](multitenancy-decisions.md#owner-integrations-none-first-preview) — No owner-configurable integrations in the first preview.

### Tenant activity and deletion lifecycle

- [tenant-activity-states-diagram](multitenancy-decisions.md#tenant-activity-states-diagram) — Figure: active, paused and suspended states as decided 2026-11-10.
- [activity-is-pause-suspend](multitenancy-decisions.md#activity-is-pause-suspend) — Activity is pause or suspend only; paused sites store uploads but compute no alarms.
- [activity-adopted-semantics-wiring](multitenancy-decisions.md#activity-adopted-semantics-wiring) — Suspend refuses ingest and reads; pause blocks reads and UI while uploads continue.
- [owner-may-pause](multitenancy-decisions.md#owner-may-pause) — Owners may pause their own site; only the operator suspends and deletes.
- [activity-row-always-provisioned](multitenancy-decisions.md#activity-row-always-provisioned) — Every tenant has an activity row; an unreadable row stops that tenant's evaluator only.
- [suspended-refusal-423](multitenancy-decisions.md#suspended-refusal-423) — Suspended and paused refusals return 423 (narrowed by [restore-fence-generation](multitenancy-decisions.md#restore-fence-generation): retryable during restore).
- [d6-activity-control-path](multitenancy-decisions.md#d6-activity-control-path) — Paused or suspended tenants do no evaluator or realtime data work; detection needs no data write.
- [connector-pause-gap-accepted](multitenancy-decisions.md#connector-pause-gap-accepted) — A connector started while paused waits for unpause; no data is lost.
- [deletion-request-auto-pauses](multitenancy-decisions.md#deletion-request-auto-pauses) — An owner's deletion request pauses the site; cancelling restores the earlier state.
- [preview-deletion-confirmation](multitenancy-decisions.md#preview-deletion-confirmation) — Deletion needs an explicit request and operator confirmation; no mandatory waiting period.
- [tenant-deletion-key-retention](multitenancy-decisions.md#tenant-deletion-key-retention) — Deletion keeps Transit keys and export artifact 30 days, then the operator destroys keys.
- [key-destruction-removes-export](multitenancy-decisions.md#key-destruction-removes-export) — Key destruction also removes the export artifact file, in the same audit entry.
- [export-removal-no-retry](multitenancy-decisions.md#export-removal-no-retry) — A repeat destruction reports the recorded removal outcome; it does not retry.

### Restore and recovery

- [restore-identity-and-cloning](multitenancy-decisions.md#restore-identity-and-cloning) — Restore keeps the original tenant id; cloning is a separate operation with new secrets.
- [deleted-tenant-exact-artifact-first](multitenancy-decisions.md#deleted-tenant-exact-artifact-first) — Deleted-tenant recovery first uses the exact confirmed deletion artifact within retention.
- [m5-bounded-snapshot-reconciliation](multitenancy-decisions.md#m5-bounded-snapshot-reconciliation) — Current-state recovery reconciles a bounded consistent snapshot (narrowed by [stream-fed-clinical-materializer](multitenancy-decisions.md#stream-fed-clinical-materializer)).
- [tenant-local-insertion-semantics](multitenancy-decisions.md#tenant-local-insertion-semantics) — Insertion order is required only within a tenant and collection; pursue tenant-local insertion state.
- [tenant-local-restore-existing-allocator](multitenancy-decisions.md#tenant-local-restore-existing-allocator) — Original-tenant restore preserves other tenants (narrowed by [restore-suspend-drain-replace](multitenancy-decisions.md#restore-suspend-drain-replace)).
- [restore-history-forward-correction](multitenancy-decisions.md#restore-history-forward-correction) — Restore publishes normal history updates and deletions so clients converge.
- [restore-service-processes](multitenancy-decisions.md#restore-service-processes) — Restore works across separately deployed roles (narrowed by [restore-suspend-drain-replace](multitenancy-decisions.md#restore-suspend-drain-replace): no cohort invalidate).
- [restore-fence-generation](multitenancy-decisions.md#restore-fence-generation) — Tenant generation fencing replaces the operation window (narrowed by [restore-fence-read-path](multitenancy-decisions.md#restore-fence-read-path) and [catalogue-verification-admin-owned](multitenancy-decisions.md#catalogue-verification-admin-owned)).
- [restore-fence-read-path](multitenancy-decisions.md#restore-fence-read-path) — Read-only port skips the final generation compare; writes keep lock then generation read.
- [restore-suspend-drain-replace](multitenancy-decisions.md#restore-suspend-drain-replace) — Restore is suspend, drain in-flight transactions, replace, activate.
- [restore-census-and-ownership-phase](multitenancy-decisions.md#restore-census-and-ownership-phase) — Ownership operations refuse unless the tenant is active (census part: see Unclear).
- [restore-resume-and-precheck](multitenancy-decisions.md#restore-resume-and-precheck) — Interrupted restore reopens by audited `resume` (narrowed by [restore-suspend-drain-replace](multitenancy-decisions.md#restore-suspend-drain-replace): operation-record precheck).

### Event feed, evaluator and realtime

- [d6](multitenancy-decisions.md#d6) — Replication slot is the durable spine; clinical writes never depend on notifications (narrowed by [event-driven-reset](multitenancy-decisions.md#event-driven-reset)).
- [event-driven-reset](multitenancy-decisions.md#event-driven-reset) — Stop tuning the polling architecture; maintained pgstream CDC drives evaluator and realtime.
- [pgstream-operating-constraints](multitenancy-decisions.md#pgstream-operating-constraints) — One evaluator receiver, no broker, narrow streaming role, strict mode; heartbeat machinery retires.
- [evaluator-platform-restart](multitenancy-decisions.md#evaluator-platform-restart) — pgstream restarts separately from the evaluator process.
- [stream-fed-clinical-materializer](multitenancy-decisions.md#stream-fed-clinical-materializer) — Committed clinical rows stream into the evaluator; snapshots only for bootstrap, recovery and gaps.
- [single-host-streaming-first](multitenancy-decisions.md#single-host-streaming-first) — Qualify a simple single-host baseline first (narrowed by [cluster-fan-out-testing](multitenancy-decisions.md#cluster-fan-out-testing)).
- [single-evaluator-efficiency-priority](multitenancy-decisions.md#single-evaluator-efficiency-priority) — One evaluator's efficiency first (narrowed by [operable-architecture-first](multitenancy-decisions.md#operable-architecture-first): lower priority).
- [trusted-worker-performance-boundary](multitenancy-decisions.md#trusted-worker-performance-boundary) — Trusted evaluator and feed workers skip per-tenant impersonation and repeated integrity screens.
- [tenant-version-batch-read](multitenancy-decisions.md#tenant-version-batch-read) — One batched version read per pass (narrowed by [trusted-worker-performance-boundary](multitenancy-decisions.md#trusted-worker-performance-boundary)).
- [version-batch-shared-login-bound](multitenancy-decisions.md#version-batch-shared-login-bound) — Shared pool login bound accepted (narrowed by [event-driven-reset](multitenancy-decisions.md#event-driven-reset): idle feed checkpoint part).
- [evaluator-settings-safety-net](multitenancy-decisions.md#evaluator-settings-safety-net) — The evaluator re-reads every tenant's full settings on a slow timer, 10 minutes default.
- [evaluator-settings-error-shape](multitenancy-decisions.md#evaluator-settings-error-shape) — Settings-read failures reach the evaluator as `SETTINGS_POLICY_UNAVAILABLE` with a cause code.
- [alarm-output-idempotent-by-content](multitenancy-decisions.md#alarm-output-idempotent-by-content) — Alarm output freshness and origins derive from content, so overlapping evaluators produce one request.
- [alarm-repeat-clock](multitenancy-decisions.md#alarm-repeat-clock) — Active alarms repeat on the single-site heartbeat clock, independent of evaluator revisions.
- [versioned-output-not-owner-lock](multitenancy-decisions.md#versioned-output-not-owner-lock) — **Proposed, deferred** by [versioned-output-deferred](multitenancy-decisions.md#versioned-output-deferred): versioned conditional output commits.
- [versioned-output-deferred](multitenancy-decisions.md#versioned-output-deferred) — W not joined; xdripjs keeps its in-memory notification interval in both modes, documented.
- [realtime-connection-driven](multitenancy-decisions.md#realtime-connection-driven) — Realtime loads a tenant only while it has sockets (narrowed by [static-hash-ownership](multitenancy-decisions.md#static-hash-ownership): placement).
- [realtime-move-alarm-parity](multitenancy-decisions.md#realtime-move-alarm-parity) — Reconnects do not replay alarms; they return on the heartbeat (narrowed by [static-hash-ownership](multitenancy-decisions.md#static-hash-ownership): no dynamic moves).
- [realtime-no-socket-cap](multitenancy-decisions.md#realtime-no-socket-cap) — No per-process socket cap; disconnects carry cause codes; flood control belongs to the edge.
- [tenant-devicestatus-status-parity](multitenancy-decisions.md#tenant-devicestatus-status-parity) — Tenant status reports `devicestatus: {advanced: true, days: 1}` as a single site does.

### Alarms and external delivery

- [tenant-wide-alarm-suppression](multitenancy-decisions.md#tenant-wide-alarm-suppression) — Ack and snooze suppress tenant-wide, keeping the original absolute expiry across restart.
- [durable-notification-requests-and-retries](multitenancy-decisions.md#durable-notification-requests-and-retries) — Persist a stable notification request before dispatch; retry the same identity after ambiguity.
- [first-preview-no-push-provider](multitenancy-decisions.md#first-preview-no-push-provider) — No live push provider; in-app alarms; Nightscout-to-Nightscout sync is the first external channel.
- [notification-bounds-single-tenant-constants](multitenancy-decisions.md#notification-bounds-single-tenant-constants) — Initial notification and connector bounds are the single-tenant constants.
- [external-delivery-admission-by-probe](multitenancy-decisions.md#external-delivery-admission-by-probe) — External delivery is admitted by channel-appropriate probes, not a human-observed device.

### Testing, capacity and process

- [performance-signals-not-gates](multitenancy-decisions.md#performance-signals-not-gates) — Performance results are signals; correctness and safety gates stay strict.
- [capacity-characterize-not-gate](multitenancy-decisions.md#capacity-characterize-not-gate) — Capacity runs characterize; they stop only on incorrect behavior or an unmeasurable harness.
- [capacity-test-tiers](multitenancy-decisions.md#capacity-test-tiers) — Smoke, discovery and acceptance tiers with a target ladder (narrowed by [cluster-fan-out-testing](multitenancy-decisions.md#cluster-fan-out-testing): environments).
- [outcome-evaluator-gate](multitenancy-decisions.md#outcome-evaluator-gate) — The evaluator gate judges outcomes against the 120 s clinical deadline; typed transient retries are counted.
- [preload-is-a-signal](multitenancy-decisions.md#preload-is-a-signal) — Whole-roster preload convergence is a signal; traffic starts when roles are ready.
- [m7-envelope-measured-not-declared](multitenancy-decisions.md#m7-envelope-measured-not-declared) — Operating limits come from measurement (narrowed by [operable-architecture-first](multitenancy-decisions.md#operable-architecture-first)).
- [local-10k-release](multitenancy-decisions.md#local-10k-release) — Run the local 10,000-tenant realistic-mix point now on the a72 reference.
- [latency-lane-held](multitenancy-decisions.md#latency-lane-held) — The latency-observer lane does not start this cycle (narrowed by [cluster-fan-out-testing](multitenancy-decisions.md#cluster-fan-out-testing)).
- [cluster-fan-out-testing](multitenancy-decisions.md#cluster-fan-out-testing) — The existing cluster runs concurrent scenarios per namespace; largest points on the workstation; droplets stop.
- [reserved-k8s-worker](multitenancy-decisions.md#reserved-k8s-worker) — A worker may be reserved by taint, never evicting (narrowed by [cluster-fan-out-testing](multitenancy-decisions.md#cluster-fan-out-testing): clean-number points only).
- [workload-acceleration-local-only](multitenancy-decisions.md#workload-acceleration-local-only) — Remote and capacity runs use real time; only local harness checks accelerate.
- [concurrent-branch-experiments](multitenancy-decisions.md#concurrent-branch-experiments) — Isolated synthetic branch experiments may run before full acceptance.
- [flexible-experiment-limits](multitenancy-decisions.md#flexible-experiment-limits) — Reference sizes are configurable; identify a restriction's source before adding it.
- [routine-diagnostic-image-delivery](multitenancy-decisions.md#routine-diagnostic-image-delivery) — Routine low-cost diagnostic image pushes and pulls need no per-image approval.
- [disposable-native-harness](multitenancy-decisions.md#disposable-native-harness) — Native acceptance uses a disposable harness (narrowed by [simple-run-cleanup](multitenancy-decisions.md#simple-run-cleanup)).
- [simple-run-cleanup](multitenancy-decisions.md#simple-run-cleanup) — Cleanup is one owned delete plus one absence check.
- [m6-split-and-queue-collapse](multitenancy-decisions.md#m6-split-and-queue-collapse) — Milestones M6a–M6d for the preview; M7 before any production cohort.
- [restore-candidate-frozen](multitenancy-decisions.md#restore-candidate-frozen) — The next frozen candidate is the restore branch joined with the K1 deploy profile and helper.
- [8898-continue-adding](multitenancy-decisions.md#8898-continue-adding) — #8898 stays draft and keeps receiving batches; merge before 16.0.0 is undecided.
- [three-lane-coordination](multitenancy-decisions.md#three-lane-coordination) — One coordinator and three lanes: source, gate/instrument, operations; optional capabilities paused.
- [fresh-context-phase-ownership](multitenancy-decisions.md#fresh-context-phase-ownership) — Fresh chats at phase boundaries; explicit custody transfer (refined by [three-lane-coordination](multitenancy-decisions.md#three-lane-coordination)).

## Superseded or retired

The text of every row below was archived unchanged on 2026-11-18 in [the superseded-decisions archive](../../archive/tenancy/multitenancy-decisions-superseded-2026-11-18.md); each link resolves to a one-line stub in multitenancy-decisions.md that points there.

| row | replaced by | reason |
|---|---|---|
| [d9](multitenancy-decisions.md#d9) | its own text | historical base; the current-dev delivery plan supersedes it |
| [allocator-preserving-restore-first](multitenancy-decisions.md#allocator-preserving-restore-first) | [tenant-local-insertion-semantics](multitenancy-decisions.md#tenant-local-insertion-semantics), [restore-suspend-drain-replace](multitenancy-decisions.md#restore-suspend-drain-replace) | shared allocator and shared pause not the target |
| [deploy-tree-lives-in-nightscout-deploy](multitenancy-decisions.md#deploy-tree-lives-in-nightscout-deploy) | [deploy-tree-home-now](multitenancy-decisions.md#deploy-tree-home-now), [core-static-plan-retired](multitenancy-decisions.md#core-static-plan-retired) | move timing and core copy replaced |
| [evaluator-static-partition](multitenancy-decisions.md#evaluator-static-partition) | [static-hash-ownership](multitenancy-decisions.md#static-hash-ownership), [alarm-output-idempotent-by-content](multitenancy-decisions.md#alarm-output-idempotent-by-content) | heartbeat agreement replaced; idempotence premise refuted |
| [evaluator-partition-now](multitenancy-decisions.md#evaluator-partition-now) | [static-hash-ownership](multitenancy-decisions.md#static-hash-ownership), [legacy-topology-retirement](multitenancy-decisions.md#legacy-topology-retirement) | pool partition flag topology retires |
| [8898-review-after-batch](multitenancy-decisions.md#8898-review-after-batch) | [8898-continue-adding](multitenancy-decisions.md#8898-continue-adding) | batch joined; draft continues |
| [push-m7-join-9db](multitenancy-decisions.md#push-m7-join-9db) | [restore-candidate-frozen](multitenancy-decisions.md#restore-candidate-frozen) | completed one-time join instruction |
| [bench-first-on-workstation](multitenancy-decisions.md#bench-first-on-workstation) | [capacity-test-tiers](multitenancy-decisions.md#capacity-test-tiers), [cluster-fan-out-testing](multitenancy-decisions.md#cluster-fan-out-testing) | run environments now set by tiers and fan-out |
| [m7-capacity-gate](multitenancy-decisions.md#m7-capacity-gate) | [performance-signals-not-gates](multitenancy-decisions.md#performance-signals-not-gates), [capacity-test-tiers](multitenancy-decisions.md#capacity-test-tiers) | fixed tenant gate replaced by signals and target ladder |
| [m7-baseline-discovery](multitenancy-decisions.md#m7-baseline-discovery) | [event-driven-reset](multitenancy-decisions.md#event-driven-reset), [capacity-test-tiers](multitenancy-decisions.md#capacity-test-tiers) | polling-architecture baseline stopped |
| [m7-parallel-unaccepted-measurement](multitenancy-decisions.md#m7-parallel-unaccepted-measurement) | [concurrent-branch-experiments](multitenancy-decisions.md#concurrent-branch-experiments), [capacity-test-tiers](multitenancy-decisions.md#capacity-test-tiers) | generalized into discovery tier |
| [capacity-ab-1000-two-machines](multitenancy-decisions.md#capacity-ab-1000-two-machines) | [event-driven-reset](multitenancy-decisions.md#event-driven-reset), [cluster-fan-out-testing](multitenancy-decisions.md#cluster-fan-out-testing) | polling-era remote comparison; droplets stop |
| [cost-proportional-to-activity](multitenancy-decisions.md#cost-proportional-to-activity) | [event-driven-reset](multitenancy-decisions.md#event-driven-reset) | polling, epoch and roster mechanisms replaced by CDC |
| [d6-paged-backstop](multitenancy-decisions.md#d6-paged-backstop) | [event-driven-reset](multitenancy-decisions.md#event-driven-reset) | named as superseded there |
| [d6-sql-reader-transport](multitenancy-decisions.md#d6-sql-reader-transport) | [event-driven-reset](multitenancy-decisions.md#event-driven-reset) | SQL polling reader replaced by pgstream |
| [feed-slot-advance-idle](multitenancy-decisions.md#feed-slot-advance-idle) | [event-driven-reset](multitenancy-decisions.md#event-driven-reset) | named as superseded there |
| [feed-healthy-sweep-default](multitenancy-decisions.md#feed-healthy-sweep-default) | [event-driven-reset](multitenancy-decisions.md#event-driven-reset), [pgstream-operating-constraints](multitenancy-decisions.md#pgstream-operating-constraints) | polling-era feed sweep |
| [change-stamp-definer-function](multitenancy-decisions.md#change-stamp-definer-function) | [write-clock-history-arms](multitenancy-decisions.md#write-clock-history-arms) | clock no longer serves change detection |
| [write-clock-complete](multitenancy-decisions.md#write-clock-complete) | [write-clock-history-arms](multitenancy-decisions.md#write-clock-history-arms) | rationale retired; history requirement moved |
| [incremental-refresh](multitenancy-decisions.md#incremental-refresh) | [incremental-refresh-realtime-only](multitenancy-decisions.md#incremental-refresh-realtime-only), [stream-fed-clinical-materializer](multitenancy-decisions.md#stream-fed-clinical-materializer) | checkpoint re-reads replaced by streamed rows |
| [incremental-refresh-realtime-only](multitenancy-decisions.md#incremental-refresh-realtime-only) | [stream-fed-clinical-materializer](multitenancy-decisions.md#stream-fed-clinical-materializer), [realtime-connection-driven](multitenancy-decisions.md#realtime-connection-driven) | evaluator streams input; realtime consumes output |
| [admission-epoch-everywhere](multitenancy-decisions.md#admission-epoch-everywhere) | [restore-fence-generation](multitenancy-decisions.md#restore-fence-generation), [catalogue-verification-admin-owned](multitenancy-decisions.md#catalogue-verification-admin-owned) | per-transaction catalogue epoch replaced |
| [root-writer-fenced](multitenancy-decisions.md#root-writer-fenced) | [restore-fence-generation](multitenancy-decisions.md#restore-fence-generation) | operation window replaced by generation fencing |
| [settings-screen-evaluator-only](multitenancy-decisions.md#settings-screen-evaluator-only) | [trusted-worker-performance-boundary](multitenancy-decisions.md#trusted-worker-performance-boundary) | evaluator per-read screen named as superseded |
| [legacy-decision-reuse-window](multitenancy-decisions.md#legacy-decision-reuse-window) | [legacy-decision-reuse-60s](multitenancy-decisions.md#legacy-decision-reuse-60s) | amended window default and scope |
| [realtime-controlled-moves](multitenancy-decisions.md#realtime-controlled-moves) | [static-hash-ownership](multitenancy-decisions.md#static-hash-ownership) | dynamic placement and map moves retire |
| [realtime-shard-rule](multitenancy-decisions.md#realtime-shard-rule) | [static-hash-ownership](multitenancy-decisions.md#static-hash-ownership) | shard map replaced by per-process slice |
| [realtime-automatic-recovery](multitenancy-decisions.md#realtime-automatic-recovery) | [static-hash-ownership](multitenancy-decisions.md#static-hash-ownership), [k1-per-role-deployments](multitenancy-decisions.md#k1-per-role-deployments) | peer takeover and map revisions retire; platform restarts |

## Unclear

| row | question that needs answering |
|---|---|
| [pool-desired-count-in-table](multitenancy-decisions.md#pool-desired-count-in-table) | [static-hash-ownership](multitenancy-decisions.md#static-hash-ownership) makes changing K a restart for evaluator and realtime. Does the in-table expected count still govern `vcpool`, or retire everywhere? |
| [restore-census-counter-writers](multitenancy-decisions.md#restore-census-counter-writers) | [restore-suspend-drain-replace](multitenancy-decisions.md#restore-suspend-drain-replace) retires the cohort census after replacement. Does the pre-restore census of connected writers (here and in [restore-census-and-ownership-phase](multitenancy-decisions.md#restore-census-and-ownership-phase)) also retire? |
| [evaluator-revision-on-content-change](multitenancy-decisions.md#evaluator-revision-on-content-change) | Content-only revisions persist in later rows; does the revision-driven consumer wake and stale-selection retry survive output CDC ([stream-fed-clinical-materializer](multitenancy-decisions.md#stream-fed-clinical-materializer))? |
| [evaluation-cost-candidates](multitenancy-decisions.md#evaluation-cost-candidates) | Which of steps A–E remain after the stream-fed working set and [operable-architecture-first](multitenancy-decisions.md#operable-architecture-first)? |
| [evaluator-idle-opportunity](multitenancy-decisions.md#evaluator-idle-opportunity) | Is the idle-safety witness still part of the run verdict after [outcome-evaluator-gate](multitenancy-decisions.md#outcome-evaluator-gate)? |
| [realtime-move-readiness-viewers](multitenancy-decisions.md#realtime-move-readiness-viewers) | With dynamic moves retired by [static-hash-ownership](multitenancy-decisions.md#static-hash-ownership), does a shard takeover readiness contract still apply, for example at restart? |
