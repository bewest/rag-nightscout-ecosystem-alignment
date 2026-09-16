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

# Review packet — P0-I (PR #8736)

**bf/parms - PR #8736, BF-37, BF-38, BF-39**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/parms` |
| base | `origin/dev@a8888f0d` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=P0-I` is the measurement |
| semver | `patch` |
| register entries | `BF-37`, `BF-38`, `BF-39` |

## What this changes

3 commits at eb0bc918. lib/client/browser-utils.js, lib/language.js.

## Why that semver

all three are bug fixes with no declared-surface movement. BF-38 is latent -
no shipped catalogue uses more than %3.

## What an operator would notice

> A web address with a bare option in it - anything ending in "?", or
> containing "&&", or a setting with no value such as "?debug" - stopped the
> page loading entirely, leaving only the loading message. That is fixed.
> Two smaller fixes go with it: a translation containing ten or more
> substitutions came out with a stray digit, and an access token belonging
> to a subject whose name contains an underscore was being corrupted in the
> address bar (the server was accepting it anyway, so nothing was broken for
> you).

## Who should review this, and why

maintainer. OPENED 2026-09-16 as PR #8736, base dev. Worth stating in the
review request: classification is patch with one judgement call (the
underscore decoding, see semver_reason); the BF-37 test is invisible to `npm
run test:unit`, so a green run there is evidence for BF-38 and none for BF-37;
and BF-39 breaks nothing live today - both token spellings return 200 - which
the body says outright rather than implying a break.

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/parms`** &nbsp;·&nbsp; kind: `static`

bf/parms has not fallen behind origin/dev

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/parms >/dev/null`** &nbsp;·&nbsp; kind: `static`

trial-merge into origin/dev is conflict-free

**`TEST=browser-utils.queryparms npm run test-single`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-parms`

BF-37 and BF-39; in NEITHER local brace list (GT1)

**`TEST=language npm run test-single`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-parms`

BF-38. Non-vacuous by GT1's control - 1 failing when the fix is removed from
pristine dev code.

**`git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/parms | grep -q eb0bc918036a7802a0b88`** &nbsp;·&nbsp; kind: `network`

the branch behind PR #8736 is on the remote at the exact tip this item was
measured against. Read-only. Verified 2026-09-16.

**`node tools/queue/gates/pr-body-parity.js --only 8736`** &nbsp;·&nbsp; kind: `network`

the live body of PR #8736 still matches the file it was posted from. Bodies
drift in one direction - a correction gets written into the file first - and
the only previous record that one was owed was a sentence in a notes: field,
which is what let #8738 stay wrong in public for a day. It does NOT measure
whether the body is TRUE: parity with a wrong file is still parity, and every
figure in these bodies has been wrong at least once. NON-VACUITY, reproduced
2026-09-16: one altered file gives 1 failing, an empty body dir gives 6
failing. SKIPS with exit 0 when gh is unauthenticated.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Review and merge state of PR #8736 is upstream's, and cannot be gated from
  here without a GitHub API call. Tracked, not driven.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf-parms.md`](../../reports/phase0-pr-bodies/bf-parms.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

Sequencing letter I. CORRECTION: the sequencing document at line 165 lists the
commits as 522c6ffb, eb0bc918, c9a7a21c mapped to BF-37, BF-39, BF-38. Re-
measured, the branch order is 522c6ffb (BF-37), c9a7a21c (BF-38), eb0bc918
(BF-39). GT3 found the same.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-I` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-15, against cgm-remote-monitor-official `a8888f0d`.*
