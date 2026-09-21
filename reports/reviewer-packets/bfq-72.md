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

# Review packet — BFQ-72

**BF-72 - an unauthenticated $regex can spend minutes of database CPU**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `origin/dev@59430336` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=BFQ-72` is the measurement |
| semver | `minor` |
| register entries | `BF-72` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

No line is wrong, which is why this is needs-decision and not not-started.
$regex and $options are in lib/server/query-operator-allowlist.js
FIELD_OPERATORS by design, and lib/server/query.js promotes treatments.notes
to a regex as a documented search affordance. A fix changes what the search
affordance accepts, so its blast radius is every client that sends a pattern -
which the 14-project census counted as source, not runtime.

## Why that semver

Every candidate fix removes reachable behaviour from a documented search
affordance - a pattern that works today stops working - so it is not a patch
by the project's own reading of its surface. Not major: no route is removed,
no required input is added, and ordinary patterns are unaffected. If the
chosen fix turns out to reject a pattern shape a real client sends, that
reclassifies it, which is an argument for measuring runtime traffic before
choosing.

## What an operator would notice

> DO NOT PUBLISH THIS PARAGRAPH AHEAD OF A DECISION. Nightscout's older API
> lets a request search text fields using a pattern. There is no limit on
> how complicated that pattern may be, and a complicated one can make the
> database work for minutes on a single request - long enough that the site
> stops answering for everyone using it. On a site that allows anonymous
> reading, which is Nightscout's default, no password or token is needed to
> send one. Your data is not exposed or altered by this; what is at risk is
> the site being there when you look at it. If you watch Nightscout to make
> decisions, this is a reason to have a second way to see your readings -
> which is good practice regardless. Restricting access at your proxy or
> hosting provider is what helps today. Nightscout is not a medical device
> and this is not medical advice; discuss what you rely on Nightscout for
> with your care team.

## Who should review this, and why

SECURITY, and the same person who has to answer P0-K's sequencing question,
because it is the same question about the same advisory. DISCLOSURE-SENSITIVE:
this is a one-request unauthenticated denial of service against a default
install, live on the shipping release and on dev. The mechanism is in the
register; the three patterns are deliberately not, and the probe is outside
version control twice over. The ordinary path for this stack - a public issue
or PR carrying the reproduction - publishes a working attack against every
unpatched Nightscout, and there is no patch to move to.

## What was measured

**`node tools/queue/gates/bf72-regex-operand-bounded.js`** &nbsp;·&nbsp; kind: `static`

Asserts that SOME bound on the $regex operand exists on the v1 read path - a
length cap, a required literal prefix, a nested-quantifier rejection or a
linear-time engine - without prescribing which. FAILS TODAY, by design. Its
first finding is the control: $regex must be REACHABLE for the finding to
exist, so a future change that refused the operator outright flips the control
rather than passing silently. Non-vacuity proven both directions on 2026-09-21
against the scratch ref tmp/bf72-vacuity-probe. WORTH KNOWING: the first draft
of this gate looked for a bound within 400 characters of a $regex occurrence
and did NOT flip under that same ablation, because the natural site for a fix
is over a thousand characters from the accept-set literal. A gate that only
recognises a fix written in one place reads a real fix as absent; the detector
is line-scoped and name-based instead.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- THE TIMING MEASUREMENT IS DELIBERATELY NOT IN THIS REPOSITORY, and the
  static gate above is the cheaper half of the evidence rather than the
  finding. Writing the timing measurement in means writing the patterns in,
  and this repository is public while the defect is live on the shipping
  release - the BF-70 constraint, same reasoning. Held at
  externals/work/crm-advisory/tmp/bf72-regex-cpu.js with its README: 20 000
  seeded entries, mongod 7.0.43, control 22 ms, benign anchored prefix 29
  ms, three nested-quantifier patterns 60 s / 65 s / 71 s, stable across two
  runs.
- NO FIX IS GATED BECAUSE NO FIX HAS BEEN MEASURED. Four candidates are
  named in the register - pattern length cap, required literal prefix,
  nested-quantifier rejection, linear-time engine - and each trades
  capability for cost. Choosing is a decision about the search affordance's
  contract, and the programme's record on "the obvious fix costs nothing"
  claims (RT-REBASE) is the reason this is not written as an engineering
  task with a prescribed answer.
- THE AMPLIFICATION FIGURE IS A FLOOR, NOT A MEASUREMENT OF A REAL SITE. 20
  000 documents is small; a real entries collection is far larger and the
  cost is superlinear per document. Nothing here measures a real deployment,
  and nothing should claim to - rule 0 forbids pointing this at anyone's
  instance.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

FOUND 2026-09-21 while re-measuring the advisory's third PoC, and it is not
the defect the advisory describes there. The advisory frames PoC C as $regex
data extraction. On the shipped `readable` default that is close to vacuous -
entries, treatments and devicestatus are the three collections prep_storage
admits, all three are already readable, and the API returns whole documents,
so a regex oracle reveals nothing a plain read does not. What the same
operator does do is cost, and that was not in the advisory. SEQUENCING WITH
P0-K. #8743 merged on 2026-09-18 and did not narrow $regex, because narrowing
it was never the intent - the census found real clients sending it. So this
entry is not a regression from that branch and is not fixed by it; it is the
residual the branch's own PR body pointed at without naming. STATE IS needs-
decision AND NOT gate-not-met ON PURPOSE. A gate does fail, but the blocking
thing is not work: it is whether Nightscout's security contact process is
invoked and in what order, which is the identical question P0-K left open and
which nobody has answered. Filing it as engineering-ready would misrepresent
what it is waiting for.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-72` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-21, against cgm-remote-monitor-official `59430336`.*
