# Needs a human

*Contributor-facing. The subset of the work queue where no further engineering
advances anything — a person has to push, decide, or review. Narrative revised
2026-09-16; tables generated.*

The queue has 75 items. Most of them are work. This page is only the items whose
claimed state means **the next move belongs to a person**, grouped by the kind of
person, so that "what is blocked on me" is one page instead of a filter nobody
runs.

Four states qualify:

| state | what it means |
|---|---|
| `ready-to-push` | every runnable gate passes; the next step is a human push |
| `needs-decision` | waiting on a decision, not on work |
| `in-flight-upstream` | handed to upstream; not ours to land |
| `unsettled` | not yet established that this is a defect at all |

> **`in-flight-upstream` is the one that hides.** It reads like progress, and it
> is — but it is also a queue of pull requests sitting unreviewed. Nine of them.
> Given that this project's last 100 child pull requests were merged with zero
> human reviews, "in flight" is where the governance gap actually lives.

---

## Grouped by who it waits for

<!-- BEGIN GENERATED: needs-a-human -->

### Maintainer &mdash; 19 items

| id | claimed state | what it is | PR |
|---|---|---|---|
| `BFQ-40` | `in-flight-upstream` | BF-40 - $exists is not read as a boolean on dev; fixed by bf/coercion | &mdash; |
| `P0-B` | `in-flight-upstream` | bf/cache - PR #8740, T0.2 and T0.3 read-path cost | #8740 |
| `P0-D` | `in-flight-upstream` | bf/coercion - PR #8737, query filter typing (T0.5) and the $exists inversion | #8737 |
| `P0-E` | `in-flight-upstream` | bf/reads - PR #8738, six read-path fixes, independent of bf/coercion | #8738 |
| `P0-F` | `in-flight-upstream` | fix/connect-timer-jitter - PR #68, BF-34 backoff precedence and start jitter | #68 |
| `P0-G` | `in-flight-upstream` | bf/food - PR #8735, BF-16 quick-pick filter, BF-35 bolus calculator chooser | #8735 |
| `P0-H` | `in-flight-upstream` | bf/merge - PR #8734, BF-36 client delta merge reads past the end | #8734 |
| `P0-I` | `in-flight-upstream` | bf/parms - PR #8736, BF-37, BF-38, BF-39 | #8736 |
| `P0-K` | `needs-decision` | bf/operators - BF-04 extracted, BF-70 found - NOT YET A PR, needs a disclosure d | &mdash; |
| `RT-D3` | `needs-decision` | Answer the D3 question before 15.0.9 ships | &mdash; |
| `T30-RESEARCH` | `needs-decision` | T3.0 part 1 - enumerate the per-tenant configuration surface | &mdash; |
| `DOC-LINKS` | `ready-to-push` | Every path the programme's documents and tooling cite must resolve | &mdash; |
| `DOC-VIEWS` | `ready-to-push` | A reviewer-facing surface over the queue: three overview pages and a packet per  | &mdash; |
| `P0-C-REMEDIATE` | `ready-to-push` | Operator remediation for tokens already stored in plaintext - text, not tooling | &mdash; |
| `P0-J` | `ready-to-push` | bf/throttle - BF-30, failed-auth throttling, compatibility default | #8605 |
| `P0-TAG` | `ready-to-push` | nightscout-connect release/v0.0.14 and tag - prepared, needs a human push | &mdash; |
| `T30-AUTH` | `ready-to-push` | The auth plane - Ory Kratos/Hydra against building it ourselves, and the three-i | &mdash; |
| `BFQ-09` | `unsettled` | BF-09 - socket dedup truthiness skips a falsy value | &mdash; |
| `BFQ-52` | `unsettled` | BF-52 - the age plugins can only ask for their urgent alarm in one window | &mdash; |

### Maintainer + a second human &mdash; 3 items

| id | claimed state | what it is | PR |
|---|---|---|---|
| `P0-A` | `in-flight-upstream` | bf/alarms - PR #8739, BF-28, BF-29, BF-31 | #8739 |
| `BFQ-47` | `needs-decision` | BF-47 - an ordinary subject edit destroys stored fields, on today's release | &mdash; |
| `RT-0` | `needs-decision` | Release 15.0.9 | #8598, #8605 |

### SECURITY reviewer &mdash; 1 item

| id | claimed state | what it is | PR |
|---|---|---|---|
| `P0-C` | `ready-to-push` | bf/auth - BF-17 plaintext token (BF-30 split out to P0-J) | &mdash; |

### Upstream reviewers &mdash; 1 item

| id | claimed state | what it is | PR |
|---|---|---|---|
| `P0-T01` | `in-flight-upstream` | T0.1 - PR #8733, the two quadratic treatment scans | #8733 |

### SAFETY reviewer &mdash; 1 item

| id | claimed state | what it is | PR |
|---|---|---|---|
| `A7A-7` | `unsettled` | §7a item 7 - the clock question | &mdash; |

<!-- END GENERATED: needs-a-human -->

---

## The open pull requests

One bounded review packet per row lives in `reports/reviewer-packets/`.

<!-- BEGIN GENERATED: open-prs -->

| PR | id | branch | what it fixes | who should review |
|---|---|---|---|---|
| **#68** | `P0-F` | `fix/connect-timer-jitter` | fix/connect-timer-jitter - PR #68, BF-34 backoff precedence  | Maintainer |
| **#8733** | `P0-T01` | `fix/quadratic-treatment-processing` | T0.1 - PR #8733, the two quadratic treatment scans | Upstream reviewers |
| **#8734** | `P0-H` | `bf/merge` | bf/merge - PR #8734, BF-36 client delta merge reads past the | Maintainer |
| **#8735** | `P0-G` | `bf/food` | bf/food - PR #8735, BF-16 quick-pick filter, BF-35 bolus cal | Maintainer |
| **#8736** | `P0-I` | `bf/parms` | bf/parms - PR #8736, BF-37, BF-38, BF-39 | Maintainer |
| **#8737** | `P0-D` | `bf/coercion` | bf/coercion - PR #8737, query filter typing (T0.5) and the $ | Maintainer |
| **#8738** | `P0-E` | `bf/reads` | bf/reads - PR #8738, six read-path fixes, independent of bf/ | Maintainer |
| **#8739** | `P0-A` | `bf/alarms` | bf/alarms - PR #8739, BF-28, BF-29, BF-31 | Maintainer + a second human |
| **#8740** | `P0-B` | `bf/cache` | bf/cache - PR #8740, T0.2 and T0.3 read-path cost | Maintainer |

<!-- END GENERATED: open-prs -->

Two things a reviewer should know before opening any of them:

- **`#8739` (`bf/alarms`) and `#8740` (`bf/cache`) are not ordinary.** `bf/alarms`
  changes the code path that decides whether an alarm fires; `bf/cache` carries a
  gate that is **red permanently by design**, and the packet says why so that the
  red is not read as an unfinished branch.
- **`#8733` is upstream's, not ours.** It is listed because it is part of Phase 0,
  not because this project can land it.

---

## The decisions, and what each costs while it waits

Engineering cannot advance these. Each needs somebody to choose.

### `RT-D3` — does a two-major charting upgrade ship under a patch number?

15.0.9 carries D3 5.16 → 7.9. That is two major versions of a charting library
arriving under a **patch** version, and `dev` has no real-browser coverage to catch
what breaks. The adopted release train puts 15.0.9 first, so **every later cut waits
behind this answer.**

The question is not "is D3 7.9 fine" — it is whether the project's version numbers
are allowed to mean something. Semver for an application only means anything once
the public surface is *declared*: the API v1/v3 contracts, the plugin interface, the
env-var configuration surface, the database schema, the Node floor, and the
ingestion paths. That declaration does not exist yet, and this decision is where its
absence first costs something real.

### `RT-0` — release 15.0.9

Downstream of `RT-D3`. Also the first release that would exercise the three-decision
publication rule end to end: merge the code, push the tag, publish the package.

### `BFQ-47` — BF-47, and it needs intent before it needs code

An ordinary subject edit destroys stored fields **on today's release**. The fix
depends on whether that behaviour was deliberate, and nobody has established which.
Writing a fix first would be guessing at intent and calling it a repair.

### `BFQ-09`, `BFQ-52`, `A7A-7` — `unsettled`, which is not the same as open

These are not yet established as defects at all. `unsettled` exists as a state
precisely so that "we looked and could not settle it" does not silently become
either "fixed" or "open". `A7A-7` carries a safety dimension — it is the clock
question inside the alarm path.

---

## What is deliberately *not* on this page

- **Engineering work.** 34 items are `not-started` and need somebody to do them,
  not to decide them. Those are in `queue/QUEUE.md`.
- **`blocked` items.** They wait on another *item*, not on a person. Unblocking
  them is a consequence of the rows above, not a separate decision.
- **`gate-not-met` items.** A gate is failing. That is work.

---

## Checking this page against the gates

Everything above is a **claim** read from the manifest. The measurement is:

```bash
make queue-status STATE=ready-to-push     # do the gates agree these are ready?
make queue-status                          # all of it (~7s)
make views-check                           # are this page's tables current?
```

`make queue-status` prints `CLAIM DIVERGES` when an item claims `ready-to-push`
and a gate disagrees. That warning caught a wrong state on its first ever run, so
it is worth running before acting on any row here.

<!-- BEGIN GENERATED: provenance -->

*Generated from `queue/work-queue.yaml` by `tools/queue/emit_views.py`. Manifest `measured_at` **2026-09-15**, against cgm-remote-monitor-official `a8888f0d` and this repository at `75c38a17`. Every state above is a **claim** about what the gates will say &mdash; `make queue-status` is the measurement.*

<!-- END GENERATED: provenance -->
