# `bf/connect-pin`: move the connector pin to v0.0.14 — a security fix first

*(Deliberately unlettered, matching `docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md`, which
letters the set **A–I** — where **F** is the `nightscout-connect` branch — and leaves this one
unlettered. It is still one of the nine `cgm-remote-monitor` PRs.)*

> **Base: `origin/dev` `a8888f0d`. This is one of NINE INDEPENDENT PRs in `cgm-remote-monitor`.
> There is no stack — no Phase 0 branch is based on another, and this one merges cleanly against
> `origin/dev` and against all eight of the others.** One file, one line. The tenth Phase 0 PR,
> `fix/connect-timer-jitter` (**F**), is in the **`nightscout-connect`** repository and is this
> one's upstream.
>
> **This PR cannot be merged on its own — but the dependency is a tag, not a branch.** It requires
> the `nightscout-connect` tag `v0.0.14` to exist on GitHub first, and it requires a
> `package-lock.json` regeneration **in this same PR, after that tag is pushed**. See "The
> package-lock step" — it is not optional and it is not a detail. That sequencing constraint is the
> only ordering requirement anywhere in the Phase 0 set.

## What changes for you

**This is a security fix. If you have ever turned on Nightscout's logging to work out why your
CGM data stopped arriving, your Dexcom or MiniMed username and password may have been written
into your server's log in readable form.**

Nightscout uses a separate component called *nightscout-connect* to fetch your readings from your
CGM vendor. The version Nightscout currently points at is missing three fixes that keep
credentials and personal data out of the log:

- one that stops **Dexcom** usernames, passwords and session identifiers reaching the log,
- one that stops **MiniMed** credentials and patient data reaching the log,
- one that stops internal data payloads being dumped to the log.

The currently-pinned version does contain a related change — it makes the detailed logging
**opt-in**, so it is off unless you switch it on. That narrows *when* the leak can happen. **It
does not stop it happening when you turn logging on to diagnose a problem — which is exactly the
moment people turn it on.** Someone whose data has stopped arriving turns on logging, reproduces
the failure, and the log now contains their vendor password. They then often paste that log into
a GitHub issue or a Facebook group asking for help.

**So this is the change that actually closes it**, and it is the reason this PR is a security fix
rather than a version bump.

### What to do about logs you already have

If you have turned connector logging on at any point:

- **Treat any Nightscout log you still have as containing your CGM vendor password.** Delete old
  log files, and check anywhere you may have uploaded one — a GitHub issue, a forum or group post,
  a screenshot, a message to someone helping you.
- **If a log containing your credentials was ever shared anywhere public, change your CGM vendor
  account password**, at the vendor's own site. That account is the one that holds your glucose
  history, and for Dexcom Share it is also the one your followers connect through.
- **Do not paste raw logs when asking for help.** Even after this fix, logs can contain
  information you would not choose to publish.

### Three other things come with this version

- **Your CGM data will keep arriving after a vendor outage instead of possibly going dark for
  days.** A defect meant every retry setting the connector was given was thrown away and replaced
  with a 256-millisecond default. That has **two** consequences, and the second is the one that can
  stop your readings:
  - after a failure it retried roughly **586 times faster than intended**, and every site retried
    in exact lockstep; and
  - because the internal ceiling limits the *doubling count* rather than the *wait itself*, once
    enough attempts had failed the wait grew to about **74.6 hours** — **just over three days in
    which a site that had recovered would not try again.** Reproduced against the currently pinned
    connector code. **Both halves ship on `dev` today.** The version this PR moves to caps the wait
    at 30 minutes.

  See `fix-connect-timer-jitter.md`, which explains a counter-intuitive consequence: **a vendor
  outage will now appear to recover more slowly** — minutes instead of a quarter of a second — and
  why that is the fix rather than a regression.
- **A MiniMed data-contract fix**, so glucose values and measurement times keep their expected
  shape.
- **The connector now shuts down cleanly** instead of leaving listeners and waits behind.

---

## Technical detail

One file, one line:

```diff
-"nightscout-connect": "https://github.com/nightscout/nightscout-connect/archive/234d47c85510a77f07b3be0d2c026dd0272715d6.tar.gz",
+"nightscout-connect": "https://github.com/nightscout/nightscout-connect/archive/refs/tags/v0.0.14.tar.gz",
```

`dev` pinned an **untagged commit on an unmerged feature branch**.

> **The pin is not a `v0.0.13` build, and "we ship 0.0.13" should be retired as a description of
> `dev`.** Measured 2026-09-15 in the connector repository: `git describe --tags 234d47c8` =
> **`v0.0.12-28-g234d47c`**, and `git merge-base --is-ancestor` says the tag is **not** an ancestor
> of the pin **and** the pin is not an ancestor of the tag — they diverge. `git rev-list
> --left-right --count v0.0.13...234d47c8` = **1 / 1**: the pin carries one commit the tag lacks
> (`234d47c`, the opt-in debug logging) and lacks one the tag has (`b394411`, a merge commit that
> introduces no content the pin does not already have). The installed package **self-reports
> version `0.0.13`**, which is where the belief comes from. This matters here because the table
> below is a comparison *against* the tag, not a statement that the pin descends from it.

Measured against the `v0.0.13` tag, that pin contains exactly **one** commit — the opt-in debug
logging — and **not** these:

| commit | |
|---|---|
| `9fa2c3c` | Prevent Dexcom credentials and sessions from reaching runtime logs |
| `5349d47` | Keep MiniMed credentials and patient data out of runtime logs |
| `77e2396` | Keep internal output payloads out of runtime logs |
| `8406edf` | Preserve MiniMed glucose and measurement-time status contracts |
| `51b6e6e` | Release connector listeners and settle output waits on stop |
| `c1cce2a` | BF-34 backoff precedence and start jitter |

Verified by `git merge-base --is-ancestor` for all six against `234d47c` — six for six returned
**not an ancestor**.

**Pinning a tag rather than a commit is the other half of this change.** The release-readiness
review objected that `dev` pinned an untagged SHA: reproducible but unreviewable, and it leaves the
release with no connector version to name in its notes. `v0.0.14` is nameable.

### A split worth knowing about

There are **four** connector pins in flight across the trains, not three:

| ref | pin | has the redaction fixes? | has the opt-in narrowing? |
|---|---|---|---|
| `master` (15.0.8) | `v0.0.13` tag | no | no |
| `dev` (15.0.9 candidate) | `234d47c8` | **no** | yes |
| `chore/mime-exposure-review` (cut 4) | `c962a13f` | yes | **no** |
| `chore/nightscout-modernization` (cut 5) | `b77e5bb` | yes | yes |

The two mitigations are **split across the two release trains** and neither has both until cut 5.
Since the adopted train ships 15.0.9 first and holds cut 4 back longest, that gap persists for the
whole train unless this PR lands. `v0.0.14` is the first ref carrying all seven commits. *(Measured
independently; cut 4's pin appears in no other programme document.)*

## The package-lock step

**`package-lock.json` is deliberately NOT updated in this commit, and it must not be updated by
hand.**

The lockfile records an integrity hash computed over the tarball GitHub generates for the tag.
**That tarball does not exist until the tag is pushed**, so the correct hash cannot be known
locally. A hash invented locally would break `npm ci` for **everyone**.

Leaving the lock pointing at the old commit makes `npm ci` fail **loudly** as out-of-sync, which is
the correct failure — better than a lock that looks valid and is not.

**The required sequence:**

1. Push the `v0.0.14` tag in the `nightscout-connect` repository (`fix/connect-timer-jitter` and
   `release/v0.0.14` land first).
2. Run `npm install` in this branch, which fetches the real tarball and writes the real hash.
3. Commit the regenerated `package-lock.json` **into this same PR**.
4. Confirm `npm ci` succeeds before merging.

CI will fail on this PR until step 3 is done. **That failure is expected and is the point.**

## Evidence

- Backfix register: **BF-34** (backoff option precedence) — explicitly the *smaller* half of this
  change. The log-redaction commits are the reason to merge it.
- `docs/30-design/modernization/cgm-remote-monitor-release-readiness-2026-09-14.md` §5 for the pinning objection.
- `docs/60-research/modernization/gt4-semver-classification-2026-09-15.md` for the four-pin measurement.
- Verified 2026-09-15: `release/v0.0.14` is `649a7de`, the annotated tag `v0.0.14` points at it,
  `v0.0.13` (`b394411`, `origin/main`) **fast-forwards** to it — no divergence to reconcile — and
  nothing is pushed. `origin`'s connector tags stop at `v0.0.13`.

## Test evidence

- This branch changes one line of `package.json` and no code, so it has no tests of its own. The
  evidence is the connector's: **135 passing, 0 failing**, with 19 new tests, and every part of the
  fix reverted in turn and confirmed caught.
- Merges clean against `origin/dev` `a8888f0d` — re-run 2026-09-15 18:52, tree `05f051b356`.

> **Note for the reviewer:** this worktree has no `node_modules` and no `my.test.env`, so the
> cgm-remote-monitor suite cannot be run in it as it stands (re-confirmed 2026-09-15). Run it
> wherever the lockfile is regenerated. **There is no `TEST=… npm run test-single` command to quote
> for this branch** — it changes one line of `package.json` and no code, so it has no test of its
> own by construction. The test evidence that matters is the connector's, in
> `fix-connect-timer-jitter.md`.

## Semver

**Minor for `cgm-remote-monitor`, and this branch is not one of the three rows that force Phase 0
to major.** No route changes, no API response changes shape, no environment variable is added or
removed, and no Nightscout default flips. What moves is a **dependency pin**, and the behaviour the
new dependency brings is caller-visible: retry waits go from a quarter of a second to minutes, with
a 30-minute ceiling. An operator who had learned the old recovery timing will see different
timing — which is a release-note matter, not a migration, and nothing they configured stops working.

**The connector's own version number is a separate question, and it is open.** `v0.0.14` arguably
should be `0.1.0`: five caller-visible API changes were measured, three breaking by any reading.
That decision costs nothing to change because `cgm-remote-monitor` pins by **tarball URL**, not by
a semver range, so nothing here floats either way. It is raised, with the list, in
`fix-connect-timer-jitter.md` and must be settled **before the tag is pushed**.

**The operator-visible text above belongs in the release notes.** It is *not* a `CHANGELOG.md`
entry and this branch adds none: under the maintainer's rule, `CHANGELOG.md` is a **release
output** generated by GitHub tooling between releases, and branches never hand-edit it. **The
section that must not be dropped is "What to do about logs you already have."** This is a
credential-exposure fix, and the fix does not retire a password that has already been written into
a log and shared. Only the operator can do that, at their CGM vendor's own site, and the release
note is the only place most of them will ever be told.

---

## Follow-ups deliberately **not** in this PR

- **The lockfile regeneration itself** — step 3 above. In this PR, but not in this commit, and it
  cannot be done until the tag is pushed.
- **`master` is still on `v0.0.13`** and therefore still has none of the redaction fixes. Whether
  15.0.8 operators get a patched connector is a separate release decision, not covered here.
- **Cut 4 pins `c962a13f`** and will need the same move to `v0.0.14` or later, or it ships the
  redaction without the opt-in narrowing.
- **The connector version should arguably be `0.1.0`, not `0.0.14`** — five
  caller-visible API changes (reversed option precedence, a changed default, a new throw). Raised in
  `fix-connect-timer-jitter.md`; it costs nothing to change because cgm-remote-monitor pins by
  tarball URL, not by semver range.
