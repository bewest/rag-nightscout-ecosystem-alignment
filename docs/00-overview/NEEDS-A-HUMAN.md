# Needs a human

*Contributor-facing. The subset of the work queue where no further engineering
advances anything — a person has to push, decide, or review. Prose revised
2026-09-23 against cgm-remote-monitor `origin/dev` `ddd9b600` and nightscout-connect
`official/dev` `977da8a`; tables generated.*

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

### Maintainer &mdash; 12 items

| id | claimed state | what it is | PR |
|---|---|---|---|
| `BFQ-102` | `in-flight-upstream` | bf/object-id-consistency - one rule for a record's own hex _id across profile, d | #8758 |
| `RT-COUNT-COMPAT` | `in-flight-upstream` | Reads accept the count shapes oref0 and GluPredKit send; 15.0.9 stays a patch | &mdash; |
| `ADV-CONFIG` | `needs-decision` | The readable-by-world warning, the careportal role, and the two settings behind  | #8746 |
| `ADV-XSS-META` | `needs-decision` | GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74) | &mdash; |
| `BFQ-95` | `needs-decision` | BF-95 - an uploader clock running ahead delays the stale-data alarm | &mdash; |
| `FU-PRBODIES` | `needs-decision` | Merged PR bodies have drifted from the files they were posted from | &mdash; |
| `P0-TAG` | `needs-decision` | nightscout-connect 0.1.0 - the full release, from connector dev | #70 |
| `T30-RESEARCH` | `needs-decision` | T3.0 part 1 - enumerate the per-tenant configuration surface | &mdash; |
| `P0-C-REMEDIATE` | `ready-to-push` | Operator remediation for tokens already stored in plaintext - text, not tooling | &mdash; |
| `T30-AUTH` | `ready-to-push` | The auth plane - Ory Kratos/Hydra against building it ourselves, and the three-i | &mdash; |
| `BFQ-09` | `unsettled` | BF-09 - socket dedup truthiness skips a falsy value | &mdash; |
| `BFQ-94` | `unsettled` | BF-94 - a kept profile instance can return a temp basal that has been replaced | &mdash; |

### Maintainer + a second human &mdash; 2 items

| id | claimed state | what it is | PR |
|---|---|---|---|
| `BFQ-47` | `in-flight-upstream` | BF-47 - an ordinary subject edit destroys stored fields, on today's release | &mdash; |
| `RT-0` | `needs-decision` | Release 15.0.9 | #8598, #8605 |

### SECURITY reviewer &mdash; 2 items

| id | claimed state | what it is | PR |
|---|---|---|---|
| `BF2-AUTH` | `in-flight-upstream` | bf2/auth-hardening - bf/auth + bf/throttle + the client-ip.js backport behind TR | #8754 |
| `BFQ-72` | `needs-decision` | BF-72 - an unauthenticated $regex can spend minutes of database CPU | &mdash; |

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
| **#8754** | `BF2-AUTH` | `bf2/auth-hardening` | bf2/auth-hardening - bf/auth + bf/throttle + the client-ip.j | SECURITY reviewer |
| **#8758** | `BFQ-102` | `bf/object-id-crud` | bf/object-id-consistency - one rule for a record's own hex _ | Maintainer |

<!-- END GENERATED: open-prs -->

Twenty-four cgm-remote-monitor pull requests from this work are merged into `dev` and none is
released: the thirteen backfix PRs (twelve from this programme, plus #8741 from an external
contributor), and eleven of the thirteen 15.0.9 additions (#8748, #8749, #8750, #8751, #8752, #8753,
#8755, #8756, #8757, #8759, #8760). Two are open: #8754 (login security fixes and `TRUST_PROXY`, waiting on the
security review by the maintainer and Andy) and #8758 (records keep their own `_id`).
`rc/15.0.9-combined-36b` (3015/0/3 on every Node and MongoDB pair) tested every 15.0.9 unit except
#8760, which merged after it. `rc/15.0.9-combined-59`, which is `dev` `ddd9b600` with #8754 and #8758,
passes 3028/0/3 on every Node and MongoDB pair. One more run follows the pin to exact `0.1.0`, before
the tag (maintainer, 2026-09-23; `RT-0`).

The connector half, in `nightscout-connect`, measured 2026-09-23 against connector `dev` `977da8a`:
every programme fix is merged there (PRs #64 with #61, #66 and #67; #68; #77; #78; #79), `dev`
declares `0.1.0`, and prerelease `0.1.0-dev.3` is published on npm under `next`. cgm-remote-monitor
`dev` pins exactly `0.1.0-dev.3` (#8759); `master` still pins tag `v0.0.13`. `P0-TAG` is the
maintainer's call on when to cut the full `0.1.0`; a last Nightscout pin to exact `0.1.0` follows it,
and PR #70 (`dev` → `main`) follows the tag.

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
still exposed to all of them. Release PR #8598 is open at `ddd9b600`, green on every CI check, and has
no approving review. Still before the tag: #8754 and #8758 (tested together on current `dev`),
connector `0.1.0` and its pin with one more combined run, the release notes, and that review. What 15.0.9 contains and whether it is ready:
[`release-readiness-15.0.9-2026-09-22.md`](../30-design/modernization/release-readiness-15.0.9-2026-09-22.md)
(a 2026-09-22 snapshot; the combined rc record is
[`rc-15.0.9-combined-2026-09-23.md`](../30-design/remedial/rc-15.0.9-combined-2026-09-23.md)).

### `P0-TAG` — when to cut `nightscout-connect` 0.1.0

Every programme connector fix is in connector `dev`, which declares `0.1.0`, and prerelease
`0.1.0-dev.3` is on npm and is what Nightscout `dev` installs. Cutting the full release is a tag on
`dev` plus an approval; it is the maintainer's judgement when the prerelease has been exercised
enough. A Nightscout pin to exact `0.1.0`, with a re-run of the combined rc, follows it.

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

*Generated from `queue/work-queue.yaml` by `tools/queue/emit_views.py`. Manifest `measured_at` **2026-09-23**, against cgm-remote-monitor-official `ddd9b600` and this repository at `c1a5e719`. Every state above is a **claim** about what the gates will say &mdash; `make queue-status` is the measurement.*

<!-- END GENERATED: provenance -->
