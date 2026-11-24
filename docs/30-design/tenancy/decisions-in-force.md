# Multitenant decisions in force

The original November 18 review indexed the anchored rows at `a0a8c3956d`. Subsequent programme decisions and amendments extend that index. This is a **read-derived** guide. Each linked [decision row](multitenancy-decisions.md) owns its policy and evidence. The [execution log](execution-log.md#candidate-5-qualification-and-nominal-discovery) identifies the candidate and what has been measured.

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
- [write-clock-history-arms](multitenancy-decisions.md#write-clock-history-arms) — The write clock serves only v3 history no-missed-write (arms settled by [multitenant-requires-write-clock](multitenancy-decisions.md#multitenant-requires-write-clock)).
- [multitenant-requires-write-clock](multitenancy-decisions.md#multitenant-requires-write-clock) — Arm (a) per-tenant clock row is kept; multitenant requires `writeClock`; floor checks move to `admin` (narrowed by [platform-verification-removal](multitenancy-decisions.md#platform-verification-removal): floors are operation postconditions).

### Roles, listeners and horizontal shape

- [statefulset-ordinal-scaling](multitenancy-decisions.md#statefulset-ordinal-scaling) — Evaluator and realtime are StatefulSets, ordinal from the hostname, K = replicas (one env value), one headless Service; api is a Deployment; cohort and participant manifest deleted. Evaluator K is bound at seed only under pgstream; writer-driven fixtures are K-free, one seed serves any K (amended 2026-11-20).
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
- [legacy-topology-retirement](multitenancy-decisions.md#legacy-topology-retirement) — Legacy pools and leases retire. [Writer-driven transport](multitenancy-decisions.md#writer-driven-transport-direction) replaces the native stream input.
- [pool-primitive-shared](multitenancy-decisions.md#pool-primitive-shared) — One pool-membership primitive, kinds kept separate (narrowed by [legacy-topology-retirement](multitenancy-decisions.md#legacy-topology-retirement): kept for connectors).
- [census-operational-list](multitenancy-decisions.md#census-operational-list) — Operational catalogues are listed explicitly and excluded from per-tenant restore, export and deletion.
- [pool-member-hygiene](multitenancy-decisions.md#pool-member-hygiene) — Pool members reclaim stale sockets and wait-and-alert instead of exiting.
- [cohort-pod-not-scaled](multitenancy-decisions.md#cohort-pod-not-scaled) — Never scale the all-roles monolith horizontally (narrowed by [k1-per-role-deployments](multitenancy-decisions.md#k1-per-role-deployments)).
- [vcpool-egress-capacity](multitenancy-decisions.md#vcpool-egress-capacity) — Connector pools are sized against upstream quotas; core reports upstream refusals per member.
- [evaluator-scale-direction](multitenancy-decisions.md#evaluator-scale-direction) — Profile first, then K evaluator processes; no coalescing window (narrowed by [static-hash-ownership](multitenancy-decisions.md#static-hash-ownership): not urgent).

### Platform/application boundary, startup and simplification

- [platform-verification-removal](multitenancy-decisions.md#platform-verification-removal) — No configuration-digest certificate and no per-tenant verified floor; migration Job plus schema check; a range of single-concern health endpoints.
- [config-few-dozen-env](multitenancy-decisions.md#config-few-dozen-env) — A few dozen environment settings (about 74 is fine) plus minimal PostgreSQL bookkeeping; per-role JSON documents retire.
- [predictable-fixes-then-test](multitenancy-decisions.md#predictable-fixes-then-test) — Predictable simplifications run affected tests only, no per-item break-it control; qualify the joined candidate once.
- [provisioning-secrets-in](multitenancy-decisions.md#provisioning-secrets-in) — Secrets flow into Jobs and roles, never out of a Pod; one apply converges.
- [prometheus-metrics-narrow](multitenancy-decisions.md#prometheus-metrics-narrow) — official Prometheus Node client (`@prometheus-io/client`), `/metrics` on an internal port, opt-in, multitenant roles only (not the classic server); no tenant-id labels; one Prometheus Pod plus `postgres_exporter` per lab run, TSDB snapshot retained; per-input events still decide verdicts; no OTel tracing now. Supersedes metrics-endpoint-deferred.
- [storage-events-single-tenant-parity](multitenancy-decisions.md#storage-events-single-tenant-parity) — `/storage` socket events fire for exactly the write paths a single site uses.
- [writer-driven-transport-direction](multitenancy-decisions.md#writer-driven-transport-direction) — **Adopted 2026-11-21**: the api is the only writer; post-commit hints to the owning evaluator and realtime; level-triggered recompute plus sweep; pgstream, its slot and the storage-event journal retire.
- [stateful-evaluator-resident-window](multitenancy-decisions.md#stateful-evaluator-resident-window) — **Adopted 2026-11-21**: each evaluator slice keeps its tenants' windows resident and updates them from the pending mark; memory is planned per resident; output byte-identical to the full rebuild.
- [evaluator-k-planned-restart](multitenancy-decisions.md#evaluator-k-planned-restart) — K changes by planned restart with headroom; no logical-shard map, live K change or hash change.
- [prerelease-schema-in-place](multitenancy-decisions.md#prerelease-schema-in-place) — No operator databases yet: multitenant schema and migrations change in place; two-step migrations start at the first operator release.
- [platform-application-boundary](multitenancy-decisions.md#platform-application-boundary) — Application assumes a verified platform and fails closed; it never re-verifies the platform while serving.
- [brittle-check-removal](multitenancy-decisions.md#brittle-check-removal) — Checks that refuse for anything other than a product property are removed; run identity is image digest plus run configuration.
- [unclear-rows-resolved](multitenancy-decisions.md#unclear-rows-resolved) — The six Unclear questions resolved toward removal (desired count, writer census, revision wake, cost step A, idle witness, move readiness).
- [architecture-justified-removal](multitenancy-decisions.md#architecture-justified-removal) — Machinery from an obsolete design is removed on architecture grounds with correctness controls, no measurement.
- [serial-machinery-retirement](multitenancy-decisions.md#serial-machinery-retirement) — Remove serial machinery the streaming design no longer needs, rather than tune it.
- [operable-architecture-first](multitenancy-decisions.md#operable-architecture-first) — Simplified, runnable, operable architecture first; performance work is lower priority meanwhile.
- [boot-independent-of-tenants](multitenancy-decisions.md#boot-independent-of-tenants) — Serving boot is independent of tenant count; expensive platform verification runs on `admin` (narrowed by [platform-verification-removal](multitenancy-decisions.md#platform-verification-removal): no verification record or proof).
- [catalogue-verification-admin-owned](multitenancy-decisions.md#catalogue-verification-admin-owned) — Admin verifies the catalogue once per deployment; serving keeps one cheap fail-closed check (narrowed by [platform-verification-removal](multitenancy-decisions.md#platform-verification-removal): migration Job plus schema-version check).
- [stable-evaluator-runtime](multitenancy-decisions.md#stable-evaluator-runtime) — Evaluator runs on a stable schema; relevant DDL after startup stops it with a typed code.
- [migration-rehearsal-separate](multitenancy-decisions.md#migration-rehearsal-separate) — Migrations are rehearsed as scheduled maintenance, separate from performance and acceptance runs.
- [multitenant-upgrade-shape](multitenancy-decisions.md#multitenant-upgrade-shape) — Platform rolls processes; core supplies two-step migrations and checks (narrowed by [stable-evaluator-runtime](multitenancy-decisions.md#stable-evaluator-runtime)).
- [tenant-local-startup-admission](multitenancy-decisions.md#tenant-local-startup-admission) — A suspended tenant never prevents other tenants becoming ready after a restart.
- [tenant-defect-tenant-scoped](multitenancy-decisions.md#tenant-defect-tenant-scoped) — A defect in one tenant's state refuses that tenant only; deployment defects refuse startup.
- [readiness-serve-then-warm](multitenancy-decisions.md#readiness-serve-then-warm) — A role is ready when its own dependencies are up; tenants warm in the background (narrowed for the api by [api-tenant-cache-bounded-lru](multitenancy-decisions.md#api-tenant-cache-bounded-lru)).
- [api-tenant-cache-bounded-lru](multitenancy-decisions.md#api-tenant-cache-bounded-lru) — The api's per-tenant state is a bounded LRU optimization; a miss builds inline; restart cost is independent of tenant count.
- [datastore-loss-recover-in-place](multitenancy-decisions.md#datastore-loss-recover-in-place) — On PostgreSQL loss a role reports unhealthy, reconnects and rebuilds; exits only past a bound.
- [datastore-loss-before-window-retirement](multitenancy-decisions.md#datastore-loss-before-window-retirement) — Move datastore-loss recovery to a connection probe before retiring the operation window.
- [lane-failure-recover-in-place](multitenancy-decisions.md#lane-failure-recover-in-place) — A failed session lane is replaced in place, never hiding an uncertain completion.
- [compose-restart-on-failure](multitenancy-decisions.md#compose-restart-on-failure) — Compose production default is `restart: on-failure`; tests may disable restart.
- [pg-connection-budget](multitenancy-decisions.md#pg-connection-budget) — Deploy sizes `max_connections` from the declared per-role connection budget.
- [pg-connection-pooler-allowed](multitenancy-decisions.md#pg-connection-pooler-allowed) — PgBouncer and/or a larger `max_connections` meet the budget as K grows; check session state before transaction pooling.

### Deployment repository and Kubernetes

- [d12](multitenancy-decisions.md#d12) — Alignment holds tooling and evidence; shipping code and tests live in `cgm-remote-monitor`.
- [platform-home-nightscout-deploy](multitenancy-decisions.md#platform-home-nightscout-deploy) — Platform concerns without a core home move to `nightscout-deploy`.
- [deploy-tree-home-now](multitenancy-decisions.md#deploy-tree-home-now) — `nightscout-deploy` holds the Compose tree now (narrowed by [deployment-plan-contract](multitenancy-decisions.md#deployment-plan-contract)).
- [deployment-plan-contract](multitenancy-decisions.md#deployment-plan-contract) — One deployment plan in deploy, checked against a contract core publishes.
- [core-static-plan-retired](multitenancy-decisions.md#core-static-plan-retired) — Core's static Compose plan retires; core tests use a small registry-mode fixture plan.
- [deploy-repo-readme](multitenancy-decisions.md#deploy-repo-readme) — The deploy README addresses operators: what runs, how to run it, the pinned core commit.
- [k1-per-role-deployments](multitenancy-decisions.md#k1-per-role-deployments) — Kubernetes: one Deployment per role, `Recreate`, per-role Services; migrations as Jobs before serving (narrowed by [statefulset-ordinal-scaling](multitenancy-decisions.md#statefulset-ordinal-scaling): evaluator and realtime are StatefulSets).
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
- [operator-repair-scope](multitenancy-decisions.md#operator-repair-scope) — Use provision for creation, inspect for diagnosis and known-good backups for exceptional recovery. Factory reset preserves clinical data and credentials.
- [deployment-signing-secret](multitenancy-decisions.md#deployment-signing-secret) — Vault keeps only the per-tenant `data` key; tenant signing keys derive in process from one deployment secret (file via Vault Agent or Secret); no signing key in PostgreSQL; issuance never calls Vault; one Kubernetes Secret delivers the signing secret; the api `ns-access+jwt` data verifier, `verifyLegacyCredential` and the api `access` namespace retire (2026-11-20).
- [one-call-usable-provisioning](multitenancy-decisions.md#one-call-usable-provisioning) — One bulk admin call returns usable tenants (owner, subject, credential in the provisioning transaction); the harness prefers an exact key and verifies a bootstrap migration receipt when restoring a compatible writer-driven Kubernetes fixture from an ancestor (amended 2026-11-21).
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
- [vault-readiness-honest](multitenancy-decisions.md#vault-readiness-honest) — Vault is Ready only when it can serve; a sealed restart stops the run; unseal automation is staged toward production.
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
- [platform-backup-and-test-fixtures](multitenancy-decisions.md#platform-backup-and-test-fixtures) — The deployment manages PostgreSQL and Vault backup, rollback and seeded fixture copies.
- [tenant-copy-export](multitenancy-decisions.md#tenant-copy-export) — Core exports per-tenant COPY data with a digest manifest and restores it under the tenant fence.
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
- [restore-census-and-ownership-phase](multitenancy-decisions.md#restore-census-and-ownership-phase) — Ownership operations respect tenant activity. The later [unclear-rows resolution](multitenancy-decisions.md#unclear-rows-resolved) retired the pre-restore writer census.
- [restore-resume-and-precheck](multitenancy-decisions.md#restore-resume-and-precheck) — Interrupted restore reopens by audited `resume` (narrowed by [restore-suspend-drain-replace](multitenancy-decisions.md#restore-suspend-drain-replace): operation-record precheck).

### Event feed, evaluator and realtime

- [d6](multitenancy-decisions.md#d6) — Clinical writes remain independent of notification delivery. [Writer-driven transport](multitenancy-decisions.md#writer-driven-transport-direction) supersedes the replication slot.
- [single-host-streaming-first](multitenancy-decisions.md#single-host-streaming-first) — The November 16 UDS baseline and pgstream qualification retain their source scope. See the [current campaign](execution-log.md#candidate-5-qualification-and-nominal-discovery).
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
- [nominal-clinical-write-age](multitenancy-decisions.md#nominal-clinical-write-age) — Qualify recent direct and connector writes on sites with retained history. Measure bulk historical recovery separately.
- [deadline-from-acceptance](multitenancy-decisions.md#deadline-from-acceptance) — The clinical deadline runs from acceptance; catch-up is per accepted input; no warm evidence in any gate.
- [latency-objectives](multitenancy-decisions.md#latency-objectives) — p95 within 30 s at expected load is the planning objective; about 1 s the stretch; 120 s the clinical gate under overload.
- [plannable-scale-campaign](multitenancy-decisions.md#plannable-scale-campaign) — Every fix built at once behind switches, joined by a cutoff, end state on the looping-shape fixture tested all on and all off, back down one switch at a time from failing evidence; $40, teardown 09:00 PST 2026-11-22.
- [evaluator-scaling-strategy](multitenancy-decisions.md#evaluator-scaling-strategy) — The evaluator scales by K and by cutting cost per cycle. Worker threads are rejected. Incremental plugins are not pursued; prepared data kept resident below the plugins is allowed.
- [evaluator-k-bound](multitenancy-decisions.md#evaluator-k-bound) — Evaluator K is 1..32 and realtime K is 1..8, and the two may differ on Compose. PostgreSQL gets 1 GiB `/dev/shm`. Joins the #8898 line; the 10k K=20 result tests the join.
- [evaluator-capacity-headroom](multitenancy-decisions.md#evaluator-capacity-headroom) — K comes from planned tenants per slice: 0.8 × the measured density that meets p95 ≤ 30 s and recovers from a restart within 120 s. Each join re-measures it, and K shrinks at a release.
- [per-tenant-lock-bounded-hold](multitenancy-decisions.md#per-tenant-lock-bounded-hold) — Cut per-tenant lock hold time (write clock, outbox, checkpoint) to the minimum: a fixed number of statements independent of batch size, never across other pools or waits outside the database; the clock contract is unchanged and lock-free stays unadopted.
- [multitenant-write-settings-at-defaults](multitenancy-decisions.md#multitenant-write-settings-at-defaults) — The multitenant api runs `WRITE_*` at the 16.0.0 defaults; per-tenant values only through D22 if a need is measured.
- [one-large-postgresql-primary](multitenancy-decisions.md#one-large-postgresql-primary) — One PostgreSQL primary on its own node, grown vertically; cells are a later fleet option; load starts after autovacuum and warm-up.
- [no-realtime-fast-path](multitenancy-decisions.md#no-realtime-fast-path) — No rows to browsers ahead of the evaluator; realtime sends delta frames computed from evaluator output.
- [storage-machinery-removal](multitenancy-decisions.md#storage-machinery-removal) — Remove `storage_bytes` and its trigger and the duplicate and prefix indexes (done on branch, −17.1 %); the per-tenant counter and the stored output frame stay; pgstream-era checkpoint leftovers go with the pool-era modules; other index cuts wait for `idx_scan`.
- [tied-sort-key-permutation](multitenancy-decisions.md#tied-sort-key-permutation) — Ties order by insertion ordinal; parity means same records, values and client-visible winners, not MongoDB's cache-dependent order.
- [predictions-max-size-single-tenant-parity](multitenancy-decisions.md#predictions-max-size-single-tenant-parity) — `PREDICTIONS_MAX_SIZE` read and applied exactly as on a single site; device-status retention keeps everything.
- [devicestatus-hour-chunks](multitenancy-decisions.md#devicestatus-hour-chunks) — **Parked 2026-11-24**: chunks passed the contract and cut devicestatus bytes 82 %, but failed the window-read and write-hold gates.
- [connector-secret-entry-admin](multitenancy-decisions.md#connector-secret-entry-admin) — Connector secrets enter through a write-only admin resource that writes record and audit row; no other writer.
- [preload-is-a-signal](multitenancy-decisions.md#preload-is-a-signal) — Whole-roster preload convergence is a signal; traffic starts when roles are ready.
- [m7-envelope-measured-not-declared](multitenancy-decisions.md#m7-envelope-measured-not-declared) — Measure the operating envelope on the selected profile under the [current test tiers](multitenancy-decisions.md#capacity-test-tiers).
- [local-10k-release](multitenancy-decisions.md#local-10k-release) — Dated authorization for the a72 discovery point. See the [current campaign](execution-log.md#candidate-5-qualification-and-nominal-discovery) for subsequent experiments.
- [latency-lane-held](multitenancy-decisions.md#latency-lane-held) — The latency-observer lane does not start this cycle (narrowed by [cluster-fan-out-testing](multitenancy-decisions.md#cluster-fan-out-testing)).
- [cluster-fan-out-testing](multitenancy-decisions.md#cluster-fan-out-testing) — The existing cluster runs concurrent scenarios per namespace; largest points on the workstation; droplets stop.
- [reserved-k8s-worker](multitenancy-decisions.md#reserved-k8s-worker) — A worker may be reserved by taint, never evicting (narrowed by [cluster-fan-out-testing](multitenancy-decisions.md#cluster-fan-out-testing): clean-number points only).
- [workload-acceleration-local-only](multitenancy-decisions.md#workload-acceleration-local-only) — Remote and capacity runs use real time; only local harness checks accelerate.
- [concurrent-branch-experiments](multitenancy-decisions.md#concurrent-branch-experiments) — Isolated synthetic branch experiments may run before full acceptance.
- [flexible-experiment-limits](multitenancy-decisions.md#flexible-experiment-limits) — Reference sizes are configurable; identify a restriction's source before adding it.
- [generous-run-resources](multitenancy-decisions.md#generous-run-resources) — Test fixtures set requests only; no per-role limits; setup sizes unbounded or progress-based; bound a run only for a scenario that needs it (narrowed by [requests-typical-scheduler-decides](multitenancy-decisions.md#requests-typical-scheduler-decides)).
- [start-roles-before-priming](multitenancy-decisions.md#start-roles-before-priming) — Every role starts before provisioning and priming; no remaining-roles stage.
- [requests-typical-scheduler-decides](multitenancy-decisions.md#requests-typical-scheduler-decides) — Requests near typical use; the scheduler places; Pending is the fit result; no harness fit solver or Compose allocation accounting.
- [repeated-standard-point](multitenancy-decisions.md#repeated-standard-point) — A result is one scenario run three times on one freeze; only product properties fail a run.
- [routine-diagnostic-image-delivery](multitenancy-decisions.md#routine-diagnostic-image-delivery) — Routine low-cost diagnostic image pushes and pulls need no per-image approval.
- [disposable-native-harness](multitenancy-decisions.md#disposable-native-harness) — Native acceptance uses a disposable harness (narrowed by [simple-run-cleanup](multitenancy-decisions.md#simple-run-cleanup)).
- [simple-run-cleanup](multitenancy-decisions.md#simple-run-cleanup) — Cleanup is one owned delete plus one absence check.
- [m6-split-and-queue-collapse](multitenancy-decisions.md#m6-split-and-queue-collapse) — Milestones M6a–M6d for the preview; M7 before any production cohort.
- [restore-candidate-frozen](multitenancy-decisions.md#restore-candidate-frozen) — Historical freeze of the restore branch, K1 deploy profile and helper. Later candidates have their own [execution records](execution-log.md).
- [8898-continue-adding](multitenancy-decisions.md#8898-continue-adding) — #8898 stays draft and keeps receiving batches; merge before 16.0.0 is undecided.
- [three-lane-coordination](multitenancy-decisions.md#three-lane-coordination) — One coordinator and three lanes: source, gate/instrument, operations; optional capabilities paused.
- [fresh-context-phase-ownership](multitenancy-decisions.md#fresh-context-phase-ownership) — Fresh chats at phase boundaries; explicit custody transfer (refined by [three-lane-coordination](multitenancy-decisions.md#three-lane-coordination)).

## Superseded or retired

The [November 18 archive](../../archive/tenancy/multitenancy-decisions-superseded-2026-11-18.md) holds rows retired in the original review. Later amendments are recorded on their decision rows.

| row | replaced by | reason |
|---|---|---|
| [stream-native-coverage-direction](multitenancy-decisions.md#stream-native-coverage-direction) | [writer-driven-transport-direction](multitenancy-decisions.md#writer-driven-transport-direction) | Mechanism scoped to the retired pgstream transport |
| [evaluator-platform-restart](multitenancy-decisions.md#evaluator-platform-restart) | [writer-driven-transport-direction](multitenancy-decisions.md#writer-driven-transport-direction) | Mechanism scoped to the retired pgstream transport |
| [stream-fed-clinical-materializer](multitenancy-decisions.md#stream-fed-clinical-materializer) | [writer-driven-transport-direction](multitenancy-decisions.md#writer-driven-transport-direction) | Mechanism scoped to the retired pgstream transport |
| [stream-source-identity-in-data](multitenancy-decisions.md#stream-source-identity-in-data) | [writer-driven-transport-direction](multitenancy-decisions.md#writer-driven-transport-direction) | Mechanism scoped to the retired pgstream transport |
| [ack-path-tenant-independent](multitenancy-decisions.md#ack-path-tenant-independent) | [writer-driven-transport-direction](multitenancy-decisions.md#writer-driven-transport-direction) | Mechanism scoped to the retired pgstream transport |
| [vcpool-proof-role](multitenancy-decisions.md#vcpool-proof-role) | [platform-verification-removal](multitenancy-decisions.md#platform-verification-removal) | Startup certificate retired for serving roles |
| [event-driven-reset](multitenancy-decisions.md#event-driven-reset) | [writer-driven-transport-direction](multitenancy-decisions.md#writer-driven-transport-direction) | stream-fed evaluator and realtime replaced by writer-driven hints (2026-11-21) |
| [pgstream-operating-constraints](multitenancy-decisions.md#pgstream-operating-constraints) | [writer-driven-transport-direction](multitenancy-decisions.md#writer-driven-transport-direction) | pgstream retired (2026-11-21) |
| [private-stream-router](multitenancy-decisions.md#private-stream-router) | [writer-driven-transport-direction](multitenancy-decisions.md#writer-driven-transport-direction) | no stream to route (2026-11-21) |
| [clinical-deadline-from-warm](multitenancy-decisions.md#clinical-deadline-from-warm) | [deadline-from-acceptance](multitenancy-decisions.md#deadline-from-acceptance) | warm evidence rebuilt per-tenant warm-up machinery; work follows input (row kept in place, not archived) |
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

None open. The six questions listed here on 2026-11-18 were resolved by [unclear-rows-resolved](multitenancy-decisions.md#unclear-rows-resolved): the in-table desired count, the pre-restore writer census, the revision-driven wake and stale-selection retry, evaluation-cost step A, the idle-safety witness in the run verdict and the shard-move readiness contract retire.
