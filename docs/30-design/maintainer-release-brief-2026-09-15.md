# Phase 0 release brief — for the maintainer who merges

**Date:** 2026-09-15 · **Audience:** a Nightscout maintainer with merge rights on
`nightscout/cgm-remote-monitor` and `nightscout/nightscout-connect`.
**Status:** DRAFT for maintainer review. Nothing in this batch has been pushed, tagged, merged or
published. Everything below was prepared locally and stopped there, deliberately.

This is the one document to read before you start typing. It is written so you can read it once and
then act. Where a number appears, the sentence says how it was measured. Where the reasoning is
inference rather than measurement, it says so.

Read §1, §2, §3 and §4 before you touch anything. §5 is the per-branch detail you will want open
while reviewing PRs. **§9 and §9a are the rollback and the "how would I even notice" list — read
§9a before you merge, not after**, because most of what this batch touches fails silently.

> **This document has been through an adversarial review pass (2026-09-15) and carries its
> corrections inline.** Three claims in the first draft were refuted and are struck through rather
> than deleted, so that a wrong claim cannot be quietly re-raised: the CodeQL trigger claim (§4,
> §12.5), the `CHANGELOG.md` add/add claim (§5 branch G, §8.4), and the `$exists` inversion claim
> (§5 branch D, §11). Two test-coverage gaps were closed (`bf/auth`, `bf/cache`) and one was not
> (`bf/alarms`). Figures added or re-measured in that pass say so.

---

## 1. One screen: what ships, to whom, what an operator notices

**What ships:** nine bug-fix branches for `cgm-remote-monitor`, all based directly on `origin/dev`
(`a8888f0d`), plus one release of the `nightscout-connect` connector (`v0.0.14`).

**To whom:** every self-hosted Nightscout operator who takes the next release off `dev`. There is no
tenancy or multi-tenant content in this batch at all. Single-tenant self-hosting is the only
consumer.

**What an operator will actually notice.** Six things, in the order they matter:

1. **An urgent insulin-reservoir alarm starts arriving that never arrived before.** If you run with
   `IAGE_ENABLE_ALERTS` on, the "Insulin reservoir change overdue!" notification has never fired in
   any release, because the code compared the reservoir age against a field that was never filled
   in. It now fires **once**, in the single evaluation window where the reservoir age first equals
   your configured `IAGE_URGENT` threshold (default 72 hours) and the clock is within 20 minutes
   past the hour — it is not repeated afterwards. The reported level also stops being stuck at WARN
   and reads URGENT for as long as the reservoir is overdue. On Pushover the notification carries
   the `persistent` sound. **This is a new alert on a safety surface for people who have never heard
   it.** It needs its own line in the release notes, in plain language, at the top, and the release
   note must say it fires once rather than repeating — someone who expects it to nag will be
   misled. (`bf/alarms`) *(Verified today by reading `lib/plugins/insulinage.js:91-115` on the
   branch; not executed against a running site.)*
2. **The bolus calculator's quick-pick list stops naming one meal and loading another.** This is the
   most consequential fix in the batch: the carbohydrate total that reached the insulin calculation
   could come from a record the user did not choose, under a label they did read, with no error
   shown. It has shipped since 2017. (`bf/food`)
3. **A page that used to freeze, or never load at all, keeps working.** A URL with a bare flag
   (`?debug`, a trailing `&`) stopped the page loading entirely; a deleted treatment could freeze
   the display until reload. (`bf/parms`, `bf/merge`)
4. **API queries that quietly returned nothing start returning rows.** Numeric and decimal filters
   were compared as text, so many filters matched nothing and answered `200 OK` with an empty list.
   (`bf/coercion`, `bf/reads`)
5. **A handful of previously-accepted API query spellings now return `400`.** `?count=0` and five
   other spellings are rejected instead of being answered with the whole collection. This is the
   only operator-facing *restriction* in the batch and the only thing that can break a working
   integration. (`bf/reads`)
6. **The connector retries a failing vendor far less aggressively.** After an outage, data will
   appear to resume *more slowly* than operators are used to. That is the fix, not a regression —
   the old behaviour retried 586× too fast and in lockstep across every account.
   (`nightscout-connect v0.0.14` + `bf/connect-pin`)

Two security fixes are in the batch and are not operator-visible in normal use (`bf/auth`), and one
pure performance fix changes no bytes on the wire (`bf/cache`).

> **Not medical advice.** The release notes derived from this document go to people managing their
> own or a family member's diabetes. Keep every safety caveat, define any jargon, and do not
> describe alarm or algorithm behaviour in a way that could mislead someone relying on it. Point
> readers at their care team for anything about their own therapy.

---

## 2. THE THREE HUMAN DECISIONS, IN ORDER — and the fact that there are three

A release here is **three separate human decisions**, not one. This batch needs all three, and they
are not interchangeable:

| # | decision | what it does | reversible? |
|---|---|---|---|
| **1** | **Merge the code** | a PR merge into `dev` | yes — `git revert` (see §9) |
| **2** | **Push the tag** | `nightscout-connect v0.0.14` becomes a real, downloadable tarball | **effectively no** — a tag other people have fetched should be superseded, not moved |
| **3** | **Publish the package** | `npm publish` for `nightscout-connect` | **no** — npm unpublish is time-limited and disruptive |

They are separate because each is a different kind of commitment and each gets its own review. The
ordering below is not stylistic: **decision 2 must happen before the `package-lock.json` in
`bf/connect-pin` can be regenerated at all** (see §3).

**One correction you should have before you start.** Decision 3 is *not* what delivers the connector
fix to operators, and the sequencing document says otherwise. Measured on every relevant ref today
(`git show <ref>:package.json`), **nothing in the Nightscout tree depends on `nightscout-connect`
from the npm registry.** Every pin is a GitHub tarball URL:

| `cgm-remote-monitor` ref | `nightscout-connect` pin | post-v0.0.13 fixes it carries |
|---|---|---|
| `origin/master` (15.0.8 — what operators run) | `…/archive/refs/tags/**v0.0.13**.tar.gz` | **0 of 6** |
| `origin/dev` (15.0.9 candidate) | `…/archive/**234d47c8**.tar.gz` | **0 of 6** |
| `origin/chore/mime-exposure-review` (cut 4) | `…/archive/**c962a13f**.tar.gz` | 4 of 6 |
| `origin/chore/nightscout-modernization` (cut 5) | `…/archive/**b77e5bb**.tar.gz` | 5 of 6 |
| **`bf/connect-pin`** | `…/archive/refs/tags/**v0.0.14**.tar.gz` | **6 of 6** |

*Measured* by `git merge-base --is-ancestor <commit> <pin>` for each of the six commits
(`9fa2c3c`, `5349d47`, `77e2396`, `8406edf`, `51b6e6e`, `c1cce2a`) against each pin, in
`externals/nightscout-connect`. **All five rows of the table above were re-measured independently
during adversarial review on 2026-09-15 and reproduce exactly**, including the five `package.json`
pin strings. **`v0.0.14` is the first ref that carries all six**, and the tarball pin means **the tag
push (decision 2), not the npm publish (decision 3), is what delivers it.**

Note what the first two rows mean: `dev`'s pin is one commit past the `v0.0.13` tag and that commit
is the debug-logging opt-in. **The 15.0.9 candidate as currently pinned ships without any of the
three connector log-redaction fixes.** Turning debug logging on to diagnose a problem — precisely
when an operator does it — can put Dexcom or MiniMed credentials and patient data into runtime logs.
`bf/connect-pin` is the branch that closes that.

Decision 3 remains a real decision you may still want to make (it retires the "three pinning
mechanisms" defect and gives the release a nameable connector version), but **it does not gate this
batch.** I could not check whether `nightscout-connect` is currently published on npm at all — this
machine has no network egress by rule. See §11.

### The commands — **these are the ones the HUMAN runs**

Everything below leaves this machine. Nothing above this line does.

```bash
# ── DECISION 1: merge the code ────────────────────────────────────────────────
# Push branches to origin (or to your fork) and open PRs against `dev`.
# NEVER push a branch ONTO dev or master — that is a publication event, see §4.
#
# NOTE ON REMOTES in this checkout (verified today with `git remote -v`): there are THREE.
#   origin    https://github.com/nightscout/cgm-remote-monitor.git   <- upstream, over HTTPS
#   official  git@github.com:nightscout/cgm-remote-monitor.git       <- the same repo, over SSH
#   bewest    https://github.com/bewest/cgm-remote-monitor.git       <- the fork
# `origin` here is UPSTREAM, not a fork. If you would rather use SSH, substitute `official`.
# If you push to `bewest` instead, read §6 first — one workflow can auto-close a fork PR.
cd /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official
for b in bf/alarms bf/cache bf/auth bf/food bf/merge bf/parms bf/coercion bf/reads; do
  git push origin "$b"
done
# Then open eight PRs. Base `dev` for all of them EXCEPT bf/reads —
# open bf/reads against `bf/coercion` and retarget it to `dev` once bf/coercion merges.
# (GitHub retargets automatically when the base branch merges.)

# ── DECISION 2: push the tag ──────────────────────────────────────────────────
# Fast-forwards nightscout-connect main to the release, then publishes the tag.
#
# FETCH FIRST. `origin/main` below is a cached remote-tracking ref; nothing on this machine has
# contacted GitHub, so it may be stale and the check would then pass on old information.
# (A stale check cannot cause damage — git refuses a non-fast-forward push — but it can give
# false confidence.)  Also note the LOCAL branch `main` in that checkout is 28 commits behind
# `origin/main`; do not push it, and do not use it in this check.
git -C /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/nightscout-connect fetch origin

# VERIFY THE FAST-FORWARD — this should print "fast-forward OK" and exit 0:
git -C /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/nightscout-connect \
    merge-base --is-ancestor origin/main release/v0.0.14 && echo "fast-forward OK"

git -C /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/nightscout-connect \
    push origin release/v0.0.14:main
git -C /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/nightscout-connect \
    push origin v0.0.14

# ── DECISION 3: publish the package (optional for this batch — see above) ─────
npm publish      # run from externals/nightscout-connect, and only if you want it on npm

# ── AFTER the tag exists, and not one second before: regenerate the lock ──────
cd /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-bf-connect-pin
npm install                         # regenerates package-lock.json against the real tarball
git commit -am "Regenerate the lock against connect v0.0.14"
git push origin bf/connect-pin      # then open the bf/connect-pin PR against dev
```

**Order matters and the failure is silent if you get it wrong.** `bf/connect-pin`'s PR should be
opened *after* the tag is pushed and the lock regenerated, so that what a reviewer sees is a
consistent pair. §3 explains why.

---

## 3. THE PACKAGE-LOCK TRAP — read this before anyone "fixes" it

**`bf/connect-pin` (`0807eb1c`) changes exactly one file, `package.json`, by one line. It does NOT
update `package-lock.json`, and that is deliberate.**

Measured in `externals/work/crm-bf-connect-pin`:

```
package.json:140        "nightscout-connect": "https://github.com/nightscout/nightscout-connect/archive/refs/tags/v0.0.14.tar.gz"
package-lock.json:58    "nightscout-connect": "https://github.com/nightscout/nightscout-connect/archive/234d47c85510a77f07b3be0d2c026dd0272715d6.tar.gz"
package-lock.json:7894  "resolved":  ".../archive/234d47c85510a77f07b3be0d2c026dd0272715d6.tar.gz"
package-lock.json:7895  "integrity": "sha512-gJCEEHXVDriBcYvDWPMCernrC5YPxB9zko4oeiYwUYYlWKN12G5CsgvFl7XH0Rxmfrtu2yLdpdqi/vmA3A9gwQ=="
```

`git show --stat 0807eb1c` confirms: **1 file changed, 1 insertion, 1 deletion.**

**Why the lock is stale on purpose.** That `integrity` field is a SHA-512 hash over the tarball
**GitHub generates on demand for a tag**. Until `v0.0.14` is pushed, that tarball does not exist, so
there is no hash to write. A hash invented locally — or copied from a locally-built archive — would
not match what GitHub serves, and **`npm ci` would fail for every operator and every CI run, with an
integrity error that looks like supply-chain tampering.**

**Leaving the lock stale produces the correct failure instead.** `npm ci` refuses to run when
`package.json` and `package-lock.json` disagree, and says so loudly and unambiguously:
*"npm ci can only install packages when your package.json and package-lock.json are in sync."* That
is a clear, actionable, honest error. An invented hash is a confusing, dishonest one.

> ### The trap
> **Anyone who "fixes" the out-of-sync lock before the tag is pushed has broken it.**
> There is no way to produce a correct `integrity` value for a tarball that does not exist yet.
> A reviewer who sees the red `npm ci` and asks for the lock to be regenerated is asking for the
> right thing **in the wrong order**.
>
> **The correct sequence, and the only one:**
> 1. Push the tag (`git push origin v0.0.14`). GitHub now generates the tarball.
> 2. `cd externals/work/crm-bf-connect-pin && npm install`. npm fetches the real tarball and writes
>    the real hash.
> 3. Commit the regenerated `package-lock.json` **in the same PR** as the `package.json` change.
>
> If you must open the PR before the tag exists, say in the PR description that the lock is
> deliberately stale, that CI is expected to be red on `npm ci`, and that the lock lands in a second
> commit after the tag. Do not merge it red.

---

## 4. WHICH PUSHES PUBLISH — verified against the workflow files today

I re-read every workflow file rather than trusting the summary I was handed. The summary held, with
**one correction** (marked ✱).

### `cgm-remote-monitor` — `.github/workflows/` on `origin/dev` (`a8888f0d`)

Three workflow files exist: `main.yml`, `codeql-analysis.yml`, `close-accidental-sync-prs.yml`.

| you push to… | publishes? | what actually runs |
|---|---|---|
| **`dev`** | **YES — PUBLISHES A DOCKER IMAGE** | `main.yml` job `docker-build` |
| **`master`** | **YES — PUBLISHES A DOCKER IMAGE** | same job, same condition |
| any other branch on `origin` | **no** | **nothing at all** |
| a branch on your fork | **no** | nothing (the `repository_owner` guard also fails) |
| opening a PR against `dev`/`master` | no | full test matrix + `docker-build-pr`, which **builds without publishing** |

The publishing condition, read verbatim from `main.yml` (the `docker-build` job at line 94 and the
`publish` job at line 145 both carry it):

```yaml
if: (github.ref == 'refs/heads/master' || github.ref == 'refs/heads/dev') && github.repository_owner == 'nightscout'
```

and the `publish` job logs in with

```yaml
username: ${{ secrets.DOCKER_USER }}
password: ${{ secrets.DOCKER_PASS }}
DOCKER_IMAGE: nightscout/cgm-remote-monitor
```

`main.yml`'s triggers are `push: branches: [master, dev]` and
`pull_request: branches: [master, dev]`. `codeql-analysis.yml`'s are
`push: branches: [dev, master]`, `pull_request: branches: [dev, master]`, plus a weekly cron.
**So a feature-branch push runs no workflow whatsoever** — not CI, not CodeQL, not Docker.

✱ ~~**Correction.** The claim that "PRs targeting `chore/nightscout-modernization` run full CI" is
true **only of the workflow file that lives on the modernization branch**, not of the one on `dev`…
`codeql-analysis.yml` on the modernization branch still lists only `[dev, master]`.~~

> **THIS "CORRECTION" WAS ITSELF WRONG AND IS WITHDRAWN (adversarial review, 2026-09-15).**
> Struck through rather than deleted, because a deleted wrong claim gets raised again.
> Measured with `git show origin/chore/nightscout-modernization:.github/workflows/codeql-analysis.yml`
> at `0a4109f6`: line 17 `push: branches: [ dev, master ]`, line 19
> **`pull_request: branches: [ dev, master, chore/nightscout-modernization ]`**. CodeQL *does* list
> the modernization branch under `pull_request`. The sequencing document's original sentence
> (`phase0-pr-sequencing-2026-09-15.md:36`, "`main.yml` and CodeQL both list it under
> `pull_request`") is **correct as written**. The error here was reading only the `push:` line.

What *is* true, and is worth keeping: the split between the two workflow files is real. On `dev`,
`main.yml`'s `pull_request` list is `[master, dev]` only; on `chore/nightscout-modernization` it is
`[master, dev, chore/nightscout-modernization]`, and that branch's `main.yml` also carries a
`concurrency` group and **three** extra jobs `dev` does not have (`maintained-mongo`,
`replica-test`, `browser-test`). **None of this affects Phase 0**, because every PR in this batch
targets `dev` (or `bf/coercion`) and gets the full `dev` matrix plus a non-publishing Docker
build.

### `nightscout-connect` — `.github/workflows/` on `release/v0.0.14`

**Exactly one workflow file exists.** `test.yml`, read in full:

```yaml
name: Connector regression tests
on: [push, pull_request]
permissions:
  contents: read
jobs:
  test:
    strategy:
      matrix:
        node: ['22.23.2', '24.20.0']
    steps: [checkout, setup-node, npm install --ignore-scripts, npm test]
```

`permissions: contents: read`. **No secrets are referenced. No registry login. No release workflow
at all.** Pushing the `v0.0.14` tag runs the test suite on Node 22 and 24 and **publishes nothing**.
`npm publish` for the connector is entirely manual and always has been.

**Bottom line for the nervous:** you can push every `bf/*` branch to `origin` and push the connector
tag without publishing a single artefact. The only two pushes that ship anything are onto
`cgm-remote-monitor`'s `dev` or `master`, and you will only do those through a PR merge.

---

## 5. Per branch: what it fixes, what changes, who approves

Semver classification is from the versioning analysis (GT4, `docs/60-research/gt4-semver-classification-2026-09-15.md`).
Test evidence is stated per branch with the suite that was actually run; where a suite was **not**
re-run, it says so and says why. **See §11 before treating any green tick as complete.**

Merge-tree state, **re-measured independently during adversarial review on 2026-09-15**: all nine
branches merge cleanly against `origin/dev`, and **all 36 unordered pairs among the nine branches —
`bf/connect-pin` included — merge cleanly against each other.** (`git merge-tree --write-tree
--name-only` for every pair; a clean result is a single tree hash with no file list. 36 pairs, 0
conflicts.) The `CHANGELOG.md` conflict recorded in the sequencing document is **gone**, though not
for the reason first given here — see §5 branch G and §8.4: `CHANGELOG.md` already exists on
`origin/dev`, so no add/add conflict was ever possible. `bf/reads` has since been rebased onto
`bf/coercion` — see the ordering note below.

### The one ordering constraint — and it changed since the sequencing document was written

**`bf/coercion` is now an ancestor of `bf/reads`.** Verified:
`git merge-base --is-ancestor bf/coercion bf/reads` succeeds, and `bf/reads` is 8 commits ahead of
`dev` with `88d1f8a4` (`bf/coercion`'s only commit) as its first. The rebase described as pending in
§3 of the sequencing document has been applied; the branch tip moved `824380a0` → `0d19bb31`.

**Practical consequence:** *merging `bf/reads` merges `bf/coercion` with it, whether or not you have
approved `bf/coercion`.* Open `bf/reads` against base `bf/coercion` so the PR shows only its own
seven commits. If you merge `bf/reads` against `dev` directly, you are approving both at once.

No other pair has a containment relationship (checked all 72 ordered pairs).

---

### A — `bf/alarms` · `5dcf783f` · 3 commits · **⚠ NEEDS A HUMAN'S EXPLICIT YES**

| | |
|---|---|
| **Fixes** | BF-28, BF-29, BF-31 |
| **Semver** | **minor** for the URGENT fix, **patch** for the ENABLE warning, **major** for the Alexa locale removal → **the branch as a whole is major** |
| **Evidence** | `docs/30-design/nightscout-backfix-register.md` BF-28/BF-29/BF-31; commit messages carry their own before/after measurements |
| **Approver** | **A maintainer must say yes in writing.** This is the one branch in the batch that starts an alarm. |

**The operator-visible change, in plain language:**

> If you have insulin-reservoir alerts turned on (`IAGE_ENABLE_ALERTS` — the setting that lets the
> Insulin Age plugin raise notifications), you will start receiving an urgent "Insulin reservoir
> change overdue!" notification when your reservoir reaches the age you configured (72 hours unless
> you changed it). **You have never received this notification before, on any version of
> Nightscout.** The feature was documented and the code was broken: it compared the reservoir's age
> against a setting it never read. Nothing about your insulin, your pump or your therapy has
> changed — only whether Nightscout tells you.
>
> **It fires once, not repeatedly.** The alert is raised in the single evaluation window where the
> age first equals your threshold and the clock is within 20 minutes past the hour. If you miss it,
> nothing raises it again; the on-screen Insulin Age pill will show URGENT for as long as the
> reservoir is overdue, and that pill is the thing to watch. **Do not describe this as a repeating
> or persistent alarm in the release notes** — someone who expects it to keep nagging will rely on
> something that will not happen. (On Pushover the notification is sent with the `persistent`
> sound; that is a Pushover sound name, not a promise that Nightscout repeats the alert.)
>
> This is not medical advice, and nothing here is guidance about insulin dosing. Nightscout is not a
> medical device and an alert is not a substitute for your own schedule for changing a reservoir.
> If you are unsure what reservoir-change interval is right for you, that is a question for your
> care team.

Also on this branch: an `ENABLE` entry that names a plugin's *file* (`ENABLE=cannulaage` instead of
`cage`) now prints a `console.warn` suggesting the right name, where before it was silently ignored;
and `POST /api/v1/alexa` / `/api/v1/googlehome` **stop honouring a per-request `locale`**, answering
in the server's configured language instead. That last one is a capability removal with no
replacement in the same changeset — it is why the branch classifies as major — and the removal is
correct, because the old code set process-global state so one assistant request re-languaged every
later request in the process.

**Why a human, specifically.** An alarm that has never fired starting to fire is the one change in
this batch that reaches someone at 3 a.m. It is the right fix and it is documented behaviour, but
"we restored a documented alarm" and "we added a new alarm" are the same event from the operator's
chair. The decision to accept that, and the wording of the release note, is a maintainer's, not an
agent's.

**One thing to look at while reviewing.** The fixed line is
`if (insulinInfo.age >= prefs.urgent)` (`lib/plugins/insulinage.js:91`), but the line under it is
unchanged: `sendNotification = insulinInfo.age === prefs.urgent` (`:92`), and the notification is
additionally gated on `prefs.enableAlerts && sendNotification && insulinInfo.minFractions <= 20`
(`:108`). The *level* is now correctly URGENT for as long as the reservoir is overdue, but the
*notification* is still gated on exact equality **and** on being within 20 minutes past the hour.
That matches how the three sibling plugins (`cannulaage`, `sensorage`, `batteryage`) behave, so it
is consistent rather than wrong — but it means the notification fires in one evaluation window and
not after. **Worth an explicit decision rather than an assumption, and the release-note wording
depends on it** (see the plain-language box above). Verified by reading these lines on the branch
during adversarial review; not executed.

**Test evidence:** the branch's `npm run test:unit` run was **346 passing / 7 failing** (GT1), and
all seven are attributed to the environment, not the code. Three grounds, **all three re-checked
during adversarial review on 2026-09-15**: (a) `mongod` on this worktree's configured port 27034 is
still not listening (`ss -ltn`; the live ports are 27017, 27018, 27019, 27023, 27031, 27032, 27033,
27044); (b) six failures are byte-identical to the `dev` baseline's mongo-down failures, and the
branch's diff touches only `lib/api/alexa/index.js`, `lib/api/googlehome/index.js`,
`lib/plugins/index.js`, `lib/plugins/insulinage.js` and their four test files — none of the failing
files and none of the code they exercise; (c) the seventh is a missing client bundle,
`node_modules/.cache/_ns_cache/public/js/bundle.app.js`, confirmed still absent in this worktree
only (`npm run bundle` there fixes it).

**The full CI-equivalent suite (`npm test`) has still not been run on this branch, and an attempt
during adversarial review did not close the gap.** Pointing the suite at a different live `mongod`
without touching the worktree's files produced 1707 passing / 25 failing, but the failures were
about the substituted environment — the same worktree is also missing
`node_modules/.cache/_ns_cache/randomString`, so the server bootstraps differently. **That run is
not evidence about the code and is not counted anywhere in this document.** Closing this gap
properly needs the worktree's own `mongod` on 27034 started and `npm run bundle` run there. See
§11.

---

### C — `bf/auth` · `64db1f35` · 2 commits · **⚠ NEEDS A HUMAN'S EXPLICIT YES**

| | |
|---|---|
| **Fixes** | BF-17 (plaintext token persisted), BF-30 (auth throttle bypass) |
| **Semver** | **major** — the storage allow-list discards unknown fields; the throttle change and the `notes` field are each minor |
| **Evidence** | register BF-17, BF-30 (both marked *reproduced live*) |
| **Approver** | **A maintainer, and ideally a second pair of eyes. This is security.** |

**What it fixes.** (1) Editing a subject through the stock admin UI **wrote that subject's API access
token into the database in plaintext**, into a field the server otherwise only derives. Anyone with
read access to the database got API access. (2) The failed-authentication delay was keyed on the
caller-supplied `X-Forwarded-For` header, so a client that rotated that header was never throttled —
brute-force guessing against `API_SECRET` and tokens ran unthrottled.

**The operator-visible change, in plain language:**

> Nothing you do changes. Two security holes close. **If any of your API tokens were written to the
> database in plaintext by editing a subject in the admin UI, this fix stops it happening again but
> does not undo it.** Tokens are derived from the subject's id, its name and your site's key, so the
> fix cannot invalidate a token that already exists. If you think a token may have been exposed,
> rotating it is your action, not the software's.

**Three things a reviewer must weigh, and the third is the sharp one:**

1. **The fix does not invalidate existing tokens.** Verified by reading `reload()`: `digest`,
   `accessToken` and `accessTokenDigest` are recomputed from `subject._id`, `subject.name` and the
   enclave key on every load. Rotation is the operator's action. **The PR must carry a remediation
   note saying which rotation options exist.**
2. **The throttle now keys on the socket peer address plus a salted credential digest.** Behind a
   shared proxy, failing clients share one bucket. The reason this is minor and not major: the sleep
   moved to the *failure* path and requests with no credential are never throttled, so **no request
   that successfully authenticates is ever delayed by another client's failures.** Verified by
   reading the diff.
3. **⚠ The subject/role storage becomes an allow-list, and the write is a `replaceOne`.** Measured
   by reading `lib/authorization/storage.js:50-51, 58, 138-158` on the branch:
   ```js
   var SUBJECT_FIELDS = ['name', 'roles', 'notes', 'created_at'];
   var ROLE_FIELDS    = ['name', 'permissions', 'notes', 'created_at'];
   function save (collection, fields) { … var doc = ownedFields(obj, fields);
                                        await collection.replaceOne({_id: doc._id}, doc, {upsert: true}); }
   ```
   **Scoped correctly — this was overstated in the first draft and is corrected here (adversarial
   review, 2026-09-15).** The data loss is *mostly pre-existing, not introduced by this branch*, and
   a reviewer needs the difference:
   - **Already true on `dev` today.** `origin/dev:lib/authorization/storage.js` `save()` is already
     `collection.replaceOne({_id: obj._id}, obj, {upsert: true})` on the caller's object, and
     `origin/dev:lib/authorization/endpoints.js:40` returns only
     `pick(subject, ['_id','name','accessToken','roles'])`. The stock admin UI
     (`lib/admin_plugins/subjects.js:35-53`) `PUT`s back exactly that object. **So on today's
     release, editing a subject in the admin UI already destroys `notes`, `created_at` and any
     third-party field.** `bf/auth` in fact *reduces* one case of this, by adding `notes` to the
     `GET` response and to the allow-list.
   - **What the branch newly removes** is a third-party tool's ability to *keep* its own fields by
     sending them in its own `PUT`: `ownedFields()` now strips anything outside the allow-list
     regardless of what the caller sent. Before, such a tool round-tripping its full document kept
     its fields; now it cannot store them through this API at all.
   **This is still the one change in the batch that a code revert cannot fully undo** (see §9) — but
   the honest question for the community is narrower than "do you run third-party tooling": it is
   *"does any third-party tool write extra fields to subjects or roles through
   `/api/v2/authorization/`, and does it depend on them surviving?"* Not reproduced against a real
   deployment, and no third-party tool was inspected.

Also: `GET /api/v1/subjects` gains a `notes` field (additive; it stops the admin edit dialog
blanking notes).

**Test evidence — GAP NOW CLOSED (adversarial review, 2026-09-15).** `npm run test:unit` on this
branch: **361 passing / 0 failing** (GT1, in the worktree with its own `my.test.env` on port 27031).
And `npm test` — the full `./tests/*.test.js` tree, which is what CI runs via `test-ci`, and which
on this branch is 161 files — **2047 passing, 3 pending, 0 failing, exit 0**, run today in
`externals/work/crm-bf-auth` against its own `mongod` on 27031 (server 7.0.43, driver 5.9.2). The
first draft of this document said no full-tree run existed for `bf/auth`; that is no longer true.
See §11.

---

### B — `bf/cache` · `4f86bab1` · 2 commits

| | |
|---|---|
| **Fixes** | BF-06 (fixed), BF-07 (**partly** fixed) |
| **Semver** | **patch** — identical bytes on the wire |
| **Evidence** | register BF-06/BF-07; `docs/60-research/t02-t03-cache-clone-2026-09-15.md` |
| **Approver** | ordinary review |

**Operator-visible:** the site gets faster under load and answers exactly the same. `/api/v1/entries`
untyped read measured at **0.837 ms → 0.025 ms**; the three cache calls in the load cycle at
**3.747 ms → 2.657 ms**. Both measured on this machine by the branch author's harness, not on a live
site — treat the *ordering* (much faster) as solid and the absolute numbers as machine-specific.

**Say this in the PR:** the T0.3 gate was `< 1 ms` and **it was not met** (2.657 ms). See §8.

Also removes a **dead write** at `lib/data/dataloader.js:204` on `origin/dev`
(`if (!element.mills) element.mills = element.date` on an array that is discarded), pinned by a test
that fails if the write returns. *(The line is **204**, not the 203 stated in the first draft;
`git show origin/dev:lib/data/dataloader.js | grep -n` puts it at 204. Corrected during adversarial
review.)*

**Test evidence — GAP NOW CLOSED (adversarial review, 2026-09-15).** `npm run test:unit`,
**371 passing / 0 failing** (GT1). And `npm test` (the full `./tests/*.test.js` tree, 160 files on
this branch) in `externals/work/crm-bf-cache`: **2040 passing, 3 pending, 0 failing, exit 0**, run
today against its own `mongod` on 27033. The first draft said no full-tree run existed for
`bf/cache`; that is no longer true.

---

### G — `bf/food` · `73495331` · 1 commit · **read this one first**

| | |
|---|---|
| **Fixes** | BF-16, and **BF-35** — the highest-severity defect in the batch |
| **Semver** | **minor** — a v1 response changes contents |
| **Evidence** | register BF-16, BF-35; sequencing document §2 carries the annotated source |
| **Approver** | ordinary review, but read the BF-35 explanation before approving |

**BF-35, in plain language:**

> In the bolus calculator, the drop-down list of saved quick picks was built from your whole food
> database but the selection was looked up in a shorter, filtered list. **So picking a quick pick by
> name could load a different record's food, and the carbohydrate total that went into the insulin
> calculation was not the one you chose.** Nothing told you. The list also offered plain foods that
> are not quick picks, and choosing one of the last entries threw an error. This has been present
> since October 2017.

Everything else in this batch returns a wrong answer to a query or fails to raise an alarm. **This
one puts a carbohydrate total the user did not choose into a bolus calculation, under a label they
did read.** It is the strongest argument in the batch for shipping rather than continuing to audit.

**BF-16** also lands: `/api/v1/food/quickpicks` filtered on the literal string `'false'`, so quick
picks written by a JSON client vanished from it; and `restoreBoolValue` in the editor turned a real
boolean `true` into `false`, silently un-hiding a hidden quick pick on every editor load.

**Two things whoever lands this must know:**

1. ~~**It deliberately does not create `CHANGELOG.md`.** That file does not exist on `a8888f0d`;
   both `bf/reads` and `bf/coercion` add it, and a third add would be a third add/add conflict.~~

   **REFUTED (adversarial review, 2026-09-15). Struck through, not deleted.** `CHANGELOG.md`
   **already exists on `origin/dev` (`a8888f0d`)** — `git ls-tree --name-only origin/dev
   CHANGELOG.md` returns it, and its `## [Unreleased]` section already carries the 15.0.9 entries.
   Neither `bf/reads` nor `bf/coercion` *adds* the file; they **append** to it
   (`git diff --numstat origin/dev <branch> -- CHANGELOG.md`: `bf/coercion` +40/-0, `bf/reads`
   +90/-0, where `bf/reads`' 90 contains `bf/coercion`'s 40 because it now contains that commit).
   The other six branches — `bf/alarms`, `bf/auth`, `bf/cache`, `bf/food`, `bf/merge`, `bf/parms` —
   do not touch the file at all. **There is no add/add conflict and there never was one**, and
   because `bf/reads` contains `bf/coercion` there is no conflict between those two either.

   **What survives, and it still needs doing:** `bf/food` carries **no `CHANGELOG.md` entry of its
   own**, and BF-35 is the highest-severity defect in the batch. Its release-note text is in the
   register. Adding it is an ordinary edit to the existing `## [Unreleased]` section — the only
   hazard is the usual one of two branches appending to the same section, which `git` resolves as a
   normal content conflict, not an add/add. **It needs an entry**: the quick-pick list changes both
   its contents and what selecting an entry does.
2. **A drift tripwire fires when this lands, and it is not a breakage.**
   `tools/nsschema/code_model.py`'s `SOURCE_ASSERTIONS` deliberately pins the quoted `'false'` in
   `lib/server/food.js`, so that fixing it *forces* the food model to be revisited.
   `make schema-code-drift` will fail the day this reaches the tooling repo's checkouts. What to
   replace the anchors with is written into BF-16.

**Test evidence — measured, and independently reproduced during adversarial review:** `npm test`
(the full `./tests/*.test.js` tree, which is what CI runs via `test-ci`; 161 files on this branch) in
`externals/work/crm-bf-food`: **2042 passing, 3 pending, 0 failing** — run twice, by two different
agents, same figures. This matters because **`npm run test:unit` never executes BF-35's test** —
`tests/boluscalc.quickpick.test.js` matches neither the `test:unit` nor the `test:integration` brace
list (GT1 verified this by regex-matching the name against both lists). A green `test:unit` on this
branch is not evidence for BF-35. A green `npm test` is.

---

### H — `bf/merge` · `b06c6faf` · 1 commit

| | |
|---|---|
| **Fixes** | BF-36 |
| **Semver** | **patch** — client only, no contract |
| **Evidence** | register BF-36 |
| **Approver** | ordinary review |

**Operator-visible:** *"Delete a treatment, then edit an older one, and the page stops updating until
you reload it."* The client's delta merge captured the cached array's length once and then spliced
that array, so a removal followed by a non-matching item read past the end and threw. The throw
escapes into `dataUpdate`, which has no `try`/`catch`.

**Severity is medium, not high, and the reason sets the batch's priority order:** the failure is
**not silent**. `updateClock` runs on its own timer chain, so the time-ago indicator keeps working
and visibly marks the page stale. *BF-35 tells you a wrong thing; BF-36 stops telling you things,
visibly.*

**Test evidence — measured, and independently reproduced during adversarial review:** `npm test`
(the full `./tests/*.test.js` tree, 160 files on this branch) in `externals/work/crm-bf-merge`:
**2040 passing, 3 pending, 0 failing**, exit 0 — run twice, same figures. *(The first draft recorded
this run as "2040 passing, 0 failing" and omitted the 3 pending that every other run in this
document reports; corrected.)* `tests/receiveddata.merge.test.js` is also in neither local brace
list, so the same caveat as `bf/food` applies to any `test:unit` result on this branch.

---

### I — `bf/parms` · `eb0bc918` · 3 commits

| | |
|---|---|
| **Fixes** | BF-37, BF-38, BF-39 |
| **Semver** | **patch** — client URL parsing and translation substitution |
| **Evidence** | register BF-37/BF-38/BF-39 |
| **Approver** | ordinary review |

**Operator-visible:** *"A link with a trailing `&`, or `?mute` instead of `?mute=true`, used to leave
you staring at 'Loading' forever."* `queryParms()` read `[1]` of each `key=value` split without
checking one existed, and it is the **first real statement of `client.init`** — so the page stopped
loading with nothing on screen but the loading message and a `TypeError` in a console nobody reads.
Fixed by reading a valueless parameter as the empty string, which is what both existing callers
already treat as absence.

Also: `%1` no longer eats `%10` in translations (latent — no shipped catalogue uses more than `%3`),
and `queryParms()` stops replacing `_` with a space, which was corrupting access tokens whose subject
name contains an underscore. **That corruption was measured to have no live effect** — `checkToken`
splits on `-` and matches the last segment, so the corruption landed entirely in the part nothing
reads. It is fixed because it is an accidental coupling that breaks the moment either end is
tightened, not because anything is broken today.

**⚖ One behaviour note for the release notes:** a bookmarked URL that relied on `_` being decoded as
a space will behave differently. GT4 classified this as patch and flagged it as the judgement call.

**Test evidence — measured, and independently reproduced during adversarial review:** `npm test`
(the full `./tests/*.test.js` tree, 160 files on this branch) in `externals/work/crm-bf-parms`:
**2035 passing, 3 pending, 0 failing**, exit 0 — run twice, same figures.
`tests/browser-utils.queryparms.test.js` is in neither local brace list, so the full-tree run is the
one that counts — `npm run test:unit` (362 passing, GT1) never executes BF-37's test.

---

### D — `bf/coercion` · `88d1f8a4` · 1 commit

| | |
|---|---|
| **Fixes** | BF-02, BF-11, BF-03 (devicestatus + profile), BF-32 |
| **Semver** | **minor** — filters that returned nothing start returning rows |
| **Evidence** | register BF-02/BF-03/BF-11/BF-32 |
| **Approver** | ordinary review. **Merge this before `bf/reads`.** |

**Operator-visible:** *"API queries that quietly returned an empty list now return your data."*
Filters were compared as text against numeric fields. **158** schema-driven coercions across five
collections (`devicestatus` 99, `treatments` 29, `entries` 20, `profile` 10, `activity` 0 — counted
today from `lib/server/query-coercion.json`) replace the hand-written `walker` entries, of which the
three regular-expression ones on `treatments` (`notes`, `eventType`, `enteredBy`) are deliberately
kept because they are search affordances, not type claims. Measured old-vs-new **during adversarial
review on 2026-09-15** by executing both versions of `lib/server/query.js` on the same inputs
(`origin/dev`'s copy extracted to a scratch directory, the branch's copy in place):

| query | before | after |
|---|---|---|
| `treatments?find[duration][$gte]=30` | `{"$gte":"30"}` — matched nothing | `{"$gte":30}` |
| `treatments?find[insulin][$gte]=1.5` | `{"$gte":1}` — rounded down | `{"$gte":1.5}` |
| `entries?find[sgv][$exists]=true` | `{"$exists":NaN}` — see the correction below; **on a real MongoDB this already returned the right documents** | `{"$exists":"true"}` |

That third row is BF-32, found while fixing the others: the old walker coerced operator *operands*
as if they were field values, so `find[sgv][$exists]=true` reached the driver as `{$exists: NaN}`.

> ### ⚠ CORRECTION — BF-32's stated impact does not survive contact with a real MongoDB
>
> **Measured during adversarial review, 2026-09-15, against two live `mongod` servers** (3.6.8 on
> port 27033 and 7.0.43 on ports 27019/27023/27031/27032, via driver 5.9.2), inserting
> `[{_id:1, sgv:100}, {_id:2}]` and running each operand spelling:
>
> | operand sent | real MongoDB returns | `mingo` returns |
> |---|---|---|
> | `true` (boolean) | `[1]` — has the field | `[1]` |
> | `false` (boolean) | `[2]` — lacks the field | `[2]` |
> | `"true"` (string) | `[1]` — has | `[1]` |
> | `"false"` (string) | `[1]` — **has** | `[1]` |
> | `NaN` | `[1]` — **has** | **`[2]`** |
>
> MongoDB's truthiness for a BSON double is `value != 0`, and `NaN != 0` is true, so the server
> treats `{$exists: NaN}` as `{$exists: true}`. JavaScript treats `NaN` as falsy, so `mingo` — the
> D8 differential-test oracle — does not. **Consequences for this branch:**
>
> 1. **`find[sgv][$exists]=true` was *not* returning "the documents that lack the field" on `dev`.**
>    `{$exists: NaN}` returned the documents that *have* it, which is the right answer, reached by
>    accident. The register's BF-32 wording, this document's earlier wording, and the
>    operator-facing sentence in `bf/reads`' own `CHANGELOG.md` ("which MongoDB reads as *false*, so
>    the query returned exactly the records you did not ask for") **are all wrong on this point**,
>    and the CHANGELOG one ships to operators. Raise it on the PR.
> 2. **There is no `$exists=false` inversion.** Both spellings produced `{$exists: NaN}` on `dev`
>    (verified by executing `origin/dev:lib/server/query.js`: the value is a literal `NaN` for both
>    `'true'` and `'false'`), and both therefore returned "has the field". After the branch both
>    return `"true"`/`"false"` as strings, and both still return "has the field". **Nothing
>    observable about `$exists` changes on MongoDB.** The open question §11 recorded — "is
>    `$exists=false` inverted by `bf/coercion`?" — **is now settled: no.**
> 3. **What BF-32 does still fix, and this part holds:** the other non-value operators on the ten
>    numeric walker-covered fields were being run through `parseInt`. Measured by executing both
>    copies of `query.js`: `find[sgv][$type]=number` reached the driver as `NaN` on `dev` and as
>    `"number"` on the branch; `find[sgv][$regex]=^1` as `NaN` on `dev` and as `"^1"` on the branch.
>    So the branch is right to stop coercing operands; only the *headline example* chosen for it was
>    wrong.
> 4. **A separate, pre-existing defect is exposed by this and is *not* fixed by the batch:**
>    `find[<any field>][$exists]=false` has never meant "lacks the field" anywhere in API v1 — the
>    string `"false"` is truthy to MongoDB, so it returns the documents that *have* it, on `master`,
>    on `dev`, and after this branch, on every field of every collection. It is described in the
>    notes handed up with this document as a proposed register entry with **no id allocated**.
> 5. **`mingo` is not a faithful oracle for non-boolean `$exists` operands.** Under D8 that matters
>    for the seam's differential tests, not for Phase 0, but it should be recorded.
>
> None of this changes whether `bf/coercion` should merge. The numeric and decimal rows above —
> which are the reason the branch exists — are unaffected and were re-checked.

**Test evidence.** Two runs, and the second is the one that counts. (1) `npm run test:unit` **on this
worktree**, **368 passing / 6 failing** — the six are environmental, not defects: `mongod` on this
worktree's configured port 27030 is not listening (confirmed by `ss -ltn`), the six failures are
byte-identical to the `dev` baseline's mongo-down failures (`verifyauth` ×4, `API_SECRET` ×2), and
the branch's diff touches none of those files. That run was not repeated; the port being down was
re-confirmed during adversarial review. (2) **This branch's commit is contained in `bf/reads`**, and
the full `./tests/*.test.js` tree was run there twice today, by two agents:
**2076 passing, 3 pending, 0 failing**, exit 0 both times. So `bf/coercion`'s code *is* covered green
by a full-tree run — as merged with `bf/reads`, not in isolation. See §11.

**Non-vacuity (GT1, measured):** `tests/query.test.js` from this branch cannot even load against
pristine `dev` code (`Cannot find module '../lib/server/query-coercion'`), so the test does
distinguish fixed from unfixed.

---

### E — `bf/reads` · `0d19bb31` · 8 commits (7 its own, **plus `bf/coercion`'s**)

| | |
|---|---|
| **Fixes** | BF-01, BF-05, BF-13, BF-14, BF-15, BF-33 |
| **Semver** | **major**, driven by one row — the `?count=` restriction |
| **Evidence** | register BF-01/BF-05/BF-13/BF-14/BF-15/BF-33 |
| **Approver** | ordinary review, **but the restriction needs a conscious yes** |
| **Base** | **`bf/coercion`, not `dev`** |

Six read-path fixes: a count endpoint that built its filter from the defaults and counted nothing;
v3 paging that lost and duplicated documents when the whole sort chain tied; a dotted `?fields=`
that answered `{}` with `200`; `?limit=0x10` that removed the v3 bound entirely; and a `console.log`
that printed every count request's filter *and its values* to stdout on the request path.

**⚠ The restriction — this is the only thing in the batch that can break a working integration:**

> Six previously-accepted spellings of `?count=` now return **HTTP 400**: `0`, `0x10`, `2.5`, `-3`,
> `1e2`, `abc`, plus any integer above `Number.MAX_SAFE_INTEGER`. `1`, `10`, `" 5 "`, absent and
> empty are unchanged.

GT4 measured this by executing the branch's `parseCount`/`hasCount` against an exact transcription
of the old code over 11 inputs. **Two details the branch's own CHANGELOG understates:**

- `?count=0` previously reached the driver as `.limit(0)`, which on MongoDB means **unbounded** —
  the whole collection. That is the defect. The other five spellings are the collateral.
- **The validator is `app.use`'d on the whole v1 app before every router**, so it applies to
  **writes as well as reads**. A `POST /api/v1/treatments?count=0` now returns `400` where it
  previously succeeded. The branch `CHANGELOG.md` lists read routes only.
  **This belongs in the release notes as a restriction, in those words.**

  **Coverage, enumerated in full from `lib/api/index.js` on the branch (read line by line during
  adversarial review; `validateCount` is `app.use`'d at line 51):** everything mounted *after* it is
  covered — `/entries*`, `/echo/*`, `/times/*`, `/slice/*`, `/count/*` (all five on the entries
  router), `/treatments*`, `/profile*`, `/devicestatus*`, `/notifications*`, `/activity*`,
  `/food*`, `/status*`, `/alexa*`, `/googlehome*`, plus the `verifyauth` and `adminnotifiesapi`
  routers mounted at `/`. **One route is NOT covered**, and the first draft did not say so:
  `app.use('/experiments', …)` is mounted at line 38, *before* the validator, so
  `/api/v1/experiments?count=0` keeps the old behaviour. That is the whole list — 15 mount points
  covered, 1 not.

**Ordering constraint inside the branch:** `1d0064bd` (BF-05, "Every count request printed its
filter…") must follow `af717c8f` (BF-01, "count/:storage/where counted nothing…") — they share two
files. The branch is already in that order. *(The first draft named `c8fb536b` and `4a398d47`; those
are the **pre-rebase** SHAs and exist only on the safety ref `bf/reads-prerebase`. `git branch
--contains` confirms neither is on `bf/reads`. Corrected during adversarial review.)*

**The merge-correctness step this pair gets and neither PR gets alone.** `bf/coercion` and `bf/reads`
both rewrite query construction and share six files under `lib/server/`. A clean textual merge is
not a correct merge. The known instance was that `aggregate.js` calls `query.js` and passed no
options, so the count path could stay untyped after two PRs that each looked complete. **On the
merged tree that is not what happens**: BF-01's fix delegates to each collection's own `query_for`,
and every one of those already names its collection, so coercion's `collection:` option reaches
`query.js` on the count path. **That chain was verified by reading it, and the suites pass — but
there is no end-to-end assertion that a numeric filter on `count/devicestatus/where` returns rows on
the merged tree.** That test does not exist. It is the one test worth adding, and until it exists
this paragraph is reasoning, not measurement.

**Test evidence — the strongest evidence in the batch, and now measured twice:** `npm test`
(the full `./tests/*.test.js` tree, 164 files on this branch) in `externals/work/crm-bf-reads`,
which is now the **merged D+E tree**: **2076 passing, 3 pending, 0 failing**, exit 0. Run once by
this document's author and **reproduced independently during adversarial review on 2026-09-15**,
same figures, and it also reproduces the figure the sequencing document reported.

*One provenance note, because this document's rule is that a number says how it was obtained:* the
additive arithmetic — base **2028** + `bf/reads` 35 + `bf/coercion` 13 = 2076 — rests on the base
figure **2028, which is quoted from `phase0-pr-sequencing-2026-09-15.md:503` and was NOT re-measured
by either agent.** No full-tree run of pristine `origin/dev` was made. The 2076 is measured; the
decomposition of it is inherited. If the additivity matters to your review, run `npm test` in a
worktree at `a8888f0d`.

*Operational note for whoever re-runs this:* the suite refuses to start if its test database holds
more than 100 entries ("Production safety check activated"). A suite run that is interrupted leaves
the database dirty and the next run halts. Let a run finish, or re-run with
`TEST_SAFETY_MAX_ENTRIES` raised for that invocation only.

Note what this run does and does not cover: it exercises `bf/coercion` **as merged**, so it is also
the only full-tree evidence for `bf/coercion`'s code in this batch. It does **not** cover the
end-to-end count-path assertion described above, which does not exist.

A safety ref `bf/reads-prerebase` = `824380a0` exists locally; delete it after the PRs merge.

---

### `bf/connect-pin` · `0807eb1c` · 1 commit · **gated on decision 2**

| | |
|---|---|
| **Fixes** | delivers BF-34, BF-08 and the three connector log-redaction commits to `dev` |
| **Semver** | **minor** — one line, but it is the vehicle for every connector change |
| **Evidence** | register BF-34, BF-08; `docs/60-research/gt4-semver-classification-2026-09-15.md` §6 |
| **Approver** | ordinary review, **after the tag is pushed and the lock regenerated** |

**Operator-visible, and it is counter-intuitive:**

> **After a Dexcom or CareLink outage, your glucose data will appear to come back more slowly than
> you are used to.** That is the fix. The connector was retrying a failing vendor 586× faster than
> configured, and every account was retrying in exact lockstep — which is the behaviour least likely
> to get you reconnected and most likely to get the pool rate-limited. Retries now honour the
> configured 2.5-minute interval, spread randomly, capped at 30 minutes.

**The measured precision, because the round number in circulation is imprecise:** the ratio is
**585.94× exactly** (150000 ÷ 256) at every attempt below the ceiling — not an average. The shipped
ceiling is **30 minutes**, not the five years an uncapped exponent would give, because
`lib/builder.js` supplies `max_interval_ms = expected_data_interval_ms × 6`. The load measurement:
100 actors delivered the same 800 requests **across 3 s before and 67 s after**, with the upstream
refusing authentication. *(Provenance: the 585.94× and the 30-minute ceiling are GT4's measurements
— `docs/60-research/gt4-semver-classification-2026-09-15.md` — and the 3 s → 67 s figure is T0.4's
author's, on this machine. Neither was re-measured for this document. Quote the direction with
confidence; quote the absolute numbers with the method attached. See §11.)*

Also delivered: start/interval jitter (both windows default `0`, so nothing changes for anyone who
does not set them), and **three log-redaction commits that keep Dexcom and MiniMed credentials,
sessions and patient data out of runtime logs**. See §2 for why `dev` does not have those today.

**Test evidence — re-run during adversarial review, 2026-09-15:** the connector's own suite
(`npm test` = `node --test`) in `externals/work/nc-jitter`: **tests 135, pass 135, fail 0**. That
worktree is `fix/connect-timer-jitter` at `c1cce2a`, and `git diff --stat c1cce2a release/v0.0.14`
is `package.json` + `package-lock.json`, version bump only — so the run covers exactly the code the
tag ships. The 19 new tests and the revert-each-part-in-turn non-vacuity check are T0.4's author's
work, not re-done here.

The `cgm-remote-monitor` side is a one-line `package.json` change with no test of its own, and
**`bf/connect-pin`'s worktree has no `node_modules` and no `my.test.env`, so no `cgm-remote-monitor`
suite has been run there at all.** That is fine — it is one line — but do not read a green tick that
does not exist.

---

## 6. The fork-route trap

If you push branches to your fork rather than to `origin`, one workflow can eat a PR.

`.github/workflows/close-accidental-sync-prs.yml` runs on `pull_request_target: types: [opened]` and
**auto-closes the PR when all three of these hold**, read verbatim from the script:

```js
const isFromFork   = baseRepo !== headRepo;
const isLikelySync = /\b(sync|merge|update|pull|new)\b/i.test(pr.title || "");
const isEmptyPR    = pr.changed_files === 0 && pr.additions === 0 && pr.deletions === 0;
if (![isFromFork, isLikelySync, isEmptyPR].every(Boolean)) { return; }
```

**A real PR is never auto-closed, because the third condition fails** — every branch in this batch
has a non-empty diff. But several of the most natural titles for this work contain those words:
*"Merge the read-path fixes"*, *"Update the connector pin"*, *"New quick-pick chooser fix"*. **If a
PR ever vanishes with a polite comment about syncing your fork, that is why** — reopen it and
rename it. Pushing to `origin` instead of a fork avoids the condition entirely.

---

## 7. Why the review gate exists

Stated once, because it is load-bearing and not a lecture.

**Two prescribed fixes in the backfix register turned out to be wrong when someone actually ran
them** (BF-14's prescribed fix was itself defective and copying it would have spread an unbounded
read; BF-30's preferred fix measured as a net regression), and **at least seven register entries
have carried a claim that did not survive contact with running code.** The register's own header
names five — **BF-12** (a mis-transcription: the walker coerces `rssi`, not `rawbg`), **BF-31**
("reaches alarm text" — it does not; the catalogue is read once at boot), **BF-14**, **BF-16** (the
"wrong order in the built-in editor" half: real, and reached nobody, because the endpoint it named
has no in-tree consumer), and **BF-03** (`food` never reaches `query.js`; `activity` has no numeric
field). Its own §1 table flags two more the header omits: **BF-08** ("the interval half of this
entry was wrong") and **BF-30**. GT3 counted the same seven.

**Make that eight.** This document's own adversarial review added one: **BF-32**'s stated impact —
that `{$exists: NaN}` "returned exactly the documents that lack the field" — is false against a real
MongoDB, where `NaN != 0` makes it read as `true` (§5, branch D). That one was caught only because
someone ran it against a server instead of reasoning about JavaScript truthiness, and the wrong
version of it is currently in operator-facing `CHANGELOG.md` text on `bf/reads`.

*Two cautions about the sentence that usually follows this one.* The register asserts "not one entry
that began with a reproduction has had to be retracted" — that is the register's own claim and was
not independently checked here, and GT3 found three entries (BF-17, BF-30, BF-31) whose provenance
markings contradict themselves, a prepended "reproduced" block above a body that still reads "not
reproduced". And "two of **five**" prescribed fixes: the denominator is inherited from the briefing
and was not verified. Review is where reading-derived confidence meets running code, and in this
programme that meeting has changed the answer often enough to be the point of the exercise.

The corollary is mechanical: **`dev` and `master` are publication events, not branches.** A push to
either pushes a Docker image (§4). Treat a merge as shipping, because it is.

---

## 8. Known-incomplete — so nothing surprises you later

**These are deliberate, not oversights. Each has a reason on the record.**

1. **T0.3's gate was not met, and the remainder was left on purpose.** The gate was "the three cache
   calls in the load cycle cost < 1 ms"; measured result is **2.657 ms**, down from 3.747 ms.
   **2.6 ms of the remaining 2.66 ms is `devicestatus`**, whose caller rewrites `uploaderBattery`
   into `uploader` on every document, and whose `mergeProcessSort` writes `_id` and `mills` on top,
   on documents that then live in `ddata` for the life of the process. Taking that clone away means
   **proving no consumer anywhere in the plugin tier writes to a device-status document — and a grep
   is not that proof.** `entries` and `treatments` were taken (0.845 → 0.035 ms and
   0.397 → 0.017 ms); `devicestatus` keeps its clone. **`bf/cache`'s PR description must say the
   gate was not met and why**, or it will read as a completed optimisation.
2. **The `aggregate.js` follow-up is RESOLVED by the combination, but its test does not exist.** The
   prediction was that `bf/coercion` and `bf/reads` could both land clean and leave the count path
   untyped. On the merged tree they compose correctly (§5, branch E). **What is missing is an
   end-to-end assertion that a numeric filter on `count/devicestatus/where` returns rows.** Until
   someone writes it, "the two fixes compose" is read-derived reasoning. It needs **both D and E
   merged** to be testable at all.
3. **The limit rule is written twice, on purpose.** `lib/server/count.js` and v3's `parseLimit` each
   carry their own copy, so that each commit could land alone. **Unify them afterwards.** This is a
   debt with a name: *two readings of one rule is the root cause of this entire family of defects* —
   BF-14 and BF-33 are the same bug in two dialects. Leaving it duplicated through the merge is the
   right call; leaving it duplicated after is not.
4. ~~**`CHANGELOG.md` is added by two branches and not by the third that needs it.**~~ **REFUTED —
   see §5 branch G.** `CHANGELOG.md` **already exists on `origin/dev`**; `bf/coercion` and
   `bf/reads` append to it (+40 and +90 lines), the other six branches do not touch it, and there
   is no add/add conflict anywhere. **What still needs doing is unchanged and is the point:
   `bf/food` carries no `CHANGELOG.md` entry, and BF-35 is the highest-severity defect in the
   batch. Its release note has to be written into the existing `## [Unreleased]` section by hand.**
5. **A schema-drift tripwire will fire when `bf/food` lands** (§5, branch G). It is a deliberate
   anchor, not a breakage.
6. **Four other follow-ups are recorded and not in these PRs:** `plugins.isPluginEnabled` always
   returns `true` (no caller, so no register id); a second unguarded `console.log` on a request path
   in `lib/authorization/storage.js` (line **113**, not the `:84` the register cites — I confirmed
   113 on `bf/auth`); the `alexa` `switch` has no `default`, so an unrecognised `request.type` calls
   neither `res.json` nor `next()` and the request hangs until the client times out (it sits beside
   a line `bf/alarms` already changes, so **it should land with that branch**); and BF-04 needs
   *extraction* from the seam branch rather than a fresh fix.
7. **After these land, `origin/dev` moves**, so `chore/nightscout-modernization` and the seam branch
   both need a refresh before more tenancy work.

---

## 9. If something goes wrong after merge — rollback, per branch

**The general shape.** Every branch is a small number of commits on `dev`, merged by PR. A revert is
`git revert -m 1 <merge-commit>` on a branch, then a PR back into `dev`. **Do not push the revert
straight to `dev`** — that is still a publication event and still pushes an image (§4). The revert
goes through the same PR path as the merge did.

**Per branch, what a revert actually gets you:**

| branch | reverting is… | what a revert does NOT undo |
|---|---|---|
| `bf/cache` | **clean and safe** | nothing — no wire format, no schema, no persisted state. The safest revert in the batch. |
| `bf/merge` | **clean and safe** | nothing — client-only code, no persisted state |
| `bf/parms` | **clean and safe** | nothing — client-only URL parsing |
| `bf/food` | **clean**, but see right | nothing persisted, **but** the schema-drift anchors (§8.5) have to be reverted with it or `make schema-code-drift` stays red in the tooling repo |
| `bf/coercion` | **clean** | nothing persisted. Reverting restores the old wrong answers: numeric and decimal filters go back to matching nothing or being rounded down. (It does **not** restore an "inverted `$exists`" — there was never one; see §5 branch D.) |
| `bf/reads` | **clean**, but **order matters** | it contains `bf/coercion`'s commit. Reverting the `bf/reads` merge reverts coercion too unless coercion was merged separately first. **Merge `bf/coercion` as its own PR so the two can be reverted independently.** |
| `bf/alarms` | **clean** code-wise | **an operator who received the new URGENT notification has already received it.** A revert stops future ones; it cannot un-ring a phone. If the alarm turns out to be unwanted, the honest remedy is a release note and a settings answer, not a silent revert |
| **`bf/auth`** | ⚠ **clean code, IRREVERSIBLE DATA** | **the storage allow-list is a `replaceOne` (§5, branch C). Any field outside the allow-list that a third-party tool stored on a subject or role, and that was dropped while the fix was live, is gone; reverting the code does not bring it back.** Read §5 branch C for the scope: an admin-UI edit **already** destroys such fields on today's `dev`, so what this branch newly removes is a third-party tool's ability to preserve its own fields by sending them in its own `PUT`. Still the only one-way change in the batch. If you have any doubt about third-party subject tooling, the time to resolve it is *before* the merge, not after |
| `bf/connect-pin` | **clean** — revert the one-line pin **and** the regenerated lock together | **the pushed `v0.0.14` tag stays pushed** and, if you published, the npm version stays published. Reverting the pin moves `dev` back to `234d47c8`; it does not unmake the release |

**If the connector release itself is wrong after the tag is pushed:** do not move or delete the tag.
Cut `v0.0.15` and move the pin. A tag other people may have fetched is part of the public record.

**A rollback you will not need but should know exists:** the merge order is unconstrained except for
`bf/coercion` before `bf/reads`, and all 36 pairs merge cleanly (§5), so a revert of any one branch
does not conflict with the others.

### 9a. How you would NOTICE — the failure modes here are quiet

**A revert you never trigger is worthless.** Most of what this batch touches fails *silently*: a
query answers `200 OK` with the wrong rows, an alert does not arrive, data stops being written
without anything turning red. This is the list of observable symptoms, so that an operator report
can be matched to a branch instead of being absorbed as "Nightscout being odd".

| if an operator reports… | suspect | first check |
|---|---|---|
| "my glucose data stopped arriving" or "there is a gap since the upgrade" | `bf/connect-pin` / connector `v0.0.14` | Is the gap *after a vendor outage*? Slower recovery is the intended fix (§5). A gap with **no** outage is not — check the connector log for retry lines and the last `entries` timestamp |
| "my uploader/script started getting errors", HTTP `400 Bad count` | `bf/reads` | Search the access log for `?count=` values that are `0`, `-3`, `2.5`, `1e2`, `0x10` or non-numeric. This is the one *intended* new rejection |
| "a report or dashboard now shows far more (or fewer) rows than it did" | `bf/coercion` (+`bf/reads`) | Expected: filters that used to match nothing now match. Decimal bounds are no longer rounded down, so a `$gte=1.5` bound now **excludes** 1.0-unit boluses it used to include |
| "the page stopped updating / the time-ago stopped advancing" | `bf/merge` | Browser console for a `TypeError` out of `dataUpdate`. This one is *visible*: the time-ago indicator keeps running and marks the page stale |
| "the page never finishes loading, just says Loading" | `bf/parms` | The URL. A bare flag or a trailing `&` is the trigger. Browser console shows a `TypeError` on the first statement of `client.init` |
| "a bookmarked link stopped working" | `bf/parms` | Underscores in the query string are no longer turned into spaces |
| "a quick pick loads the wrong food / wrong carbs" | `bf/food` | **This is what the batch fixes.** If it is reported *after* the merge, that is a regression and is the highest-priority report in the batch |
| "I got an insulin-reservoir alert I have never seen" | `bf/alarms` | Expected; see §5 branch A. It fires once, not repeatedly |
| "my Alexa/Google Home replies switched language" | `bf/alarms` | Expected: per-request locale is gone, replies use the server's configured language |
| "our admin tool's extra fields on a subject disappeared" | `bf/auth` | §5 branch C. **Not recoverable by reverting** |
| "everything is slower / nothing changed" | `bf/cache` | Byte-identical responses by design; a *behaviour* change here would be a bug |

**Two silent ones worth watching for deliberately, because nobody will report them:**

1. **A count or a filter that answers `200` with the wrong rows.** Nothing logs this. If you have a
   site you can query, run one numeric filter (`/api/v1/treatments.json?find[duration][$gte]=30`)
   and one count (`/api/v1/count/entries/where`) before and after the merge and keep both answers.
2. **`npm ci` going red on `bf/connect-pin`.** That is the *designed* failure (§3) and it is loud —
   but only until someone "fixes" it. If the lock stops being red without the tag having been
   pushed, something has invented a hash. Check `package-lock.json`'s `integrity` against the
   tarball GitHub actually serves.

**None of the above is medical advice, and none of it is guidance about anyone's therapy.** If a
data gap or a missing alert affects how someone is managing their own or a family member's diabetes,
the right next step is their care team, not a release note.

---

## 10. Suggested merge order

There is no technical requirement beyond D-before-E, but this order front-loads the review that
matters and keeps the two decisions needing an explicit yes separate from everything else:

1. **`bf/food`** — highest severity, one commit, smallest thing to read
2. **`bf/parms`**, **`bf/merge`**, **`bf/cache`** — self-contained, low blast radius
3. **`bf/coercion`**, then **`bf/reads`** — in that order, with the merged-tree check from §5
4. **`bf/alarms`** — after an explicit maintainer yes and the alarm release note is drafted
5. **`bf/auth`** — after an explicit maintainer yes and the third-party-tooling question is answered
6. **`bf/connect-pin`** — last, after the tag is pushed and the lock regenerated

---

## 11. What has NOT been verified — read this before trusting a green tick

**I am being explicit here because two things in this programme have already gone wrong by treating a
green suite as evidence.**

### Which suites were actually run, and on what

`npm test` runs `./tests/*.test.js` — **every test file in the tree**, the same glob CI runs via
`test-ci` (`test-ci` differs only in using `tests/ci.test.env` and wrapping mocha in `nyc`). On
`origin/dev` that is **159 files**; the branches add their own, so it is 160 on `bf/alarms`,
`bf/cache`, `bf/merge` and `bf/parms`, 161 on `bf/auth` and `bf/food`, 159 on `bf/coercion` and 164
on `bf/reads` (counted today with `git ls-tree`). `npm run test:unit` and `npm run test:integration`
are **brace lists** resolving to **44 and 89 files** respectively, union **107**, leaving **52 files
matched by neither** (GT1 expanded both lists with `shopt -s nullglob` on a worktree at `a8888f0d`
and counted).

**Four of those 52 unmatched files are the evidence for this very batch:**
`tests/boluscalc.quickpick.test.js` (BF-35), `tests/receiveddata.merge.test.js` (BF-36),
`tests/browser-utils.queryparms.test.js` (BF-37) and `tests/dataloader.test.js`. **A green
`npm run test:unit` is not evidence that BF-35's fix works.** Use `npm test`.

| branch | suite run | result | by whom |
|---|---|---|---|
| `bf/food` | **`npm test` (full tree)** | **2042 passing, 3 pending, 0 failing** | author, **and reproduced by adversarial review** |
| `bf/merge` | **`npm test` (full tree)** | **2040 passing, 3 pending, 0 failing** | author, **and reproduced by adversarial review** |
| `bf/parms` | **`npm test` (full tree)** | **2035 passing, 3 pending, 0 failing** | author, **and reproduced by adversarial review** |
| `bf/reads` (= merged D+E) | **`npm test` (full tree)** | **2076 passing, 3 pending, 0 failing** | author, **and reproduced by adversarial review** |
| `bf/auth` | **`npm test` (full tree)** | **2047 passing, 3 pending, 0 failing**, exit 0 | **adversarial review, today** |
| `bf/cache` | **`npm test` (full tree)** | **2040 passing, 3 pending, 0 failing**, exit 0 | **adversarial review, today** |
| `bf/coercion` | `npm run test:unit` on the branch alone | 368 passing / **6 failing — environmental**. Its code is separately covered green by the `bf/reads` full-tree run above, which contains it | GT1 (+ via `bf/reads`) |
| `bf/alarms` | `npm run test:unit` only | 346 passing / **7 failing — environmental**. **No valid full-tree run exists** — an attempt during adversarial review, pointed at a substituted `mongod`, produced 1707/25 and is discarded as an environment artefact (§5 branch A) | GT1 |
| `bf/connect-pin` | **none — cannot be run** | no `node_modules`, no `my.test.env` in that worktree | — |
| the connector | its own suite (`node --test`) | tests 135, pass 135, fail 0 | T0.4's author, **and re-run by adversarial review today** |

**Why the integration suite was not re-run everywhere.** The worktrees each point at their own
`mongod` (`my.test.env` names ports 27030–27034, 27018, 27117; where a port is shared the database
name differs), so they are better isolated than the programme's own warning claims — but **two of the
configured `mongod` instances are not running on this machine right now** (ports 27030 for
`bf/coercion` and 27034 for `bf/alarms` are absent from `ss -ltn`; re-checked during adversarial
review). Running the full suite on those two branches would produce failures that are about this
machine, not about the code — an attempt to substitute another `mongod` for `bf/alarms` demonstrated
exactly that. Running several full integration suites concurrently against shared instances is
exactly the interference this programme has already been bitten by.

**And a caveat nobody in this programme has written down: the local `mongod` servers are not the
ones CI or operators use.** Measured today via `serverStatus()`: ports 27017, 27033 and 27044 are
**MongoDB 3.6.8**; ports 27019, 27023, 27031 and 27032 are **7.0.43**. CI's matrix on `dev` is
MongoDB **4.4, 5.0 and 6.0**, and `docker-compose.yml` on `dev` ships **4.4**. So every green figure
in the table above was obtained on a server version that neither CI nor a stock self-hoster runs.
Nothing in this batch is obviously version-sensitive, but a green local suite is **not** a
prediction of a green CI matrix.

**So, precisely:** `bf/alarms` has **no valid full-tree run at all**. `bf/coercion` has no full-tree
run *in isolation*, but its single commit is contained in `bf/reads`, whose full-tree run is green
and was made twice — so coercion's code is covered as merged, which is how it will ship. For both
branches, the `test:unit` failures are **attributed** to the environment on three grounds, all three
re-checked during adversarial review: the configured port is demonstrably not listening, the failing
files are byte-identical to the `dev` baseline's mongo-down failures, and neither branch's diff
touches those files or the code they exercise. **That is a strong attribution, not a measurement.**
*CI will settle it.*

**Revised from the first draft:** the branches with no full-tree run of their own are now **two**,
not four — `bf/alarms` and `bf/connect-pin`. `bf/auth` and `bf/cache` were run to completion during
adversarial review (2047/3/0 and 2040/3/0, both exit 0). **`bf/alarms` is still one of the two
branches needing an explicit human yes, and it is still the one with the weakest test evidence in
the batch.** Starting its `mongod` on 27034 and running `npm run bundle` in that worktree would
close it in about two minutes.

### Claims in this document that are inference, not measurement

- **"The two fixes compose correctly on the merged D+E tree."** Verified by reading the call chain;
  no end-to-end test asserts it (§8.2).
- **"`bf/auth` does not invalidate existing tokens."** Verified by reading `reload()`; not
  reproduced against a real deployment.
- **"The `bf/auth` allow-list drops third-party fields."** Verified by reading `SUBJECT_FIELDS`,
  `ownedFields()` and the `replaceOne` call. Not reproduced against a real deployment, and **I do not
  know whether any third-party tool actually stores extra fields.**
- **"`bf/alarms`' seventh unit failure is a missing bundle, not a defect."** GT1 read the failure
  text; adversarial review re-confirmed today that
  `node_modules/.cache/_ns_cache/public/js/bundle.app.js` is absent in that worktree.
- **"`bf/alarms`' fixed alarm fires once, in one evaluation window."** Verified by reading
  `lib/plugins/insulinage.js:91-115` on the branch. **Not executed.** This is the claim the
  operator-facing release note depends on, so it is the one worth running before the note ships.
- **"The two `bf/coercion` + `bf/reads` composition claims about `api.query_for`."** Verified by
  reading `lib/server/aggregate.js` and the five `collection:` declarations on the merged tree.
  No test asserts it end to end.
- **"Base 2028" in the additive arithmetic for `bf/reads`.** Quoted from
  `phase0-pr-sequencing-2026-09-15.md:503`; no full-tree run of pristine `origin/dev` was made by
  anyone. The 2076 total is measured; its decomposition is not.
- **All performance figures** (`0.837 → 0.025 ms`, `3.747 → 2.657 ms`, `3 s → 67 s`) were measured on
  this machine by their branch authors' harnesses, **not on a live Nightscout site.** Across four
  measurement passes in this programme the *ordering* of options has been stable while the absolute
  figures moved. Quote the direction with confidence; quote the absolute numbers with the method
  attached.
- **CI state at any branch tip has not been checked.** No network calls were made. Nothing in this
  batch has been through GitHub Actions even once.

### Things I could not settle at all

See the open questions handed up with this document.

**One of the three has since been settled and is struck out here rather than removed:**
~~whether `$exists=false` is inverted by `bf/coercion`~~ — **settled: it is not.** Measured against
live `mongod` 3.6.8 and 7.0.43, `{$exists: NaN}` returns the documents that *have* the field, so
neither `$exists=true` nor `$exists=false` changes observable behaviour across this branch, and the
register's BF-32 wording is wrong in the other direction. Full working in §5, branch D.

**The two that remain, and they do affect a merge decision:**

- whether any third-party tool writes extra fields to subjects or roles through
  `/api/v2/authorization/` and depends on them surviving (only the community knows — and note from
  §5 branch C that a stock admin-UI edit already destroys them today);
- whether `nightscout-connect` is currently published on npm at all (no network egress from this
  machine). This only affects decision 3, which §2 shows does not gate the batch.

---

## 12. Corrections to other documents in this repository

Recorded here, **not applied** — a later reconciliation pass owns those files, and concurrent edits
to long shared documents is a failure mode this programme has already hit.

1. **`phase0-pr-sequencing-2026-09-15.md:409` and `:421`** state that `master` (15.0.8) depends on
   `nightscout-connect` as `"^0.0.12"` from npm, and concludes that "none of this reaches a current
   operator without an `npm publish`." **Both are wrong.** `git show origin/master:package.json`
   line 139 reads
   `https://github.com/nightscout/nightscout-connect/archive/refs/tags/v0.0.13.tar.gz`, and
   `origin/master:package-lock.json` agrees. The `^0.0.12` was replaced by commits `a91e8ee4` and
   `561974de` ("fix(connect): install 0.0.13 from public tarball"). The `^0.2.12` that does appear on
   `master` is `share2nightscout-bridge`, a different package. **There is no npm-range pin anywhere
   in the tree**, `master` is already on `v0.0.13`, and the tag push — not the npm publish — is what
   delivers the connector fixes.
2. **Same document, same table**, "three pinning mechanisms": there are **four** in flight.
   `chore/mime-exposure-review` (cut 4) pins `c962a13f`, which appears in no programme document.
3. **Same document, §3**: the `bf/coercion` + `bf/reads` `CHANGELOG.md` conflict and the
   "rebase E onto D" instruction are both **stale** — the rebase is applied and `bf/reads` is
   `0d19bb31`. **Note on the reason:** the conflict is gone because `bf/reads` now *contains*
   `bf/coercion`, not because an add/add was resolved — `CHANGELOG.md` already exists on
   `origin/dev` and neither branch adds it (§5 branch G). The trial-merge matrix at §1 covers 6
   pairs; the **full 9-branch matrix — all 36 unordered pairs, `bf/connect-pin` included — is
   clean**, measured during adversarial review on 2026-09-15, so the prose claims of "clean against
   all six"/"all seven" now have a matrix behind them.
4. **Same document, §2, branch I**: the `bf/parms` commit order is given as
   `522c6ffb`, `eb0bc918`, `c9a7a21c` mapped to BF-37, BF-39, BF-38. The actual branch order is
   `522c6ffb` (BF-37), `c9a7a21c` (BF-38), `eb0bc918` (BF-39).
5. ~~**Same document, §0 table**: "PRs *targeting* `chore/nightscout-modernization` run full CI
   (`main.yml` and CodeQL both list it under `pull_request`)" — **CodeQL does not.**~~
   **WITHDRAWN — this "correction" was wrong; the sequencing document is right.** Struck through
   rather than deleted. `origin/chore/nightscout-modernization:.github/workflows/codeql-analysis.yml`
   line 19 reads `pull_request: branches: [ dev, master, chore/nightscout-modernization ]`. Only its
   `push:` list (line 17) is `[ dev, master ]`. **Nothing in `phase0-pr-sequencing-2026-09-15.md:36`
   needs changing.** See §4.
6. **`nightscout-backfix-register.md`, BF-05 detail**: the unfixed sibling `console.log('Loading', opts)`
   is at `lib/authorization/storage.js:113`, not `:84`. Confirmed present on `bf/auth` today.
7. **`nightscout-backfix-register.md`, BF-32, and `bf/reads`' own `CHANGELOG.md`**: the claim that
   `{$exists: NaN}` is read by MongoDB as `false` and "returned exactly the records you did not ask
   for" is **wrong**. `NaN != 0`, so the server reads it as `true`. Measured against live `mongod`
   3.6.8 and 7.0.43 (§5, branch D). The `CHANGELOG.md` copy is **operator-facing text on a branch
   that is about to be proposed for merge**, so it should be fixed on the branch, not only in the
   register. The comment in `lib/server/query-coercion.js:25-26` on `bf/coercion`
   ("`$exists` it inverts the result, because NaN is falsy…") states the same wrong reasoning and
   should go with it.
8. **`nightscout-backfix-register.md`, §5 branch G's schema tripwire**: confirmed, not a correction —
   `tools/nsschema/code_model.py:135-136` pins both `['"]hidden['"]\s*[,:]\s*['"]false['"]` in
   `lib/server/food.js` **and** `record[key] = record[key] === 'true';` in `lib/food/food.js`, and
   `bf/food` changes both lines. So `make schema-code-drift` fails on **two** anchors when this
   lands, not one.
9. **The register's own legend is the most important correction and it is not a typo.** `fixed` means
   *"repaired on a backfix branch — NOT YET MERGED."* No entry anywhere has status `landed`, and
   nothing in this batch has been pushed. So the widely-repeated sentence *"only three open register
   entries reach an operator on today's release"* is true of the register's bookkeeping and **false
   of operators**: on today's release, all 26 §1 defects are present for every self-hoster. Any
   document that uses the open/fixed column as a measure of operator exposure is mis-sizing this
   release by an order of magnitude. **That is the argument for shipping this batch.**

---

**Draft status.** This document is a draft prepared for maintainer review. It is not a regulatory,
legal or clinical artefact, and the release notes derived from it are user-facing and must be written
in plain language with every safety caveat preserved. Nothing in it is medical advice; operators with
questions about their own therapy should consult their care team.
