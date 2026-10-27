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
| branch | `adv/r3gv-1600-dev` |
| base | `official/dev@7abe1cf6` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-72` is the measurement |
| semver | `minor` |
| register entries | `BF-72` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

No line is wrong, which is why this is needs-decision and not not-started.
$regex and $options are in lib/server/query-operator-allowlist.js
FIELD_OPERATORS by design, and lib/server/query.js promotes a treatments text
field to a regex as a documented search affordance. A fix changes what the
search affordance accepts, so its blast radius is every client that sends a
pattern - which the 14-project census counted as source, not runtime.

## Why that semver

Every candidate fix removes reachable behaviour from a documented search
affordance - a pattern that works today stops working - so it is not a patch
by the project's own reading of its surface. Not major: no route is removed,
no required input is added, and ordinary patterns are unaffected. If the
chosen fix turns out to reject a pattern shape a real client sends, that
reclassifies it, which is an argument for measuring runtime traffic before
choosing.

## What an operator would notice

> DRAFT - DO NOT PUBLISH AHEAD OF A DISCLOSURE DECISION. Nightscout's older
> API lets a request search some text fields using a search pattern. There
> is no limit on how complicated that pattern may be, and a complicated one
> can make the database work for minutes on a single request - long enough
> that the site stops answering for everyone using it. On a site that allows
> anonymous reading, which is Nightscout's default, no password or token is
> needed to send one. Your data is not exposed or altered by this; what is
> at risk is the site being there when you look at it. If you watch
> Nightscout to make decisions, this is a reason to have a second way to see
> your readings - which is good practice regardless. Restricting access at
> your proxy or hosting provider is what helps today. Nightscout is not a
> medical device and this is not medical advice; discuss what you rely on
> Nightscout for with your care team.

## Who should review this, and why

SECURITY, and the same person who answered P0-K's sequencing question, because
it is the same advisory. Disclosure-sensitive: a one-request unauthenticated
denial of service against a default install, live on 15.0.8 and on dev, with
no fix yet. The register describes the mechanism only; the reproducing
patterns are deliberately not in any tracked file, and the probe is outside
version control. A public issue or PR carrying the reproduction would publish
a working attack against every unpatched Nightscout. The disclosure
disposition was decided by the maintainer on 2026-09-23 and is held outside
version control; the open decision is the fix shape.

## What was measured

**`node tools/queue/gates/bf72-regex-operand-bounded.js`** &nbsp;·&nbsp; kind: `static`

Asserts that some bound on the $regex operand exists on the v1 read path - a
length cap, a required literal prefix, a complexity rejection or a linear-time
engine - without prescribing which. FAILS today, by design. Its first finding
is the control: $regex must be reachable for the finding to exist, so a future
change that refused the operator outright flips the control rather than
passing silently. Non-vacuity proven both directions on 2026-09-21 against the
scratch ref tmp/bf72-vacuity-probe. The detector is line-scoped and name-
based, because the natural site for a fix is over a thousand characters from
the accept-set literal and a proximity-based detector did not flip under the
same ablation.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The timing measurement is deliberately not in this repository; the static
  gate above is the cheaper half of the evidence, not the finding. Recording
  the timing measurement here would mean recording the patterns, and this
  repository is public while the defect is live on the shipping release (the
  same constraint as BF-70). Held outside version control at
  externals/work/crm-advisory/tmp/bf72-regex-cpu.js with its README.
  Reproduced 2026-09-21 on dev 59430336, 20 000 seeded entries, mongod
  7.0.43: control 22 ms, benign anchored prefix 29 ms, three adversarial
  patterns 60 s / 65 s / 71 s, stable across two runs.
- No fix is gated because no fix has been measured. Four candidates are
  named in the register - pattern length cap, required literal prefix,
  complexity rejection, linear-time engine - and each trades capability for
  cost. Choosing is a decision about the search affordance's contract, not
  an engineering task with a prescribed answer.
- The amplification figure is a floor, not a measurement of a real site. 20
  000 documents is small; a real entries collection is far larger and the
  cost grows with it. Nothing here measures a real deployment, and nothing
  should - rule 0 forbids pointing this at anyone's instance.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-27, after #8861, #8863 and #8870 merged: dev merged into the fork
branch (f64f78c4, already on the fork) as adv/r3gv-1600-dev a9da33ff
(externals/work/crm-ghsa-r3gv-dev), local, a fast-forward of the fork's
bf/regex-limits. First dev 9668b179 (9ab6c705): the seven conflicts resolved
as on the candidate; the merge equals the tested candidate merge plus dev's
later changes. Then dev 7abe1cf6 (#8870, one count path): the fix's read time
limit carried onto the single count path. Node 22.23.4, MongoDB 8.0.34 at
a9da33ff: npm test 4776 passing, 0 failing, 3 pending; test:all 5104 passing,
0 failing, 3 pending; removing the limit from the count path fails the count
test; the gate passes on the branch and fails on official/dev. 2026-10-27,
later: for the 16.0.0 entry bar (maintainer, 2026-10-27), the fix is also
merged onto session -2e's candidate cand/with d6ba8e18 (dev 2dc0c1bc + #8859,
#8861, #8863 and the count commit) as adv/r3gv-1600-cand 87335351
(externals/work/crm-ghsa-r3gv-cand), local only. Seven files conflicted where
the slices move the v1 reads onto the storage interface; the fix's read time
limit now travels through that interface, including the slices' new count
path, which had none. One slice test needed the fix's refusal expected. Node
22.23.4, MongoDB 8.0.34: npm test 4765 passing, 0 failing, 3 pending; test:all
5093 passing, 0 failing, 3 pending; the gate passes on the merge and fails on
cand/with. Removing the limit from either path fails the matching test. -2e
reports the slices re-merged onto dev 94899828 with the same non-CI tree, so
this merge stands; adv/r3gv-1600 stays the push to the fork until the slices
land. 2026-10-27: dev 8dbb60c2 merged into the fork head 532d7d7a as f64f78c4
on adv/r3gv-1600 (externals/work/crm-ghsa-r3gv-1600), eight conflicting files
resolved; a fast-forward of the fork branch, not pushed. Node 22.23.4, MongoDB
5.0.33: npm test 4558 passing, 0 failing, 3 pending; test:all 4886 passing, 0
failing, 3 pending (integration record R17). The gate passes on the branch
(BF72_REF=adv/r3gv-1600). 2026-10-25: rebased onto dev b29f1bf7; head 532d7d7a
on a branch of the advisory's private fork. Decision (maintainer): 16.0.0
only, no 15.0.x backport. Mechanism only in this repository. 2026-10-21, later
still: pushed by the maintainer to the private fork of GHSA-r3gv as bf/regex-
limits 1833ab00. No pull request is open inside the fork yet; opening it is
the next step, and the fix is published with the release that carries it. Not
in the public repository, so pr is empty. The static gate below reads
official/dev and stays red until the fix is merged there. 2026-10-21, later
(maintainer): both decisions made. Fix shape (c), chosen by the rule that
every intended use must keep working (the uses in the maintainer's public gist
dbe590ab "Get one day data out of Nightscout": /times and /slice brace globs,
created_at bounds, /echo/): a 512-character length cap on every pattern and a
5 s time limit on every query whose filter holds a regex, generated ones
included; the refusal heuristic only for caller-written $regex, /x/ and v3 re,
and only with QUERY_REGEX_REFUSE_UNSAFE=true (default off; the name may be
revisited as the release candidate matures). Shape (a) was ruled out: it
refuses patterns the /times and /slice generator builds. Head 1833ab00
(9cbf6615 plus the shape commit), full suite 3646/0/4 against dev 3569/0/4,
semver minor. Route: the private fork of the advisory this item answers
(GHSA-r3gv), pushed now; the original author of the regex-limit commits is
asked to rebuild the tests' hostile inputs in code before anything is
published. 2026-10-21: bf/regex-limits 9cbf6615 = merge of dev 04d435eb into
d359f00b; full suite 3599/0/4; not pushed; semver minor. 15.0.9 is released
and RT-0 is removed from blocks_on; what it waits on now is two maintainer
decisions, not an item. (1) The fix shape: keep the pattern-refusal heuristic,
or a length cap plus the time limit only, or the heuristic behind a flag; the
503 status at the time limit; the 5 s / 30 s defaults. (2) Disclosure: the
branch's tracked tests contain literal costly inputs, so it cannot go to a
public PR as it stands; the private advisory-fork route is recommended, and
the choice is the maintainer's. 2026-10-02 (maintainer): DEFERRED until after
15.0.9; not in RT-0's blocks_on. Branch bf/regex-limits d359f00b (on dev
25fc41d9, not pushed): Ruben Sutton's 5f71598b and 4cfe9132 with his
authorship, then ours 49a48506 (/times and /slice), 3910948b (400 for a
refused pattern, 503 at the time limit, v1 and v3, no driver text) and
d359f00b (/count). Full suite 3562/0/4 against dev 3532/0/4; the new tests
fail on dev's files and on his commits alone. No known client sends $regex or
v3 re; the patterns Nightscout's Reports page and oref0 send pass the check.
Adds safe-regex 2.1.1 (MIT). Time limit checked on MongoDB 4.4.24 and 7.0.43.
Not covered: deletes with a regex filter. PR body draft in the session
scratchpad. 2026-10-02 (maintainer): start the adoption branch for after
15.0.9. bf/regex-limits off dev 25fc41d9 in externals/work/crm-bf72, being
built by a background agent: Ruben Sutton's bddbdfe7 and 0182bb07 picked with
his authorship, then our adjustments as separate commits (time-limit errors
answered without driver text; server-built regexes not refused), after a check
of which clients send regex filters. Not pushed. Covers GHSA-47gq (API v3 re)
as well. 2026-10-02: a candidate fix exists in the private fork of GHSA-r3gv
(branch advisory-fix-1, by Ruben Sutton, code2344: bddbdfe7 2026-09-23 and
0182bb07 2026-10-02, on v15.0.8 92d08342, not on dev): a pattern check through
the safe-regex package (length 512, two nested-quantifier heuristics) on v1
$regex, v1 regex shorthand and v3 re, answered 400, plus maxTimeMS on cursors
whose query has a regex (5 s for caller filters, 30 s for server ones;
settable by environment). It needs a rebase onto dev (query.js changed under
it: operator allowlist, BF-108) and a check of which clients send regex
filters, since the heuristic refuses patterns rather than bounding them.
Adopting his commits keeps his authorship in the history. 2026-10-01: API v3's
re filter operator is the same class (reported privately 2026-09-28); measured
directly on mongod 7.0.43, one count over 20 000 documents of backtracking-
prone text took 49.6 s, 9 ms on short text. Any fix here (for example a
server-side time limit on find queries) should cover both APIs. After 15.0.9.
Open on 15.0.8 and on dev (bf72-regex-operand-bounded.js fails on origin/dev
153e5658, 2026-09-24); no fix branch. The disclosure disposition was decided
by the maintainer on 2026-09-23 and its details are held outside version
control. What remains open is the fix shape: which bound on the $regex operand
(see the no-gates), a decision about the search affordance's contract. Found
2026-09-21 while re-measuring the security advisory's third proof of concept,
which the advisory frames as $regex data extraction. On the shipped `readable`
default that is close to vacuous - entries, treatments and devicestatus are
the three collections prep_storage admits, all three are already readable, and
the API returns whole documents, so a regex oracle reveals nothing a plain
read does not. What the same operator does do is cost the database, which the
advisory does not describe. #8743 (P0-K, merged 2026-09-18) did not narrow
$regex, because the client census found real clients sending it, so this is
not a regression from that branch and is not fixed by it.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-72` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
