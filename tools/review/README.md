# `tools/review/` — the dev-cycle review harness

Brings up one real Nightscout per candidate state, seeds each identically through
the real HTTP API, and measures the difference between them.

Plan and per-unit acceptance criteria:
[`docs/30-design/remedial/dev-cycle-review-harness-plan-2026-09-17.md`](../../docs/30-design/remedial/dev-cycle-review-harness-plan-2026-09-17.md).

## Run it

```bash
export NSREVIEW_ROOT=/var/tmp/nsreview        # anywhere with ~2 GB free
tools/review/nsctl.sh init                    # clone + private node_modules, once
tools/review/run.sh                           # boot, seed, probe, red-control
```

Whole cycle measured at **16.7 s** for six states on 2026-09-17. `run.sh` is
idempotent: it resets and re-seeds every state each time.

Individual states:

```bash
tools/review/nsctl.sh add   PAIR rc/2026-09-dev-cycle
tools/review/nsctl.sh reset PAIR production   # stop, DROP db, start
tools/review/nsctl.sh url   PAIR              # open this in a browser
tools/review/nsctl.sh status
tools/review/nsctl.sh stop  --all
```

## Layout

| path | what |
|---|---|
| `nsctl.sh` | instance lifecycle — worktrees, ports, databases, detached boot, run-id namespacing |
| `seed.js` | seeds a complete instance and emits the **expectation manifest** probes assert against |
| `lib/nsprobe.js` | shared probe half: two-instance `compare()`, arm kinds, vacuity detection |
| `probes/` | one module per merge unit. **These are the harness.** |
| `scratch/` | 42 ad-hoc scripts preserved from the reconnaissance session. Evidence of how each defect was first reproduced; **not** part of the harness and not run by `run.sh`. |
| `evidence/` | captured probe output worth keeping |

## Four rules the code enforces, each learned by being bitten

1. **Never drop a database under a live server.** The in-memory cache survives,
   and the instance then serves documents that are no longer stored. BASE once
   answered with 1145 sgv documents from a 582-document database. Use
   `nsctl.sh reset`, which stops first.
2. **Never verify the seed through the endpoint under test.**
   `/api/v1/treatments.json` applies a default time window, so 29 stored
   treatments read back as 26 and look like data loss. Authoritative counts come
   from Mongo; the API counts are kept as a separate diagnostic.
3. **Never assert a build against itself.** On `bf/reads` alone the count
   endpoint returns 5 and the list endpoint returns 5 — they agree and both are
   wrong. Every arm asserts against the seeded expectation in the manifest.
4. **Every arm declares its `kind`.** A `discriminates` arm must be RED on BASE
   or it measured nothing about the branch; an `invariant` arm must be GREEN on
   BASE or its state cannot be attributed to the branch. A probe with no
   discriminating arm refuses to pass.

## Probe contract

Probes reuse `tools/queue/gates/_gate.js` `report()` verbatim — same exit codes,
same output shape — so the existing queue machinery reads them with no new
plumbing. Exit 0 = the property holds, 1 = it does not, 2 = the probe could not
run (which is neither, and must never be read as a pass).

## Data

Everything the harness writes is synthetic and generated in `seed.js`. Every
identifier-shaped value (`device`, `enteredBy`) is a literal defined at the top
of that file. **Nothing is read from `externals/ns-data` or `externals/ns-parquet`**,
which hold real patient data; if replay is added later it must pass through the
allowlist described in the plan's §4.

The API secret is generated at `init` into `$NSREVIEW_ROOT/secret` and is never
committed. `NS_HARNESS_SECRET` overrides it.

## Browser checks: the probes, the manual lab, and where they go next

Nightscout `dev` (15.0.9) has no real-browser tests: its client tests run in jsdom. So the
15.0.9 browser evidence lives here, in two forms:

- **Probes**, `probes/*-browser.js`: each drives the real client in Chrome through
  `playwright-core`, then reads the outcome from MongoDB directly. Each one runs against
  one instance and is compared across builds, usually 15.0.8 and the build under test.
- **The manual lab**, `manual-lab/lab.sh`: it seeds one instance per scenario for a person
  checking by hand. The record of the 15.0.9 run is
  [`manual-lab-15.0.9-rc-2026-09-23.md`](../../docs/60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md).

A hand check is valid for a release only while the browser-side code is unchanged.
`tools/queue/gates/client-unchanged-since-hand-check.js`, one of RT-0's gates, measures
that: it names any browser-side file or package that differs from the hand-checked tree.

### Techniques, each learned in a real run

1. **Give each identity its own browser context.** Pages in one profile share stored
   credentials. In the first `denied` alarm check, one tab's remembered secret
   authenticated a second tab, which then alarmed. The probes open a fresh
   `browser.newContext()` per identity; a person needs a separate profile per page
   (normal, Incognito, Guest).
2. **Give each scenario its own port, and close the previous scenario's pages.** Two
   "failures" in the manual run were windows still open on an earlier instance: a token
   from one instance is not valid on another, and a stale page watches a server that
   never gets the new reading.
3. **Reset between alarm arms.** An alarm is raised on a change of level, so a repeated
   value raises nothing. A silence from a subject with `notifications:*:ack` holds for
   every page on the site until it expires, and clearing it in the lab took a server
   restart. A probe with several alarm arms needs a reset step between them, or an
   order in which no arm depends on an earlier arm's silence.
4. **Raise alarms with values the server treats as glucose.** Values below 40 mg/dL
   are CGM error codes and raise nothing; the replay lab used 45 for an urgent low.
5. **Seed relative to now, per run, and control the clock for time-dependent checks.**
   Seeded data ages from the moment it is seeded; re-run `lab.sh up <name>` for a fresh
   instance. A test fixture with a fixed "now", run against code that reads the real
   clock, passed for 20 hours a day before anyone noticed. For checks that depend on
   elapsed time, such as COB falling back from device status to treatments after 10
   minutes, use Playwright's clock (`page.clock`) on the page, not waiting.
   No probe does this yet.
6. **Decide from the database, not the API.** `/api/v1/treatments` applies a default time
   window, and the server's cache can hide the stored document. For IOB and COB,
   `bf103-split-drag-browser.js` restarts the server before each read, and compares the
   stored result with an oracle: the same records with the derived time fields removed.
7. **Compute the expected value independently of the code under test.**
   `rt-d3-drag-browser.js` derives the expected time from the chart's axis, not from the
   drag handler. Each probe also carries a control in the same run, such as a dismissed
   `confirm()` that must change nothing, so that a green result shows the check can fail.
8. **Treat a page error as a failure.** Record `pageerror` in every probe. BF-90 was
   visible only in the browser console.

The manual run's "Not covered" list is also a list of what the probes should add:
Firefox and WebKit; the split drops in mmol/L and by touch; "Move insulin" by hand; the
10-minute COB fallback (technique 5); and profile editing after a failed profile load.

### Porting into cgm-remote-monitor (after cut 1)

Cut 1 (`chore/retire-jsdom`) replaces jsdom with a real-browser Mocha suite:
`tests/browser/`, pinned `playwright-core` 1.63, Chromium, Firefox and WebKit in CI, a
fresh context per test and a strict origin allow-list (`docs/test-specs/browser-tests.md`
on that branch). That suite is where these probes become permanent regression tests. Adding
a second browser harness to `dev` would only be replaced by it. In the port, a probe's
cross-build comparison becomes an ablation: the test must fail when the fix is reverted.

| probe | what it protects | port |
|---|---|---|
| `rt-d3-drag-browser.js` | a dragged treatment's stored time follows the pixel offset, and the edge clamps hold (BF-54) | first: queue item `RT-D3-SUITE`. Cut 1's `tests/browser/chart-interactions.test.js` already moves a treatment by touch and checks cancel; its "clamps" test is for the context brush. Extend that file with the treatment-drag edge cases and the axis-computed expected time |
| `bf103-split-drag-browser.js` | IOB and COB follow a treatment moved or split by drag, and from the Reports editor (BF-103) | yes |
| `quickpick-rebuild-browser.js` | the Bolus Wizard offers the right quick picks, and the carbs entered belong to the pick chosen (BF-69, BF-35) | yes |
| `food-boluscalc-browser.js` | a quick pick's carbs reach the calculation (BF-35) | fold into the quickpick test |
| `alarm-denied-browser.js` | on `denied`, a legitimate viewer receives alarms and an unauthenticated one does not (#8745) | yes |
| `alarm-no-reading-browser.js` | a device alarm reaching a page with no reading raises no error (BF-90) | yes |
| `parms-browser.js` | a bare URL flag such as `?mute` loads the page (BF-37, BF-39) | yes |
| `subject-edit-keeps-fields-browser.js` | editing a user on the admin page keeps its notes and creation date (BF-47, #8754) | once #8754 is on cut 1 |
| `quickpick-chooser-browser.js` | the two-instance first version of the quickpick check | no: superseded by `quickpick-rebuild-browser.js` |
