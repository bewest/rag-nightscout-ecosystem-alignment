# Needs a human

*Contributor-facing. The subset of the work queue where no further engineering
advances anything — a person has to push, decide, or review. Prose revised
2026-09-24 against cgm-remote-monitor `origin/dev` `153e5658` and nightscout-connect
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

`merged-upstream` items do not appear here. They need no person individually; what
they need is a release, and that is one item — `RT-0` — which is listed. This
project's last 100 child pull requests were merged with zero human reviews, so an
item leaving `in-flight-upstream` for `merged-upstream` is not by itself evidence
that it was reviewed.

---

## Grouped by who it waits for

<!-- BEGIN GENERATED: needs-a-human -->

### Maintainer &mdash; 8 items

| id | claimed state | what it is | PR |
|---|---|---|---|
| `ADV-CONFIG` | `needs-decision` | The readable-by-world warning, the careportal role, and the two settings behind  | #8746 |
| `ADV-XSS-META` | `needs-decision` | GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74) | &mdash; |
| `BFQ-95` | `needs-decision` | BF-95 - an uploader clock running ahead delays the stale-data alarm | &mdash; |
| `T30-RESEARCH` | `needs-decision` | T3.0 part 1 - enumerate the per-tenant configuration surface | &mdash; |
| `P0-C-REMEDIATE` | `ready-to-push` | Operator remediation for tokens already stored in plaintext - text, not tooling | &mdash; |
| `T30-AUTH` | `ready-to-push` | The auth plane - Ory Kratos/Hydra against building it ourselves, and the three-i | &mdash; |
| `BFQ-09` | `unsettled` | BF-09 - socket dedup truthiness skips a falsy value | &mdash; |
| `BFQ-94` | `unsettled` | BF-94 - a kept profile instance can return a temp basal that has been replaced | &mdash; |

### Maintainer + a second human &mdash; 1 item

| id | claimed state | what it is | PR |
|---|---|---|---|
| `RT-0` | `needs-decision` | Release 15.0.9 | #8598, #8605 |

### SAFETY reviewer &mdash; 1 item

| id | claimed state | what it is | PR |
|---|---|---|---|
| `A7A-7` | `unsettled` | §7a item 7 - the clock question | &mdash; |

### SECURITY reviewer &mdash; 1 item

| id | claimed state | what it is | PR |
|---|---|---|---|
| `BFQ-72` | `needs-decision` | BF-72 - an unauthenticated $regex can spend minutes of database CPU | &mdash; |

<!-- END GENERATED: needs-a-human -->

---

## The open pull requests

One bounded review packet per item awaiting review lives in `reports/reviewer-packets/`.

<!-- BEGIN GENERATED: open-prs -->

| PR | id | branch | what it fixes | who should review |
|---|---|---|---|---|

<!-- END GENERATED: open-prs -->

Twenty-seven cgm-remote-monitor pull requests from this work are merged into `dev` and none is
released:
- the thirteen backfix PRs (twelve from this programme, plus #8741 from an external contributor);
- eleven of the thirteen 15.0.9 additions (#8748, #8749, #8750, #8751, #8752, #8753, #8755, #8756,
  #8757, #8759, #8760);
- #8761 (the count shapes oref0 and GluPredKit send);
- #8762 (the pin to exactly `nightscout-connect` `0.1.0`);
- #8754 (login security fixes and `TRUST_PROXY`, with #8763 and #8765 folded in; merged as
  `4f705217`).

One is open: #8758 fixes records keeping their own `_id`. On 2026-09-25 the freeze candidate,
`dev` `4f705217` + #8758 `ab7b22d6` (tree `25ab7afc`), passed 3066/0/3 on Node 20, 22 and 24 against
MongoDB 4.4.24 and 7.0.43 ([15.0.9 integration record](../30-design/remedial/rc-15.0.9-integration-record.md)).
`dev` `4f705217` on its own passes 2577/0/3. The Loop remote-command browser checks must be repeated,
because #8764 changed `lib/api2` after they were done (RT-0).

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

The version question was settled with `RT-VERSION` (15.0.9 ships as numbered), and the drag check
passed on 2026-09-23 in automation and by hand: mouse in mg/dL and mmol/L, and touch, the same as
15.0.8. The hand check found BF-103 (a split drag keeps the old time, so IOB and COB ignore the move),
which is on 15.0.8 as well and is tracked as `BFQ-103`.

### `RT-0` — release 15.0.9

The most consequential row on this page. 15.0.9 (`origin/master..origin/dev`) is 59 first-parent merges
(`git rev-list --first-parent --count origin/master..origin/dev`, 2026-09-23); `master` is 345 commits
behind `dev`. Until 15.0.9 ships, every one of those fixes exists in code and protects nobody. They
include the fixes for two published-advisory defects that survive `AUTH_DEFAULT_ROLES=denied`,
GHSA-gjhc (BF-79, #8744) and GHSA-8849 (BF-75/76, #8745), the boot notice for world-readable sites
(#8746), and the two backported security fixes (BF-104, BF-105, #8751); every instance on 15.0.8 is
still exposed to all of them. Release PR #8598 is open. Its head is `dev` `4f705217`, and it has
no approving review. What 15.0.9 still waits on is generated from the queue in
[ROADMAP §1](ROADMAP.md#1-the-next-release-1509); what it contains and leaves broken is in
[contents.md](../../releases/cgm-remote-monitor-15.0.9/contents.md), and the test evidence is in the
[15.0.9 integration record](../30-design/remedial/rc-15.0.9-integration-record.md).

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
disposition; the details are held outside version control.

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

*Generated from `queue/work-queue.yaml` by `tools/queue/emit_views.py`. Manifest `measured_at` **2026-09-25**, against cgm-remote-monitor-official `e3adc91d` and this repository at `366a8206`. Every state above is a **claim** about what the gates will say &mdash; `make queue-status` is the measurement.*

<!-- END GENERATED: provenance -->
