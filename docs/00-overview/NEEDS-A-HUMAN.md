# Needs a human

*Contributor-facing. The subset of the work queue where no further engineering
advances anything — a person has to push, decide, or review. Prose revised
2026-09-22 against cgm-remote-monitor `origin/dev` `74fc6619` and nightscout-connect
`official/dev` `1946beb`; tables generated.*

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
| `RT-COUNT0` | `in-flight-upstream` | v1 ?count=0 answers an empty list, amending #8738 before 15.0.9 | &mdash; |
| `ADV-CONFIG` | `needs-decision` | The readable-by-world warning, the careportal role, and the two settings behind  | #8746 |
| `ADV-XSS-META` | `needs-decision` | GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74) | &mdash; |
| `FU-PRBODIES` | `needs-decision` | Merged PR bodies have drifted from the files they were posted from | &mdash; |
| `P0-TAG` | `needs-decision` | nightscout-connect 0.1.0 - the full release, from connector dev | #70 |
| `RT-4` | `needs-decision` | Deprecation release - recommended folded into 15.0.9's release notes | &mdash; |
| `T30-RESEARCH` | `needs-decision` | T3.0 part 1 - enumerate the per-tenant configuration surface | &mdash; |
| `BF2-OPS` | `ready-to-push` | bf2/ops - BF-10 compose ulimits, FU-RESIDUALS 3 and 7, BF-63 renderer | &mdash; |
| `P0-C-REMEDIATE` | `ready-to-push` | Operator remediation for tokens already stored in plaintext - text, not tooling | &mdash; |
| `RT-MONGO-FLOOR` | `ready-to-push` | README: MongoDB 4.4 is deprecated, not unsupported, in 15.0.9 | &mdash; |
| `T30-AUTH` | `ready-to-push` | The auth plane - Ory Kratos/Hydra against building it ourselves, and the three-i | &mdash; |
| `BFQ-09` | `unsettled` | BF-09 - socket dedup truthiness skips a falsy value | &mdash; |

### SECURITY reviewer &mdash; 3 items

| id | claimed state | what it is | PR |
|---|---|---|---|
| `BFQ-72` | `needs-decision` | BF-72 - an unauthenticated $regex can spend minutes of database CPU | &mdash; |
| `BF2-AUTH` | `ready-to-push` | bf2/auth-hardening - bf/auth + bf/throttle + the client-ip.js backport behind TR | &mdash; |
| `BF2-BACKPORT` | `ready-to-push` | Which modernization-only security commits fix a defect that dev has | &mdash; |

### Maintainer + a second human &mdash; 2 items

| id | claimed state | what it is | PR |
|---|---|---|---|
| `RT-0` | `needs-decision` | Release 15.0.9 | #8598, #8605 |
| `BFQ-47` | `ready-to-push` | BF-47 - an ordinary subject edit destroys stored fields, on today's release | &mdash; |

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

<!-- END GENERATED: open-prs -->

All thirteen cgm-remote-monitor backfix pull requests (twelve from this programme,
plus #8741 from an external contributor) are merged into `dev`; none is released. The connector
half, in `nightscout-connect`, measured 2026-09-22 against connector `dev` `1946beb`: every
programme fix is merged there (PRs #64 with #61, #66 and #67; #68), `dev` declares `0.1.0`, and
prerelease `0.1.0-dev.1` is published on npm under `next` through the tag workflow (`P0-PUBLISH`,
#74 and #75). `P0-TAG` is the maintainer's call on when to cut the full `0.1.0`; PR #70 (`dev` →
`main`) follows it. `P0-PIN` and `P0-LOCK` are blocked behind that release.

**Merging in the connector repository ships to nobody.** cgm-remote-monitor pins the connector by
tarball — `dev` pins commit `234d47c` and `master` pins tag `v0.0.13` — so `P0-TAG` and `P0-PIN`
are what deliver the connector fixes. `P0-PIN` is the security-relevant half, because `dev`'s
current pin omits three log-redaction fixes.

---

## The decisions, and what each costs while it waits

Engineering cannot advance these. Each needs somebody to choose.

### `RT-D3` — does a two-major charting upgrade ship under a patch number?

15.0.9 carries D3 5.16 → 7.9: two major versions of a charting library arriving under
a **patch** version, and `dev` has no real-browser coverage to catch what breaks. The
adopted release train puts 15.0.9 first, so every later cut waits behind this answer.

The question is not "is D3 7.9 fine" but whether the project's version numbers mean
something. Semver for an application means something only once the public surface is
*declared*: the API v1/v3 contracts, the plugin interface, the env-var configuration
surface, the database schema, the Node floor, and the ingestion paths. That
declaration does not exist yet, and this decision is where its absence first costs
something.

### `RT-0` — release 15.0.9

Downstream of `RT-D3`, and the most consequential row on this page. 15.0.9
(`origin/master..origin/dev`) is 48 first-parent merges (`git rev-list --first-parent --count origin/master..origin/dev`, 2026-09-22), including the thirteen backfix
PRs; `master` is 308 commits behind `dev`. Until 15.0.9 ships, every one of those fixes
exists in code and protects nobody. They include the fixes for two published-advisory
defects that survive `AUTH_DEFAULT_ROLES=denied` — GHSA-gjhc (BF-79, #8744) and
GHSA-8849 (BF-75/76, #8745) — plus the boot notice for world-readable sites (#8746);
every instance on 15.0.8 is still exposed to all three. BF-70's mechanism is described
in a merged public pull request body while 15.0.8 remains affected. Release PR #8598 is
open, mergeable, green on every CI check, and has no approving review. It is also the
first release that would exercise the three-decision publication rule end to end:
merge the code, push the tag, publish the package. What 15.0.9 contains and whether it
is ready: [`release-readiness-15.0.9-2026-09-22.md`](../30-design/modernization/release-readiness-15.0.9-2026-09-22.md).

The urgency is a reason not to let `RT-D3` sit unanswered, not a reason to release past
it.

### `P0-TAG` — when to cut `nightscout-connect` 0.1.0

Every programme connector fix is in connector `dev`, which declares `0.1.0`, and prerelease
`0.1.0-dev.1` is on npm. Cutting the full release is a tag on `dev` plus an approval; it is the
maintainer's judgement when the prerelease has been exercised enough. The connector fixes reach
operators only through a cgm-remote-monitor pin (`P0-PIN`), and that pin waits on this release.

### `BFQ-47` — BF-47 needs intent before it needs code

An ordinary subject edit destroys stored fields on 15.0.8. The fix depends on whether
that behaviour was deliberate, and nobody has established which. A fix written first
would be a guess at intent.

### `BFQ-72` — whether the security contact process is invoked

BF-72: an unauthenticated query can occupy the database for minutes. It is live on
15.0.8 and on `dev`, and there is no fix. Mechanism only is recorded in this public
repository. The blocking question is whether Nightscout's security contact process is
invoked.

### `BFQ-09`, `BFQ-52`, `A7A-7` — `unsettled`, which is not the same as open

These are not yet established as defects. `unsettled` exists so that "we looked and
could not settle it" does not silently become either "fixed" or "open". `A7A-7` carries
a safety dimension: it is the clock question inside the alarm path.

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

*Generated from `queue/work-queue.yaml` by `tools/queue/emit_views.py`. Manifest `measured_at` **2026-09-22**, against cgm-remote-monitor-official `74fc6619` and this repository at `4c7f7cfa`. Every state above is a **claim** about what the gates will say &mdash; `make queue-status` is the measurement.*

<!-- END GENERATED: provenance -->
