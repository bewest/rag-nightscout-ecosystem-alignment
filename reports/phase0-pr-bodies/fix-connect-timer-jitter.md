# F — `fix/connect-timer-jitter` (**nightscout-connect** repository): every retry interval was 256 ms

> **This is in the `nightscout-connect` repository, not `cgm-remote-monitor`.** It is the tenth
> Phase 0 PR: nine are in `cgm-remote-monitor` and are **independent of each other — there is no
> stack** — and this one is their upstream. It is the change that `bf/connect-pin` brings into
> Nightscout. It ships as tag **`v0.0.14`**.
>
> **This PR targets `dev`, and it carries more than its own commit. Read the next paragraph
> before reviewing the diff.** Measured 2026-09-16: `origin/dev` is `6dfc4f0`, its tree is
> **byte-identical to `origin/main`** `b394411` (the `v0.0.13` tag) — `git diff origin/dev
> origin/main` is empty, because `main` is just the merge commit of PR #26 and `dev` has not been
> refreshed since the 0.0.13 release. `git rev-list --count origin/dev..fix/connect-timer-jitter`
> is **11**; the diff is **27 files, +1359/−309**; the trial merge into `dev` is **clean**.
>
> **Only one of those 11 commits is this branch's own work.** The other ten are `b394411` (`main`'s
> merge commit, which `dev` lacks) and nine commits belonging to four other pull requests:
>
> | commits | work | upstream status, measured 2026-09-16 |
> |---|---|---|
> | `9fa2c3c` `5349d47` `77e2396` | Dexcom/MiniMed credential and payload redaction | **PR #64 → `dev`, OPEN** |
> | `8406edf`, merges `c962a13` `a519633` | MiniMed glucose/measurement-time data contract | PR #65 — merged, but **into `fix/dexcom-safe-logging`**, not into `dev` or `main` |
> | `51b6e6e` | release listeners, settle output waits on stop | **PR #66 → `fix/dexcom-safe-logging`, OPEN** |
> | `234d47c` | opt-in embedded debug logging (#8714) | **PR #67 → `dev`, OPEN** |
> | `b77e5bb` | the integration merge of the four above (`origin/fix/modernization-debug-logging`) | no PR |
> | `c1cce2a` | **BF-34 and T0.4 — the only new work here** | this PR |
>
> **So approving this PR approves four PRs' worth of change in one review.** That is a deliberate
> maintainer decision taken 2026-09-16, not an oversight, and it is recorded here rather than left
> for a reviewer to discover from the commit list. A reviewer who wants the redaction, data-contract
> and opt-in-logging work reviewed on its own should say so and this PR should be re-based onto
> `fix/modernization-debug-logging` instead, which reduces it to the single commit `c1cce2a`.
>
> *Two corrections to earlier drafts of this block, kept because both were wrong in the same
> direction — understating what the branch carries.* A first draft said "one commit ahead", reading
> the branch's own new commit as the whole delta. A second said the nine were **"already-merged
> … commits that `origin/main` has not yet taken"**; they are **not merged** — three of the four PRs
> are open, and the fourth merged only into a feature branch. The count against `origin/main` is 10;
> against `dev`, which is what this PR is measured on, it is 11.
>
> The release commit `649a7de` (`release/v0.0.14`, annotated tag `v0.0.14`) sits **directly on
> `c1cce2a`** — `git log --format=%p -1 649a7de` = `c1cce2a` — so **the tag and this fix are the
> same thing**, and `v0.0.13` fast-forwards to it with no divergence to reconcile.
>
> **Note for anyone reading the pin from `cgm-remote-monitor`:** `dev` does **not** pin `v0.0.13`.
> It pins `234d47c8`, which `git describe --tags` calls `v0.0.12-28-g234d47c` and which is neither
> an ancestor nor a descendant of the tag. The installed package self-reports `0.0.13`, which is
> where that belief comes from. Detail in `bf-connect-pin.md`.
>
> **The operator-facing note below is counter-intuitive and must not be softened.** After this
> fix, a CGM vendor outage will look like it takes *longer* to recover.

## What changes for you

**When your CGM vendor's servers have a problem, Nightscout will now wait noticeably longer before
your readings start arriving again. This is the fix, not a side effect. The previous behaviour was
retrying so fast that it could not have worked, and was part of the problem.**

Nightscout fetches your glucose readings from your CGM vendor on a schedule. When a fetch fails —
the vendor is down, your session expired, the network dropped — it waits, then tries again, waiting
longer after each failure. That is normal and intended.

**The waiting was broken.** Every retry setting the connector was given was thrown away and
replaced with an internal default of **256 milliseconds** — roughly a quarter of a second. All five
vendor connections are configured to wait **two and a half minutes**. They were waiting a quarter
of a second instead: about **586 times faster than intended**.

Worse, the deliberate randomness that staggers retries was also switched off, so **every Nightscout
site that failed at the same moment retried at the same instants, in lockstep, forever.** When a
vendor has an outage, every site fails together — and then hammered the vendor together, a quarter
of a second apart.

### Why "slower" is the fix

Retrying four times a second does not make your data come back sooner. The vendor is down; there is
nothing to fetch. What it does do is:

- **make it harder for the vendor to recover**, because thousands of sites are retrying in unison,
- **risk your account being rate-limited or temporarily locked**, which delays *your* data further
  and can look like a login problem,
- **burn battery and data** on whatever is running the connection.

**So after this change: if your readings stop during a vendor outage, expect to wait minutes rather
than seeing constant retrying, and expect recovery to be staggered rather than instant.** That is
the connector being a good citizen so the vendor can come back up, and so your account is not
penalised.

**What has not changed:** normal fetching, while everything is working, is exactly as before. This
only affects what happens *after a failure*. If your data stops for more than a few minutes and the
vendor is *not* having an outage, that is a different problem and worth investigating as you
normally would.

**A practical note:** during an outage the wait between attempts grows, up to a ceiling of **30
minutes**, and is randomised within that. So a site can take up to half an hour to pick up again
after the vendor recovers. If you need to force it sooner, restart Nightscout.

Nightscout is not a medical device and this note is not medical advice. **Do not rely on Nightscout
alone to notice that your data has stopped.** If your readings matter for a decision you are about
to make, check your receiver or pump directly, and talk to your care team about what to do when
remote data is unavailable.

---

## Technical detail

### The defect (BF-34)

`lib/backoff.js` merged its options as `{ ...config, ...defaults }` — **defaults last** — so every
value any caller passed was overwritten by the default. All five vendor sources configure
`interval_ms: 150000`; every one of them got the `256` default. The ratio is **585.94x exactly**
(150000 / 256) at every attempt below the ceiling — not an average or an approximation.

`use_random_slot` was likewise forced to `false`, so a pool of sites that failed together retried in
exact lockstep.

**Measured, with the upstream refusing authentication: 100 actors delivered the same 800 requests
across 3 seconds before the fix, and across 67 seconds after it.**

### Why the precedence fix could not ship alone

`exponent_ceiling` caps the **exponent**, not the delay. Honouring the configured interval by itself
puts attempt 20 at **4.99 years**. So the fix also introduces `max_interval_ms`. `lib/builder.js`
supplies `max_interval_ms = expected_data_interval_ms * 6` = **30 minutes**, which is the shipped
ceiling; with the new `'equal'` jitter default the delay at the ceiling spreads over
**[15 min, 30 min]**.

> **The same defect has a second half, and it is the half that stops a person's data.** Because the
> ceiling caps the exponent, the *discarded* 256 ms interval does not merely make retries too fast —
> at attempt ≥ 20 it yields `256 × (2²⁰ − 1)` = **74.6 hours**. So one option-merge defect produces
> **a retry storm first and a three-day dark window second**, and both ship on `cgm-remote-monitor`'s
> `dev` today. Reproduced in
> `docs/60-research/modernization/e1-dexcom-path-comparison-2026-09-15.md`. **BF-34 as originally recorded
> describes only the 586x-too-fast half**; the register entry should carry both, and in an
> operator-facing note the dark window is the more important one, because a site that is retrying
> too fast is at least still trying.

### Start and interval jitter — and why BF-08 needs no release note

The branch adds `start_jitter_ms` and `interval_jitter_ms` to the cycle machine.

**Both windows default to 0**, so **BF-08 requires no operator-facing note: a self-hosted site sees
no change in start or interval timing.** Confirmed in `lib/machines/cycle.js`:

```js
function jitter_ms (window_ms) {
  return window_ms > 0 ? Math.floor(random( ) * window_ms) : 0;
}
```

`lib/builder.js` passes `config.start_jitter_ms` and `config.interval_jitter_ms` straight through
with no default, so both are `undefined` unless set, and `jitter_ms` returns 0. A site that has not
asked for jitter behaves exactly as it does today. **The hosted vendor pool is the deployment that
sets them.**

### Why the jitter is on the start, not the interval

**All four vendor drivers already spell an 18-second random window into the timestamp they align
to**, so actors do not stay phase-locked across cycles — the interval spreads itself out. The burst
is at start-up, when every actor reaches the vendor at once, which is what `start_jitter_ms`
addresses.

## Evidence

- Backfix register: **BF-34** (option precedence), **BF-08** (interval/start jitter — the interval
  half of that entry was wrong and is recorded as such).
- `docs/60-research/modernization/gt4-semver-classification-2026-09-15.md` for the measured ratio, the ceiling and
  the five API changes.

## Test evidence

- **19 new tests. 135 passing, 0 failing.**
- The tests were checked against unfixed code: **every part of the fix was reverted in turn and the suite caught each one.**
- `backoff({jitter:'wild'})` was executed and confirmed to throw
  `backoff: unknown jitter mode "wild"`.
- Tag `v0.0.14` (`649a7de`) fast-forwards from `v0.0.13` (`b394411`): 29 files, +1362/-312, of which
  **887 lines are new test files**.
- The repository has one workflow, `test.yml`, `permissions: contents: read`, no secrets and no
  registry. There is **no release workflow at all**, so pushing the tag runs the suite and publishes
  nothing. `npm publish` for the connector is entirely manual.

## Semver, and a versioning question for the maintainer

**Classified as a patch-shaped fix carried in a `0.0.z` release, but the honest reading is a
breaking minor.** Nothing here is optional for a caller and nothing is added to the wire, but three
of the five caller-visible changes below are breaking by any reading. On a `0.0.z` version this is
invisible to npm — a caret on `0.0.z` matches that version exactly — and `cgm-remote-monitor` pins
by tarball URL rather than by range, so **no consumer floats onto this either way.** That is why
the number is a judgement call rather than a hazard.

**The operator-visible text above belongs in the release notes.** It is *not* a `CHANGELOG.md`
entry and this branch adds none: under the maintainer's rule, `CHANGELOG.md` is a **release
output** generated by GitHub tooling between releases, and branches never hand-edit it. **The
paragraph that must not be dropped is "Why 'slower' is the fix."** Without it the release note says
only that recovery after an outage got slower, which reads as a regression and will be reported as
one.

**This should arguably be `0.1.0`, not `0.0.14`.** Five caller-visible API changes,
three of which are breaking by any reading:

1. option precedence reversed (`{...config,...defaults}` → `{...defaults,...config}`),
2. the default changed from `use_random_slot: false` to `jitter: 'equal'`,
3. `backoff()` now **throws** on an unknown jitter mode,
4. a new `max_interval_ms` option,
5. `duration_for` became non-deterministic where it was deterministic.

**It costs nothing to renumber**, because cgm-remote-monitor pins by tarball URL rather than by
semver range, and npm's caret on a `0.0.z` version matches that version exactly and would float
nothing either way. The prepared tag is `v0.0.14`; changing it is a local decision taken before
anything is pushed.

---

## Follow-ups deliberately **not** in this PR

- **The version number question above** — `0.1.0` vs `0.0.14`, to settle before the tag is pushed.
- **`bf/connect-pin` in cgm-remote-monitor depends on this tag existing.** That PR also needs its
  `package-lock.json` regenerated with `npm install` *after* the tag is pushed, in the same PR,
  because the integrity hash is computed over a tarball GitHub does not generate until then.
- **`master` (15.0.8) is still pinned to `v0.0.13`** and has none of the log-redaction fixes.
  Whether current operators get a patched connector is a separate release decision.
- **The hosted vendor pool has not set `start_jitter_ms` anywhere yet.** The mechanism ships with
  both windows at 0, so the burst this was built to fix is not yet actually staggered in any
  deployment — that is configuration work, not code.
- **A rejected Dexcom session is not recovered for up to 24 hours, and this branch does not fix
  it.** When the vendor invalidates a session server-side — the ordinary way a Dexcom Share session
  ends — the rejection reaches only the fetch machine as a `FRAME_ERROR`; nothing is sent to the
  session machine, which stays `Active` holding a dead token until `EXPIRE_SESSION_DELAY`, which
  `lib/sources/dexcomshare.js` sets to **24 hours** (read-derived here; the end-to-end behaviour is
  reproduced in `docs/60-research/modernization/e1-dexcom-path-comparison-2026-09-15.md`, where 25 simulated hours
  of permanent 401 give one authentication and one login). **This is the one axis on which the
  connector is worse than the legacy Dexcom bridge it is replacing**, because the legacy bridge
  reuses no session and so recovers on the very next poll. It matters for the parcel 4/5 retirement
  decision, not for this PR, and it is named here so that landing `v0.0.14` is not mistaken for
  closing it. **No BF- id allocated here.**
