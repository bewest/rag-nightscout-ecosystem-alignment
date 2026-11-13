# Work waiting on a person: what to push, decide or review

*What this is: a record (contributor-facing). Read after the [roadmap](ROADMAP.md); leads to the
[definition of done: when a change is ready for the apps that depend on it](DEFINITION-OF-DONE.md). The subset of the work queue where no further engineering
advances anything — a person has to push, decide, or review. Prose revised
2026-10-08 against cgm-remote-monitor `official/dev` `fade2299` (the `RT-0` section 2026-10-21,
against `official/master` `c6a0d8ed`, tag `v15.0.9`) and nightscout-connect
`official/main` `4dde1ec` (tag `v0.1.0`); the multitenant section 2026-11-10 against draft #8898 `b70ad83f`; tables generated.*

This page lists only the items whose claimed state means **the next move belongs to
a person**, grouped by the kind of person, so that "what is blocked on me" is one
page.

Four states qualify:

| state | what it means |
|---|---|
| `ready-to-push` | every runnable gate passes; the next step is a human push |
| `needs-decision` | waiting on a decision, not on work |
| `in-flight-upstream` | handed to upstream; not ours to land |
| `unsettled` | not yet established that this is a defect at all |

`merged-upstream` and `released` items do not appear here. A `merged-upstream` item needs no
person individually; what it needs is a release. 15.0.9 (`RT-0`) was released on 2026-10-21, and
every item that was `merged-upstream` then is `released`.

---

## Grouped by who it waits for

<!-- BEGIN GENERATED: needs-a-human -->

### Maintainer &mdash; 36 items

| id | claimed state | what it is | PR |
|---|---|---|---|
| `BFQ-212` | `in-flight-upstream` | BF-212 - a chart-drag split leaves two treatments with one client identity; a re | #8878 |
| `BFQ-225` | `in-flight-upstream` | BF-225 - socket re-sends that #8877 changed from one stored treatment to two (v3 | #8888 |
| `LOOP-UPSTREAM-CARB-EDIT` | `in-flight-upstream` | Loop 3.14.9 drops a carb edit when the record's _id is no longer in its 24 h cac | &mdash; |
| `MT-ACTIVITY-ELIGIBILITY` | `in-flight-upstream` | Pause/suspend drive worker eligibility; evaluator stops while paused; owner may  | &mdash; |
| `MT-ADMIN-LIFECYCLE-FIT` | `in-flight-upstream` | Restore census accepts non-clinical identities; ownership refuses on non-active  | &mdash; |
| `MT-ADMIN-ROLE-OWNERSHIP` | `in-flight-upstream` | M6b: compose ownership operations into the multitenant admin role with an owners | &mdash; |
| `MT-BATCH-JOIN-1110` | `in-flight-upstream` | Join the 2026-11-10 decision batch (eight lanes) onto #8898 and run full accepta | &mdash; |
| `MT-CONSUMER-STALE-RESELECT` | `in-flight-upstream` | Alarm consumer survives evaluator timer publications during selection (BF-231) | &mdash; |
| `MT-EXPORT-EXPIRY` | `in-flight-upstream` | Key destruction removes the export artifact file in the same audited step | &mdash; |
| `MT-INTERNAL-LISTENER` | `in-flight-upstream` | Internal listener: one serve.internal per role (Ory pattern, socket default) and | &mdash; |
| `MT-KEY-RETENTION` | `in-flight-upstream` | M6b: 30-day retained-key destruction and after-window refusal | &mdash; |
| `MT-M6A-JOIN` | `in-flight-upstream` | M6a: join the accepted owner/OIDC candidate to #8898 and run the final campaign | &mdash; |
| `MT-M6B-JOIN` | `in-flight-upstream` | Join M6b ownership/retention, single-site OIDC provisioning, listener compositio | &mdash; |
| `MT-OIDC-NATIVE` | `in-flight-upstream` | M6a: run the nine-stage owner/OIDC native matrix through a disposable harness | &mdash; |
| `MT-OIDC-SINGLE-PROVISION` | `in-flight-upstream` | Single-site OIDC: declarative identity-to-role list and a role for signed-in str | &mdash; |
| `MT-OWNER-LAST-GUARD` | `in-flight-upstream` | M6b follow-up: refuse revoking the last usable owner's subject (BF-229) | &mdash; |
| `MT-OWNERSHIP-OPS` | `in-flight-upstream` | M6b: operator-assisted ownership add, transfer and recovery | &mdash; |
| `MT-ROOT-ADMIN-PARITY` | `in-flight-upstream` | Multitenant tenant API_SECRET gets single-site admin parity: subjects, roles, ad | &mdash; |
| `MT-TENANT-EXTENDED-SETTINGS` | `in-flight-upstream` | Tenant environment carries plugin extended settings so the stale-data alarm can  | &mdash; |
| `MT-VAULT-TOKEN-FILE` | `in-flight-upstream` | M6c: read the Vault token from a sink file per call (Vault Agent compatibility) | &mdash; |
| `PLAT-ENTRY` | `in-flight-upstream` | One executable (D21): bin/nightscout.js with `single` and the operator tools; im | #8862 |
| `ADV-CONFIG` | `needs-decision` | The readable-by-world warning, the careportal role, and the two settings behind  | #8746 |
| `ADV-XSS-META` | `needs-decision` | GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74) | &mdash; |
| `BFQ-95` | `needs-decision` | BF-95 - an uploader clock running ahead delays the stale-data alarm | &mdash; |
| `BFQ-ENV` | `needs-decision` | BF-48, BF-49, BF-50, BF-51 - four ways the configuration surface lies | #8849 |
| `DEPENDABOT-CONFIG` | `needs-decision` | Dependabot runs with no configuration: security PRs target master, and alerts co | &mdash; |
| `MOD-UNITS-CANONICAL` | `needs-decision` | Canonical units at write: spelling only (N1) or mg/dL plus the original (N2), an | &mdash; |
| `MOD-WRITE-VALIDATION-READ` | `needs-decision` | Flag stored records that break a write-validation rule on API v3 reads (read-sid | &mdash; |
| `DEPLOY-TREE-HOME` | `ready-to-push` | Move the Compose deploy tree to nightscout-deploy; core keeps the test fixture;  | &mdash; |
| `MT-CONNECTOR-REVERSE` | `ready-to-push` | M6d: tenant-side Nightscout connector (vcpool) pulls a family's existing site in | &mdash; |
| `MT-EVAL-COST` | `ready-to-push` | Evaluator per-evaluation cost: no per-cycle copies, dates parsed once, kept work | &mdash; |
| `MT-PERF-DB` | `ready-to-push` | Restore-fence epoch admission, bounded startup warm, pool configuration, serve-t | &mdash; |
| `MT-PERF-EVALUATOR` | `ready-to-push` | Evaluator works on change: per-member change query and due-time timers replace t | &mdash; |
| `MT-PERF-REALTIME` | `ready-to-push` | Realtime publishes on change; event-driven authorization; queued connects under  | &mdash; |
| `MT-POOL-PRIMITIVE` | `ready-to-push` | Shared pool-membership primitive (pool kind, member count, ordinal, ring slice)  | &mdash; |
| `WS-LAB` | `ready-to-push` | tools/lab/proxy-trust - socket.io (WebSocket) cells on the AR chain (W0-W3) | &mdash; |

### SAFETY reviewer &mdash; 1 item

| id | claimed state | what it is | PR |
|---|---|---|---|
| `A7A-7` | `unsettled` | §7a item 7 - the clock question | &mdash; |

<!-- END GENERATED: needs-a-human -->

---

## The open pull requests

One bounded review packet per item awaiting review lives in `reports/reviewer-packets/`.

<!-- BEGIN GENERATED: open-prs -->

| PR | id | branch | what it fixes | who should review |
|---|---|---|---|---|
| **#8862** | `PLAT-ENTRY` | `feat/nightscout-entrypoint` | One executable (D21): bin/nightscout.js with `single` and th | Maintainer |
| **#8878** | `BFQ-212` | `bf/16.0.0-split-identity` | BF-212 - a chart-drag split leaves two treatments with one c | Maintainer |
| **#8888** | `BFQ-225` | `bf/16.0.0-bf225-socket-duplicate` | BF-225 - socket re-sends that #8877 changed from one stored  | Maintainer |

<!-- END GENERATED: open-prs -->

Every PR decided for 15.0.9 is merged and was released with it on 2026-10-21; `RT-0` below records the release.

The connector half is released. On 2026-09-24 the maintainer merged `nightscout-connect` #70
(`dev` → `main`, `4dde1ec`) and tagged `main` `v0.1.0`. npm's `latest` is `0.1.0`, with
provenance. Its code is the same as `0.1.0-dev.3`'s (`977da8a`): the only difference is
`docs/releasing.md` (#80), which now records that order. Connector `dev` declares `0.1.1`, and #81 is the
next `dev` → `main` PR. cgm-remote-monitor `dev` pins exactly `0.1.0` (#8762); `master` still pins
tag `v0.0.13`.

---

## The decisions, and what each costs while it waits

Engineering cannot advance these. Each needs somebody to choose.

### `RT-D3` — answered for 15.0.9

The version is decided (15.0.9 ships as numbered), and the drag check
passed on 2026-09-23 in automation and by hand: mouse in mg/dL and mmol/L, and touch, the same as
15.0.8. The hand check found BF-103 (a split drag keeps the old time, so IOB and COB ignore the move),
which is on 15.0.8 as well and is tracked as `BFQ-103`.

### `RT-0` — 15.0.9 released (2026-10-21)

15.0.9 was released on 2026-10-21: #8598 merged as `master` `c6a0d8ed` (tree `c53c2c7f`, the same as
`dev` `4bca2ac2`'s), GitHub release `v15.0.9` "Release 15.0.9 Cinnamon Muffin", Latest, and the
`15.0.9` and `latest` Docker images published by the `master` CI run (39667944235, second attempt;
the first failed in one cell's `npm install` on `ECONNRESET` before any test ran). It carries 549
commits and 100 first-parent merges since 15.0.8, among them the fixes for two published-advisory
defects that survive `AUTH_DEFAULT_ROLES=denied`, GHSA-gjhc (BF-79, #8744) and GHSA-8849 (BF-75/76,
#8745), the boot notice for world-readable sites (#8746), and the two backported security fixes
(BF-104, BF-105, #8751). Operators who have not upgraded from 15.0.8 still have all of them. Both
approvals of #8598 were the maintainer's, at `e3adc91d`; they were not repeated at `4bca2ac2`. The
release rests on the maintainers' readiness decision of 2026-10-21. Both tags exist, `v15.0.9` and
`15.0.9`, on `c6a0d8ed`. `dev` is `04d435eb`, the 15.0.10 version bump on top of the release, and
#8824 is the new `dev` → `master` staging PR. Known issues and what is left are in
[ROADMAP §1](ROADMAP.md#1-1509-is-released-the-next-development-cycle).

### `P0-TAG` — done: `nightscout-connect` 0.1.0 is released

The maintainer released it on 2026-09-24: #70 merged into `main`, `main` was tagged `v0.1.0`, and the
publish was approved. Nightscout `dev` pins it exactly (#8762), and the combined run with that pin is
green.

#79's bounded profile fetch (`1d2ebc8`) and update-on-change (`de3cee1`) were lab-run on
2026-09-23, on code identical to what shipped. The runs were 80 min, and 46 min against sinks
running the 15.0.9 candidate
([record](../60-research/remedial/connector-profile-sync.md)). That is
shorter than the 4 h 23 min dev.2 soak, and no source outage was repeated.

### `BFQ-47` — decided, and in review

The maintainer decided on 2026-09-23 that the subject allow-list is intended. The remaining defect,
the admin page clearing `notes` and `created_at` on every edit, is fixed by `7103f657`, which is part
of #8754.

### `BFQ-72`

BF-72: an unauthenticated query can occupy the database for minutes. It is live on 15.0.8 and on
`dev`. Mechanism only is recorded in this public repository. The maintainer has decided its
disposition; the details are held outside this public repository while the defect is live on the
shipping release, under the disclosure rule ([DOCUMENT-CONTROL §3.8](DOCUMENT-CONTROL.md#38-external-and-restricted-documents)).

### `MT-M6B-JOIN`, `MT-ENDPOINT-TRANSPORT` — the multitenant preview on #8898

Draft #8898 is `b70ad83f` (read from GitHub 2026-11-10, 20:54 UTC), open; 17 checks pass
and 3 are skipped, CodeQL and the multitenant opt-in corpus among the passes. That head
carries the M6a owner/OIDC and internal service API candidate and the M6b join; its
frozen-head acceptance is the
[M6b record](../../reports/tenancy/m6b-join-2026-11-10/b70ad83f-acceptance/README.md).
The preview is dormant and opt-in; taking it out of draft, review and merge are the
maintainer's actions.

On 2026-11-09 the maintainer split M6 into M6a–M6d and M7, moved the deployment tree to
`nightscout-deploy`, chose a Vault Agent sidecar over a hand-written service-login
adapter, and retired the agent-invented grant ceremony in favour of a disposable harness
([decisions](../../releases/cgm-remote-monitor-16.0.0/decisions.md#plan-restructuring-and-process-simplification-2026-11-09)).

Settled 2026-11-10 ([decisions](../../releases/cgm-remote-monitor-16.0.0/decisions.md#deploy-companion-internal-listener-activity-policy-and-8898-timing-2026-11-10)): the internal listener shape (Ory pattern, socket default, graceful shutdown), the operator activity policy (pause/suspend; owner may pause), the `nightscout-deploy` home (pushed to the nightscout organisation; it owns the Compose tree) and #8898 timing (draft until the next batch joins).

What still needs a person:

- **Taking #8898 out of draft** after the next batch's acceptance, and posting the early design-feedback comment if wanted.
- **Nothing for the operating envelope.** On 2026-11-09 the maintainer made M7
  measured, not declared: `MT-BENCH-BASELINE`, `MT-BENCH-CONTRAST` and `MT-SCALE-UNBOUND`
  produce the numbers; limits follow.

### `BFQ-09`, `A7A-7` — `unsettled`, which is not the same as open

These are not yet established as defects. `unsettled` exists so that "we looked and could not settle
it" does not silently become either "fixed" or "open". `BFQ-09` has been measured (zero-is-real fixes
six dedup cases and changes no control) and waits on the maintainer. `A7A-7` carries a safety
dimension, the clock question inside the alarm path, and the maintainer owns it. (`BFQ-52` was settled
on 2026-09-23 and has a prepared fix, now blocked on `BFQ-92`.)

---

## What is deliberately *not* on this page

- **Engineering work.** `not-started` items need somebody to do them, not to decide
  them. They are in `queue/QUEUE.md`; the count is in the horizons table on
  [PROGRAMME-STATUS.md](PROGRAMME-STATUS.md).
- **`blocked` items.** They wait on another *item*, not on a person. Unblocking them
  follows from the rows above.
- **`gate-not-met` items.** A gate is failing. That is work.

---

## Checking this page against the gates

Everything above is a **claim** read from the manifest. The measurement is:

```bash
make queue-status STATE=ready-to-push     # do the gates agree these are ready?
make queue-status                          # all of it
make views-check                           # are this page's tables current?
```

`make queue-status` prints `CLAIM DIVERGES` when an item claims `ready-to-push` and a
gate disagrees. Run it before acting on any row here.

<!-- BEGIN GENERATED: provenance -->

*Generated from `queue/work-queue.yaml` by `tools/queue/emit_views.py`. Manifest `measured_at` **2026-09-27**, against cgm-remote-monitor-official `7000eb18` and this repository at `18cdcce0`. Every state above is a **claim** about what the gates will say &mdash; `make queue-status` is the measurement.*

<!-- END GENERATED: provenance -->
