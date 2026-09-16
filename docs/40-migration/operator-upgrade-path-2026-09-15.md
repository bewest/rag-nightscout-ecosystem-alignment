# Operator upgrade path across the adopted release train

**DRAFT REQUIRING REVIEW.** Written 2026-09-15 against measurements taken the same day. Nothing in
this document has been rehearsed on a live Nightscout site. It must be reviewed by a maintainer,
and the platform-specific steps must be validated on each platform, before any of it is published
to operators. Section 12 lists exactly what a reviewer has to check.

**This is not medical advice.** Nightscout is software you run yourself. It shows diabetes data; it
does not decide therapy. Nothing here tells you anything about insulin, carbohydrates, or how to
treat a high or a low. If your Nightscout site being down for an hour, or your data having a gap in
it, would affect how you or someone in your family manages diabetes, then: **plan the upgrade for a
time when you can sit and watch it**, not overnight and not while travelling; make sure whoever
relies on the site knows it may be down; and if a gap in the record matters clinically — for
example because your care team reads your reports between visits — talk to your care team about the
timing first.

---

## 0. BLOCKING CORRECTION — the adopted train cannot be built as described

**This section was added after the rest of the document was written, on re-measurement. It
contradicts the release plan this document was asked to describe, and it must be resolved by a
maintainer before any of Releases 4 or 5 are published. Sections 3, 6, 7, 10 and 11 carry the
correction inline where it changes an instruction.**

The adopted train says: ship **cuts 3 + 5 combined** as a dependency release, and **hold cut 4
back** behind a deprecation release, because cut 4 is the one that deletes the built-in Dexcom and
MiniMed data collectors.

**That is not possible.** The five cuts are points on a single straight line of development, and
each one contains everything before it. **Cut 4 is an ancestor of cut 5.** Shipping cut 5
necessarily ships cut 4.

*(Measured 2026-09-15: `git merge-base --is-ancestor origin/chore/mime-exposure-review
origin/chore/nightscout-modernization` exits 0 — cut 4 is contained in cut 5. Cut 5 is 154 commits
past cut 4. The same command over each consecutive pair confirms the whole chain is linear, which
reproduces the GT2 pass.)*

The consequence is not theoretical, and it is the one that matters to an operator:

> **The legacy collectors are already gone at cut 5.** `lib/plugins/bridge.js` (Dexcom Share) and
> `lib/plugins/mmconnect.js` (MiniMed CareLink) are **present** on dev and on cuts 1–3, and
> **absent** on cut 4 **and on cut 5**.
>
> *(Measured: `git cat-file -e <ref>:<path>` for both files across `origin/dev`,
> `origin/chore/compose-mongodb6`, `origin/chore/mime-exposure-review` and
> `origin/chore/nightscout-modernization`. Both files exist on dev and cut 3; neither exists on
> cut 4 or cut 5. `lib/server/mmconnect-connect-compat.js` appears at cut 4 and persists into
> cut 5.)*

So a "dependency release" built from cut 5 would **remove both CGM collectors** — the exact change
the train intends to hold back, arriving one release **earlier** than planned and **without** the
deprecation release in front of it. An operator told (as this document originally told them, in
section 3) that the dependency release does not affect data collection could take it and find their
glucose data stops arriving, or — if they use MiniMed without `CONNECT_COUNTRY_CODE` — find their
entire site serving an error page.

**A second, independent symptom of the same problem, visible in this document's own compatibility
matrix:** the nightscout-connect pin would go *backwards* between the two releases. Cut 5 pins
commit `b77e5bb` (**9** commits past v0.0.13, of which 6 are non-merge); cut 4 pins `c962a13f`
(5 commits past, 4 non-merge). `c962a13f` is a strict ancestor of `b77e5bb`, so shipping cut 5 and
then cut 4 would genuinely **downgrade** the connector — not merely change it.
*(Re-measured 2026-09-15 in `externals/nightscout-connect`: `git rev-list --count b394411..<sha>`
gives 9 and 5 respectively (`--no-merges`: 6 and 4), and `git merge-base --is-ancestor c962a13f
b77e5bb` exits 0. An earlier pass recorded "7" for `b77e5bb`; that figure is wrong on either
counting convention and is corrected here.)*

**What a maintainer has to decide.** There are only three shapes available, and this document
cannot choose between them:

1. **Ship cut 5, and accept that the CGM retirement ships with it.** The deprecation release must
   then come *before* the dependency release, not after it, and the dependency release inherits
   cut 4's full risk profile (section 3, Release 5b).
2. **Stop the train at cut 3** for the dependency release, and take cut 5's Express/Helmet/EJS work
   later, after the deprecation release and cut 4. This is the only option that **both** preserves
   the intended ordering **and** stays a prefix cut. (Option 1 is also a prefix cut — cut 5 is the
   stack tip — it just abandons the ordering. Only option 3 is non-prefix. An earlier draft of this
   section claimed option 2 was "the only option that is still a prefix cut"; that was wrong and is
   corrected here.)
3. **Build a non-prefix release** — cut 5 with cut 4's collector deletions reverted. This is real
   surgery on 154 commits, it produces a tree nobody has tested, and it forfeits the
   "parcel-as-prefix" property that makes the whole cut scheme reviewable.

**Option 2 is the only one that delivers what the train was adopted to deliver**, and it is the
assumption this document now makes wherever it had to pick one, because it is the only option under
which the operator instructions in sections 3, 7 and 10 remain true. It is flagged as an inference,
not a decision — the decision is the maintainer's.

**Until this is resolved, the Release 4 and Release 5 instructions below should not be published.**
Releases 0 through 3 — which include the whole Node floor move, the subject of this document's
central question — are unaffected and stand as written.

---

## 1. Who this is for, and the two-minute version

This is for the person who runs a Nightscout site: for themselves, for their child, or for someone
they care for. You do not need to be a programmer to read it. Every technical word is defined the
first time it appears.

**The short version.**

There are five upgrades coming, not one. They are meant to arrive one at a time over several
months. You do not have to take all of them, and you do not have to take them quickly. But they
arrive in a fixed order, and **the second one is the hard one** — it is the one that can leave your
site switched off rather than merely looking different.

| # | Release (working name) | What it is really about | Can it take your site down? |
|---|---|---|---|
| 0 | **15.0.8** | What you are running today | — |
| 1 | **15.0.9** | Bug fixes, quieter logs | No. Low risk. |
| 2 | **Cut 1** (jsdom retirement) | **Raises the minimum Node version.** Drops Node 20. | **Yes. This is the dangerous one.** |
| 3 | **Cut 2** (build/runtime separation) | How the web pages are built and sent to your browser | Unlikely, but it is the largest code change |
| 4 | **Dependency release** (cut 3; see §0) | New MongoDB driver. Possibly also new Express/Helmet — unsettled | Possibly, if your database is very old |
| 5 | **Deprecation notice**, then **Cut 4** | **Deletes the built-in Dexcom and MiniMed data collectors** | **Yes, for anyone using those.** Held back deliberately. |

⚠️ **Row 4 is unsettled.** The plan called this release "cuts 3 + 5 combined", but cut 5 already
contains cut 4's deletion of the CGM collectors, so that combination would move row 5's risk into
row 4. **See section 0.** Rows 0–3 are unaffected.

The single most important sentence in this document:

> **Release 2 raises the minimum Node version to 22.23.2 or 24.20.0, and it arrives before any of
> the improvements that come later. If Nightscout starts on a Node version outside that range, it
> prints one line and shuts itself off. It does not limp along. It stops.**

The second most important sentence:

> **Node 20 stopped receiving security updates on 30 April 2026 — over four months ago. If you are
> on Node 20 today you are already on an unsupported runtime. Release 2 is not what makes that
> true; it is what makes it visible.**

---

## 2. Words this document uses

Read this once; the rest will make sense.

- **Node** (or Node.js) — the program that actually runs Nightscout. Nightscout is written in
  JavaScript, and Node is what reads that JavaScript and does what it says. It has version numbers
  of its own (20, 22, 24) that are completely separate from Nightscout's version numbers (15.0.8,
  15.0.9). *Both* matter, and confusing the two is the most common upgrade mistake.
- **LTS** — "Long Term Support". Node releases an even-numbered version each year and promises to
  keep fixing security problems in it for about three years. Node 20's promise ended 30 April 2026.
  Node 22's ends 30 April 2027. Node 24's ends 30 April 2028. (*Provenance, corrected on review:*
  the Node 22 and Node 24 dates are stated verbatim in cut 1's own `docs/runtime-upgrade.md`
  line 7. **The Node 20 date is not in that file** — it comes from this repository's
  `docs/10-domain/node-lts-upgrade-analysis.md`, which records "Node 20 EOL: 2026-04-30". Neither
  source was checked against nodejs.org, because this session has no network access; a reviewer
  should confirm all three against the [Node release
  schedule](https://github.com/nodejs/Release#release-schedule) before publishing.)
- **npm** — the tool that downloads the other pieces of code Nightscout depends on. It comes with
  Node.
- **MongoDB** — the database where all your glucose readings, treatments and profiles are actually
  stored. Usually hosted by MongoDB Atlas, sometimes run by you.
- **Driver** — the piece of code inside Nightscout that knows how to talk to MongoDB. It has its
  own version number too (currently 5; becoming 7). The driver version and the database version are
  different things, and a driver only works with a range of database versions.
- **CI** — "continuous integration": the automated tests that run every time a developer changes
  the code. "In CI" means "the project tests this combination". "Removed from CI" means "nobody is
  testing this any more" — which is **not** the same as "this no longer works". Section 6 is
  entirely about that distinction.
- **Environment variable** — a setting you give Nightscout from outside the code, such as
  `MONGODB_URI` or `API_SECRET`. On most hosting platforms these are typed into a settings screen.
- **Docker image** — a pre-packaged, ready-to-run copy of Nightscout including its Node. If you run
  Nightscout with Docker you do **not** install Node yourself; the image already contains one.
- **Image tag vs image digest** — `nightscout/cgm-remote-monitor:latest` is a *tag*: a moving
  label that points at whatever was built most recently. A *digest* (a long `sha256:...` string) is
  a permanent pointer to one exact build. **Rolling back reliably requires a digest.** Section 8
  explains how to write yours down.
- **nightscout-connect** — the separate piece of software that fetches your glucose readings from a
  vendor (Dexcom Share, LibreLink, etc.) and puts them into your Nightscout. Nightscout ships with
  a specific version of it built in.

---

## 3. The version-by-version ladder

### A caution about the version numbers themselves

**Measured 2026-09-15:** all five cut branches *and* the 15.0.9 branch currently declare
`"version": "15.0.9"` in `package.json`. Two very different builds — one that runs on Node 20 and
one that refuses to — both call themselves 15.0.9 right now.

*(How measured: `git show <ref>:package.json` parsed as JSON, for `origin/dev`,
`origin/chore/retire-jsdom`, `origin/chore/build-runtime-separation`,
`origin/chore/compose-mongodb6`, `origin/chore/mime-exposure-review`,
`origin/chore/nightscout-modernization`. Independently found by the GT4 pass.)*

This is a defect and it is filed in section 12. **Until it is fixed, "what version am I on?" is not
a question an operator can answer from the version number, and no support volunteer can triage from
it either.** Throughout this document I therefore call the releases "Release 1" through "Release 5"
and name the branch, rather than pretending version numbers exist. A reviewer must assign real
numbers before any of this is published.

---

### Release 0 — where you are now: 15.0.8

**What you are running.** Nightscout 15.0.8. It declares it wants Node 20 or newer
(`engines.node: ">=20.x"`), but the check that actually runs at startup only insists on Node 16 or
newer.

*(Measured: `git show origin/master:package.json`; `git show origin/dev:lib/server/bootevent.js`
function `checkNodeVersion`, which calls `semver.satisfies(nodeVersion, '>=16.x')` and only exits
below that. So the **declared** floor and the **enforced** floor are different today. Confirmed
independently by the GT4 pass.)*

**Why that matters.** It means that today Nightscout will happily start on Node 16, 18 or 20 even
though the manifest says 20+. A lot of long-running sites are on Node 16 or 18 and nobody has ever
told them. Those sites will hit Release 2 hardest.

**Your database.** 15.0.8 uses MongoDB driver 5.9.2, which will connect to any MongoDB from 3.6
upwards.

*(Measured by reading the installed driver's own constants:
`externals/cgm-remote-monitor-official/node_modules/mongodb/lib/cmap/wire_protocol/constants.js`
gives `MIN_SUPPORTED_SERVER_VERSION = "3.6"`.)*

**Your connector.** 15.0.8 pins nightscout-connect to the `v0.0.13` release.

*(Measured: `git show origin/master:package.json`. Note this corrects a statement in
`docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md:388` and in the programme preamble, both of
which say master pins `"^0.0.12"`. It does not; it pins the v0.0.13 tarball. First found by the GT4
pass; re-confirmed here.)*

---

### Release 1 — 15.0.9 (the bug-fix release)

**What changes for you**

- A set of bug fixes: unnamed profiles, embedded profile-switch schedules, a "low and falling"
  warning on the clock view, and some treatment queries that could fail.
  *(Measured: `git log --oneline --no-merges 9205ea30..origin/dev` returns **46** commits,
  including `e46fdd2a`, `8f86cee0`, `06372e1d`, `02161b93`; 40 of the other 42 are translation
  updates, and the remaining two are the quiet-logging change `c2ac743c` and a docs tidy-up. The
  full range `9205ea30..origin/dev` is 59 commits counting merges. An earlier draft said "the
  other 55 commits" while citing the `--no-merges` command; the two numbers come from different
  counting conventions and the pairing was wrong.)*
- **Your server logs go quiet.** Routine diagnostic logging is now off unless you switch it on.
  Warnings and errors still appear. Two new settings appear: `DEBUG_LOGGING` and `CONNECT_DEBUG`,
  both defaulting to off.
  *(Measured: `git diff origin/master origin/dev -- lib/server/env.js` shows
  `logging: readENVTruthy('DEBUG_LOGGING', false)` added, and a `CONNECT_DEBUG` override block.)*
- The charts use a newer drawing library (D3 version 7 instead of 5). You should not see a
  difference. See the honest caveat below.

**What you MUST do before upgrading**

- Take a database backup (section 9).
- Nothing else. Your Node version, your database and your settings all stay as they are.

**What you MUST do during/after**

- Nothing mandatory. If you were relying on the chatty log output to diagnose something, set
  `DEBUG_LOGGING=true` to get it back.

**⚠️ A safety caveat you should not skip.** Turning `DEBUG_LOGGING` on is exactly what an operator
does when something is broken — and the version of nightscout-connect bundled with 15.0.9 does
**not** yet contain three fixes that stop vendor account credentials and patient data from being
written into those logs. So the moment you switch debug logging on to diagnose a problem is the
moment credentials can land in your log files.

*(Measured in `externals/nightscout-connect`: `git merge-base --is-ancestor` shows commits
`9fa2c3c` "Prevent Dexcom credentials and sessions from reaching runtime logs", `5349d47` "Keep
MiniMed credentials and patient data out of runtime logs" and `77e2396` "Keep internal output
payloads out of runtime logs" are each **not** ancestors of the commit `234d47c8` that 15.0.9 pins.
Six for six on the wider commit set. Independently established by GT3 and GT4.)*

**Practical advice:** turn `DEBUG_LOGGING` on only while you are actively looking at a problem,
turn it off again afterwards, and do not paste raw logs into a public Facebook group or Discord
channel. If you need to share a log, ask for help privately first. A maintainer should consider
whether Release 1 ought to carry the connector update (`bf/connect-pin`, which moves the pin to
v0.0.14 and contains all of these fixes) rather than shipping without it.

**How long it takes.** *(Estimate, not measured.)* Docker: 5–15 minutes. Source install: 10–30
minutes for `git pull` plus `npm ci`. Heroku/Azure: one deploy cycle.

**How to check it worked.** Load your site. Check that a glucose reading has arrived in the last
10 minutes. Open the reports page and pull up a day you know has data. Confirm your care-portal
treatments still appear.

**How to undo it.** Straightforward — deploy the previous image digest or `git checkout` the
previous commit and re-run `npm ci`. No database change is made, so nothing needs restoring.

---

### Release 2 — Cut 1, `chore/retire-jsdom` — **THE NODE FLOOR MOVE**

This is the one to take seriously. It has its own full section (section 5). Here is the ladder
entry.

**What changes for you**

- **The minimum Node version becomes `^22.23.2 || ^24.20.0`.** Read that as: "Node 22, but at least
  22.23.2 — or Node 24, but at least 24.20.0. Nothing else."
- Nightscout now **exits immediately** if Node is outside that range, before it loads any of your
  settings or touches your database.
  *(Measured: `lib/server/runtime-policy.js` on cut 1 is twelve lines, nine of them code — it reads
  `engines.node` from `package.json`, and on mismatch prints an error and calls `process.exit(1)`.
  It is invoked from both `lib/server/server.js:26` and `lib/server/bootevent.js:31`.)*
- MongoDB 4.4 is removed from the project's automated testing. **Your 4.4 database will still
  work.** See section 6 for exactly what that means.
- The developer testing tools change (jsdom out, Playwright in). This has **no operator-visible
  effect** and you can ignore it — but it is the reason this release exists and the reason it is
  named after a test library.

**What you MUST do BEFORE upgrading**

1. **Find out what Node version you are on.** Section 5.1 tells you how, per platform.
2. **If you are not on 22.23.2+ or 24.20.0+, move Node first, as a separate step, and confirm your
   current Nightscout still works on it.** Do not move Node and Nightscout in the same change. If
   you do both at once and the site fails, you will not know which one broke it.
3. Take a database backup (section 9).
4. Write down your current image digest or commit (section 8).

**What you MUST do during**

- Source installs: delete `node_modules` and run a fresh `npm ci`. Do **not** reuse the folder that
  was installed under the old Node — some dependencies are compiled against a specific Node version
  and silently misbehave otherwise. The project's own upgrade note says the same thing.

**How long it takes.** *(Estimate.)* If your Node is already new enough: same as Release 1. If you
have to move Node: budget **60–90 minutes and do it on a day off**, most of which is waiting and
double-checking rather than typing.

**How to check it worked.** After starting, the very first thing to check is that it started at
all. Then the same checks as Release 1.

**How to undo it.** Yes, rollback works — but read section 7.2, because *how* you roll back depends
on your platform and the widely-quoted phrase "trivially revertible" is only true for one kind of
operator.

**⚠️ Hazards for whoever prepares this release (not for you).** This branch has not been brought up
to date with 15.0.9 — it is 59 commits behind `dev` — and merging the two produces **four**
conflicts, not one. *(Measured: `git merge-tree --write-tree --name-only origin/dev
origin/chore/retire-jsdom` reports `lib/server/bootevent.js`, `package.json`, `package-lock.json`
and a modify/delete on `tests/clock-client.test.js`. No merge was performed; `merge-tree` computes
the result without touching any ref.)* Two of them can go wrong silently:

- **`package.json`** — the conflict hunk is exactly the nightscout-connect pin plus a test
  dependency. Taking the branch's side wholesale would roll the connector *backwards* from
  15.0.9's commit `234d47c8` to the v0.0.13 tag.
- **`tests/clock-client.test.js`** — `dev` adds 56 lines to this file in commit `06372e1d`
  ("show concern for low and falling clock readings"), and cut 1 **deletes the file** as part of
  jsdom retirement. Resolving the modify/delete the obvious way — accept the deletion — keeps the
  production fix and throws away its only test. Cut 1's Playwright replacement
  (`tests/browser/clock-client.test.js`) contains **zero** references to "concern" or "falling",
  against 3 in `dev`'s file. *(Measured with `grep -ciE 'concern|falling'` on both files, using
  `dev`'s file as the positive control.)* That test covers the warning face on the clock view —
  the screen people glance at — so losing it silently is the more consequential of the two.

See section 12; both are release-engineering items, not something an operator can act on.

---

### Release 3 — Cut 2, `chore/build-runtime-separation`

**What changes for you**

- How the JavaScript that runs *in your browser* is packaged and delivered. Separate bundles per
  page, a narrower set of chart code, a reworked event system and startup sequence.
- This is **the largest code change of the five**: 60 production files, +923/−465 lines.
  *(Measured: `git diff --numstat origin/chore/retire-jsdom origin/chore/build-runtime-separation`
  filtered to `lib/`, `views/`, `bin/`, `webpack/`, `static/`, `server.js`, `app.js`. Reproduces
  the release-readiness §5 figure exactly.)*
- **No change to the Node floor** (it stays exactly `^22.23.2 || ^24.20.0` — measured identical on
  all five cuts), no change to the database, no change to your settings.

**What you MUST do before**

- Backup (section 9). If you are on Release 2 already, nothing else.

**What you MUST do during/after**

- **Hard-refresh your browser** (Ctrl+Shift+R, or Cmd+Shift+R on a Mac) on every device that uses
  the site, including phones. Because this release changes how pages are bundled and includes a
  substantially rewritten service worker (`views/service-worker.js`, 196 lines changed), a stale
  cached copy in your browser is the most likely thing to go wrong. If the site looks broken or
  half-loaded, hard-refresh before you panic.
- If you use Nightscout as a phone home-screen app, you may need to close and reopen it.

**How long it takes.** *(Estimate.)* Same as Release 1, plus a few minutes per device for the
refresh.

**How to check it worked.** Load the main chart on a computer *and* on a phone. Check the reports
page and the profile editor, since those are separate page bundles now and a packaging mistake
would show up on one page and not another.

**How to undo it.** Yes, cleanly. Roll back the image or commit and hard-refresh again.

---

### Release 4 — the dependency release

> ⚠️ **READ SECTION 0 FIRST. The contents of this release are not settled.**
>
> The plan called this "cuts 3 + 5 combined": `chore/compose-mongodb6` (MongoDB driver 7, jQuery
> UI) plus `chore/nightscout-modernization` (Express 5, Helmet 8, EJS 6, Axios 1, Swagger). But
> cut 5 already contains cut 4, and cut 4 **deletes the built-in Dexcom and MiniMed collectors**
> (measured; section 0). So a release built from cut 5 would also do everything described under
> Release 5b below, including the three ways it can take a whole site down.
>
> **The rest of this section describes the cut 3 half only** — the MongoDB driver change — because
> that is the half that is settled, and because it is the half with the database implications an
> operator has to prepare for. **If the maintainer decides to ship cut 5 here after all, then
> everything in Release 5b applies to this release too, and the deprecation release must come
> before it, not after.**

**What changes for you**

- **The MongoDB driver goes from 5 to 7.** This is the change that could affect your database. Full
  detail in section 6. The headline: *the oldest MongoDB the driver will talk to rises from 3.6 to
  4.4.*
  *(Measured directly from the two installed drivers' own constants. Driver 5.9.2:
  `MIN_SUPPORTED_SERVER_VERSION = "3.6"`, `MIN_SUPPORTED_WIRE_VERSION = 6`. Driver 7.6.0 (installed
  at `externals/work/crm-seam/node_modules/mongodb`): `MIN_SUPPORTED_SERVER_VERSION = "4.4"`,
  `MIN_SUPPORTED_WIRE_VERSION = 9`. **One caveat on that provenance:** cut 3 declares `^7.6.0`, a
  range, and the 7.6.0 read here was installed in a different worktree. A future 7.x that raised
  its own minimum would change this answer, so a reviewer should re-read the constant from the
  install the release actually produces, not from this one.)*
- The bundled `docker-compose.yml` changes its default MongoDB from 5.0.32 to 6.0.27. **This only
  affects you if you use that file to run your own database**, and see the warning in section 6.4 —
  it is not safe to simply let it upgrade.
- **If cut 5 is included (unsettled — section 0):** Express (the web-server library) goes from 4 to
  5, and Helmet (the security-headers library) from 4 to 8. These are large internal changes with
  no intended visible effect. **And the built-in Dexcom and MiniMed collectors are deleted** —
  read Release 5b in full before taking this release.

**What you MUST do before**

- **Find out what MongoDB version you are on** (section 6.2) — before this release, not after.
- Backup, and this time **verify the backup restores** (section 9.3). This is the release where a
  database problem is most plausible.
- If you are on MongoDB 4.2 or older, you must upgrade your database **first**, as a separate
  project, on its own timeline. Do not attempt it in the same change window.

**What you MUST do after**

- Check anything that talks to your Nightscout over its API: uploaders, Loop/Trio/AAPS, watch
  faces, follower apps. Express 5 and Helmet 8 both change HTTP behaviour at the edges, and the
  project has **no measured evidence** about third-party clients. That gap is section 12's largest
  open question.

**How long it takes.** *(Estimate.)* The Nightscout upgrade itself: like Release 1. A MongoDB
version upgrade, if you need one: a separate multi-hour exercise with its own rehearsal.

**How to check it worked.** Load the site; confirm new readings arrive from your uploader within
one CGM cycle (5 minutes); post a test treatment from the care portal and confirm it appears; open
reports over a multi-week range to exercise larger queries.

**How to undo it.** The Nightscout part, yes. **If you upgraded your MongoDB, that part is a one-way
door** — section 7.4.

---

### Release 5a — the deprecation release (Dexcom/MiniMed notice)

Deliberately inserted before cut 4. Its purpose is to warn people, not to change anything.

**What changes for you.** Warnings in your logs and release notes telling you that the built-in
Dexcom Share collector (`BRIDGE_*` settings) and the built-in MiniMed CareLink collector
(`MMCONNECT_*` settings) are going away, and what to switch to.

**What you MUST do.** Read the warning and find out whether it applies to you. If you have
`BRIDGE_` or `MMCONNECT_` settings configured, it applies to you.

**A measured gap this release has to close.** A migration path for **Dexcom** already exists in the
shipping code today — `lib/server/bridge-connect-compat.js` is present on both master and dev and
automatically translates `BRIDGE_*` settings to the new `CONNECT_*` ones, and the boot process
prints deprecation warnings naming `DEXCOM_BRIDGE_USE_LEGACY`. A migration path for **MiniMed does
not exist today at all**: `lib/server/mmconnect-connect-compat.js` is created in cut 4 itself, the
same change that deletes the old collector. So the deprecation release has **real code to write for
MiniMed**, not just a warning string to add.

*(Established by the GT4 pass; the file-existence half re-confirmed here.)*

---

### Release 5b — Cut 4, `chore/mime-exposure-review` — **HELD BACK**

> ⚠️ **"Held back" is the intent, not yet a fact.** Everything in this section is contained in
> cut 5, so if cut 5 ships as part of Release 4, all of this arrives *there* instead — earlier, and
> without the deprecation release in front of it. See section 0. The description below is accurate
> about what cut 4 does; only *when* it reaches operators is unsettled.

**This release deletes the built-in Dexcom Share and MiniMed CareLink data collectors.** It is
deliberately held back behind the deprecation release, and it is the release where "my site is
down" and "my glucose data stopped arriving" become likely rather than theoretical.

**What changes for you**

- The old `BRIDGE_*` (Dexcom) and `MMCONNECT_*` (MiniMed) collectors are removed. Data collection
  moves to nightscout-connect.
- Also in this release: trusted-proxy handling, DOMPurify, Moment/timezone changes.
- 66 production files, +324/−511. *(Measured, same method as above.)*

**⚠️ The three ways this release can take your whole site down**

These were established by the GT4 pass by *executing* cut 4's migration shim under several
environment shapes, and reading the boot path. They are not speculation:

1. **You use MiniMed (`MMCONNECT_*`) and have no `CONNECT_COUNTRY_CODE` set.** The migration
   refuses, which produces a boot error, and a boot error makes Nightscout serve an error page for
   *every* address — no charts, no API, no websockets. **The entire site goes down, not just
   MiniMed data collection.** The shim cannot guess your country from your existing settings, so
   *no* MiniMed operator can upgrade without manually adding a setting first.
2. **You use Dexcom and MiniMed at the same time.** This works today as two independent collectors.
   After cut 4 there is one collector setting and the second source has nowhere to go — same total
   outage. **The ability to collect from two CGM sources at once is removed**, and that removal
   appears in no summary of the cut.
3. **You set `DEXCOM_BRIDGE_USE_LEGACY=true`** to opt out. After cut 4 that setting is accepted and
   silently ignored. Your data keeps flowing (Dexcom credentials are still migrated), but your
   stated intention is discarded without telling you.

**What you MUST do before.** Check whether you have any `BRIDGE_` or `MMCONNECT_` setting. If you
have `MMCONNECT_`, add `CONNECT_COUNTRY_CODE` and verify the new collector works **on the previous
release** before taking this one. If you use two sources, stop and ask for help — there is no
documented path for you yet.

**How to undo it.** Roll the application back. But note that a rollback here also rolls back
whatever settings changes you made, so keep a written copy.

---

## 4. Testing the reasoning behind putting the Node move first

The brief for this document recorded the project's reasoning for landing cut 1 first, and asked me
to test it rather than repeat it. Here is the test. Two of the three claims survive; one is stated
on the wrong basis and one is true only for some operators.

**Claim 1: "An operator would rather do the runtime move once, early, than bundled with a feature
retirement."**

**Holds, and I can now show it is genuinely once.** All five cut branches declare *byte-identical*
`engines` — `{"node": "^22.23.2 || ^24.20.0", "npm": ">=10.x"}`. So the floor moves at cut 1 and
never moves again anywhere in the remaining stack. An operator who does the Node move at Release 2
is done with Node for the rest of the train.

*(Measured: `git show <ref>:package.json | python3 -c "...print(json.load(sys.stdin)['engines'])"`
across all five cut tips. This is a stronger statement than the reasoning claimed, and it is the
best argument for the ordering.)*

**Claim 2: "Cut 1 is the smallest production change in the stack (21 files, +91/−123)."**

**The conclusion holds; the number is measured on the wrong basis and should not be published.**
The published figure, 21 files +91/−123, is cut 1 compared against *today's dev*, which also counts
undoing dev's own 59 commits. Cut 1's true incremental production change is **11 files, +68/−54**.
Both figures reproduce exactly on this machine. Against the other cuts measured the same way
(11 / 60 / 23 / 66 / 36 files), cut 1 is indeed the smallest — by more than the published number
suggests. So publishing the corrected number makes the argument better, not worse.

*(Measured: incremental diffs from merge-base `9205ea30` and then cut-to-cut, bucketed to
production paths. Independently found by the GT2 pass; reproduced here to the digit.)*

**Claim 3: "Trivially revertible — the engines field plus a boot check."**

**True mechanically, and true for exactly one kind of operator.** `runtime-policy.js` derives its
range from `package.json`'s `engines.node`, so there genuinely is only one field to change and no
second hard-coded copy. But:

- **Editing that field is a code edit.** An operator running the published Docker image has no
  `package.json` to edit. Their rollback is real and easy, but it is "redeploy the previous image
  digest", not "revert one field" — a different action requiring different preparation (section 8).
- **Reverting the field restores the permission without the assurance.** The same branch removes
  Node 20 from the test matrix, so a reverted floor permits a Node version that nothing tests.
- **Other files state the required or recommended Node version independently**, and a one-field
  revert leaves them stale and contradicting each other. *(Enumeration re-measured on review; an
  earlier draft cited a single grep that does not in fact produce the list it was attached to, and
  included `Dockerfile`, which states no floor at all — `node:22-alpine` is consistent with either
  `>=20.x` or `^22.23.2`.)* Measured on `origin/chore/retire-jsdom`:
  - **State the floor as a version range** — `package.json` `engines.node` (the one authoritative
    field), `README.md:156` ("Node 22.23.2+ or 24.20.0+"), `docs/runtime-upgrade.md`,
    `docs/meta/architecture-overview.md`, `docs/plans/nightscout-modernization.md`, the seven files
    under `docs/test-specs/`, `tests/runtime-policy.test.js` and `tests/dependency-babel.test.js`.
    *(`git grep -lniE '22\.23\.2|24\.20\.0' origin/chore/retire-jsdom` — 16 paths, of which
    `package-lock.json` and `.github/workflows/main.yml` are the other two.)*
  - **State a recommended version instead, and so do not match that grep at all** — `.nvmrc`
    (`22` → `24`) and `bin/setup.sh` (NodeSource `setup_20.x` → `setup_24.x`, line 3), plus
    `azuredeploy.json` (parameter default `16.16.0` → `~24`, which §12.1 item 1 shows is dead code).
    *(Read directly with `git show <ref>:<path>`.)*
  - `CONTRIBUTING.md` does **not** state a Node version on cut 1; an earlier measurement pass
    (GT2) listed it, and that is wrong on this ref.

**A claim nobody made, that I think is the strongest argument of all:** Node 20 reached end of life
on 30 April 2026. Today is 15 September 2026. An operator on Node 20 has been running without
security updates for four and a half months already. Framing Release 2 as "Nightscout is taking
something away from you" is both unkind and inaccurate; it is Nightscout noticing something that
was already true. **I would lead the operator-facing release note with that**, because it converts
the message from a demand into a warning the operator will be glad of.

*(Provenance, corrected on review: the Node 20 EOL date comes from **one** place in the repo,
`docs/10-domain/node-lts-upgrade-analysis.md`, which flags "Node 20 EOL: **2026-04-30**" at lines
18, 44 and 211. An earlier draft said it was in cut 1's `docs/runtime-upgrade.md` as well; measured,
**it is not** — that file gives only the Node 22 (2027-04-30) and Node 24 (2028-04-30) dates and
says "Node 20 is retired" without a date. The claim rests on a single in-repo source and has not
been checked against nodejs.org from this session. **A reviewer must confirm the date upstream
before it is published to operators**, because this document leans on it as the main argument for
taking Release 2.)*

**The one thing about the ordering I would push back on.** Cut 1 is *not* a pure runtime change as
currently constituted. Because it has never been updated against 15.0.9, it carries an older
nightscout-connect pin, and the merge that brings it up to date has a conflict in exactly that
line. That is fixable in five minutes by whoever prepares the release — but it must be *noticed*,
and "cut 1 is trivially small and low-risk" is precisely the framing that makes people not look.
Section 12 files it.

---

## 5. The Node floor move, in detail

This is the step that can leave your site **off** rather than **odd**. Read the whole section
before you start.

### 5.1 Find out what Node version you are on

Do this **now**, before any release ships. It takes two minutes and it determines how much work
Release 2 is for you.

| If you run Nightscout on… | Do this |
|---|---|
| **Your own Linux server / Raspberry Pi / VPS** (you ran `git clone` and `npm install`) | Open a terminal on that machine and type `node --version`. It prints something like `v20.11.1`. |
| **Docker or docker-compose** | Run `docker run --rm <the image tag you actually run> node --version` — for example `nightscout/cgm-remote-monitor:latest`, but use **your** tag, because `:latest` may not be what you deployed. This asks the image itself, which is the number that matters — not the Node on your host machine. |
| **Heroku** | In the Heroku dashboard open your app → "More" → "Run console", type `node --version`. |
| **Azure App Service** | In the Azure portal, your app → "Development Tools" → "SSH" or "Advanced Tools (Kudu)" → Debug console, then `node --version`. |
| **Railway / Render / Fly.io / Northflank / another platform-as-a-service** | Use that platform's shell/console feature and run `node --version`. If there is no shell, look for a "Node version" or "runtime" setting in the build configuration. |
| **You genuinely do not know** | Look at your Nightscout's startup log. On 15.0.8 the boot prints a line about the Node version being supported. |

**Write the answer down.** You will want it if you need to roll back.

### 5.2 What "22.23.2 or 24.20.0" actually means

This is not a simple "Node 22 and up" floor and it will surprise people. The accepted range is
`^22.23.2 || ^24.20.0`, and cut 1 ships a test that spells out exactly what is rejected:

**Accepted:** v22.23.2, v22.24.0, v24.20.0, v24.21.0 — and anything later within the 22 and 24
lines.

**Rejected:** v16.20.2, v20.20.0, **v22.0.0**, **v22.23.1**, v23.0.0, **v24.19.0**, v24.20.0-rc.1,
**v25.0.0**, **v26.8.1**.

*(These are not my examples. They are the literal version strings in
`tests/runtime-policy.test.js` on cut 1, asserted to exit with status 1 through both entry points.)*

Three consequences that will generate support questions:

1. **"I'm on Node 22 and it still won't start."** Very likely true and correct. Node 22.20 is
   Node 22 and is still rejected. **The major number is not enough — check the full version.**
2. **Odd-numbered Node versions are rejected**, so Node 23 and Node 25 will not run Nightscout even
   though they are newer.
3. **Future Node versions are rejected too.** Node 26, when it arrives, will not start Nightscout
   until somebody edits `package.json`. This is a deliberate whitelist, not a floor.
   *(Partly answered on review: cut 1's own `docs/runtime-upgrade.md` line 3 says "Earlier patches,
   odd-numbered releases, prereleases, and **Node 26 Current** are not supported", and line 5 adds
   that "these minimum patches reflect the supported release baseline at the time of this change".
   So the exclusion is deliberate for Node 26 in its pre-LTS "Current" phase. What the project has
   **not** written down is what happens when Node 26 becomes LTS — there is no documented process
   for widening the range, and no scheduled owner for doing it.)* A reviewer should record that
   process, because otherwise Nightscout will refuse to start after a *future* Node upgrade that an
   operator has every reason to think is safe, and it will look like a Nightscout bug.

### 5.3 How to move Node, per platform

**General rule that applies everywhere: move Node first as its own change, confirm your existing
Nightscout still runs on it, and only then upgrade Nightscout.** Your current 15.0.8 runs fine on
Node 22 and 24 — its enforced floor is "16 or newer" with no upper limit — so this two-step
sequence is safe and it is what makes the failure diagnosable.

**Linux server / Raspberry Pi / VPS, using nvm (recommended)**

`nvm` ("Node Version Manager") lets you have several Node versions installed and switch between
them, which makes rollback trivial.

```
nvm install 24
nvm use 24
node --version          # must print v24.20.0 or higher
```

Then, in your Nightscout folder:

```
rm -rf node_modules
npm ci
```

**Do not skip the `rm -rf node_modules`.** Reusing a `node_modules` folder built under a different
Node version is a classic source of strange, hard-to-diagnose failures.

To roll back: `nvm use 20` (or whatever you noted down), then `rm -rf node_modules && npm ci`
again.

**Linux server, using the system package manager**

Cut 1 updates `bin/setup.sh` to install from NodeSource's `setup_24.x` instead of `setup_20.x`.
*(Measured: `git show origin/chore/retire-jsdom:bin/setup.sh` line 3.)* This is a system-wide
change and is **harder to undo than nvm**. If you have the choice, use nvm.

**Docker (the published image)**

You most likely do not have to do anything. The image builds on `node:22-alpine` and ships its own
Node, so upgrading the image upgrades Node with it.

*(Measured: `git show origin/chore/retire-jsdom:Dockerfile` — `FROM node:22-alpine` for both the
builder and runtime stages. Unchanged from dev and from every other cut.)*

**But verify it, with one command, before you trust it:**

```
docker run --rm <the-new-image> node --version
```

If that prints anything below v22.23.2, **do not deploy it** — report it instead, because it means
the published image cannot start.

*(Correction made on review: an earlier draft of this document said nothing in the build checks
this. **It does.** From cut 1 onward the `docker-build-pr` CI job builds the image on amd64 and
arm64 and then runs, against the built image itself:*

```
docker run --rm "$IMAGE" node -e "require('./lib/server/runtime-policy')(); console.log(process.version)"
```

*followed by a start-up smoke test that requires the container to answer on port 1337. So the
image's own Node is put through the very check that would reject it, and the job fails if it does.
Measured: `git show origin/chore/retire-jsdom:.github/workflows/main.yml`, job `docker-build-pr`;
the same step is present on cuts 2–5.)*

**The residual risk is narrower than "unchecked", and it is worth stating precisely**, because it
is the part a reviewer still has to close: that validation runs on `pull_request` only. The
`docker-build` job — the one that actually pushes to Docker Hub when `master` or `dev` moves — has
**no** runtime-policy step, and it builds with `no-cache: true`, so it resolves the floating
`node:22-alpine` tag afresh at publish time. A patch-level regression in that tag between the PR
build and the publish build would therefore ship unvalidated. The fix is one line: copy the
`docker run ... runtime-policy` step into `docker-build` as well.

**A second Docker warning:** if you *build* the image yourself (many docker-compose users do)
rather than pulling the published one, Docker may reuse a `node:22-alpine` layer it cached months
ago. Run `docker pull node:22-alpine` before building, or you can produce an image that refuses to
start for a reason that is entirely invisible in your configuration.

**Heroku**

Heroku picks the Node version from `engines.node` in `package.json`, so deploying the new release
should pull a suitable Node automatically. **The project has not verified this.** Cut 1's own
`docs/runtime-upgrade.md` lists Heroku under "the following remain release checks until a
maintainer records actual host evidence", and asks specifically for the buildpack to be verified
against the engine range, with an upgrade *and rollback* exercise recorded. Treat Heroku as
unvalidated until that evidence exists.

**Azure App Service**

Treat Azure as the highest-risk platform, for two reasons.

First, the project itself lists Azure as unvalidated in the same "release checks" block, and asks
for `SCM_COMMAND_IDLE_TIMEOUT=300` to be set and the legacy deployment script to be cleaned up
before release.

Second — and this appears in no other document — **the Azure deployment template is internally
broken, on dev and on cut 1 alike.** The template has a parameter for the Node version (cut 1
changes its default from `16.16.0` to `~24`), but **that parameter is referenced nowhere in the
template**, while the application settings block hard-codes `WEBSITE_NODE_DEFAULT_VERSION` to the
literal string `"8.11.1"`.

*(Measured: `git show <ref>:azuredeploy.json` parsed as JSON. Count of
`parameters('WEBSITE_NODE_DEFAULT_VERSION')` references in the whole template: **0**, on both dev
and cut 1. Literal value in `appSettings`: `8.11.1`, on both.)*

So cut 1's Azure "fix" changes a default that nothing reads, while the setting that Azure actually
applies still asks for Node 8.11.1. Node 8 is rejected by Nightscout's floor today and rejected far
more decisively after cut 1. Azure may well be ignoring an unavailable version and falling back to
something modern — which is the only explanation for Azure deployments working at all today — but
that is a guess, and it means **no Azure operator's Node version is actually being controlled by
the file that appears to control it.** Section 12 files this as a defect. An Azure operator should
set `WEBSITE_NODE_DEFAULT_VERSION` manually in the portal's application settings and verify with
the console, rather than trusting the template.

**Railway, Render, Fly.io, Northflank, Oracle Cloud and similar**

The repository contains no configuration for these, so the project has no evidence about them and
neither do I. Most of them read `engines.node` from `package.json`, in which case they will behave
like Heroku. Check your platform's Node setting explicitly, and use its console to confirm
`node --version` before upgrading Nightscout.

### 5.4 What it looks like when it goes wrong

**Recognising this failure is the whole point of this subsection.** If you take Release 2 on too
old a Node, here is exactly what happens:

- Your site returns an error from your hosting platform — a 503, an "Application Error" page, or
  simply nothing at all. **You do not get a Nightscout page with a message on it**, because
  Nightscout never gets far enough to serve a page. The check runs before configuration is loaded
  and before the database is touched.
- In your logs you get **one line**, and this is the line to search for:

```
ERROR: Node v20.19.0 is not supported. Nightscout requires Node ^22.23.2 || ^24.20.0. Upgrade Node before starting Nightscout; Node 24 LTS is recommended.
```

*(That is the literal message from `lib/server/runtime-policy.js` on cut 1, with a version number
substituted.)*

- On a platform that restarts crashed apps, you will see it **restart in a loop**, printing that
  same line each time.

**What it is NOT.** It is not a database problem, not a MongoDB connection string problem, not an
`API_SECRET` problem, and not corrupted data. **Nothing has been written to your database** —
Nightscout exited before it connected. Your data is untouched and safe. If you see that line, the
fix is Node, and only Node.

**What to do:** roll back to the previous release (section 7.2), confirm your site is up, then move
Node as a separate step, then try again.

---

## 6. Compatibility matrix

### 6.1 The three tiers, which are the point of this section

The task of this section is to be precise about the difference between "left CI" and "unsupported",
because those two phrases get used interchangeably and they have completely different consequences
for you. There are actually **three** tiers, not two:

| Tier | What it means | What happens to you |
|---|---|---|
| **1. Refuses to connect** | The MongoDB driver itself checks the server version and raises a `MongoCompatibilityError`. | **Hard failure.** Nightscout cannot reach your data at all. |
| **2. Works, but nobody tests it** | The driver connects happily; the project has removed that combination from its automated tests. | **It keeps working.** Nobody promises it will keep working, and a future bug affecting it will not be caught before release. |
| **3. Tested in CI** | The project runs its full test suite against this combination on every change. | Supported in the meaningful sense. |

**MongoDB 4.4 after cut 1 is tier 2, not tier 1.** The project removed it from CI. The driver still
talks to it. The project's own release note says this in as many words: *"An existing 4.4 connection
may still work; that does not make it supported."* Your 4.4 database will not stop working on the
day cut 1 ships. You should still plan to move off it, because it reached end of life on
29 February 2024 — but you are not on a deadline set by Nightscout.

### 6.2 Find out what MongoDB version you are on

- **MongoDB Atlas (most operators):** log in to cloud.mongodb.com, open your cluster, and the
  version is shown on the cluster card (e.g. "MongoDB 6.0.13"). Atlas upgrades free and shared
  tiers automatically, so most Atlas users are already on 6.0 or newer and **nothing in this
  section will block your upgrade.**
  *(One honest qualification, because "6.0 is fine" is the kind of reassurance that ages badly:
  MongoDB 6.0 itself reached end of life on 31 July 2025, and 5.0 on 31 October 2024. Both are
  above Nightscout's floor and both are still in the project's CI, so neither stops you upgrading
  Nightscout — but if you are running your **own** server on 5.0 or 6.0, you are on an unmaintained
  database, the same way Node 20 is an unmaintained runtime. The dates are measured, from the
  project's own `docs/runtime-upgrade.md` line 33 on cut 1, which cites MongoDB's published
  lifecycle schedule. **What Atlas does about it is not measured** — this document has no Atlas
  account and made no network request. The common understanding is that Atlas keeps its managed
  clusters patched and moves them off end-of-life versions for you, but treat that as an
  assumption, not a promise: if you are on Atlas, check your cluster's version yourself and read
  Atlas's own end-of-life notices.)*
- **Your own MongoDB:** connect with `mongosh` and run `db.version()`.
- **Docker-compose using the bundled file:** the version is in `docker-compose.yml` on the `mongo:`
  service line. On master and dev today it says `mongo:5.0.32`.

### 6.3 The matrix

Node columns: the minimum accepted. MongoDB: the oldest server the bundled driver will connect to,
and what CI covers. All driver numbers below are measured from the drivers' own
`MIN_SUPPORTED_SERVER_VERSION` constants, not from documentation.

| Release | Node accepted | Node enforced how | Mongo driver | Oldest Mongo that CONNECTS | Mongo covered by CI | nightscout-connect |
|---|---|---|---|---|---|---|
| **15.0.8** (today) | declared ≥20, **enforced ≥16**, no upper limit | warn-then-exit below 16 | 5.9.2 | **3.6** | 4.4, 5.0, 6.0 | v0.0.13 tag |
| **R1 — 15.0.9** | same as above | same | 5.9.2 | **3.6** | 4.4, 5.0, 6.0 | commit `234d47c8` |
| **R2 — cut 1** | **`^22.23.2 \|\| ^24.20.0`** | **hard `process.exit(1)` before config loads** | 5.9.2 | **3.6** | **5.0, 6.0** (4.4 removed) | v0.0.13 tag *(see §12)* |
| **R3 — cut 2** | unchanged | unchanged | 5.9.2 | **3.6** | 5.0, 6.0 + 7.0, 8.0 | v0.0.13 tag |
| **R4 — cut 3** | unchanged | unchanged | **7.6.0** | **4.4** | 5.0.32, 6.0.27, 7.0.40, 8.0.29 | v0.0.13 tag |
| *(cut 4)* | unchanged | unchanged | 7.6.0 | **4.4** | same as cut 3 | commit `c962a13f` |
| *(cut 5)* | unchanged | unchanged | 7.6.0 | **4.4** | same as cut 3 | commit `b77e5bb` |

*(CI matrices measured from each ref's `.github/workflows/main.yml`. Node floors from each ref's
`package.json` `engines`. Driver versions from each ref's `package.json` `dependencies.mongodb`.
Connector pins from each ref's `package.json`.)*

⚠️ **The last two rows are listed in stack order, not in release order, because the release order
is unsettled (section 0).** Note what they show: the connector pin **goes backwards** if cut 5 ships
before cut 4 — `b77e5bb` is **9** commits past v0.0.13 and `c962a13f` is 5, and `c962a13f` is an
ancestor of `b77e5bb`. That backwards step is a
direct symptom of the ordering problem, and it is one of the cheapest ways for a reviewer to
confirm section 0 independently.

⚠️ **From cut 3 onward, CI stops testing the exact minimum Node versions.** Cuts 1 and 2 test
`['22.23.2', '22', '24.20.0', '24']` — the floor itself and the latest of each line. Cuts 3, 4 and
5 test only `['22', '24']`. So the two version numbers the software refuses to start below are, from
cut 3 on, **not exercised by any test job**. *(Measured from each ref's `main.yml` `node-version`
matrix.)* This does not affect an operator who is comfortably above the floor, but it means a
regression exactly at the boundary would not be caught.

**How to read the matrix in one sentence:** the Node floor moves once, at R2, and the MongoDB floor
moves once, at R4, and they are deliberately in different releases so you never have to do both at
the same time.

### 6.4 What the driver change at R4 actually does to you

- **On MongoDB 4.4 or newer: nothing.** The driver's minimum becomes 4.4, which you already meet.
- **On MongoDB 4.2, 4.0 or 3.6: hard failure.** The driver refuses at connection time with a
  `MongoCompatibilityError` naming the wire version. **You must upgrade your database before taking
  R4.** This is tier 1, not tier 2 — it is a real block, not a warning.
- **On MongoDB 7 or 8: fine, and better than today.** Driver 5's tested ceiling is server 7.0;
  driver 7's is 9.0. In practice driver 5 also connects to MongoDB 8 — the version check that could
  reject a *newer* server tests the server's *minimum* wire version, which modern servers report as
  low — so this is a widening of the tested range rather than a fix for a breakage.
  *(Measured by reading `checkSupportedServer` in
  `.../mongodb/lib/cmap/connect.js`: the upper check is `minWireVersion <= MAX_SUPPORTED_WIRE_VERSION`,
  not `maxWireVersion <= ...`. Marked as **inference** for the practical claim about MongoDB 8,
  since I did not connect a driver-5 client to a live MongoDB 8 server.)*

**⚠️ If you run your own MongoDB from the bundled `docker-compose.yml`, do not simply pull the new
file and restart.** R4 changes the default image from `mongo:5.0.32` to `mongo:6.0.27`, and
**pointing a MongoDB 6 container at a data directory written by MongoDB 5 is not a supported
operation.** MongoDB requires you to step through major versions in order and to set the "feature
compatibility version" at each step. Doing it by editing one line in a compose file can leave the
database unable to start, and recovery may mean restoring from backup. If this is you: read section
9, then follow MongoDB's own upgrade procedure for your topology, rehearse it on a restored copy
first, and treat it as a separate project from the Nightscout upgrade.

---

## 7. Per-step rollback

Rollback means: putting back the previous version of the **application**. It does not mean undoing
things that happened while the new version was running. Throughout: **rolling the application back
never un-writes glucose data that arrived in the meantime, and that is good** — you do not want to
lose readings.

### 7.1 Release 1 (15.0.9) — reversible, clean

**Can you go back?** Yes.
**How?** Redeploy the previous image digest, or `git checkout` the previous commit and `npm ci`.
**What do you lose?** The bug fixes, and the quieter logging. Nothing else. No database change is
made by this release.
**One-way door?** No.

### 7.2 Release 2 (cut 1, the Node floor) — reversible, but the mechanism depends on you

**Can you go back?** Yes, and this is the release where you are most likely to need to.

**How, by platform:**

- **Docker:** redeploy the previous **digest**. This is why section 8 asks you to write it down. If
  you only wrote down `:latest`, you have no way to name the version you were on, and this becomes
  much harder.
- **Source install:** `git checkout` the previous commit, then `rm -rf node_modules && npm ci`
  **under the Node version that release expects**. If you also moved Node, move it back first
  (`nvm use 20`) — this is where nvm pays for itself.
- **Heroku:** use the platform's own rollback to the previous release.
- **Azure:** redeploy the previous artifact.

**What do you lose?** Nothing of yours. This release makes no database change and no settings
change.

**One-way door?** **No — but with an important caveat about the Node move itself.** Rolling back
*Nightscout* is easy. Rolling back *Node* is easy with nvm and awkward with a system package
manager, because a distribution-level Node install is system-wide and may be shared with other
software on the machine. **If you have anything else on that server that depends on Node, use nvm.**

**About "trivially revertible":** you will see this release described that way, and for someone
running from source it is accurate — one field in `package.json` controls the whole check. For a
Docker or Heroku operator there is no field to edit, and the real rollback is redeploying the
previous build. Both are genuinely easy. They are just not the same action, and only one of them
needs preparing in advance.

### 7.3 Release 3 (cut 2, page bundles) — reversible, clean

**Can you go back?** Yes.
**What do you lose?** Nothing.
**Watch out for:** your browser's cache and service worker. After rolling back, hard-refresh every
device again, or you may see a mix of old and new page code and conclude the rollback failed when
it did not.
**One-way door?** No.

### 7.4 Release 4 (the dependency release) — **the application is reversible; your database may not be**

*(If this release ends up including cut 5, section 7.5 applies to it as well — see section 0.)*

**Can you go back?** The Nightscout application: yes, the same way as the others. Driver 5 reads
everything driver 7 writes; this release performs no data migration and changes no schema.

**⚠️ THE ONE-WAY DOOR.** If, as part of preparing for this release, you **upgraded your MongoDB
server version**, that is a separate change and it is **not reversible by rolling Nightscout back.**
MongoDB's own downgrade rules are restrictive, a newer server rewrites internal data structures,
and the practical recovery route from a bad major upgrade is *restore from backup* — which means
losing every reading and treatment recorded since that backup was taken.

**Keep the two changes separate, in this order, with a gap between them:**

1. Upgrade MongoDB. Verify. **Wait days, not minutes.**
2. Then upgrade Nightscout.

That way, if step 2 goes wrong you roll back Nightscout, and if step 1 goes wrong you have not also
got a new Nightscout confusing the diagnosis. The project's own note makes the same point: *"Keep
application rollback and database rollback separate. Reverting Nightscout does not undo database
binary or FCV changes."*

**A second, quieter one-way risk:** third-party clients. If your uploader, watch face or follower
app breaks under Express 5 / Helmet 8, rolling Nightscout back fixes it — but only if you *notice*.
A follower app that silently stops receiving updates is the failure mode to watch for. Check within
the first hour.

### 7.5 Release 5b (cut 4, collector removal) — reversible, with the largest "but"

**Can you go back?** The application, yes.

**What do you lose?** If you reconfigured your data collection to move off `BRIDGE_*`/`MMCONNECT_*`,
rolling back does not restore your old settings — you must have kept a copy. **Write your old
settings down before you start, not after.**

**⚠️ The real risk here is not rollback, it is the gap.** If your CGM data stops arriving and you
do not notice for some hours, you have a hole in the record. For someone whose care team reviews
that record, or who relies on the site for remote monitoring of a child, that gap is the actual
harm — not the downtime. **Take this release when you can watch it, confirm within one CGM cycle
(about 5 minutes) that readings are arriving, and keep watching for an hour.**

**How to notice, not just how to fix.** This failure is silent: the site loads, the charts draw,
the numbers on screen are the last ones that arrived, and nothing announces that the last one was
half an hour ago. So check the thing that changes:

- **The "time ago" indicator on the main page** — the "5 min ago" next to the current reading. If
  that number keeps climbing past two CGM cycles (about 10–11 minutes) after an upgrade, data has
  stopped arriving, whatever the chart looks like.
- **Refresh, or open the site on a second device.** A page left open can go on showing an old
  reading; a fresh load tells you what the server actually has.
- **Check the follower app or watch face too**, not just the website. They fail independently.
- **Tell whoever else relies on the site that you are upgrading**, so that a quiet screen is read
  as "the upgrade is happening" rather than as a real reading.

If a gap in the record matters clinically — for example because your care team reads your reports
between visits — mention the date and length of the gap to them. This document is not medical
advice and cannot tell you whether a particular gap matters.

**One-way door?** Not technically. But if you are running two CGM sources at once, there is
currently no forward path at all (section 3, Release 5b), so for you it is a door that is not open
yet.

---

## 8. Before you touch anything: write these down

Five minutes now saves an evening later. Keep this somewhere that is **not** on the server you are
about to change.

1. **Which Nightscout you are on.** Docker: the **digest**, not the tag —
   `docker inspect --format='{{index .RepoDigests 0}}' <your-image>` gives you a
   `sha256:...` string that permanently identifies your exact current build. Source: the output of
   `git rev-parse HEAD`.
2. **Your Node version** (`node --version`) and **npm version** (`npm --version`).
3. **Your MongoDB version** (section 6.2).
4. **A complete copy of your environment variables / settings**, including `API_SECRET`,
   `MONGODB_URI`, your `ENABLE` list, and every `BRIDGE_*`/`MMCONNECT_*`/`CONNECT_*` setting. Most
   platforms have an "export" or a settings page you can copy from.
   **⚠️ This file contains your database password and your API secret. Store it somewhere private —
   a password manager is ideal. Do not put it in a shared folder, do not email it to yourself, and
   never paste it into a support channel.** If you need help and someone asks for your settings,
   remove `MONGODB_URI` and `API_SECRET` first.
5. **Your database backup and where it lives** (section 9).

**Keep `API_SECRET` unchanged through the whole upgrade.** Changing it during an upgrade will log
out your uploaders and followers and produce failures that look exactly like an upgrade problem but
are not.

---

## 9. Data safety

Your Nightscout holds a continuous record of your or your child's glucose. Losing it is the serious
outcome in this document — more serious than downtime, because downtime ends and lost history does
not. Treat this section as the non-optional one.

### 9.1 What actually needs backing up

**Only your MongoDB database.** That is where every glucose reading, treatment, profile, device
status and food entry lives. The Nightscout application itself holds nothing you cannot re-download
— that is what makes application rollback so easy.

### 9.2 How to take the backup

- **MongoDB Atlas (most operators):** paid tiers have automated backups — check they are actually
  enabled and check the date of the most recent one; do not assume. Free and shared tiers
  **do not have automated backups**, so you must take one yourself. Use Atlas's export, or
  `mongodump` from your own machine with your connection string.
- **Your own MongoDB:** `mongodump --uri="<your connection string>" --out=/somewhere/safe/`.
- **Either way:** copy the backup **off** the machine and **out of** the hosting account that is
  being upgraded. A backup that lives only inside the thing you are about to change is not a backup.

### 9.3 Verify the backup is real — this is the part people skip

A backup you have never restored is a hope, not a backup. **Before Release 4 in particular, do
this:**

1. **Check it is not empty.** `mongodump` prints a document count per collection as it runs. Look
   at the `entries` count — it should be in the tens or hundreds of thousands for a site that has
   been running a while, not zero and not a few dozen. A backup file of a few kilobytes for a
   two-year-old site means something went wrong.
2. **Restore it somewhere else and look at it.** Restore into a *different* database name — for
   example `mongorestore --uri="<connection string>" --dir=/somewhere/safe/
   --nsFrom='nightscout.*' --nsTo='nightscout_restoretest.*'` — then connect and run
   `db.entries.countDocuments()` and
   `db.entries.find().sort({date:-1}).limit(1)`. **Check that the newest reading is from when you
   took the backup.** If it is from three weeks ago, you have backed up the wrong database or a
   stale copy.
3. **Delete the test restore afterwards** so it does not sit there confusing you later, and so you
   are not paying to store a second copy of health data.
4. **Never restore a backup over your live database just to undo an application upgrade.** That
   throws away every reading since the backup. The project's own note says the same: *"do not
   restore an old database over new user data merely to roll back the runtime policy."* Rolling
   back the application is the correct move; restoring the database is a last resort for actual
   data corruption.

### 9.4 Treat the backup as health data

Your backup is a complete record of someone's glucose, meals and insulin. It is sensitive. Store it
encrypted if you can, keep it out of shared cloud folders that other people can browse, and delete
old copies you no longer need. If you ever share data to get help, share a screenshot of the
specific problem — never the dump file, and never your connection string.

---

## 10. Should I upgrade at all?

**Not everyone should, and being told so is more useful than being told to keep up.**

### 10.1 You should take Release 1 (15.0.9)

Almost everyone should. It is low-risk, fixes real bugs, and requires nothing of you. The main
reason to wait is if you are in the middle of something else — a new pump, a hospital stay, a
holiday — in which case wait until you have a quiet week.

### 10.2 You should plan Release 2, even if you do not want it

Because Node 20 is already past end of life, **staying on 15.0.8 forever is not the safe option it
looks like.** You are not avoiding risk, you are choosing a different one: an unmaintained runtime
that will stop receiving security fixes for the parts of it exposed to the internet.

That said, "plan" does not mean "rush". A reasonable posture is: **move Node now** (which you can do
today, without changing Nightscout at all, because 15.0.8 runs fine on Node 22 and 24), and take
Release 2 whenever you are ready. That converts the risky step into a boring one.

### 10.3 You may reasonably stop after Release 2 or Release 3

If your site works, your data flows, and you are not chasing a specific fix, there is no urgency to
Releases 3 and 4. They deliver internal modernisation, not features you asked for. **Waiting a few
months and letting other people find the problems first is a legitimate, even sensible, strategy.**

### 10.4 You should be actively cautious about Release 4 if…

- You are on MongoDB 4.2 or older (you must upgrade the database first — a real project).
- You depend on a third-party client the project has never tested against Express 5.
- You run your own MongoDB from the bundled compose file (section 6.4).
- **You use `BRIDGE_*` (Dexcom Share) or `MMCONNECT_*` (MiniMed CareLink) settings** — and this is
  the new one. Until the question in section 0 is settled, nobody can tell you whether this release
  removes your CGM collector. **Before taking it, check the release notes for whether the built-in
  collectors are still present, and if the notes do not say, ask before upgrading.** If they are
  removed, section 10.5 applies to you instead.

### 10.5 You should NOT take Release 5b yet if…

- You use `MMCONNECT_*` (MiniMed CareLink) — there is currently no migration path that does not
  require you to add settings by hand, and getting it wrong takes your whole site down.
- You run two CGM sources at once — there is currently no forward path at all.
- You use `BRIDGE_*` (Dexcom Share) and have not yet tested nightscout-connect on a previous
  release.

### 10.6 Things that should make you upgrade *sooner* rather than later

- **You turn on debug logging to diagnose problems.** Then the credential-redaction fixes matter to
  you specifically, and you want whichever release finally carries nightscout-connect v0.0.14.
- **You use the bolus calculator's quick-pick food chooser.** A high-severity defect was found in it
  this week (the chooser can resolve the wrong record, so the carbohydrate figure reaching the
  calculation comes from a food entry you did not pick, with no error shown). **The fix is not in any
  released version yet** — it sits on an unmerged branch. Until it ships, if you use quick picks,
  **check that the carb number shown matches the food you chose** before acting on it. As always,
  this is not medical advice and the calculator is a tool, not a decision.

### 10.7 The honest caveat about all of it

The five releases described here have been through automated testing and one author's own review.
**They have not been reviewed by a second person.** Across the 100 pull requests that make up this
work, every one was merged by its own author with no human review recorded. That does not mean the
code is wrong — the automated testing is genuinely extensive — but it does mean that "wait and let
others go first" is a more reasonable stance than it would normally be, and you should not feel
behind for taking it.

*(This governance finding is from the release-readiness review and is reproduced here because it is
the single most relevant fact to an operator's "should I?" decision. It is not re-measured in this
document.)*

---

## 11. Support-load estimate for the project

The release-readiness document named support load as the real cost of a five-release train, so this
section tries to size it and pre-empt the worst of it. **These volumes are estimates based on the
shape of each change, not measurements** — the project has no historical support-ticket data on
this machine and I did not contact any support channel.

### 11.1 Where the questions will come from

| Release | Predicted support load | Why |
|---|---|---|
| R1 — 15.0.9 | **Low** | Nothing required of the operator. Some "my logs went quiet" confusion. |
| **R2 — cut 1 (Node)** | **Highest by a wide margin** | Every operator outside `^22.23.2 \|\| ^24.20.0` hits a hard stop — that is anything below 22.23.2, all of Node 23, anything below 24.20.0, and Node 25 and above. Failures look like total outage. Affects the least technical operators most, since they are the ones who never touched Node. |
| R3 — cut 2 | **Medium, and mostly one question** | "The site looks broken after upgrading" → stale browser/service-worker cache. Should be almost entirely absorbable by one FAQ entry. |
| R4 — dependency release | **Medium–high, hard to answer** | Database questions need per-operator diagnosis, and third-party client breakage is unpredictable and not the project's to fix. **If cut 5 is included (section 0), add all of R5b's load to this row and expect it without the deprecation release having gone out first — the worst combination in the table.** |
| R5a — deprecation | **Medium, but valuable** | Questions arrive *before* anything breaks, which is the entire point of the release. Load here is a success, not a cost. |
| **R5b — cut 4** | **Highest severity, even if lower volume** | "My child's glucose data stopped arriving." Emotionally urgent, time-critical, and for MiniMed users currently unanswerable. |

**The single highest-value mitigation** is not an FAQ at all: it is **telling operators to move Node
before Release 2 ships**, while 15.0.8 still runs on everything. That converts the R2 support wave
from "my site is down, help" into "I did that last month". I would publish that message weeks ahead
of R2 and repeat it.

**The second highest-value mitigation** is giving support volunteers **one line to search for**. The
runtime failure prints exactly one distinctive string, and it names the problem precisely. A pinned
post reading *"If your log says `Node ... is not supported`, this is the answer"* will deflect a
large share of R2's volume without a human reading anything.

### 11.2 Draft FAQ entries

These are drafts for review, written for a non-technical operator.

---

**Q: My site was working and now it just shows an error page / won't load at all after upgrading.
Did I lose my data?**

**No. Your data is safe.** The most likely cause is the Node version. Look at your server log for a
line containing `is not supported`. If it is there, Nightscout stopped *before* it ever connected to
your database — it did not write anything, delete anything or change anything. Roll back to the
previous version to get your site up again, then sort out Node as a separate step, then upgrade
again.

---

**Q: My log says "Node v20.x is not supported. Nightscout requires Node ^22.23.2 || ^24.20.0". What
does that mean?**

Nightscout needs a newer version of Node, the program that runs it. That odd-looking text means:
Node 22 (at least version 22.23.2) or Node 24 (at least version 24.20.0). Section 5.3 of the upgrade
guide tells you how to move Node on your hosting platform. Node 20 stopped getting security updates
in April 2026, which is why the requirement changed.

---

**Q: I AM on Node 22 and it still refuses to start. Is this a bug?**

Almost certainly not. The requirement is not "Node 22" — it is "Node 22.23.2 or newer". If you are
on, say, 22.20.0, that is Node 22 and it is still too old. Run `node --version` and read the **whole**
number, not just the first part.

---

**Q: I upgraded Node to the newest version (Node 25 / Node 26) and now it won't start at all.**

Nightscout accepts only the even-numbered long-term-support lines, currently 22 and 24. Odd-numbered
Node versions (23, 25) are short-lived and are not accepted, and versions newer than 24 are not
accepted yet either. Install Node 24 specifically. **Newer is not always better here.**

---

**Q: I use Docker. Do I need to install Node?**

No. The Docker image includes its own Node. Upgrading the image upgrades Node too. If you want to
check, run `docker run --rm <image> node --version`. If you *build* the image yourself rather than
downloading it, run `docker pull node:22-alpine` first so you are not building on a stale cached
copy.

---

**Q: After upgrading, my site looks broken — missing buttons, weird layout, or a blank chart.**

Try a hard refresh first: **Ctrl+Shift+R** (Windows/Linux) or **Cmd+Shift+R** (Mac). On a phone,
close the Nightscout tab or app completely and reopen it. This release changes how the page files
are packaged, and your browser may be mixing new files with old cached ones. This fixes the large
majority of "it looks broken" reports.

---

**Q: My server log went quiet after upgrading to 15.0.9. Is something wrong?**

No, that is deliberate. Routine diagnostic messages are now off by default; warnings and errors
still appear. If you need the detail back to diagnose something, set `DEBUG_LOGGING=true`.
**Please turn it off again afterwards**, and be careful about sharing those logs — in this version
they can still contain your CGM vendor login details. If you need help, ask before pasting a log,
and remove anything that looks like a username, password or long random string.

---

**Q: Do I have to upgrade my MongoDB database?**

For most people, no. If you use MongoDB Atlas you are almost certainly on 6.0 or newer already and
nothing is required. You only *must* upgrade if you are on MongoDB 4.2 or older, and only when the
dependency release (Release 4) arrives. MongoDB 4.4 keeps working even after it leaves the project's
testing — it just stops being a combination anyone checks.

---

**Q: Nightscout says MongoDB 4.4 isn't supported any more, but my site still works. Which is it?**

Both, and the distinction is real. "Not supported" means the project no longer runs its automated
tests against 4.4, so if a future change breaks it nobody will find out before release. It does not
mean it has been switched off. You are not on a deadline, but you should plan to move — MongoDB 4.4
itself stopped getting security fixes in February 2024.

---

**Q: My glucose data stopped arriving after upgrading.**

Stop and roll back to the previous version first — get data flowing again before you investigate.
Then check whether you use the old built-in Dexcom (`BRIDGE_*`) or MiniMed (`MMCONNECT_*`) settings.
If you use MiniMed, do not take that release again yet; ask for help. **If a gap in your data
matters for someone's diabetes management, tell whoever relies on it that the site was down for that
period**, and mention the gap to your care team if they review your reports.

---

**Q: Can I just skip ahead to the newest version?**

You can, but please do not skip *reading* the steps in between, because the things you must do
before upgrading — check Node, check MongoDB, check your CGM settings — are cumulative. Jumping
straight to the end means doing all of them at once, and if something breaks you will not know
which one caused it.

---

**Q: Should I upgrade at all? My site works fine.**

Maybe not yet — see section 10. The one thing worth doing regardless of your upgrade plans is
**moving to a current Node version**, because Node 20 has not had security updates since April 2026.
You can do that today without changing Nightscout at all.

---

## 12. What a reviewer must verify, and what I could not settle

**This document is a draft.** These are the specific things a maintainer has to check before any of
it is published to operators.

### 12.1 Defects found while writing this, which are not filed anywhere

0. **THE ADOPTED RELEASE TRAIN CANNOT BE BUILT AS DESCRIBED — see section 0.** "Cuts 3 + 5
   combined, with cut 4 held back" is not a possible set of releases, because cut 4 is an ancestor
   of cut 5 and cut 5 already contains cut 4's deletion of `lib/plugins/bridge.js` and
   `lib/plugins/mmconnect.js`. Measured by `git merge-base --is-ancestor` and by
   `git cat-file -e` on both paths across all five cut tips. This is the highest-severity item in
   this document: taken literally, the plan ships the CGM ingestion retirement one release earlier
   than intended and **before** the deprecation release that exists specifically to warn people
   about it. A maintainer must choose between the three options in section 0 before Release 4's
   contents can be written down. **This defect is in the release plan, not in the code** — no
   branch is wrong; the description of how to combine them is.

1. **`azuredeploy.json` sets Node 8.11.1 and its Node parameter is dead.** The template's
   `WEBSITE_NODE_DEFAULT_VERSION` parameter is referenced zero times; the `appSettings` block
   hard-codes the literal `"8.11.1"`. True on `origin/dev` and on `origin/chore/retire-jsdom` alike.
   Cut 1's change of that parameter's default from `16.16.0` to `~24` therefore has no effect on a
   deployed site. **A reviewer must establish how Azure deployments work at all today** — my
   assumption is that Azure falls back when the requested version is unavailable, but I did not
   verify it and have no Azure environment.
2. **Merging cut 1 into 15.0.9 can silently roll the connector backwards.** The single conflict hunk
   in `package.json` contains exactly the nightscout-connect pin (dev: commit `234d47c8`; cut 1: the
   v0.0.13 tag) alongside a test-dependency removal. Taking either side wholesale is wrong: the
   resolver must take cut 1's `mongomock` removal **and** dev's connector pin. The same merge has a
   single conflict in `lib/server/bootevent.js` where cut 1's side adds a guard that skips the
   connector when no source is configured — losing that guard by taking dev's side is the other
   half of the same hazard. **Added on review: there is a third conflict that matters and the first
   draft omitted it** — `tests/clock-client.test.js` is a modify/delete (dev's `06372e1d` adds 56
   lines of coverage for the low-and-falling clock warning; cut 1 deletes the file). Accepting the
   deletion keeps the production fix with no test behind it, and cut 1's Playwright replacement
   covers construction and XSS, not the concern face. Whoever resolves this merge must decide
   deliberately where that coverage goes, and record the decision. (`package-lock.json` is the
   fourth conflict and is mechanical.)
3. **All five cut tips and dev all declare `"version": "15.0.9"`.** Until fixed, no operator can
   report which build they are on and no support volunteer can triage from a version number. This
   is the cheapest high-value fix in the whole train and it should land before R2, not after.

### 12.2 Open questions I could not settle

1. **Does the published Docker image actually satisfy its own Node floor?** *(Largely settled on
   review — this item was overstated in the first draft.)* Cut 1's Dockerfile is
   `FROM node:22-alpine`, a floating major tag, while `engines` requires `^22.23.2`, and the
   Dockerfile does not pin a patch level. But CI **does** check the result: from cut 1 onward the
   `docker-build-pr` job runs
   `docker run --rm "$IMAGE" node -e "require('./lib/server/runtime-policy')(); ..."` against the
   built image on both amd64 and arm64, then smoke-starts it. What remains open is narrow and
   concrete: **the `docker-build` job that publishes to Docker Hub carries no such step and builds
   `no-cache`**, so it re-resolves `node:22-alpine` at publish time without re-validating it. A
   reviewer should (a) add that one step to `docker-build`, and (b) confirm today's
   `node:22-alpine` with `docker run --rm node:22-alpine node --version` — one command, needing
   network access this session did not have.
2. **Heroku and Azure compatibility is unvalidated by the project's own admission.** Cut 1's
   `docs/runtime-upgrade.md` lists both as release blockers pending "actual host evidence".
   **A maintainer with accounts on those platforms must settle this**, not a document.
3. **Third-party client compatibility with Express 5 and Helmet 8 is entirely unmeasured.** No
   plugin or client corpus exists on this machine to test against. Given that the clients in
   question include uploaders that carry glucose data from AID systems, **this is the largest
   unquantified risk in the train** and it belongs to whoever owns the R4 release gate.
4. **Time estimates throughout are inferences, not measurements.** Nobody has timed a real operator
   upgrade. If the project has any historical data on how long upgrades take people, it should
   replace my numbers.
5. **Support-volume estimates in section 11 are reasoned from the shape of each change**, with no
   historical ticket data. The *ordering* (R2 highest, R1 lowest) I am confident in; the magnitudes
   I am not.
6. **What Release 4 actually contains.** Section 0. Until a maintainer picks one of the three
   options, the Release 4 and Release 5 instructions in this document are conditional and must not
   be published. **This is the only open question here that blocks publication of part of the
   document**, and it is a plan question, not a measurement question — no further measurement will
   settle it.

7. **Whether the Node whitelist rejecting future LTS versions is intended.** `^22.23.2 || ^24.20.0`
   will reject Node 26 LTS when it arrives. **This is now measured rather than reasoned:** cut 1's
   `runtime-policy.js` was executed against all thirteen version strings its own test file asserts,
   with `process.version` overridden, and `v26.8.1` exits 1 with the standard message, as do
   `v25.0.0`, `v23.0.0`, `v22.23.1` and `v24.20.0-rc.1`, while `v22.23.2`, `v22.24.0`, `v24.20.0`
   and `v24.21.0` pass. The *behaviour* is certain; only the *intent* is open. That may be a deliberate "re-validate before permitting"
   policy, in which case it needs a documented process for widening it. If it is not deliberate, it
   is a defect that will surface in about a year, at which point it will look like a Nightscout bug
   to every operator who hits it.

### 12.3 Corrections this document makes to existing repo documents

Listed in the structured return value rather than applied here, since a separate reconciliation
agent owns edits to the shared planning documents.

---

## 13. Provenance

Every number in this document was measured on 2026-09-15 against
`externals/cgm-remote-monitor-official` (`origin/dev` = `a8888f0d`, fetched 2026-09-14 18:56; no
fetch was performed for this work) and `externals/nightscout-connect`, using read-only git commands
and by reading installed `node_modules` packages. **No branch was created, modified, rebased or
merged; no worktree was touched; nothing was pushed; no network request was made.** The merge
conflict analysis used `git merge-tree --write-tree`, which computes a merge result without
altering any ref.

Where this document reproduces a figure from an earlier measurement pass (GT1–GT4), it says so. The
per-cut production diffs, the behind-counts, the conflict sets and the release-readiness §5
discrepancy were all re-measured here and reproduce those passes exactly, to the digit.

Claims marked **inference** are reasoning from measured facts, not observations. The largest of
these are: the practical behaviour of driver 5 against MongoDB 8; the cause of Azure deployments
working today despite the 8.11.1 setting; and all time and support-volume estimates.

### 13.1 Verification pass, 2026-09-15 18:50–19:00

This document was re-read adversarially after it was first written, and every load-bearing claim
was re-measured against the same refs. **One structural error was found and is recorded as section
0**; the rest of the document reproduced exactly. Specifically re-confirmed in that pass:

- `engines` byte-identical across all five cut tips; `"version": "15.0.9"` on all five plus dev.
- `runtime-policy.js` source, its two call sites (`server.js:26`, `bootevent.js:31`), and the
  literal error string — and, **newly, by execution**: the module was run with `process.version`
  overridden to each of the thirteen version strings in `tests/runtime-policy.test.js`, confirming
  exit status 1 or 0 for each. This converts sections 5.2 and 5.4 from "read" to "measured", and
  satisfies the project's non-vacuity rule: the check was made to fail, and it failed as described.
- `server.js:26` runs the runtime check **before** `require('./env')()` at line 33, which is what
  makes the section 5.4 reassurance ("nothing was written to your database") true.
- Today's enforced floor on dev is `semver.satisfies(nodeVersion, '>=16.x')` with no upper bound,
  which is what makes the "move Node first, on 15.0.8" advice safe.
- Driver constants read from the two installed packages: 5.9.2 → min server 3.6 / wire 6, max
  server 7.0 / wire 21; 7.6.0 → min server 4.4 / wire 9, max server 9.0 / wire 29. `checkSupportedServer`
  compares the server's **minimum** wire version against the driver's maximum, as described.
- `azuredeploy.json`: zero references to the `WEBSITE_NODE_DEFAULT_VERSION` parameter, literal
  `8.11.1` in `appSettings`, on dev and cut 1 alike.
- The dev × cut 1 merge conflict set (`bootevent.js`, `package.json`, `package-lock.json`,
  `tests/clock-client.test.js`) and both conflict hunks' contents.
- Cut 1 diffstats on both bases: 11 files +68/−54 incremental, 21 files +91/−123 against dev.
- Every quotation from cut 1's `docs/runtime-upgrade.md` is verbatim.

Nothing was pushed, no branch or worktree was touched, and no network request was made. The
execution test ran from an isolated copy in the session scratchpad, not from any checkout.

### 13.2 Adversarial verification pass, 2026-09-15 (third reading)

A third agent re-read this document with the explicit brief of **refuting** it, and re-measured
every load-bearing claim from the repositories rather than from any earlier pass's notes. The
results, honestly:

**Section 0's central finding survives, fully.** Re-measured independently:
`git merge-base --is-ancestor origin/chore/mime-exposure-review origin/chore/nightscout-modernization`
exits 0; cut 5 is 154 commits past cut 4; `git cat-file -e` confirms `lib/plugins/bridge.js` and
`lib/plugins/mmconnect.js` are present on `dev` and on cuts 1, 2 and 3 and absent on cuts 4 and 5,
while `lib/server/mmconnect-connect-compat.js` is absent everywhere before cut 4 and present on
cuts 4 and 5. The plan text section 0 contradicts was read at its source
(`docs/30-design/modernization/cgm-remote-monitor-release-readiness-2026-09-14.md:416`) and is quoted correctly.

**Reproduced exactly, to the digit:** all seven `package.json` version/engines/driver/connector
values in the section 6.3 matrix; both cut 1 diffstats (11 files +68/−54 incremental, 21 files
+91/−123 against dev) and the other four cuts' incremental figures (60 / 23 / 66 / 36 files); both
MongoDB drivers' `MIN_/MAX_SUPPORTED_SERVER_VERSION` and wire constants; `checkSupportedServer`'s
`minWireVersion <= MAX_SUPPORTED_WIRE_VERSION` upper test; `runtime-policy.js`'s source, its call
sites at `server.js:26` and `bootevent.js:31` (with `require('./env')` at line 33), and its error
string; the thirteen version strings in `tests/runtime-policy.test.js` and their accept/reject
outcomes, re-evaluated against the live `semver` package; `checkNodeVersion`'s `>=16.x` on both
`master` and `dev`; the four-file dev × cut 1 merge conflict set and both quoted conflict hunks;
`azuredeploy.json`'s zero parameter references and literal `8.11.1` on both refs; every CI
`node-version` and `mongodb-version` matrix; `FROM node:22-alpine` on all seven refs; the
`docker-compose.yml` mongo images; `bin/setup.sh` line 3; `.nvmrc`; `views/service-worker.js`
(72 added / 124 deleted = 196 lines changed); and every quotation from
`docs/runtime-upgrade.md`, which is verbatim.

**Corrected in this pass** (each correction is marked inline where it lands):

- The connector pin `b77e5bb` is **9** commits past v0.0.13, not 7. The "backwards pin" symptom in
  sections 0 and 6.3 stands and is in fact stronger than stated, because `c962a13f` is a strict
  ancestor of `b77e5bb`.
- Section 0's option 2 was described as "the only option that is still a prefix cut". Wrong —
  option 1 is a prefix cut too. Option 2 is the only one that is *both* a prefix cut and preserves
  the ordering.
- The Node 20 end-of-life date has **one** in-repo source, not two, and none outside the repo. It
  is the main argument for taking Release 2, so a reviewer must confirm it upstream.
- Section 12.2's first open question was overstated: CI **does** validate the built Docker image
  against `runtime-policy.js` on every pull request, from cut 1 onward. The genuine residual gap is
  that the publishing job does not.
- The section 4 enumeration of files stating the Node floor did not match the grep cited as its
  provenance, and included `Dockerfile`, which states no floor. Re-enumerated.
- The dev × cut 1 merge has four conflicts, not one, and the omitted one matters: cut 1 deletes
  `tests/clock-client.test.js`, the only coverage for `dev`'s low-and-falling clock warning.
- Smaller: the Release 1 commit count mixed two counting conventions; `runtime-policy.js` is twelve
  lines (nine of code); the FAQ's quoted error string dropped a word from the searchable text; the
  Release 2 support-load row understated which Node versions hard-stop; the MongoDB driver 7
  constants were read from a `^7.6.0` install in a different worktree; the Atlas claim in section
  6.2 was an assumption stated as fact.

**Added in this pass:** the "how to notice, not just how to fix" guidance in section 7.5, because a
CGM ingestion failure is silent and the document previously told operators only how to respond once
they already knew.

**Not verified, and still not verifiable from here:** anything requiring network access or a
hosting account — Docker Hub tag contents, Heroku, Azure, MongoDB Atlas, and all third-party client
behaviour. The time and support-volume estimates remain inferences. No file outside this document
was modified, no branch or worktree was touched, and no network request was made.
