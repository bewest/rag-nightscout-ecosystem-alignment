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

# Reviewer packets

One bounded packet per item whose next move is a human review or decision.
Each says what changed, what was measured, and - the section worth opening
first - what the measurement does not cover. Start at
docs/00-overview/REVIEWER-ONBOARDING.md if this is your first time in this
repository.

| packet | PR | claimed state | what it is |
|---|---|---|---|
| [`ADV-CONFIG`](adv-config.md) | #8746 | `needs-decision` | The readable-by-world warning, the careportal role, and the two settings behind both (BF-77, BF-78, BF-81) |
| [`BFQ-ENV`](bfq-env-bf-16-0-0-boot-resilience.md) | #8849 | `needs-decision` | BF-48, BF-49, BF-50, BF-51 - four ways the configuration surface lies |
| [`PLAT-ENTRY`](plat-entry-feat-nightscout-entrypoint.md) | #8862 | `in-flight-upstream` | One executable (D21): bin/nightscout.js with `single` and the operator tools; image ENTRYPOINT and CMD single, no image HEALTHCHECK; no start path changes |
| [`BFQ-212`](bfq-212-bf-16-0-0-split-identity.md) | #8878 | `in-flight-upstream` | BF-212 - a chart-drag split leaves two treatments with one client identity; a re-send can overwrite one's amount, and a re-upload can show the moved insulin twice |
| [`BFQ-225`](bfq-225-bf-16-0-0-bf225-socket-duplicate.md) | #8888 | `in-flight-upstream` | BF-225 - socket re-sends that #8877 changed from one stored treatment to two (v3-then-socket documented; UUID _id cases not) |
| [`ADV-XSS-META`](adv-xss-meta.md) | &mdash; | `needs-decision` | GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74) |
| [`BFQ-95`](bfq-95.md) | &mdash; | `needs-decision` | BF-95 - an uploader clock running ahead delays the stale-data alarm |
| [`DEPENDABOT-CONFIG`](dependabot-config.md) | &mdash; | `needs-decision` | Dependabot runs with no configuration: security PRs target master, and alerts count fixes that are on dev |
| [`DEPLOY-TREE-HOME`](deploy-tree-home-docs-operator-readme-20261110.md) | &mdash; | `ready-to-push` | Move the Compose deploy tree to nightscout-deploy; core keeps the test fixture; operator-facing README |
| [`LOOP-UPSTREAM-CARB-EDIT`](loop-upstream-carb-edit.md) | &mdash; | `in-flight-upstream` | Loop 3.14.9 drops a carb edit when the record's _id is no longer in its 24 h cache (raised with the Loop maintainers) |
| [`MOD-UNITS-CANONICAL`](mod-units-canonical.md) | &mdash; | `needs-decision` | Canonical units at write: spelling only (N1) or mg/dL plus the original (N2), and the conversion constant |
| [`MOD-WRITE-VALIDATION-READ`](mod-write-validation-read.md) | &mdash; | `needs-decision` | Flag stored records that break a write-validation rule on API v3 reads (read-side flag, R1/R2) |
| [`MT-ACTIVITY-ELIGIBILITY`](mt-activity-eligibility-codex-activity-eligibility-20261110.md) | &mdash; | `in-flight-upstream` | Pause/suspend drive worker eligibility; evaluator stops while paused; owner may pause |
| [`MT-ADMIN-LIFECYCLE-FIT`](mt-admin-lifecycle-fit-codex-admin-lifecycle-20261110.md) | &mdash; | `in-flight-upstream` | Restore census accepts non-clinical identities; ownership refuses on non-active tenants; admin plane rule allows same address on a different port |
| [`MT-ADMIN-ROLE-OWNERSHIP`](mt-admin-role-ownership-codex-ownership-role-20261110.md) | &mdash; | `in-flight-upstream` | M6b: compose ownership operations into the multitenant admin role with an ownership_operator identity |
| [`MT-BATCH-JOIN-1110`](mt-batch-join-1110-codex-batch-join-20261110.md) | &mdash; | `in-flight-upstream` | Join the 2026-11-10 decision batch (eight lanes) onto #8898 and run full acceptance |
| [`MT-CONNECTOR-REVERSE`](mt-connector-reverse-codex-connector-reverse-20261110.md) | &mdash; | `ready-to-push` | M6d: tenant-side Nightscout connector (vcpool) pulls a family's existing site into the tenant |
| [`MT-CONSUMER-STALE-RESELECT`](mt-consumer-stale-reselect-codex-consumer-refusal-20261110.md) | &mdash; | `in-flight-upstream` | Alarm consumer survives evaluator timer publications during selection (BF-231) |
| [`MT-EVAL-COST`](mt-eval-cost-codex-eval-cost-20261111.md) | &mdash; | `ready-to-push` | Evaluator per-evaluation cost: no per-cycle copies, dates parsed once, kept working set, in-process view reads with total order |
| [`MT-EXPORT-EXPIRY`](mt-export-expiry-codex-export-expiry-20261110.md) | &mdash; | `in-flight-upstream` | Key destruction removes the export artifact file in the same audited step |
| [`MT-INTERNAL-LISTENER`](mt-internal-listener-codex-internal-listener-20261110.md) | &mdash; | `in-flight-upstream` | Internal listener: one serve.internal per role (Ory pattern, socket default) and graceful shutdown with a deadline |
| [`MT-KEY-RETENTION`](mt-key-retention-codex-key-retention-20261110.md) | &mdash; | `in-flight-upstream` | M6b: 30-day retained-key destruction and after-window refusal |
| [`MT-M6A-JOIN`](mt-m6a-join-codex-m6a-join-20261109.md) | &mdash; | `in-flight-upstream` | M6a: join the accepted owner/OIDC candidate to #8898 and run the final campaign |
| [`MT-M6B-JOIN`](mt-m6b-join-codex-m6b-join-20261110.md) | &mdash; | `in-flight-upstream` | Join M6b ownership/retention, single-site OIDC provisioning, listener composition and CodeQL 150 into #8898 |
| [`MT-OIDC-NATIVE`](mt-oidc-native-codex-oidc-native-harness-20261109.md) | &mdash; | `in-flight-upstream` | M6a: run the nine-stage owner/OIDC native matrix through a disposable harness |
| [`MT-OIDC-SINGLE-PROVISION`](mt-oidc-single-provision-codex-oidc-single-provision-20261110.md) | &mdash; | `in-flight-upstream` | Single-site OIDC: declarative identity-to-role list and a role for signed-in strangers |
| [`MT-OWNER-LAST-GUARD`](mt-owner-last-guard-codex-m6b-followups-20261110.md) | &mdash; | `in-flight-upstream` | M6b follow-up: refuse revoking the last usable owner's subject (BF-229) |
| [`MT-OWNERSHIP-OPS`](mt-ownership-ops-codex-ownership-ops-20261110.md) | &mdash; | `in-flight-upstream` | M6b: operator-assisted ownership add, transfer and recovery |
| [`MT-PERF-DB`](mt-perf-db-codex-perf-db-20261110.md) | &mdash; | `ready-to-push` | Restore-fence epoch admission, bounded startup warm, pool configuration, serve-then-warm readiness |
| [`MT-PERF-EVALUATOR`](mt-perf-evaluator-codex-perf-evaluator-20261110.md) | &mdash; | `ready-to-push` | Evaluator works on change: per-member change query and due-time timers replace the per-tenant poll |
| [`MT-PERF-REALTIME`](mt-perf-realtime-codex-perf-realtime-20261110.md) | &mdash; | `ready-to-push` | Realtime publishes on change; event-driven authorization; queued connects under pool pressure |
| [`MT-POOL-PRIMITIVE`](mt-pool-primitive-codex-pool-primitive-20261110.md) | &mdash; | `ready-to-push` | Shared pool-membership primitive (pool kind, member count, ordinal, ring slice) for evaluator and vcpool |
| [`MT-ROOT-ADMIN-PARITY`](mt-root-admin-parity-codex-root-admin-parity-20261110.md) | &mdash; | `in-flight-upstream` | Multitenant tenant API_SECRET gets single-site admin parity: subjects, roles, admin tools |
| [`MT-TENANT-EXTENDED-SETTINGS`](mt-tenant-extended-settings-codex-tenant-extended-settings-20261110.md) | &mdash; | `in-flight-upstream` | Tenant environment carries plugin extended settings so the stale-data alarm can be enabled (BF-232) |
| [`MT-VAULT-TOKEN-FILE`](mt-vault-token-file-codex-vault-token-file-20261109.md) | &mdash; | `in-flight-upstream` | M6c: read the Vault token from a sink file per call (Vault Agent compatibility) |
| [`WS-LAB`](ws-lab-main.md) | &mdash; | `ready-to-push` | tools/lab/proxy-trust - socket.io (WebSocket) cells on the AR chain (W0-W3) |

*Generated by `tools/queue/emit_packets.py` (`make packets`) from `queue/work-queue.yaml`, `measured_at` 2026-09-27.*
