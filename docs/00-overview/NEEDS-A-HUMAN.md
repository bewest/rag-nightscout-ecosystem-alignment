# Work waiting on a person: what to push, decide or review

*What this is: a record (contributor-facing). Read after the [roadmap](ROADMAP.md); leads to the
[definition of done: when a change is ready for the apps that depend on it](DEFINITION-OF-DONE.md). The subset of the work queue where no further engineering
advances anything — a person has to push, decide, or review. Prose revised
2026-10-08 against cgm-remote-monitor `official/dev` `fade2299` (the `RT-0` section 2026-10-21,
against `official/master` `c6a0d8ed`, tag `v15.0.9`) and nightscout-connect
`official/main` `4dde1ec` (tag `v0.1.0`); tables generated.*

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

### Maintainer &mdash; 16 items

| id | claimed state | what it is | PR |
|---|---|---|---|
| `BFQ-09` | `in-flight-upstream` | BF-09 - socket dedup truthiness skips a falsy value | #8797 |
| `BFQ-172` | `in-flight-upstream` | BF-172 - the Bolus Wizard Preview mixes the profile's units with the display uni | #8819 |
| `ADV-CONFIG` | `needs-decision` | The readable-by-world warning, the careportal role, and the two settings behind  | #8746 |
| `ADV-XSS-META` | `needs-decision` | GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74) | &mdash; |
| `BFQ-164` | `needs-decision` | BF-164 - writes outside API v3 never reach the v3 storage socket | &mdash; |
| `DEPENDABOT-CONFIG` | `needs-decision` | Dependabot runs with no configuration: security PRs target master, and alerts co | &mdash; |
| `ID-ABSENT-DECISION` | `needs-decision` | Decide: a write that carries no identifier (and no _id) - keep the time-key fall | &mdash; |
| `ID-CLIENT-OID-DECISION` | `needs-decision` | Decide: may a client set _id (an ObjectId it creates), and which field wins when | &mdash; |
| `ID-DELETE-REUSE-DECISION` | `needs-decision` | Decide: after a delete, what does a re-send of the same identifier (or _id) do - | &mdash; |
| `ID-FORMAT-DECISION` | `needs-decision` | Decide: the client identifier's format (opaque string with limits; UUID not requ | &mdash; |
| `ID-SCOPE-DECISION` | `needs-decision` | Decide: is identifier unique per collection, across collections, and per tenant  | &mdash; |
| `ID-V3-IMMUTABLE-DECISION` | `needs-decision` | Decide: on an identifier match, may date, device or eventType change? | &mdash; |
| `T30-RESEARCH` | `needs-decision` | T3.0 part 1 - enumerate the per-tenant configuration surface | &mdash; |
| `P0-C-REMEDIATE` | `ready-to-push` | Operator remediation for tokens already stored in plaintext - text, not tooling | &mdash; |
| `T30-AUTH` | `ready-to-push` | The auth plane - Ory Kratos/Hydra against building it ourselves, and the three-i | &mdash; |
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
| **#8797** | `BFQ-09` | `bf/socket-dedup-zero` | BF-09 - socket dedup truthiness skips a falsy value | Maintainer |
| **#8819** | `BFQ-172` | `javier-erro:#8819` | BF-172 - the Bolus Wizard Preview mixes the profile's units  | Maintainer |

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
release rests on the maintainers' readiness decision of 2026-10-21; its known issues and what is
left (the plain `15.0.9` tag, the next development cycle) are in
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
