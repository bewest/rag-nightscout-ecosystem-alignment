# Consolidating how cgm-remote-monitor depends on nightscout-connect

**Status: DRAFT for maintainer review.** Nothing in this document has been executed.
Every command in section B is marked as something a **human** runs, and none of them has
been run. No branch, tag or lockfile was modified in preparing it. No network call was
made; the two npm experiments in section C ran offline against locally built tarballs.

**Audience:** maintainer and contributors. Section D.5 is the only operator-facing part and
is written in plain language; the rest is deliberately technical.

> **ADVERSARIAL VERIFICATION PASS, 2026-09-15, main repo HEAD `08753474`.** A second agent
> re-measured this document's load-bearing claims from the repositories rather than from the
> text. **Reproduced independently and confirmed:** the pin/override table for all seven refs;
> the `console.*` census (112/101, 108/44, 22/20, 22/20, 22/20) using a separately written
> comment-and-literal-stripping scanner; the `^0.0.12`/`^0.0.13`/`~0.0.12`/`^0.1.0` comparator
> sets and match matrix under semver 6.3.1; `1.16.0` failing `^1.18.1`; the ancestry results
> including `b394411` not being an ancestor of `234d47c` and its tree being identical to
> `6dfc4f0`; the 11-commit / 7-non-merge count; the reachability argument for v0.0.14's
> residual sites (`index.js` hardcodes `{name:'internal'}`, `config.capture` is never passed);
> the absence of publish automation and of a `files` field; the Dockerfile's
> `npm ci --cache /tmp/empty-cache --omit=optional --force`; and **every row of §C's npm
> table**, re-run over a loopback HTTP server rather than offline file tarballs — including
> the row-2 silent wrong install (exit 0, `demo-pkg/package.json` says `0.0.13`) and the
> verbatim EUSAGE text. **Corrected:** five items, each marked inline with `VERIFIER` and left
> in place rather than deleted — the "fourteen months" interval (§0.1), "safest of the three"
> (§0.2), cut 4's LibreLinkUp site count (§0.2), §C's claim that R3 catches the hand-edited
> lock, and §F.1's "and vice versa" for R4. **Added:** the boot-time credential leak and
> Glooko to §D.4 with a measured coverage statement, a one-way-door and rollback subsection
> and a silent-failure watch list to §B, and a how-to-check plus what-to-expect passage to the
> operator note in §D.5.

**Date of measurement:** 2026-09-15. Main repo HEAD `08753474`.
`externals/cgm-remote-monitor-official` `origin/dev` = `a8888f0d`, `origin/master` = `92d08342`.
`externals/nightscout-connect` `origin/main` = `b394411` (= tag `v0.0.13`).
Every number below says how it was measured. Where I am reasoning rather than measuring it
says INFERENCE.

---

## 0. Read this first: three premises of the task were wrong

This document was commissioned on a description of the problem that measurement does not
support. Two of the three corrections change what the maintainer should do, and the third
changes *why* — which matters, because the "why" is going into a commit message and a PR
that reviewers will rely on.

### 0.1 master does not depend on a semver range. There is no npm range anywhere.

The brief, and `docs/30-design/phase0-pr-sequencing-2026-09-15.md:388`, say master pins
`"^0.0.12"` — an npm range. It does not.

```
origin/master:package.json
  "nightscout-connect": "https://github.com/nightscout/nightscout-connect/archive/refs/tags/v0.0.13.tar.gz"
```

Measured with `git show origin/master:package.json` parsed as JSON. `^0.0.12` was adopted
in October 2023 and replaced on **2026-07-07** — about two months before this measurement,
not fourteen months (VERIFIER CORRECTION; the original text mis-stated the interval) — by
two commits:

| commit | date | change |
|---|---|---|
| `97a603fb` | 2023-10-12 | `^0.0.11` → `^0.0.12` (the last npm-range pin) |
| `a91e8ee4` | 2026-07-07 | `^0.0.12` → `github:nightscout/nightscout-connect#v0.0.13` |
| `561974de` | 2026-07-07 | → `.../archive/refs/tags/v0.0.13.tar.gz` |

Measured with `git log -L '/nightscout-connect/,+1:package.json' origin/master`.

`561974de`'s own message records why the `github:` shorthand was abandoned, and it is a
constraint on the end state, so it is quoted here in full:

> Avoid locking the nightscout-connect GitHub dependency to git+ssh so release and deploy
> builds without GitHub SSH keys can install the package.

The `^0.2.12` that *does* appear on master is `share2nightscout-bridge`, a different
package. The two were probably conflated.

**Consequences.** master is already on v0.0.13, not something two releases stale. The
"three pinning mechanisms" are really **one mechanism (a GitHub archive tarball) used with
two kinds of ref** — a tag, or a bare commit — plus a fourth axis nobody has written down
(§0.3). And the crux question the brief asked me to get exactly right is moot for master.
I answer it anyway in §1.3, because it decides whether "publish to npm" is a viable end
state.

### 0.2 dev's pin is not missing the log redaction. It is a second, independent, and *more complete* implementation of it.

This is the correction that matters most, because the brief asks me to treat the pin move
as a security fix and to give that "the weight it deserves" — and the prepared commit
`0807eb1c` already says so in its message.

The ancestry claim is true. `9fa2c3c`, `5349d47` and `77e2396` are not ancestors of
`234d47c` (verified with `git merge-base --is-ancestor`; GT4 measured the same). But
ancestry is not behaviour, and the behaviour is the opposite of what the ancestry suggests.

`234d47c` ("Make embedded connector debug logging opt-in") is not a flag added over leaky
code. It is an 18-file rewrite that introduces `lib/logging.js` and replaces the leaking
`console.log` calls outright. Its own comment states the policy:

```js
// Each connector owns its logger. Never replace the process-wide console or
// print source credentials, patient payloads, HTTP bodies or XState context.
```

The same Dexcom call site, in the two parallel lines:

```js
// v0.0.13 (what master ships today) - credentials and bodies, unconditional
console.log("ERROR AUTHENTICATING ACCOUNT", "status=" + status, "data=", data, "message=", err && err.message);

// 9fa2c3c (the redaction branch, in cut 4)
console.log("ERROR AUTHENTICATING ACCOUNT", "status=" + (Number.isInteger(status) ? status : "unavailable"));

// 234d47c (dev's pin) - log.error prints a message plus an HTTP status and nothing else
log.error("Dexcom authentication failed", err);
```

Both branches close the leak. They just do it differently.

To measure this rather than argue it, I extracted each pinned tree with `git archive`
into the scratchpad and counted `console.*` call sites **with comments stripped** (a first
pass that did not strip comments gave badly inflated numbers, because the redaction work
comments code out rather than deleting it — the corrected scanner is in §Appendix A.2).
"Dynamic" means the call passes at least one non-string-literal argument, i.e. it can
print a value.

| tree | pinned by | live `console.*` | of those, passing a dynamic argument |
|---|---|---:|---:|
| `v0.0.13` `b394411` | **master**, cuts 1, 2, 3 | 112 | **101** |
| `c962a13f` | cut 4 | 108 | 44 |
| `234d47c` | **dev** | 22 | 20 |
| `b77e5bb` | cut 5 | 22 | 20 |
| `v0.0.14` `649a7de` | (prepared) | 22 | 20 |

Per-source, the ranking is unambiguous:

| | MiniMed | Dexcom | LibreLinkUp | internal output (the embedded path) |
|---|---|---|---|---|
| v0.0.13 — **master** | 51 live sites: cookies, tokens, headers, patient lists, sensor data | bodies + messages | auth headers, response bodies, session incl. `authTicket` | `INTERNAL PERSISTENCE <batch>` — every entry/treatment/profile/devicestatus, every cycle |
| `c962a13f` — cut 4 | redacted | redacted | **still leaking**: 9 live `console.*` sites, 8 of them dynamic — four print authentication headers or response bodies (`:78`, `:92`, `:130`) or the session object containing `authTicket` (`:111`), and `:163` prints the transformed glucose batch | redacted |
| `234d47c` — **dev** | redacted (0 `console.*`) | redacted | redacted | redacted, and debug-gated |
| `v0.0.14` | redacted | redacted | redacted | redacted, and debug-gated |

And v0.0.13 has **no debug guard at all** — `grep -rniE "if *\(.*(debug|verbose)"` over
`lib/` and `index.js` of the v0.0.13 tree returns nothing. The logging is unconditional.

So the true picture inverts the brief:

- **dev's current pin is redacted, and safer than master's and cut 4's.** Moving it to
  v0.0.14 is not a security fix. It is, for the log-redaction question specifically, a no-op.
  *(VERIFIER CORRECTION. This bullet originally read "the safest of the three pins in the
  brief", which is wrong: cut 5's pin `b77e5bb` has the identical census — 22 live / 20
  dynamic — and **contains** `234d47c` as well as the cut-4 redaction line, so by ancestry it
  is greater-or-equal, never worse. Independently reproduced: `git diff 234d47c b77e5bb --
  lib index.js` touches only `index.js`, `lib/outputs/internal.js` and the MiniMed source.)*
- **master's pin is the leaking one**, and master is what operators actually run. It logs
  patient CGM data on every poll cycle with no flag to turn it off.
- **cut 4 — the branch GT4 credits with "all the redaction" — still leaks LibreLinkUp**
  credentials, including the `authTicket` bearer token. That is a correction to GT4 too.

I want to be careful about how far this goes. What I measured is which call sites can
print a value, per tree, plus the argument expressions at those sites. I did **not** run
the connector against a live vendor and read the output; nobody has (the connector's own
evidence says no real account has been used). So "dev's pin redacts the Dexcom, MiniMed,
LibreLinkUp and internal-output leaks" is a source-level finding, confidently measured at
the call sites, not an end-to-end observation. It is strong enough to overturn the brief's
claim, which was itself derived purely from ancestry.

### 0.3 There are four axes of disagreement, not one. The fourth is `overrides`, and on master it is a live defect.

Running the gate (§F) over all seven refs surfaced something no programme document
mentions: the branches also disagree about `overrides["nightscout-connect"]`.

| ref | pin | `overrides["nightscout-connect"]` |
|---|---|---|
| `origin/master` | v0.0.13 tag | `{"axios":"1.16.0"}` |
| `origin/dev` | `234d47c` | `{"axios":"1.20.0"}` |
| cut 1 `chore/retire-jsdom` | v0.0.13 tag | `{"axios":"1.20.0"}` |
| cut 2 `chore/build-runtime-separation` | v0.0.13 tag | `{"axios":"1.20.0"}` |
| cut 3 `chore/compose-mongodb6` | v0.0.13 tag | `{"axios":"1.20.0"}` |
| cut 4 `chore/mime-exposure-review` | `c962a13f` | `{"axios":"1.20.0"}` |
| cut 5 `chore/nightscout-modernization` | `b77e5bb` | **absent** (no `overrides` block at all; axios 1.20.0 is a direct dependency instead) |

The connector declares `"axios": "^1.18.1"` at both v0.0.13 and v0.0.14 (measured:
`git show v0.0.13^{commit}:package.json`). Measured with the repo's own semver 6.3.1:

```
axios 1.16.0 satisfies ^1.18.1?  false
axios 1.20.0 satisfies ^1.18.1?  true
```

**master forces the connector to run on an axios below its own declared minimum.**
`overrides` exists precisely to suppress the `ERESOLVE` that would otherwise catch this, so
it fails silently. master's lockfile confirms the override takes effect:
`node_modules/nightscout-connect/node_modules/axios` = `1.16.0`.

I am *not* claiming a user-visible failure from this. I did not find a specific axios API
the connector uses that 1.16.0 lacks, and I did not look hard, because the finding stands
on its own: a dependency constraint is being violated silently on the branch operators run.
It is filed as a proposed register entry at medium severity, with the caveat stated.

This is what made the whole-set gate worth building. Every individual branch's pin is
defensible on its own. It is the *set* that is incoherent, and no single-branch check can
see that.

---

## 1. The measured state

### 1.1 The pins, and where each sits on the connector's history

All five pins are GitHub archive tarballs. Measured with
`git rev-list --count b394411..<sha>` in `externals/nightscout-connect`:

| pin | shape | commits past v0.0.13 | who pins it |
|---|---|---:|---|
| `refs/tags/v0.0.13.tar.gz` | tag tarball | 0 | master, cut 1, cut 2, cut 3 |
| `234d47c8…tar.gz` | commit tarball | 1 | dev |
| `c962a13f…tar.gz` | commit tarball | 5 | cut 4 |
| `b77e5bb7…tar.gz` | commit tarball | 9 | cut 5 |
| `refs/tags/v0.0.14.tar.gz` | tag tarball | 11 | `bf/connect-pin` (prepared, unpushed) |

### 1.2 The line is NOT linear, and the brief's ancestry claim needs one correction

The brief says "234d47c8 IS an ancestor of b77e5bb, so the line is linear with no
divergence to reconcile." The first half is true. The second does not follow, and the set
as a whole is not totally ordered:

```
git merge-base --is-ancestor 234d47c b77e5bb    -> YES
git merge-base --is-ancestor 234d47c c962a13f   -> NO
git merge-base --is-ancestor c962a13f b77e5bb   -> YES
git merge-base --is-ancestor b394411 234d47c    -> NO   <- the tag is not in dev's pin
```

dev's pin and cut 4's pin are **incomparable**: neither contains the other. dev has the
logger rewrite without the redaction commits; cut 4 has the redaction commits without the
logger rewrite. They converge only at `b77e5bb` (cut 5). GT4 found this for the two
mitigations; the gate's R6 finds it mechanically for any future pin set.

There is a subtlety worth recording, because a naive ancestry gate would trip over it.
`b394411` (tag v0.0.13) is **not** an ancestor of `234d47c`. It is a merge commit whose
tree is byte-identical to its second parent `6dfc4f0` (`git diff 6dfc4f0 b394411` is
empty), and `234d47c` is `6dfc4f0` plus one commit. So dev's pin *content* really is
"v0.0.13's tree plus one commit", which is what the brief and GT4 assert — but the commit
graph does not say so, and `merge-base --is-ancestor b394411 234d47c` returns false. Both
statements are true of different things.

### 1.3 The npm caret rule, stated and applied

The brief asks for this exactly right, so: the rule first, then the application.

**Rule.** npm's caret allows changes that do not modify the left-most **non-zero** digit of
the version. For `0.0.z` the left-most non-zero digit is the patch, so `^0.0.z` permits
nothing but `0.0.z` itself.

**Measured**, with the semver library already in the tree
(`externals/work/crm-bf-reads/node_modules/semver`, version 6.3.1 — npm's own
implementation):

```
^0.0.12 => comparator set: >=0.0.12 <0.0.13
^0.0.13 => comparator set: >=0.0.13 <0.0.14
^0.1.0  => comparator set: >=0.1.0  <0.2.0

range      0.0.11  0.0.12  0.0.13  0.0.14  0.1.0  0.2.0  1.0.0
^0.0.12    -       MATCH   -       -       -      -      -
^0.0.13    -       -       MATCH   -       -      -      -
~0.0.12    -       MATCH   MATCH   MATCH   -      -      -
^0.1.0     -       -       -       -       MATCH  -      -
```

**Application.** Publishing 0.0.14 to npm would reach a `^0.0.12` dependant **never** — not
automatically, not on next install, not on a fresh `npm install`. `^0.0.12` is an exact pin
on 0.0.12 wearing a range's clothing. The same is true of `^0.0.13`, and it would be true of
GT4's recommended `0.1.0` (`^0.0.13` does not match `0.1.0`).

The practical reading: **the `^0.0.12` era was never a floating dependency in the first
place.** Had master still been on `^0.0.12`, an npm publish would have changed nothing for
anybody. This removes the one argument that would have favoured going back to npm — "at
least operators get fixes without a cgm-remote-monitor release" — because under 0.x caret
semantics they would not have. It also means the historical pin changes at `97a603fb` and
before were each a deliberate, explicit version move, exactly like a tarball bump.

The connector is on npm up to at least 0.0.12: `97a603fb`'s lockfile resolves it to
`https://registry.npmjs.org/nightscout-connect/-/nightscout-connect-0.0.12.tgz` with an
integrity hash. Whether 0.0.13 was ever published I could not determine without a network
call (rule 0); the move to `github:` at `a91e8ee4` suggests it was not. See open questions.

---

## 2. A. The end state

**Recommendation: one published, annotated git tag per connector release, referenced by
every cgm-remote-monitor branch as a GitHub archive tag tarball, with an identical
`overrides` entry, and a lockfile regenerated from the pushed tag.**

Concretely, every branch's `package.json` reads:

```json
"nightscout-connect": "https://github.com/nightscout/nightscout-connect/archive/refs/tags/vX.Y.Z.tar.gz"
```

differing only in `X.Y.Z`, and `overrides["nightscout-connect"]` is the same object on all
of them (or absent from all of them).

Note what this does and does not require. It does **not** require every branch to pin the
same *version* — dev and a modernization cut may legitimately be on different connector
releases. It requires them to pin in the same *shape*, to pin something *nameable*, to keep
the lockfile in agreement, and not to have two different trees both calling themselves
0.0.13. Those four properties are exactly R1–R5 of the gate.

### Argued against the alternatives

**Alternative 1 — npm everywhere (`"nightscout-connect": "^0.1.0"`).** Rejected.

- The argument for it is that it is the ecosystem-standard mechanism and gives operators
  fixes without a Nightscout release. §1.3 kills the second half: under 0.x caret semantics
  a range is an exact pin, so there is no float to gain until the connector reaches 1.0.0.
- It adds a publishing step that can fail independently of the tag, creating a *fifth*
  state the gate would have to track (tag exists but npm does not, or npm is ahead).
- The connector has no publish automation: `release/v0.0.14` carries one workflow,
  `.github/workflows/test.yml`, and `git grep` for `npm publish`/`NPM_TOKEN`/`npmjs` over
  `.github` and `package.json` returns nothing. Publishing would be a human running
  `npm publish` with registry credentials on a laptop — a manual step with a secret
  attached, added to a project whose stated governance problem is too few humans in the
  loop. `package.json` also has no `files` field, so a publish would pack whatever is not
  git-ignored.
- It reintroduces a second source of truth for "what is 0.0.14", when the tag already is one.

If the connector ever goes 1.0.0, revisit: at `^1.x` a range does float, and the argument
changes. That is the trigger to re-open this decision, not a date.

**Alternative 2 — tag tarball everywhere.** This is the recommendation. Why it wins:

- It is where the project already is. Four of the seven refs use it today; master reached it
  deliberately at `561974de` to solve a real problem (`git+ssh` broke deploy builds without
  GitHub SSH keys). Choosing it preserves that fix. Choosing `github:` shorthand would undo it.
- A tag is nameable. `v0.0.14` goes in release notes; `234d47c85510a77…` does not. This is
  the brief's third consequence and it is the one that survives intact.
- A tag is reviewable: it has a message, a signature if the project wants one, and a diff
  against the previous tag. A bare commit on an unmerged branch has none of that.
- `npm ci` gets a real integrity hash over a real artefact, which is the mechanism §C depends
  on.
- It needs no credentials and no publish step. Pushing the tag is the whole release.

**Alternative 3 — keep commit tarballs but require the commit be on `main`.** Rejected: it
fixes reviewability but not nameability, and the release notes problem is the one the
maintainer will feel every release.

### The one genuine weakness, stated plainly

GitHub-generated archive tarballs are not contractually byte-stable. GitHub has changed
archive compression before and checksums shifted. If that happens, every pinned
`integrity` hash in every lockfile breaks at once and `npm ci` fails everywhere until the
locks are regenerated — a loud, fleet-wide failure with an easy fix but a bad morning.
INFERENCE: I did not verify GitHub's current archive stability policy (no network), and I
am relying on recollection of the 2023 incident. A maintainer who wants this de-risked
should attach a release asset — a tarball the project generates with `npm pack` and uploads
to the GitHub release — and pin that URL instead, which is byte-stable by construction. That
is a strictly better end state on this axis and costs one step in the release procedure.
I am not recommending it now because it is a change to the release process that the current
evidence does not force, and §B is already long. It is listed as an open question.

---

## 3. B. The ordered sequence of human decisions

> **Everything in this section is run by a HUMAN.** No agent may execute any of it. Steps 1
> and 4 push to a remote, which under this project's rule 0 is a deliberate human decision
> because this code is used by people dosing insulin. Nothing here has been run.

The order is forced by one fact: **the lockfile cannot be correct until the tag is pushed**
(§C). So the tag push comes first, and the lockfile regeneration happens after it inside the
same PR.

### The one-way doors, and what rollback actually looks like

*(Added by the verifier. The original §B named no one-way door at the step that opens it —
the tag's immovability appeared only in §E.1 and open question 2 — and described no rollback
at all. Read this before step 1.)*

| step | reversible? | what "undo" really costs |
|---|---|---|
| Step 1, `git push origin v0.0.14` | **NO** | A pushed tag must be treated as immutable. Anyone who has already installed from it has its bytes in a lockfile and an npm cache; moving or deleting it makes those lockfiles resolve to something else, which is the EINTEGRITY/silent-swap failure of §C in reverse. The correct undo is **a new tag** (`v0.0.15`), never a moved one. This is also why open question 2 — `v0.0.14` or GT4's `v0.1.0` — has to be settled *before* this step. |
| Step 1, `git push origin release/v0.0.14:main` | in principle | `main` can be reset, but only before anyone pulls. Treat it as one-way in practice. |
| Step 2, lockfile regeneration | yes | It is a commit on a branch; drop the commit. |
| Step 3, opening the PR | yes | Close it. |
| **Step 4, merging to `dev`** | **NO, in effect** | The merge pushes a Docker Hub image (GT2 measured the workflow condition). Once an operator has pulled it, the way back is a **forward** release, not a revert of the merge. |
| Step 5, cuts 4/5/master | yes, individually | Each is a branch-level one-line change; revert the commit and regenerate the lock. |

**The rollback, concretely.** If v0.0.14 turns out to be wrong after step 4, the recovery is
to revert `bf/connect-pin`'s two commits on `dev` (the `package.json` line and the lockfile),
run `npm install --package-lock-only nightscout-connect` again to put the lock back on
`234d47c85510a77f07b3be0d2c026dd0272715d6`, and merge that — which ships another image. The
connector tag stays where it is. Budget one release cycle, not one command.

### How you would notice it went wrong — the failure here is SILENT

The connector is a CGM ingestion path. If v0.0.14 misbehaves, nothing throws and no alarm
fires; glucose data simply stops arriving, or arrives late, for someone managing diabetes.
The two changes in this bump that could do that are `c1cce2a` (retry interval, ceiling and
jitter — it changes *when* every source polls) and `8406edf` (what the MiniMed source
reports as glucose and measurement time). Neither has been exercised against a live vendor
by anyone (open question 5).

So after step 4, watch for:

- **A gap in entries.** Compare entry arrival rate per source before and after the release
  window. A regression in `c1cce2a`'s backoff shows up as a widening interval, not an error.
- **MiniMed timestamps.** `8406edf` touches measurement time; a systematic offset would show
  as readings landing at the wrong clock position rather than as missing readings.
- **`npm ci` failures in the field.** A self-builder who pulls `dev` between the
  `package.json` merge and the lockfile commit gets the loud EUSAGE of §C row 1. That is the
  designed failure, but it will generate reports; expect them.
- **Silence itself.** Debug logging is opt-in from `234d47c` onward, so a quiet log after
  the upgrade is expected and is *not* evidence that ingestion is healthy. Check the data,
  not the log.

### Step 0 — HUMAN DECISION, before anything is pushed

Answer §E: is dev's connector moving to v0.0.14 as part of 15.0.9, and if so is the
maintainer content to ship the eleven intervening commits? If the answer is no, stop here; the
rest of this document describes a different release.

Verify the prepared work first (read-only, safe to re-run):

```bash
# HUMAN RUNS. Read-only.
git -C externals/nightscout-connect merge-base --is-ancestor v0.0.13 release/v0.0.14 && echo "fast-forwards"
git -C externals/nightscout-connect cat-file -t v0.0.14            # expect: tag (annotated)
git -C externals/nightscout-connect rev-parse v0.0.14^{commit}     # expect: 649a7de...
git -C externals/nightscout-connect log --oneline v0.0.13..v0.0.14
```

### Step 1 — HUMAN PUSHES the connector release and tag

```bash
# HUMAN RUNS. THIS LEAVES THE MACHINE.
git -C externals/nightscout-connect push origin release/v0.0.14:main
git -C externals/nightscout-connect push origin v0.0.14
```

Pushing the tag is what brings
`https://github.com/nightscout/nightscout-connect/archive/refs/tags/v0.0.14.tar.gz` into
existence. Until this moment that URL 404s and no lockfile anywhere can reference it.

The connector repository has no release workflow beyond `test.yml`, so this publishes
nothing to npm and triggers no image build. Verified by `git ls-tree -r --name-only
release/v0.0.14 -- .github`.

### Step 2 — HUMAN regenerates the lockfile, in the PR branch, after the tag exists

```bash
# HUMAN RUNS. Requires network (it fetches the tarball GitHub now generates).
cd externals/work/crm-bf-connect-pin
npm install --package-lock-only nightscout-connect
git diff --stat package-lock.json      # expect package-lock.json only
```

Then confirm the lock now agrees with the manifest — this is gate rule R3, and it should
flip from FAIL to PASS:

```bash
# HUMAN RUNS. Read-only.
node tools/qc/connector-pin-agreement-gate.js \
  --repo externals/cgm-remote-monitor-official \
  --connect-repo externals/nightscout-connect \
  --ref origin/master --ref bf/connect-pin --ref origin/chore/nightscout-modernization
```

Commit the lockfile **into the same PR as the `package.json` change**, not a follow-up.
A merged `package.json` bump without its lockfile is a broken `npm ci` for everyone (§C).

### Step 3 — HUMAN opens the cgm-remote-monitor PR

`bf/connect-pin` → `dev`. Two commits: `0807eb1c` (the pin) and the lockfile regeneration.

**Amend `0807eb1c`'s message before opening the PR.** Its current text is the security
argument this document refutes in §0.2 — it says dev's pin "does not stop [the leaks]
happening when an operator turns logging on", which the code contradicts. It is a good
commit doing a right thing for reasons that will not survive review, and commit messages
are permanent. Suggested replacement rationale, all of it measured:

- dev pins an untagged commit on an unmerged branch: reproducible, unreviewable, and
  leaves 15.0.9 with no connector version to name in its notes.
- v0.0.14 is the first ref that contains **both** lines of connector work — the logger
  rewrite (`234d47c`, on dev) and the redaction commits (`9fa2c3c`/`5349d47`/`77e2396`, on
  cut 4). Those two pins are incomparable; neither contains the other.
- It brings BF-34: every configured retry interval was discarded, five vendor sources ran
  585.94× too fast, in lockstep, with jitter forced off.
- It brings the MiniMed glucose/measurement-time contract fix and the listener-release fix.
- It is **not** a log-redaction fix for dev. dev already has equivalent redaction. It *is*
  one for master, which is a separate decision (§E.2).

### Step 4 — HUMAN merges, which ships an image

Merging to `dev` triggers the Docker Hub image push (GT2 measured the workflow condition:
`(ref == master || ref == dev) && repository_owner == 'nightscout'`). Treat the merge, not
the PR, as the shipping moment.

### Step 5 — HUMAN brings the remaining refs into shape

Not urgent, and not all at once. In increasing order of blast radius:

```bash
# HUMAN RUNS. Each is a one-line package.json edit plus `npm install --package-lock-only`,
# on a branch, reviewed like any other change.
#
#   cut 4  chore/mime-exposure-review     c962a13f      -> refs/tags/v0.0.14.tar.gz
#   cut 5  chore/nightscout-modernization b77e5bb       -> refs/tags/v0.0.14.tar.gz
#   master                                v0.0.13 tag   -> see E.2, a release decision
#
# and reconcile overrides["nightscout-connect"] across the set (§0.3).
```

Cuts 4 and 5 are mechanical once the tag exists: both currently pin commits that v0.0.14
contains, so moving them forward adds two commits (cut 5) or six (cut 4) and removes the
unnameable pin. master is not mechanical — see §E.2.

### Step 6 — HUMAN wires the gate into CI

§F. Once every ref is in shape, the gate's verdict on the full ref set becomes PASS and can
be made blocking. Until then it is a reporting tool: it currently fails 5 of 6 rules, and a
gate that is red on day one gets ignored unless the red is expected and written down, which
is what §0.3 and §1 are for.

---

## 4. C. The package-lock constraint — why the stale lock is correct and must not be "fixed"

`bf/connect-pin` deliberately ships `package.json` pointing at v0.0.14 while
`package-lock.json` still names `234d47c8…`. This looks like an oversight. It is not, and
the next person to notice it will want to fix it. Here is why they must not, demonstrated
rather than asserted.

**The mechanism.** A lockfile entry carries an `integrity` field: a SHA-512 over the exact
bytes of the tarball. The tarball for `refs/tags/v0.0.14.tar.gz` is generated by GitHub, on
demand, and **does not exist until the tag is pushed**. There is no way to compute the
correct hash before step B.1. A hash invented, guessed, or copied locally is not merely
useless — it is actively dangerous, as the experiment below shows.

**The experiments.** All run offline (`--offline`) against two locally built tarballs
differing only in content, with npm 11.12.1 on Node v24.15.0. No network. Full method in
Appendix A.3.

| # | lockfile state | npm cache | flags | result |
|---|---|---|---|---|
| 1 | stale: manifest on new, lock on old (**this is `bf/connect-pin` today**) | any | plain | `EUSAGE`, **exit 1**, nothing installed: *"lock file's demo-pkg@0.0.13 does not satisfy demo-pkg@0.0.14"* |
| 2 | hand-edited: URL and version updated, **old `integrity` left in place** | warm (old tarball cached) | plain | **exit 0 — and it silently installed the OLD package** while the lock claimed the new version |
| 2b | same as 2 | cold | plain | `EINTEGRITY`, exit 1, nothing installed |
| 2c | same as 2 | cold | `--force --omit=optional` (the Dockerfile's flags) | `EINTEGRITY`, exit 1 |
| 3 | correctly regenerated after the tag exists | any | plain | exit 0, installs the new package |
| 4 | stale (as 1) | cold | `--force --omit=optional` | `EUSAGE`, exit 1 |

**Row 1 is the point.** The stale lock produces a loud, specific, exit-1 failure that names
both versions, and installs nothing. That is the correct failure: it stops the build and
tells the operator exactly what is wrong. Leaving it stale is a feature.

**Row 2 is the trap**, and it is the reason this section exists. Someone "fixing" the lock
by editing the URL and version but keeping the old integrity hash gets a **green build that
installs the wrong code**. npm resolved the stale hash against its content-addressable
cache, found the old tarball, and used it — exit 0, no warning. In the real case that old
tarball is `234d47c8`'s archive, which is in the npm cache of every machine that has ever
installed dev. The lock would say v0.0.14; the running code would be `234d47c8`.

Rows 2b and 2c are the consolation: the failure mode is cache-dependent, and the official
Docker build is safe from it. The Dockerfile runs `npm ci --cache /tmp/empty-cache
--omit=optional --force` — always a cold cache — so it gets `EINTEGRITY` and fails loudly.
`--force` does **not** defeat either check; I tested it specifically because the Dockerfile
uses it. So the silent-wrong-install hazard applies to developer machines and to any CI
runner with a warm npm cache, not to the published image.

**The rule.** Do not touch `package-lock.json` until the tag is pushed. Then regenerate it
with npm (`npm install --package-lock-only nightscout-connect`), never by hand, and commit
it in the same PR as the `package.json` change.

> **VERIFIER CORRECTION — struck, not deleted.** The original text ended: *"Gate rule R3 is
> the mechanical check that this happened."* ~~R3 is the mechanical check that this
> happened.~~ **It is not.** R3 compares three *spec strings* — `package.json`'s spec, the
> lockfile root's spec, and the lockfile entry's `resolved`. In the row-2 trap all three
> agree; only `integrity` is stale. `connector-pin-agreement-gate.js` reads `integrity`
> into `lockIntegrity` in `observe()` and **no rule ever uses it** (verified:
> `grep -n integrity tools/qc/connector-pin-agreement-gate.js` returns only the three
> observation lines). Reproduced on a synthetic fixture whose lockfiles carry the literal
> integrity string `"sha512-x"`: the gate returns **PASS, exit 0**. So the single most
> dangerous state this section identifies — a lockfile whose URL and version are current
> and whose hash still addresses the old tarball — is caught by **no gate rule at all**.
> What catches it is `npm ci` on a **cold** cache (rows 2b/2c), which is the published
> Docker build but not a developer laptop or a warm CI runner.
>
> R3 *does* catch the deliberately-stale state of row 1, which is what §F.2's "R3 flips to
> FAIL" refers to. That claim stands; only the sentence above it was too broad.
> A proposed register entry for the gate gap is in the verifier's return value.

---

## 5. D. What each branch's operators actually receive, and when

This is the section that answers "do the log-redaction fixes reach anyone", and the answer
is not the one the brief expected.

### D.1 How a connector fix reaches an operator at all

There is exactly one path, and it has three gates in series:

```
connector commit
  -> a connector TAG is pushed                                  (human, step B.1)
  -> a cgm-remote-monitor package.json pin moves to that tag     (human, a PR)
  -> a cgm-remote-monitor RELEASE ships that branch              (human, a release)
  -> the operator upgrades, or pulls a new Docker image
```

Nothing floats. Every pin is a fixed tarball URL, so no operator receives a connector
change without a cgm-remote-monitor release. Merging in the connector repository ships to
nobody — the brief's first consequence, confirmed. What the brief gets wrong is which
release matters: it is not only dev's.

### D.2 The table

| branch | version | who runs it | connector today | log-redaction state **today** | what moving the pin gives them | when |
|---|---|---|---|---|---|---|
| `master` | 15.0.8 | **every operator on a current release** | v0.0.13 tag | **Leaking. Unconditionally.** The plaintext source password for whichever source is configured, printed at every boot by `index.js:54`; plus MiniMed cookies/tokens/patient lists, Dexcom auth bodies, LibreLinkUp `authTicket`, Glooko auth headers and body, and every CGM batch via `INTERNAL PERSISTENCE`. No flag disables any of it. | The whole redaction, plus BF-34 | **Never, on current plans.** No proposal moves master's pin. See E.2. |
| `dev` | 15.0.9 candidate | nobody yet; everyone after 15.0.9 | `234d47c` | **Already redacted**, by the independent logger rewrite. Debug output is opt-in via `DEBUG_LOGGING`/`CONNECT_DEBUG`. | BF-34, the MiniMed contract fix, the listener-release fix, a nameable version — **not** redaction | On 15.0.9 release, if step B.3 lands |
| `chore/nightscout-modernization` (cut 5) | 15.0.9 | nobody; future release train | `b77e5bb` | Already redacted (contains both lines) | BF-34 and the release tag only (2 commits) | Whenever cut 5 ships |
| cuts 1–3 | 15.0.9 | nobody | v0.0.13 tag | **Leaking**, same as master | The whole redaction | Whenever those cuts ship — and the adopted train ships cut 1 and cut 2 **early** |
| cut 4 | 15.0.9 | nobody | `c962a13f` | Partly: MiniMed and Dexcom redacted, **LibreLinkUp still leaking** | LibreLinkUp redaction, BF-34 | Held back longest on the adopted train |

### D.3 The finding the maintainer needs

**The log-redaction fixes currently reach nobody who is not already covered, and the
population most exposed is the one nobody is proposing to fix: operators on master.**

The adopted release train makes this worse before better. Cuts 1 and 2 are scheduled as the
first two low-blast-radius releases after 15.0.9 — and **both still pin v0.0.13**. If they
ship as they stand, operators who upgrade to cut 1 or cut 2 move from a leaking connector
to... the same leaking connector, in a release that was chosen for being safe. Cut 4, which
carries most of the redaction, is held back the longest.

That is a sequencing inversion worth surfacing on its own, independent of everything else
in this document. It is cheap to fix: cuts 1–3 pin the v0.0.13 tag, so moving them to
v0.0.14 is the same one-line change as dev's, with no incomparability to reason about.

*(VERIFIER QUALIFICATION. "Cheap" is true of the edit on each cut branch and false of
landing it. GT2 measured that cuts 1–4 are each **59 commits behind `origin/dev`** and
conflict against it under `git merge-tree --write-tree` in 4–5 files — and `package.json`
and `package-lock.json` are among the conflicting files on every one of them. So the pin
edit is one line, but it lands inside a merge that already has to be resolved by hand in
exactly those two files. Do not schedule it as a five-minute change.)*

### D.4 What "leaking" concretely means on master

For an operator running Nightscout 15.0.8 with `CONNECT_SOURCE` configured, the process log
receives, with no configuration that turns it off:

- **At every boot, for every source, the plaintext source credentials.**
  `index.js:54` is `console.log("INPUT PARAMS", spec, validated.config)`, and
  `validated.config` is the object the source's own `validate()` builds — for Dexcom it
  carries `sharePassword`, for MiniMed `carelinkPassword`, for LibreLinkUp
  `linkUpPassword`, for Glooko the Glooko password. `index.js:57` prints the whole
  `validated` object again when the configuration is rejected. This is the most universal
  of the leaks: it does not depend on which source is selected, and it happens before any
  network call. *(Added by the verifier; the original enumeration omitted it. Measured by
  reading `index.js:20-60` and `lib/sources/dexcomshare.js:291-316` in the v0.0.13 tree.)*
- `INTERNAL PERSISTENCE <batch>` on **every poll cycle** — the full batch object: CGM
  entries, treatments, profiles, devicestatus.
- On MiniMed: session cookies, bearer tokens, request and response headers, the patient
  list, and the raw sensor payload (51 live `console.*` sites in
  `lib/sources/minimedcarelink/index.js`). `:296` logs the login `payload`, which contains
  `username` and `password` in plaintext.
- On Dexcom: the response body and error message of a failed authentication.
- On LibreLinkUp: the authentication response headers and body, and the session object
  containing `authTicket`.
- **On Glooko** (named to operators in D.5 but missing from the original list):
  `GLOOKO AUTH` prints the authentication response headers and body, and `SESSION USER`
  prints the session's user object. The password itself is not logged by the Glooko source
  — but it is logged by `index.js:54` above, like every other source's.
- **On the `nightscout` source** (Nightscout-to-Nightscout): 7 live sites including the
  base URL, the collection queries and the full check response.

**Coverage of this enumeration, measured:** every file under `lib/` and `index.js` of the
v0.0.13 tree was scanned; the per-file live/dynamic counts are `index.js` 5/3,
`lib/outputs/internal.js` 7/5, `lib/outputs/nightscout.js` 15/14 and
`lib/outputs/filesystem.js` 3/3 (both **unreachable** from Nightscout — `index.js` selects
`{name:'internal'}`), `lib/outputs/index.js` 2/2, `lib/sources/minimedcarelink/index.js`
51/50, `lib/sources/librelinkup.js` 9/8, `lib/sources/nightscout.js` 7/6,
`lib/sources/dexcomshare.js` 5/4, `lib/sources/glooko/index.js` 4/3,
`lib/sources/glooko/convert.js` 1/1, `lib/sources/index.js` 1/1, `lib/trace-axios.js` 2/1.
Totals 112/101, matching the §0.2 table. Nothing under `lib/` is omitted.

Where those logs go depends on the deployment — a container log driver, a hosting
provider's log viewer, a systemd journal, a support forum post. That last one is the
realistic exposure path: an operator diagnosing "my CGM data stopped" copies their log into
a public issue.

### D.5 Operator-facing note (plain language)

> **If you run Nightscout 15.0.8 and you use the built-in CGM connector**
> (a `CONNECT_SOURCE` setting for Dexcom Share, LibreLinkUp, Glooko or MiniMed CareLink):
>
> Your Nightscout log file currently contains the username, password or session token for
> your CGM account, and a copy of your glucose readings. This happens all the time, not
> only when something goes wrong, and there is no setting in 15.0.8 that turns it off.
>
> This is not a problem with your setup and nothing is wrong with your data. It does not
> affect your readings, your alarms, or anything you see on screen. It matters in one
> situation: **if you share your log with someone else.**
>
> What to do for now:
> - Do not paste your Nightscout log into a public place — a GitHub issue, a Facebook group,
>   a Discord channel — without removing the personal parts first. If you are not sure what
>   to remove, ask for help privately rather than posting it.
> - If you have already posted a log somewhere public, consider changing the password on
>   your CGM account.
> - Check who can see your hosting provider's log viewer.
>
> **How to check your own log, if you want to.** Your log is the text your hosting provider
> shows under "logs", "log stream" or "console output" — it is a record of what the software
> printed while it ran, not part of your Nightscout data. Look for lines that begin with any
> of these: `INPUT PARAMS`, `SUBMITTING LOGIN`, `LIBRE LINKUP AUTH`, `GLOOKO AUTH`,
> `LIBRE SESSION FROM AUTH`, `INTERNAL PERSISTENCE`. Those are the lines that contain your
> account details or your glucose readings. You do not need to change anything on your
> Nightscout site to check this, and there is nothing in the site's settings that stops
> these lines being printed.
>
> **What to expect when the fix reaches you.** Your log will become much quieter — that is
> the fix working, not something breaking. What is *not* expected is your readings stopping:
> if your graph stops updating, or readings start appearing at the wrong times, after any
> upgrade, that is worth reporting. The quiet log means you cannot rely on the log to spot
> it, so watch the graph itself.
>
> A fixed version of the connector exists and is being prepared for release. This note will
> be updated when a release carrying it is available.
>
> This is not medical advice, and nothing here asks you to change anything about your
> insulin, your therapy or your devices. If you have questions about your diabetes care,
> talk to your care team.

*(Draft wording. A maintainer should decide whether, when and where to publish this. It
describes a real exposure on a current release and that makes publication a judgement call
about disclosure timing, not a documentation task. Flagged for the maintainer in §E.2.)*

---

## 6. E. Decisions that are the maintainer's, not mine

### E.1 Does 15.0.9 take the eleven intervening connector commits?

Moving dev's pin from `234d47c` to `v0.0.14` is not a mechanical bump. Measured with
`git rev-list --count 234d47c..649a7de`: **11 commits, 7 of them non-merge.** (The brief
says 9; 9 is the count from v0.0.13 to `b77e5bb`, cut 5's pin. From dev's pin to the release
it is 11. Corrected.)

What comes with it:

| commit | what it changes |
|---|---|
| `9fa2c3c` | Dexcom credentials and sessions out of logs — *dev already has equivalent redaction* |
| `5349d47` | MiniMed credentials and patient data out of logs — *ditto* |
| `77e2396` | internal output payloads out of logs — *ditto* |
| `8406edf` | **MiniMed glucose and measurement-time status contracts** — a behaviour change on a CGM ingestion path |
| `51b6e6e` | connector listeners released and output waits settled on stop |
| `c1cce2a` | **BF-34**: retry interval precedence, the 30-minute ceiling, `jitter:'equal'` default |
| `649a7de` | version 0.0.13 → 0.0.14 |
| +4 merges | |

The three redaction commits are, for dev, largely redundant with what it already has (§0.2)
— they will produce a merged tree, not a behaviour change, on call sites dev has already
rewritten. The four that genuinely change dev's behaviour are `8406edf`, `51b6e6e`,
`c1cce2a` and the version bump.

The one to look at hardest is `8406edf`: it changes what the MiniMed source reports as
glucose and measurement time. That is a data-correctness change on a CGM path, in a release
(15.0.9) that is otherwise a bug-fix release. GT4 separately classifies the v0.0.14 API
changes as breaking and argues the connector should be **0.1.0, not 0.0.14** — reversed
option precedence, a changed default, and a new `throw`. That recommendation and this pin
move interact: if the maintainer takes GT4's advice, the tag to push in step B.1 is
`v0.1.0` and every URL in this document changes accordingly. **That is a decision to make
before step B.1, not after**, because the tag cannot be moved once pushed.

**This is a release-content decision.** I have no basis to make it.

### E.2 Does master get a connector fix, and is the exposure disclosed?

This is the decision §D.3 forces and it is genuinely uncomfortable, so I will not soften it.

Operators on 15.0.8 are running a connector that writes CGM credentials and patient data to
logs unconditionally. No current plan changes that. The options, none of which I am
recommending:

1. **Do nothing.** 15.0.9 ships, and 15.0.8 operators remain exposed until they upgrade.
   Defensible if 15.0.9 is close and adoption is fast.
2. **Move master's pin to v0.0.14 and cut 15.0.8.1.** Small diff (one line plus a lockfile),
   but it is a release, with everything that implies. Note it would also need the axios
   override reconciled (§0.3), or master keeps forcing axios 1.16.0 into a connector that
   wants `^1.18.1`. *(VERIFIER: "small diff" describes the cgm-remote-monitor change, not
   the behaviour delta. master is on the v0.0.13 tag, so this option moves it across
   **all 11 commits** of `b394411..649a7de` — measured — including `8406edf`'s MiniMed
   glucose/measurement-time contract change and `c1cce2a`'s retry-timing change. That is
   strictly more connector change than the dev bump of §E.1, on the branch every current
   operator runs, in what would be a patch release. If the goal is only to stop the log
   leak, `234d47c` alone achieves it with less behaviour change — at the cost of pinning
   an unnameable commit, which is what the rest of this document argues against.)*
3. **Move cuts 1–3 to v0.0.14 before they ship** (§D.3). Cheap, mechanical, and fixes the
   sequencing inversion regardless of what happens to master.
4. **Publish the operator note in §D.5 now**, so people stop pasting logs into public
   issues, and let the code fix follow.

Options 3 and 4 are cheap and independent of 1 and 2.

There is also a disclosure question underneath: this is a credential-exposure bug in
shipping software used by people managing diabetes. Whether it warrants an advisory, a
quiet fix, or a note in release notes is a maintainer and possibly a Foundation decision,
not an engineering one. I am flagging it rather than deciding it.

### E.3 Which tag shape, if the release-asset option is taken

§A's weakness paragraph. Attaching an `npm pack` tarball as a GitHub release asset and
pinning that is byte-stable where an auto-generated archive is not. It changes the release
procedure. Maintainer's call; not required by anything measured here.

---

## 7. F. Preventing recurrence: the whole-set gate

### F.1 What it has to check, and why single-branch checks cannot

Every branch's pin is individually defensible. The defect is a property of the **set**:
four pin values, two ref shapes, three `overrides` states, and four different code trees all
reporting `nightscout-connect@0.0.13` to `npm ls`. A per-branch lint sees nothing wrong. So
the gate takes a ref list and compares across it.

`tools/qc/connector-pin-agreement-gate.js` (274 lines, present in the working tree,
untracked at the time of writing). Read-only: every fact comes from `git show <ref>:<file>`.
It never checks out, writes to, or fetches in either repository, so it is safe to run against
the shared checkout while other sessions are live.

```
node tools/qc/connector-pin-agreement-gate.js \
     --repo externals/cgm-remote-monitor-official \
     --connect-repo externals/nightscout-connect \
     --ref origin/master --ref origin/dev --ref origin/chore/nightscout-modernization
```

| rule | what it asserts |
|---|---|
| R1 SHAPE | every ref declares the dependency in the same shape (npm-range / tag-tarball / commit-tarball / git-shorthand) |
| R2 NAMEABLE | every pin carries a name a release note can cite; a bare-commit tarball does not |
| R3 LOCK-AGREE | `package.json` spec == lockfile root spec == lockfile `resolved`, per ref |
| R4 VERSION-1-1 | across the set, one reported `version` maps to exactly one tree. **The "and vice versa" this row originally claimed is NOT implemented** — see the note below |
| R5 OVERRIDES | `overrides[<pkg>]` is identical across refs, or absent from all |
| R6 ORDERED | the pinned commits are totally ordered by ancestry, so the set has a newest member containing all the others. **Skipped, not passed, without `--connect-repo`** |

Exit codes: `0` pass, `1` at least one rule failed, `2` usage, **`3` a rule did not run**.
The last one is the anti-vacuity design: a skipped rule exiting 0 is how a gate quietly
dies, so a skip fails unless the caller passes `--allow-skip`. Verified:

```
skip, no --allow-skip    -> exit=3
skip, with --allow-skip  -> exit=0
```

> **VERIFIER CORRECTIONS to this table, two of them.** Both reproduced on a synthetic
> fixture built for this review (two throwaway repos in the scratchpad; no worktree
> touched).
>
> 1. **R4 is one-directional.** The implementation buckets refs by `lockVersion` and fails
>    only when one version maps to more than one `resolved` URL. The reverse — one tree
>    reporting two different versions — is not checked. A fixture in which one ref's lock
>    claims version `7.7.7` while resolving the same tag tarball as its siblings returns
>    **PASS, exit 0**. The gate's own docblock carries the same overclaim. The direction
>    that *is* implemented is the one that fires on the real repository today (four trees
>    all reporting `0.0.13`), so §F.2's R4 result stands; the rule's description did not.
> 2. **R3 does not look at `integrity`** — see the boxed correction at the end of §C. The
>    row-2 trap of §C passes every rule in this table.
>
> Independently confirmed as stated: R1, R2, R4, R5 and R6 all fire on the real seven-ref
> set with R3 passing (exit 1); substituting `bf/connect-pin` for `origin/dev` flips R6 to
> PASS and R3 to FAIL; and the skip path returns exit 3 without `--allow-skip` and exit 0
> with it (measured on a two-ref set where R1-R5 pass, since a rule failure otherwise
> masks the skip in the exit code).
>
> One more, tool-side and not fixable from this document: the gate's own header comment
> lists only exit codes 0/1/2 (omitting 3) and says "three different code trees all
> reporting `nightscout-connect@0.0.13`" where the run reports **four**.

### F.2 What it says about the real repository today

Full seven-ref run, verdict **FAIL (5 of 6 rules)**, exit 1:

- **R1** fails: 4 refs tag-tarball, 3 refs commit-tarball.
- **R2** fails: dev, cut 4 and cut 5 pin unnameable commits.
- **R3** passes: every ref's lock currently agrees with its own manifest.
- **R4** fails: version `"0.0.13"` is reported by **4 different trees**.
- **R5** fails: three different `overrides` states (§0.3) — *this is how the axios defect
  was found; no human had noticed it.*
- **R6** fails: dev's pin is incomparable with master's, with cuts 1–3's, and with cut 4's.

With `bf/connect-pin` substituted for `origin/dev`, **R6 flips to PASS** — v0.0.14 contains
every other pin — and R3 flips to FAIL, correctly reporting the deliberately stale lockfile
of §C. That is the gate tracking the migration: R6 is what the pin move fixes, R3 is what
step B.2 fixes.

### F.3 Break-it matrix (rule 2: a check that has never failed is not evidence)

Asserting the gate would catch a disagreement is not enough. I built a synthetic fixture —
a throwaway cgm-remote-monitor-shaped repo with three branches and a throwaway connector
repo with a tagged linear history plus one sibling commit, both created by me in the
scratchpad, **no real worktree touched** (rule 5) — put it in the intended end state,
confirmed the gate **passes**, then broke one rule at a time.

| # | mutation | rules fired |
|---|---|---|
| B0 | control: end state, untouched | **none — PASS** |
| B1 | dev declares the same tag via `git+…#v0.0.14` shorthand | `R1` |
| B2 | all three refs pin the same commit by SHA instead of by tag | `R2` |
| B3 | dev's manifest moves to v0.0.14, lock left on v0.0.13 (**the `bf/connect-pin` state**) | `R3` |
| B4 | master's lock claims version `0.0.14` while resolving the v0.0.13 tree | `R4` |
| B5 | modernization drops the `nightscout-connect` override | `R5` |
| B6 | dev pins a tag on a sibling line that v0.0.14 does not contain | `R6` |
| B7 | control: after restoring every mutation | **none — PASS** |

Every rule fires **alone** on a targeted break, and the control passes both before and
after. The gate distinguishes the states it claims to distinguish, and it is not a gate that
can never pass — B0 and B7 rule out the failure mode where a check is red on everything.

Isolating B4 to R4 alone required the lock to *lie* about its version while both refs stayed
tag-shaped, which is worth noting because it is also the most realistic way R4 fires in
practice: a lockfile whose recorded version no longer matches the tree it resolves.

*(VERIFIER: B4 has a precondition the row does not state. It fires only when the ref set
spans **two different tags**, so that the lying version collides with a sibling's. On a
fixture where all three refs pin the same tag, the same mutation — lock version changed,
`resolved` left alone — passes at exit 0. Reproduced both ways.)*

### F.4 Queue entry

Proposed as a `static` gate — cheap, local, read-only, no database, no network — runnable by
default in `make queue-status`. Returned in `queue_items` rather than written here, since
`queue/work-queue.yaml` is being edited by other sessions.

The honest limitation: the gate compares refs **as they exist in the local clone**. It
cannot see a ref that has not been fetched, so in CI it needs the fetch to precede it, and
a stale local clone makes it report on stale facts. That is a real vacuity risk and it is
why R6 skips loudly rather than passing when the connector repo is absent.

---

## 8. Open questions

1. **Was nightscout-connect 0.0.13 ever published to npm?** 0.0.11 and 0.0.12 were
   (registry `resolved` URLs with integrity in `97a603fb`'s lockfile). The move to `github:`
   at `a91e8ee4` suggests 0.0.13 was not, but settling it needs `npm view nightscout-connect
   versions`, a network call I did not make. Matters only if alternative 1 is reconsidered.
   **Settled by:** a maintainer with network access, in one command.
2. **v0.0.14 or v0.1.0?** GT4 argues the connector's API changes are breaking and the release
   should be 0.1.0. I did not re-derive that. It must be decided **before** step B.1 because
   a pushed tag cannot be moved. **Settled by:** the maintainer, against GT4's report.
3. **Does master's axios 1.16.0 actually break the connector at runtime?** I established the
   constraint violation (`1.16.0` does not satisfy `^1.18.1`) but did not hunt for an axios
   API the connector uses that 1.16.0 lacks. **Settled by:** running the connector's own
   suite against axios 1.16.0 — cheap, and nobody has done it.
4. **Is GitHub's archive tarball byte-stable enough to pin integrity against?** INFERENCE
   from a past incident; not verified. Decides whether §E.3's release-asset option is worth
   the process change. **Settled by:** maintainer judgement plus GitHub's current docs.
5. **Do the redaction commits and the logger rewrite merge cleanly in behaviour, not just in
   text?** v0.0.14 contains both lines and its tree is clean, but nobody has run the
   connector against a live vendor. The connector's own evidence says no real account has
   been used. **Settled by:** a maintainer with a test vendor account, or accepted as a
   known limit.
6. **Where do operator logs actually go, per deployment?** §D.4's exposure assessment assumes
   the common cases. I did not survey hosting providers. **Settled by:** whoever writes the
   disclosure in E.2, if one is written.

---

## Appendix A — how things were measured

**A.1 Pins, ancestry, overrides.** All from `git show <ref>:package.json` and
`git show <ref>:package-lock.json` parsed as JSON, in
`externals/cgm-remote-monitor-official`; ancestry from `git merge-base --is-ancestor` and
`git rev-list --count` in `externals/nightscout-connect`. Read-only; no checkout, no fetch,
no worktree created or removed in either repository.

**A.2 Log-site census.** Each pinned tree extracted with `git archive <sha> | tar -x` into
the scratchpad. A Python scanner strips comments and string literals with a small state
machine, finds `console.(log|error|warn|debug|info)(` call sites under `lib/` and
`index.js` (excluding `test/`), balances parentheses to capture the argument text, and
classifies a site as "dynamic" if anything remains after removing string literals,
whitespace, commas and `+`.

*Correction to my own first pass, recorded because it changed the numbers materially:* the
initial scanner did **not** strip comments, and the redaction work comments code out rather
than deleting it. That inflated every count — v0.0.14 appeared to have 52 dynamic sites when
it has 20. The table in §0.2 is from the corrected scanner.

A related distinction the scanner makes and a raw grep does not: cut 4's MiniMed block
still has 47 live `console.*` calls, but **none** of them passes a dynamic argument — the
redaction there replaced the arguments with static strings rather than removing the calls.
v0.0.14 has 0 `console.*` in that file at all. Both count as redacted; they are not the
same edit.

Reachability of the residual sites in v0.0.14 was checked by reading `index.js`: the
embedded cgm-remote-monitor path selects `{ name: 'internal', logger: log }`, so
`lib/outputs/nightscout.js`, `lib/outputs/filesystem.js` and the `default` output are
unreachable from Nightscout; and `lib/trace-axios.js` is reached only via
`config.capture && cfg.tracker` in `lib/builder.js:86`, which is off by default.

**A.3 npm experiments.** npm 11.12.1, Node v24.15.0, entirely offline (`--offline`), in a
scratchpad directory. Two packages built with `npm pack`, identical but for one string, so
their SHA-512s differ. A three-line `package.json`/`package-lock.json` pair was mutated per
row of the §C table; `--cache ./coldcache` gave a cold cache. Nothing in the real tree was
installed, and no registry or GitHub endpoint was contacted.

**A.4 Semver.** `externals/work/crm-bf-reads/node_modules/semver` v6.3.1 (npm's own
implementation), via `semver.satisfies` and `new semver.Range(r).set`.

**A.5 Gate fixture.** Two throwaway git repositories created by me under the scratchpad.
No existing worktree under `externals/work/` was read-modified, repointed or removed.

---

## Appendix B — corrections this document makes to other documents

Listed here for the reconciliation agent. **I edited none of these files.**

| document | says | measured |
|---|---|---|
| `phase0-pr-sequencing-2026-09-15.md:388` | master pins `"^0.0.12"` from npm | master pins the `v0.0.13` **tag tarball**; no npm range exists anywhere in the tree |
| task brief / programme preamble | "three pinning mechanisms" | one mechanism (GitHub archive tarball), two ref shapes, **five** pins in flight incl. cut 4's, plus a fourth undocumented axis (`overrides`) |
| task brief | dev's pin ships without three log-redaction fixes; making logging opt-in "does not stop them happening" | dev's pin contains an independent, **more complete** redaction; the leaking pin is **master's** |
| task brief | moving dev's pin pulls in 9 commits | **11** (7 non-merge). 9 is v0.0.13 → `b77e5bb` |
| task brief / GT4 | cut 4 "has all the redaction" | cut 4 still leaks LibreLinkUp auth headers, response bodies and the session `authTicket` |
| task brief | "234d47c8 is an ancestor of b77e5bb, so the line is linear" | true, but the **set** is not totally ordered: dev's pin and cut 4's are incomparable |
| — (unrecorded anywhere) | — | master forces `nightscout-connect → axios 1.16.0`, violating the connector's `^1.18.1`; `overrides` suppresses the ERESOLVE |
| — (unrecorded anywhere) | — | cuts 1, 2 and 3 pin v0.0.13 and are scheduled to ship **first**, so the adopted train ships the leaking connector to upgraders before the fixed one |
| commit `0807eb1c` message | states the refuted security rationale | should be amended before the PR is opened (§B.3) |
| this document, §0.1 | `^0.0.12` was replaced "fourteen months ago" | replaced **2026-07-07**, about two months before measurement; 2023-10-12 is when `^0.0.12` was *adopted* |
| this document, §0.2 | dev's pin is "the safest of the three pins in the brief" | cut 5's `b77e5bb` has the identical census and **contains** `234d47c` plus the cut-4 redaction line; dev's is tied at best |
| this document, §0.2 | cut 4's LibreLinkUp: "4 live sites" | 9 live `console.*` sites, 8 dynamic; four print auth headers/bodies or the `authTicket` session, one prints the glucose batch |
| this document, §D.4 | enumerates MiniMed / Dexcom / LibreLinkUp / internal output | omitted the **boot-time `INPUT PARAMS` log of the validated source config**, which prints the plaintext password for *every* source, and omitted **Glooko** and the `nightscout` source |
| this document, §C | "Gate rule R3 is the mechanical check that this happened" | R3 compares spec strings only; `integrity` is observed and never used by any rule, so §C's row-2 trap passes the gate at exit 0 |
| this document, §F.1 | R4 is one-to-one "and vice versa" | only the version→tree direction is implemented; one tree reporting two versions passes |
| `tools/qc/connector-pin-agreement-gate.js` header | exit codes "0, 1, 2"; "three different code trees" | the tool also exits **3** on a skip, and the real run reports **four** trees |
