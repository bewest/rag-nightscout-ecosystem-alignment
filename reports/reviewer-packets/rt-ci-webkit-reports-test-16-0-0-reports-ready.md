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

# Review packet — RT-CI-WEBKIT-REPORTS (PR #8869)

**WebKit's cached-bundle startup test still fails on dev after bdd569a3: report
requests cancelled 'due to access control checks'**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `test/16.0.0-reports-ready` |
| base | `official/dev@eed31dca` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=RT-CI-WEBKIT-REPORTS` is the measurement |
| semver | `n/a` |

## What this changes

tests/browser/page-startup.test.js only (9a44e16f): the first controlled
navigation waits for the reports page's first report before the next visit,
and the browser-error collector records the page each error came from and
prints it with a failure.

## Why that semver

test reliability and diagnostics

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 9a44e16f test/16.0.0-reports-ready`** &nbsp;·&nbsp; kind: `static`

The wait and the error-page diagnostics are on the branch.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Not reproduced locally before or after the change, in the Playwright
  v1.63.0 image on WebKit, even with the fixture delaying entries 1.5 s and
  a 1 s pause before leaving /report/; Chromium does not report cancelled
  requests as page errors, so a CPU-throttled Chromium run cannot show it
  either. The wait closes the one step that left /report/ unguarded, but
  that this is the cause is not proven: the new "Error pages" line names the
  document on the next CI failure. After the change page-startup is 28
  passing on WebKit, Chromium and Firefox; a forced error on /report/ prints
  Error pages: [".../report/"].

## Evidence

- [`releases/cgm-remote-monitor-16.0.0/contents.md`](../../releases/cgm-remote-monitor-16.0.0/contents.md)

## Notes carried on the item

2026-10-27: pushed by the maintainer and opened as #8869 into dev (head
9a44e16f). 2026-10-27: dev b84871d7's push run 40571593504 failed Browser
tests (26, webkit) "boots every page from cached bundles and retires the old
cache on upgrade" with fifteen report requests "due to access control checks",
the failure bdd569a3 was meant to end; that merge published no image. Prepared
on test/16.0.0-reports-ready off dev eed31dca, not pushed. A first idea, a
page marker for the deferred first report, was measured and dropped: sampling
every 5 ms showed no moment where the old readiness check passed before the
first report started, even at 8x CPU throttling in Chromium.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-CI-WEBKIT-REPORTS` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
