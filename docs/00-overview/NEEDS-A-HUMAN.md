# Work waiting on a person

*Contributor and maintainer guide, updated 2026-11-24. The tables route work
according to the [queue](../../queue/README.md). Verify the named upstream PR,
source head and gates before acting.*

## Grouped by who it waits for

| Claimed state | What the reviewer checks |
|---|---|
| `ready-to-push` | Check the branch and gates, then decide whether to publish. |
| `needs-decision` | Read the alternatives and their operator effects. |
| `in-flight-upstream` | Check the upstream disposition and any remaining part of the item. |
| `unsettled` | Establish whether the observed behaviour is a defect. |

<!-- BEGIN GENERATED: needs-a-human -->

### Maintainer &mdash; 32 items

| id | claimed state | what it is | PR |
|---|---|---|---|
| `LOOP-UPSTREAM-CARB-EDIT` | `in-flight-upstream` | Loop 3.14.9 drops a carb edit when the record's _id is no longer in its 24 h cac | &mdash; |
| `MT-ACTIVITY-ELIGIBILITY` | `in-flight-upstream` | Pause/suspend drive worker eligibility; evaluator stops while paused; owner may  | &mdash; |
| `MT-ADMIN-LIFECYCLE-FIT` | `in-flight-upstream` | Restore census accepts non-clinical identities; ownership refuses on non-active  | &mdash; |
| `MT-ADMIN-ROLE-OWNERSHIP` | `in-flight-upstream` | M6b: compose ownership operations into the multitenant admin role with an owners | &mdash; |
| `MT-BATCH-JOIN-1110` | `in-flight-upstream` | Join the 2026-11-10 decision batch (eight lanes) onto #8898 and run full accepta | &mdash; |
| `MT-CONNECTOR-REVERSE` | `in-flight-upstream` | M6d: tenant-side Nightscout connector (vcpool) pulls a family's existing site in | &mdash; |
| `MT-CONSUMER-STALE-RESELECT` | `in-flight-upstream` | Alarm consumer survives evaluator timer publications during selection (BF-231) | &mdash; |
| `MT-EVAL-COST` | `in-flight-upstream` | Evaluator per-evaluation cost: no per-cycle copies, dates parsed once, kept work | &mdash; |
| `MT-EXPORT-EXPIRY` | `in-flight-upstream` | Key destruction removes the export artifact file in the same audited step | &mdash; |
| `MT-INTERNAL-LISTENER` | `in-flight-upstream` | Internal listener: one serve.internal per role (Ory pattern, socket default) and | &mdash; |
| `MT-KEY-RETENTION` | `in-flight-upstream` | M6b: 30-day retained-key destruction and after-window refusal | &mdash; |
| `MT-M6A-JOIN` | `in-flight-upstream` | M6a: join the accepted owner/OIDC candidate to #8898 and run the final campaign | &mdash; |
| `MT-M6B-JOIN` | `in-flight-upstream` | Join M6b ownership/retention, single-site OIDC provisioning, listener compositio | &mdash; |
| `MT-OIDC-NATIVE` | `in-flight-upstream` | M6a: run the nine-stage owner/OIDC native matrix through a disposable harness | &mdash; |
| `MT-OIDC-SINGLE-PROVISION` | `in-flight-upstream` | Single-site OIDC: declarative identity-to-role list and a role for signed-in str | &mdash; |
| `MT-OWNER-LAST-GUARD` | `in-flight-upstream` | M6b follow-up: refuse revoking the last usable owner's subject (BF-229) | &mdash; |
| `MT-OWNERSHIP-OPS` | `in-flight-upstream` | M6b: operator-assisted ownership add, transfer and recovery | &mdash; |
| `MT-PERF-DB` | `in-flight-upstream` | Restore-fence epoch admission, bounded startup warm, pool configuration, serve-t | &mdash; |
| `MT-PERF-EVALUATOR` | `in-flight-upstream` | Evaluator works on change: per-member change query and due-time timers replace t | &mdash; |
| `MT-PERF-REALTIME` | `in-flight-upstream` | Realtime publishes on change; event-driven authorization; queued connects under  | &mdash; |
| `MT-POOL-PRIMITIVE` | `in-flight-upstream` | Shared pool-membership primitive (pool kind, member count, ordinal, ring slice)  | &mdash; |
| `MT-ROOT-ADMIN-PARITY` | `in-flight-upstream` | Multitenant tenant API_SECRET gets single-site admin parity: subjects, roles, ad | &mdash; |
| `MT-TENANT-EXTENDED-SETTINGS` | `in-flight-upstream` | Tenant environment carries plugin extended settings so the stale-data alarm can  | &mdash; |
| `MT-VAULT-TOKEN-FILE` | `in-flight-upstream` | M6c: read the Vault token from a sink file per call (Vault Agent compatibility) | &mdash; |
| `ADV-CONFIG` | `needs-decision` | The readable-by-world warning, the careportal role, and the two settings behind  | #8746 |
| `ADV-XSS-META` | `needs-decision` | GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74) | &mdash; |
| `BFQ-95` | `needs-decision` | BF-95 - an uploader clock running ahead delays the stale-data alarm | &mdash; |
| `BFQ-ENV` | `needs-decision` | BF-48, BF-49, BF-50, BF-51 - four ways the configuration surface lies | #8849 |
| `DEPENDABOT-CONFIG` | `needs-decision` | Dependabot runs with no configuration: security PRs target master, and alerts co | &mdash; |
| `MOD-UNITS-CANONICAL` | `needs-decision` | Canonical units at write: spelling only (N1) or mg/dL plus the original (N2), an | &mdash; |
| `MOD-WRITE-VALIDATION-READ` | `needs-decision` | Flag stored records that break a write-validation rule on API v3 reads (read-sid | &mdash; |
| `WS-LAB` | `ready-to-push` | tools/lab/proxy-trust - socket.io (WebSocket) cells on the AR chain (W0-W3) | &mdash; |

### Maintainer + a second human &mdash; 2 items

| id | claimed state | what it is | PR |
|---|---|---|---|
| `BFQ-241` | `ready-to-push` | BF-241 - one upload limit, UPLOAD_BODY_LIMIT, for entries, treatments and device | &mdash; |
| `BFQ-246` | `ready-to-push` | BF-246 - linear mergeProcessSort in the shared dataloader (16.0.0) | &mdash; |

### SAFETY reviewer &mdash; 1 item

| id | claimed state | what it is | PR |
|---|---|---|---|
| `A7A-7` | `unsettled` | §7a item 7 - the clock question | &mdash; |

<!-- END GENERATED: needs-a-human -->

<a id="the-open-pull-requests"></a>

## Pull requests referenced by the queue

A PR here is the reference recorded on an item awaiting upstream action. A
partial fix can merge while the item remains open. Use the
[reviewer packets](../../reports/reviewer-packets/README.md) for each item's scope.

<!-- BEGIN GENERATED: open-prs -->

| PR | id | branch | what it fixes | who should review |
|---|---|---|---|---|

<!-- END GENERATED: open-prs -->

## Release and multitenant decisions

For the closing single-tenant release, use the [16.0.0 decisions](../../releases/cgm-remote-monitor-16.0.0/decisions.md)
and [testing notes](../../releases/cgm-remote-monitor-16.0.0/testing-notes.md). Record live
alarm delivery, real-rig/cohort and rollback observations against the exact candidate.
The maintainer coordinates private pre-tag work and staging.

For the multitenant preview, check the candidate and remaining evidence in the
[execution log](../30-design/tenancy/execution-log.md) before requesting review
or proposing publication. Adopted choices are indexed in the
[decisions in force](../30-design/tenancy/decisions-in-force.md).

## Checking this page against the gates

```bash
make queue-status STATE=ready-to-push
make views-check
```

<!-- BEGIN GENERATED: provenance -->

*Generated from `queue/work-queue.yaml` by `tools/queue/emit_views.py`. Manifest `measured_at` **2026-09-27**, against cgm-remote-monitor-official `7000eb18` and this repository at `18cdcce0`. Every state above is a **claim** about what the gates will say &mdash; `make queue-status` is the measurement.*

<!-- END GENERATED: provenance -->
