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

# Review packet — ADV-XSS-META

**GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73,
BF-74)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `origin/master@92d08342` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=ADV-XSS-META` is the measurement |
| semver | `n/a` |
| register entries | `BF-73`, `BF-74` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

No code change proposed for the two advisories - the fixes shipped in 15.0.8
(72a2257e, a6835ca3, da548d2a, all contained in tag v15.0.8). What is
outstanding is advisory metadata plus two decisions, BF-73 and BF-74, that
were found beside them and that neither advisory covers.

## Why that semver

No code change is proposed by this item; the fixes already shipped.

## What an operator would notice

> Two reported ways of storing malicious content in your Nightscout were
> fixed in release 15.0.8. If you are on 15.0.8 or later you need do
> nothing, including nothing about entries that were already saved: content
> of this kind stored by an older version does not run on a patched server.
> This was checked by putting an example straight into the database and then
> opening the pages that display it. If you are still on 15.0.7 or earlier,
> upgrading is the fix. Nightscout is not a medical device and this is not
> medical advice.

## Who should review this, and why

MAINTAINER, plus whoever owns the GitHub advisory drafts. Four metadata
corrections, all derived rather than estimated: GHSA-mjp4-84fw-gj4v - affected
<= 15.0.7 confirmed; set patched_versions to 15.0.8, which currently sits
BLANK against a closed vulnerable range, saying "fixed in something" and
"fixed in nothing" at once. Severity high unchanged. Add CVSS 4.0
AV:N/AC:L/AT:N/PR:L/UI:A/VC:H/VI:H/VA:N/SC:N/SI:N/SA:N = 8.4 (its own proposed
vector with UI:P corrected to UI:A) and CVSS 3.1
AV:N/AC:L/PR:L/UI:R/S:C/C:H/I:H/A:N = 8.7. GHSA-5mrq-gpqw-q5v5 - `critical`
overstates it; recommend `high` at the same 8.4. Correcting UI:P to UI:A moves
9.3 to 9.2, still Critical; what produces Critical is SC:H/SI:H, and that is a
double count - the stolen API secret's entire blast radius IS the Nightscout
instance, which is the vulnerable system and is already counted by VC:H/VI:H.
There is no subsequent system. The escalation itself must NOT be softened:
lib/client/hashauth.js stores sha1(API_SECRET) in localStorage and that hash
IS the value the api-secret header accepts, so same-origin script gets admin.
That belongs in VC:H/VI:H. BOTH should state that no stored-data remediation
is needed after upgrading from 15.0.7 - see notes. The current state, one
`critical` with SC:H/SI:H and one `high` with SC:N/SI:N for the identical
credential theft, is the thing most needing correction. Then two decisions
that are contract questions, not bugs. BF-73: express's errorhandler is
mounted with its NODE_ENV === 'development' guard COMMENTED OUT, identically
at v15.0.7, v15.0.8 and dev, and git log -L carries those four lines back to
7947e300 in 2019 - so it was deliberate, and restoring the guard is a decision
about what a production error page owes an operator debugging their own site.
BF-74: API v3 `settings` writes skip the purifier every other v3 collection
gets; purifying UI-configuration values could corrupt them, and no first-party
sink consumes the field, so the right answer may be a comment rather than a
fix.

## What was measured

**`git -C externals/work/crm-adv-shipping tag --contains a6835ca3 | grep -qx v15.0.8`** &nbsp;·&nbsp; kind: `static`

The purification commit is in the 15.0.8 tag. This is the claim the whole item
rests on - that operators on the shipping release are already fixed - so it is
gated rather than asserted.

**`git -C externals/work/crm-adv-shipping grep -q "purifyObject" v15.0.8 -- lib/server/websocket.js`** &nbsp;·&nbsp; kind: `static`

The socket write path calls the purifier at v15.0.8; it does not at v15.0.7.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The render-side and stored-payload results are not gated and cannot
  cheaply be. They needed a real headless Chromium against /report and a
  jsdom+d3 harness loading each ref's own renderer.js, with the payload
  inserted straight into mongo to bypass every write path. Recorded in the
  evidence document with their v15.0.7 positive controls; re-running them is
  a half-day, not a gate.

## Evidence

- [`docs/60-research/remedial/ghsa-xss-pair-verification-2026-09-21.md`](../../docs/60-research/remedial/ghsa-xss-pair-verification-2026-09-21.md)
- [`docs/reports/security-hotfix-eval-2026/report-01-stored-xss.md`](../../docs/reports/security-hotfix-eval-2026/report-01-stored-xss.md)
- [`docs/30-design/remedial/security-advisory-disposition-2026-09-21.md`](../../docs/30-design/remedial/security-advisory-disposition-2026-09-21.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

DECIDED 2026-09-23 (maintainer) - apply all four metadata corrections to the
draft advisories. The advisories stay drafts; applying is a human step
(advisories/apply-metadata.sh --apply). REPRODUCED, and every "fixed" cell is
paired with a positive v15.0.7 control from the same run - four write paths
across three refs, end-to-end over real HTTP and socket, with the document
read back out of mongo, and v3 driven with a real JWT on all three refs. The
fix is broader than either advisory claims: PUT /api/v1/treatments/, POST
/api/v1/food and POST /api/v1/activity also had no purification at 15.0.7 and
now do. The headline, which source-reading could not have answered: a payload
a 15.0.7 server had ALREADY STORED does not fire on a patched server. At
15.0.7 the day-to-day report executed it in a real browser; at 15.0.8 and dev
it renders as visible text. That is true only because the output-escaping half
of the fix (da548d2a) landed alongside the purification half - had only the
purifier shipped, the answer would be the opposite. Both advisories should say
so. Residual sinks: none. 32 `.html(` sites on dev classified; a mechanical
scan for unescaped free-text interpolation found 25 hits across 10 files at
v15.0.7 and zero at v15.0.8 and dev. The internal report's sweep claim names 4
files; the shipped sweep covers 10. Sanitizer bounds: a string over the size
budget is NOT passed through unsanitized - it throws RangeError and the write
is REFUSED on all four paths, fail-closed. The POSSIBLE_HTML_MARKUP pre-filter
is evadable, but none of the three evading forms executes at any sink on any
ref, including v15.0.7 - the defence-in-depth argument the purifier's own
header makes, now measured. BF-73 was filed because the XSS fix created its
trigger: the new RangeError escapes uncaught to the error page. Independently
reproduced against v15.0.8 - the 500 body named six absolute paths and the
deployment's directory layout.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=ADV-XSS-META` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-23, against cgm-remote-monitor-official `ddd9b600`.*
