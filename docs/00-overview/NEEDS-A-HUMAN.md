# Needs a human

*Contributor-facing. The subset of the work queue where no further engineering
advances anything — a person has to push, decide, or review. Prose revised
2026-10-03 against cgm-remote-monitor `official/dev` `74942ec6` and nightscout-connect
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
they need is a release, and that is one item — `RT-0` — which is listed.

---

## Grouped by who it waits for

<!-- BEGIN GENERATED: needs-a-human -->

### Maintainer &mdash; 10 items

| id | claimed state | what it is | PR |
|---|---|---|---|
| `BFQ-09` | `in-flight-upstream` | BF-09 - socket dedup truthiness skips a falsy value | #8797 |
| `ADV-CONFIG` | `needs-decision` | The readable-by-world warning, the careportal role, and the two settings behind  | #8746 |
| `ADV-XSS-META` | `needs-decision` | GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74) | &mdash; |
| `DEPENDABOT-CONFIG` | `needs-decision` | Dependabot runs with no configuration: security PRs target master, and alerts co | &mdash; |
| `RT-PROPAGATION` | `needs-decision` | How the release train reaches dev: merge dev into the cuts, or rebase the cuts o | &mdash; |
| `T30-RESEARCH` | `needs-decision` | T3.0 part 1 - enumerate the per-tenant configuration surface | &mdash; |
| `BFQ-124` | `ready-to-push` | BF-124 - the treatment tooltip converts a BG already in display units (issue #59 | &mdash; |
| `P0-C-REMEDIATE` | `ready-to-push` | Operator remediation for tokens already stored in plaintext - text, not tooling | &mdash; |
| `T30-AUTH` | `ready-to-push` | The auth plane - Ory Kratos/Hydra against building it ourselves, and the three-i | &mdash; |
| `WS-LAB` | `ready-to-push` | tools/lab/proxy-trust - socket.io (WebSocket) cells on the AR chain (W0-W3) | &mdash; |

### Maintainer + a second human &mdash; 1 item

| id | claimed state | what it is | PR |
|---|---|---|---|
| `RT-0` | `needs-decision` | Release 15.0.9 | #8598, #8605 |

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

<!-- END GENERATED: open-prs -->

Every PR decided for 15.0.9 is merged except the fixes for BF-124 and BF-127, whose branches are
being prepared; `RT-0` below gives the release's state.

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

### `RT-0` — release 15.0.9

The most consequential row on this page. `dev` is at `74942ec6` (the merge of #8800, 2026-10-03):
95 first-parent merges and 537 commits since 15.0.8
(`git rev-list [--first-parent] --count official/master..official/dev`). Until 15.0.9 ships, every
one of those fixes exists in code and protects nobody. They include the fixes for two
published-advisory defects that survive `AUTH_DEFAULT_ROLES=denied`, GHSA-gjhc (BF-79, #8744) and
GHSA-8849 (BF-75/76, #8745), the boot notice for world-readable sites (#8746), and the two
backported security fixes (BF-104, BF-105, #8751); every instance on 15.0.8 is still exposed to all
of them.

- **Merged.** Every PR decided for 15.0.9 except the fixes for BF-124 and BF-127, decided 2026-10-02 and on branches being prepared (queue `BFQ-124`, `BFQ-127`), the last being #8800 (BF-94); the list is in
  [contents.md](../../releases/cgm-remote-monitor-15.0.9/contents.md), which also says what the
  release leaves broken. Crowdin #8730 is held out because its sync reverts translations `dev`
  corrected (BF-132).
- **Tests.** The last full run is run 020 on `ce30a94d` (2026-09-27): 3473/0/3 in all six cells
  (Node 20, 22 and 24 against MongoDB 4.4.24 and 7.0.43), with an A/B soak against 15.0.8. Each PR
  merged since carries its own evidence (its GitHub CI and a full suite on its branch). #8800's head
  `a06e75d6` has the same tree as `74942ec6`, and passes the full suite, 3538/0/4, on one cell
  (Node 24, MongoDB 7.0.43). A full six-cell run on `74942ec6` comes next
  ([15.0.9 integration record](../30-design/remedial/rc-15.0.9-integration-record.md)).
- **Real-site soak.** `RT-SOAK` is done: the maintainer decided on 2026-09-30 that real sites
  running the candidate count as the soak, and reports (2026-10-02) stable behaviour from Loop, Trio
  and AndroidAPS users on `dev`. The lab's 72 h soak was not run.
- **Release PR.** #8598 (`dev` → `master`) is at `74942ec6` and mergeable; its CI on `74942ec6`:
  27 checks passed, 3 skipped (read 2026-10-03 00:21Z).
  It was approved at `e3adc91d`; re-approval at `74942ec6` is owed.
- **Version.** Decided: 15.0.9. `RT-VERSION`'s gate measures the modernization cut branches, which
  also declare 15.0.9 and are renumbered when they are rebased; it holds the cuts, not this release.
- **What remains** before the tag, including the queue's open `RT-0` blockers, is listed once, in [ROADMAP §1](ROADMAP.md#1-the-next-release-1509).

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
