# Needs a human

*Contributor-facing. The subset of the work queue where no further engineering
advances anything — a person has to push, decide, or review. Narrative revised
2026-09-21; tables generated.*

The queue has 88 items. Most of them are work. This page is only the items whose
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

> **`in-flight-upstream` used to be the one that hid, and the shape of the problem
> has changed rather than gone.** Revised 2026-09-21: nine pull requests sat here
> unreviewed on 2026-09-16; **thirteen have since merged** — ten Phase 0 pull
> requests between 2026-09-17 and 2026-09-20, then the three advisory pull requests
> #8744, #8745 and #8746 on the evening of 2026-09-21 — and one remains, in the
> connector repository. This project's last 100 child pull requests were merged
> with zero human reviews, so a PR leaving this list is not by itself evidence it
> was reviewed. The governance gap moved from "waiting" to "merged", which is
> harder to see, not better.
>
> **A fifth state, `merged-upstream`, deliberately does NOT appear on this page.**
> Those items need no person individually; what they need is a release, and that
> is one item — `RT-0` — which is listed. Putting nine merged fixes here would pad
> the page and bury the single decision that actually unblocks them.

---

## Grouped by who it waits for

<!-- BEGIN GENERATED: needs-a-human -->

### Maintainer &mdash; 13 items

| id | claimed state | what it is | PR |
|---|---|---|---|
| `P0-F` | `in-flight-upstream` | fix/connect-timer-jitter - PR #68, BF-34 backoff precedence and start jitter | #68 |
| `ADV-CONFIG` | `needs-decision` | The readable-by-world warning, the careportal role, and the two settings behind  | #8746 |
| `ADV-XSS-META` | `needs-decision` | GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74) | &mdash; |
| `FU-PRBODIES` | `needs-decision` | Five merged PR bodies have drifted from the files they were posted from | &mdash; |
| `P0-TAG` | `needs-decision` | nightscout-connect release/v0.0.14 and tag - prepared, needs a human push | &mdash; |
| `RT-D3` | `needs-decision` | Answer the D3 question before 15.0.9 ships | &mdash; |
| `T30-RESEARCH` | `needs-decision` | T3.0 part 1 - enumerate the per-tenant configuration surface | &mdash; |
| `DOC-LINKS` | `ready-to-push` | Every path the programme's documents and tooling cite must resolve | &mdash; |
| `DOC-VIEWS` | `ready-to-push` | A reviewer-facing surface over the queue: three overview pages and a packet per  | &mdash; |
| `P0-C-REMEDIATE` | `ready-to-push` | Operator remediation for tokens already stored in plaintext - text, not tooling | &mdash; |
| `T30-AUTH` | `ready-to-push` | The auth plane - Ory Kratos/Hydra against building it ourselves, and the three-i | &mdash; |
| `BFQ-09` | `unsettled` | BF-09 - socket dedup truthiness skips a falsy value | &mdash; |
| `BFQ-52` | `unsettled` | BF-52 - the age plugins can only ask for their urgent alarm in one window | &mdash; |

### Maintainer + a second human &mdash; 2 items

| id | claimed state | what it is | PR |
|---|---|---|---|
| `BFQ-47` | `needs-decision` | BF-47 - an ordinary subject edit destroys stored fields, on today's release | &mdash; |
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

One bounded review packet per row lives in `reports/reviewer-packets/`.

<!-- BEGIN GENERATED: open-prs -->

| PR | id | branch | what it fixes | who should review |
|---|---|---|---|---|
| **#68** | `P0-F` | `fix/connect-timer-jitter` | fix/connect-timer-jitter - PR #68, BF-34 backoff precedence  | Maintainer |

<!-- END GENERATED: open-prs -->

**Revised twice on 2026-09-21: this list is down to one, and the reason matters.**
It held nine cgm-remote-monitor pull requests on 2026-09-16. All of them merged,
along with #8733, between 2026-09-17 and 2026-09-20; the three advisory pull
requests raised that evening — #8744, #8745, #8746 — merged the same day they were
opened. What is left is the connector half: PR #68 is open, four sibling connector
PRs (#61, #64, #66, #67) are open, and the prepared `v0.0.14` tag is still unpushed.

**The second revision is the one to read.** The earlier sentence here said the
connector half "has not moved at all". It has. On the evening of 2026-09-21
`nightscout-connect`'s `dev` took the Glooko work (#71) and restored connector
regression CI (#72), and — the part that matters — **bumped its own `package.json`
to 0.0.14**, the same version this programme has had a prepared, unpushed tag for
since 2026-09-15, on a tree that conflicts with `dev` in six files. So there are now
two candidate 0.0.14s. `P0-TAG` moved from `ready-to-push` to `needs-decision`
because of it, and `P0-PIN` and `P0-LOCK` are blocked behind a question that is no
longer "when does somebody push the tag" but "which 0.0.14 is the real one".

One thing a reviewer should know before opening #68: **merging it in the connector
repository ships it to nobody.** cgm-remote-monitor pins the connector by tarball,
so `P0-TAG` and `P0-PIN` are what deliver it — and `P0-PIN` is the security-relevant
half, because `dev`'s current pin omits three log-redaction fixes.

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

**Its weight changed on 2026-09-20, grew again on 2026-09-21, and this is now the
most consequential row on the page.** `dev` carries ten merged Phase 0 fixes *and
three merged security fixes* that `origin/master` does not — `master` is **308
commits behind**, up from 299 the same evening — so until 15.0.9 ships, **every one
of those fixes is code that exists and protects nobody**. The three that landed on
2026-09-21 close two published-advisory defects (GHSA-gjhc, GHSA-8849) plus the
world-readable boot notice, and every live instance is still exposed to all three. One of them, BF-70, had its mechanism
described in a merged public pull request body on 2026-09-18 while the shipping
release remains affected. That is not a reason to rush a release past `RT-D3`; it is
a reason not to let `RT-D3` sit unanswered, and the two are different things.

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

*Generated from `queue/work-queue.yaml` by `tools/queue/emit_views.py`. Manifest `measured_at` **2026-09-21**, against cgm-remote-monitor-official `74fc6619` and this repository at `fd632602`. Every state above is a **claim** about what the gates will say &mdash; `make queue-status` is the measurement.*

<!-- END GENERATED: provenance -->
