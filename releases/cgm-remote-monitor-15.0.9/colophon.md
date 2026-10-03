# How 15.0.9 was made

*Contributor- and maintainer-facing. Living record, measured 2026-10-03 against cgm-remote-monitor
`official/dev` `1ad03e29` (the 15.0.9 candidate, release PR #8598) and `official/master` `92d08342`
(tag `15.0.8`, the shipping release), in `externals/cgm-remote-monitor-official` after
`git fetch official`, and this repository at `89922349`; re-measure before quoting. Nothing here is
tagged or released. What 15.0.9 contains is in [contents.md](contents.md), the maintainer's
decisions in [decisions.md](decisions.md), defect facts in the
[backfix register](../../docs/30-design/remedial/nightscout-backfix-register.md), and test runs in
the [integration record](../../docs/30-design/remedial/rc-15.0.9-integration-record.md). This page
counts and links; it does not restate those files. The dated snapshot this page replaces as the
current figures is [paving the cowpaths, 2026-09-27](../../docs/60-research/programme/paving-the-cowpaths-2026-09-27.md).*

The same page with charts of these figures: [How 15.0.9 was made, with charts](../../site/pages/cgm-remote-monitor-15.0.9-colophon.html).

Unless a row says otherwise, `git` commands run in `externals/cgm-remote-monitor-official` and the
range `R` is `official/master..official/dev`.

## 1. What 15.0.9 is

15.0.9 is the next release of Nightscout's server and web app (cgm-remote-monitor). It is
everything merged to the `dev` branch from 15.0.8 (2026-09-04) to `1ad03e29` (2026-10-03 01:00Z): mostly
fixes for defects present in 15.0.8, with dependency updates and translations. It is not tagged;
the checks still owed before the tag are listed in [§8](#what-is-left-open) and in
[contents §Open items](contents.md#open-items-a-releaser-must-settle).

| figure | value | command |
|---|---|---|
| time frame | 2026-09-04 (15.0.8's commit date, and the first merge) to 2026-10-02, the last merge's date in its committer's time zone (2026-10-03 01:00Z) | `git log --first-parent --format=%ad --date=short R \| sort \| sed -n '1p;$p'`; `git log -1 --format=%ad --date=short 15.0.8` |

<!-- chart: kpis -->

## 2. Size

| figure | value | command |
|---|---|---|
| PR merges | 97; every first-parent commit in the range is a PR merge | `git rev-list --first-parent --count R`; `git log --first-parent --merges --format=%h R \| wc -l` |
| commits | 543 (337 non-merge, 17 author names) | `git rev-list [--no-merges] --count R`; `git log --no-merges --format=%an R \| sort -u \| wc -l` |
| files | 313 of 894 on `dev` changed: 131 added, 179 modified, 1 deleted (`tests/loop-server.test.js`), 2 renamed | `git diff --name-status official/master official/dev`; `git ls-tree -r --name-only official/dev \| wc -l` |
| lines | +30,210 / −1,935 | `git diff --shortstat official/master official/dev` |
| new modules under `lib/` | 18 | `git diff --name-status official/master official/dev -- lib \| grep -c '^A'` |

<!-- chart: merges -->

By directory (files changed / files on `dev`, lines):

| directory | changed / on `dev` | lines |
|---|---:|---:|
| `tests` | 142 / 320 | +21,535 / −132 |
| `lib` | 105 / 241 | +5,113 / −931 |
| `translations` | 34 / 34 | +1,021 / −4 |
| root files | 11 / 30 | +1,609 / −861 (`package-lock.json` +1,357 / −815) |
| `docs` | 11 / 84 | +838 / −3 |
| `static` | 3 / 133 | +31 / −0 |
| `views` | 5 / 15 | +29 / −4 |
| `.github` | 1 / 6 | +27 / −0 |
| `tools` | 1 / — | +7 / −0 |
| `bin` | 0 / 12 | — |

Command: `git diff --numstat official/master official/dev`, summed by first path segment;
`git ls-tree -r --name-only official/dev <dir> \| wc -l`.

PR merges per phase (`git log --first-parent --format=%ad --date=short R | sort | uniq -c`):

| dates | merges | what merged |
|---|---:|---|
| 09-04 – 09-06 | 32 | cycle opens (#8597); 15 Dependabot updates; outside contributors' fixes; two Crowdin syncs |
| 09-09 | 1 | #8726, routine logging off by default |
| 09-17 – 09-21 | 15 | Phase 0 backfix PRs and the three live-update access fixes (#8744–#8746) |
| 09-23 – 09-24 | 14 | backfix 2, connector 0.1.0 pin, count compatibility, login hardening |
| 09-25 – 09-27 | 24 | #8758 (records keep their own `_id`), GitHub triage fixes, three carried outside PRs, regression fixes, #8784–#8786 |
| 09-30 – 10-02 | 11 | #8788, #8790 (outside contributor), #8791, #8793–#8796, #8799–#8802 |

## 3. Contributions

### PR merges by PR author

Command: the PR number from each first-parent subject
(`git log --first-parent --format=%s R | grep -oE '#[0-9]+'`), then one GraphQL query for all 97
(`gh api graphql`, `pullRequest(number:N){author{login} headRepositoryOwner{login}}` on
`nightscout/cgm-remote-monitor`), equivalent to `gh pr view N --json author` for each.

| GitHub login | PRs | from |
|---|---:|---|
| bewest | 54 | branches in `nightscout/cgm-remote-monitor`: the 50 programme backfix PRs in [contents](contents.md#programme-backfix-prs-50-plus-8741), three connector pins (#8752, #8759, #8762) and #8750 |
| dependabot | 15 | Dependabot branches, all merged 2026-09-05 |
| AndyLow91 | 10 | 8 from `nightscout/` branches (#8597, #8697, #8699, #8701, #8702, #8726, #8778, #8781), 2 from a fork (#8601, #8602) |
| bjorkert | 4 | fork |
| awss1i | 2 | fork |
| sulkaharo | 2 | the Crowdin syncs #8599 and #8603 (`crowdin_incoming`) |
| alanshurafa, alias-rahil, je-l, jgr-lab, lejcey, NandhaKishorM, PieterGit, toniuhlemann, vidia, wyomarus | 1 each | fork |

16 logins. The release PR #8598 (`dev` → `master`) is AndyLow91's and is not in the range.

### Outside contributors' PRs

PRs from forks, leaving out AndyLow91's two: 16 PRs by 12 logins. What
each changes is in [contents §Other fixes](contents.md#other-fixes-external-and-upstream-contributors).

| PR | login | merged | what |
|---|---|---|---|
| #8587, #8589, #8590, #8567 | bjorkert | 09-04, 09-05 | COB pill uses the uploader's COB; report page built once; treatments filter by event type; deleted documents no longer resurrected in the cache |
| #8516 | PieterGit | 09-04 | README: MongoDB 4.4 support note (amended by #8750) |
| #8583 | NandhaKishorM | 09-05 | Loop remote-command errors without internal diagnostics |
| #8588 | toniuhlemann | 09-05 | report SGV de-duplication no longer cascades |
| #7338 | jgr-lab | 09-06 | js-beautify option in docs |
| #8729 | wyomarus | 09-20 | chart update guarded against a 0-height container |
| #8741 | vidia | 09-20 | credential settings kept as strings |
| #8732 | alias-rahil | 09-21 | profile and pill behaviour on sites with incomplete data |
| #8530 | alanshurafa | 09-25 | a 48-hour choice in the main chart |
| #8568 | lejcey | 09-25 | AAPS loop re-enable ends the offline marker (BF-114) |
| #8419 | je-l | 09-25 | iOS Loop push-notification and websocket tests |
| #8788, #8790 | awss1i | 09-30, 10-01 | Day to Day events past midnight (BF-148); Food Editor scrolls by touch (BF-150) |

### Commits

Command: `git shortlog -sn --no-merges R`, grouped here by the GitHub login of the PR author above.

| who | commits |
|---|---:|
| bewest | 135 |
| Crowdin syncs (sulkaharo's account) | 103 (99 "New translations en.json", 4 "Update source file en.json") |
| AndyLow91 | 47 |
| dependabot | 15 |
| the outside contributors listed above, and one Copilot-authored commit | 37, from 13 author names |
| **total** | **337** non-merge commits |

The earliest non-merge commit is from 2022 (#7338's branch).

## 4. Tests added

| figure | 15.0.8 | 15.0.9 candidate | command |
|---|---:|---:|---|
| `it(` calls under `tests/` | 1,288 | 2,361 | `git grep -cE '^\s*it\(' <ref> -- tests`, summed |
| `*.test.js` files under `tests/` | 157 | 253 | `git ls-tree -r --name-only <ref> tests \| grep -c '\.test\.js$'` |
| of them at `tests/*.test.js` (what `npm test` runs) | 133 | 227 | `git ls-tree --name-only <ref> tests/ \| grep -c '\.test\.js$'` |
| lines, `tests/` | — | +21,535 / −132 (142 files; 102 added) | `git diff --shortstat official/master official/dev -- tests` |
| lines, `lib/` | — | +5,113 / −931 (105 files) | `git diff --shortstat official/master official/dev -- lib` |
| passing / failing / pending, full suite | 1533 / 0 / 3 | 3563 / 0 / 4 | below |

`it(` counts static calls; mocha's executed count also includes tests generated in loops, so the
two rows differ.

- **15.0.8: 1533/0/3**, measured 2026-09-27, one cell, in a clean checkout of `92d08342` (Node
  24.15.0, a fresh `mongo:7.0.43` container with `--ulimit nofile=64000:64000`), with
  `NODE_ENV=test npx env-cmd -f <env> mocha --timeout 5000 --require ./tests/hooks.js --exit ./tests/*.test.js`
  ([snapshot §4](../../docs/60-research/programme/paving-the-cowpaths-2026-09-27.md#4-delta-in-testing)).
- **Candidate: 3563/0/4** on #8802's head `b13b7a3a`, which has the same tree as `1ad03e29`
  (`7d16c516`), Node 24.15.0, MongoDB 7.0.43, one cell, fresh database, 2026-10-02
  ([contents §Evidence](contents.md#evidence)). 2,030 more passing tests than 15.0.8 (2.32×).
- **Last six-cell run: run 020 on `ce30a94d`, 3473/0/3** (2026-09-27; Node 20.20.0 / 22.23.2 /
  24.20.0 × MongoDB 4.4.24 / 7.0.43). Run 021, the six-cell run on the final head `1ad03e29`, is in
  progress.
- CI on #8598 at `1ad03e29`: 27 checks passed, 3 skipped (read 2026-10-03 01:16Z; [contents §Identity](contents.md#identity)).

### Run history

From the [integration record's run history](../../docs/30-design/remedial/rc-15.0.9-integration-record.md#run-history).
Each run is a candidate tree (`dev` plus the units under test), so a count can fall when a unit is
removed. Every run had 0 failing except 016 (4–5 failing, from the Crowdin #8730 merge, which was
then held out).

| run | bf2 | a | b | c | d | e | 36b | 59 | 010 | 011 | 012 | 013 | 014 | 015 | 016 | 017 | 018 | 019 | 020 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| date (09-) | 23 | 23 | 23 | 23 | 23 | 23 | 23 | 23 | 24 | 25 | 25 | 25 | 25 | 25 | 25 | 25 | 26 | 26/27 | 27 |
| cells (blank: not recorded) | 2 | | | 6 | 6 | 12 | 6 | 6 | 6 | 6 | 6 | 6 | 6 | 6 | 6 | 6 | 6 | 6 | 6 |
| passing | 2480 | 2416 | 2421 | 2508 | 2520 | 2534 | 3015 | 3028 | 3046 | 3066 | 3090 | 3094 | 3097 | 3106 | 3139 | 3170 | 3396 | 3458 | 3473 |

<!-- chart: tests -->

After run 020, each merge was checked on its own branch, one cell (Node 22.23.2, MongoDB 7.0.43
unless stated), from the [integration record §After run 020](../../docs/30-design/remedial/rc-15.0.9-integration-record.md#after-run-020)
and [contents §Evidence](contents.md#evidence):

| merge | check | passing / failing / pending |
|---|---|---|
| #8785 `295f1177` | test only; CI nine cells; the file 12 of 12 | — |
| #8786 `7000eb18` | CI nine cells (Node 20/22/24 × MongoDB 4.4/5/6); byte-identical bundle | 3478/0/3 each |
| #8788 `3014f883` | local full suite on `bbc6e75e` | 3481/0/3 |
| #8791 `50bc1084` | branch | 3485/0/3 |
| #8793 `839a1565` | branch | 3502/0/3 |
| #8794 `a143d507` | branch; `npm ci` on Node 20/22/24 and npm 12; byte-identical bundle | 3512/0/4 |
| #8795 `25fc41d9` | `fdf88f4e`, fresh `npm ci` | 3532/0/4 |
| #8796 `ca6fcfaf` | `e20b66ba`, same tree | 3534/0/4 |
| #8799 `f105f688` | branch (documentation and the Azure template only) | 3534/0/4 |
| #8800 `74942ec6` | `a06e75d6`, same tree (Node 24.15.0) | 3538/0/4 |
| #8801 `68262e86` | its tree | 3552/0/4 |
| #8802 `1ad03e29` | `b13b7a3a`, same tree (Node 24.15.0), fresh database | 3563/0/4 |

How each unit adds to the count, step by step with titles compared, is in the integration record
("How each unit adds to the suite count"); #8758 alone added 489 tests at `ab7b22d6`.

### Probes and labs

| class | what it checks | count | where |
|---|---|---:|---|
| defect probes | each reproduces one register defect against a running server (or in process): exits 1 on a tree with the defect and 0 on a fixed one, run against 15.0.8 as the control | 16 tracked | `tools/lab/triage-2026-09/` |
| release-candidate probes | BF-131 (a deleted reading kept in the cache) and BF-146 (late API v3 treatments missing from IOB and COB), including after a restart | 2 | `tools/lab/rc-soak/probe-*.js` |
| A/B soak harness | 15.0.8 and the candidate fed the same synthetic traffic side by side; replies compared, with an expected-difference entry for each intended change, plus liveness, leak and latency checks and an A/A control | 1 harness, 13 expected-difference entries | `tools/lab/rc-soak/` ([README](../../tools/lab/rc-soak/README.md)), `expected-diffs.json` |
| browser probes | a headless browser drives the web page for client-side fixes (alarms, quick picks, treatment drag, subject edit, URL parameters) | 9 | `tools/review/probes/*-browser.js` |
| Phase 0 server probes | the first backfix PRs' fixes on a running server, with a provenance pre-gate that checks which code is loaded | 7 + `provenance.js` | `tools/review/probes/` |
| focused labs | records found, edited and deleted by their own `_id` (object-id); client address behind real proxies (proxy-trust); Nightscout-to-Nightscout connector sync (connector-soak); AAPS loop re-enable (aaps-offline); APNs connections left open (apns-shutdown); an open page's basal display after a temp basal is edited (bf94-browser) | 6 | `tools/lab/<name>/` |
| journey lab | plays the phones (Loop, Trio, AAPS, caregivers) against real servers so a person can walk user journeys in a browser | 1 | `tools/review/journey-lab/` |
| consumer-replay lab | 13 probes sending the exact request shapes 40 client projects send, to 15.0.8 and the candidate | 13 | results in [`reports/consumer-impact-15.0.9/lab-results.md`](../../reports/consumer-impact-15.0.9/lab-results.md); the scripts stay outside version control |
| queue gates | one script per acceptance check on a queue item; most also have a red control | 38 (35 `.js`, 3 `.sh`) | `tools/queue/gates/` |

Commands: `git ls-files tools/lab | wc -l` (333 files in 8 directories, 237 of them bf94-browser's recorded results); `git ls-files tools/review/probes | wc -l` (18);
`ls tools/queue/gates | wc -l`; the expected-difference count is `len(diffs)` in
`tools/lab/rc-soak/expected-diffs.json`. Run 020 ran 1 new probe and repeated 21 of run 019's.
One further probe is kept untracked because its defect's details stay out of the public tree.

## 5. Quirks and contracts defined

A quirk entry records one way real Nightscout documents depart from the schema that enough of
the ecosystem does that a reader must handle it, with its measured prevalence, the projects that
write it and what a reader should do ([`specs/quirks/README.md`](../../specs/quirks/README.md)).

| collection | quirk ids | status |
|---|---:|---|
| devicestatus | 5 | active |
| entries | 3 | active |
| profile | 4 | active |
| treatments | 5 | active |
| **all** | **17** | all `active` (measured in the corpus) |

Command: `grep -c 'id: QUIRK' specs/quirks/*.yaml`; `grep 'status:' specs/quirks/*.yaml | sort | uniq -c`.
Dates: `git log --format='%h %ad %s' --date=short -- specs/quirks`: all 17 added 2026-09-10
(`8bcc373d`); paths corrected 2026-09-16 (`1a10007b`). Re-measure with `make schema-quirks`.

What else defines the contract 15.0.9 is held to:

| material | count | command or source |
|---|---:|---|
| schema models, `specs/nsschema` | 10 collection models (`activity`, `auth_roles`, `auth_subjects`, `devicestatus`, `entries`, `food`, `profile`, `settings`, `status`, `treatments`), plus `server-indexes.json` and `dosing-input-sources.yaml`; added 2026-09-10 to 09-16 | `ls specs/nsschema/*.model.json \| wc -l`; `git log --format=%ad --date=short -- specs/nsschema` |
| conformance files | 483 | `git ls-files conformance \| wc -l` |
| mapping projects | 23 directories under `mapping/` (one is `cross-project`) | `ls -d mapping/*/ \| wc -l` |
| client census | 40 client repositories, each checked against the same 15 surfaces with a positive control for every "not found"; 67 consumer-visible changes (C1–C67) | [consumer impact](../../docs/60-research/remedial/consumer-impact-15.0.9-2026-09-23.md), [`reports/consumer-impact-15.0.9/`](../../reports/consumer-impact-15.0.9/change-inventory.md) |
| compatibility settings 15.0.9 adds | 3: `API_V1_COUNT_LEADING_NUMBER` and `API_V1_COUNT_ZERO_WINDOW` (on by default; oref0's `count=N?…` and GluPredKit's `count=0` in a date window, #8761) and `TRUST_PROXY` (unset is a documented permanent setting, #8754) | `git grep -nE 'API_V1_COUNT_\|TRUST_PROXY' official/dev -- lib/server/env.js`; [versioning policy §5.7](../../docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md#57-compatibility-flags) |

## 6. Defects

### Arrival by origin

Command: `python3 tools/programme/defect-arrival.py` (about 35 s). A defect's filing date is the
first commit under `docs/` that mentions its id. Origins are the snapshot's id lists, with BF-148 and BF-150 (GitHub issues #8223 and #8192) added
to `github`; an id not in a list counts as `latent`. Closed means the register status is `merged`, `closed` or
`decided`.

| origin | ids | closed | meaning |
|---|---:|---:|---|
| latent | 96 | 61 | present on 15.0.8, found by audit, lab, survey or review of an outside PR |
| github | 14 | 14 | reproduced from upstream GitHub issues (BF-107, BF-118–128, BF-148, BF-150) |
| connector | 9 | 9 | eight in nightscout-connect 0.1.0, which 15.0.9 pins exactly; BF-43 by the axios override (#8565) |
| review | 10 | 10 | found in review of #8758 before it merged; nine fixed on the branch, BF-110 kept by decision |
| escaped | 7 | 7 | introduced on `dev` by a merged fix PR ([below](#regressions-caught-before-release)) |
| seam, cuts, invalid | 24 | — | not part of 15.0.9 |
| **all** | **160** | | |

<!-- chart: arrival -->

<!-- chart: burnup -->

Per day, to 2026-10-03 (open and closed count only the 136 ids in scope):

| date | latent | github | connector | review | escaped | not in 15.0.9 | filed | closed | open |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 09-14 | 15 | 0 | 1 | 0 | 0 | 1 | 17 | 0 | 16 |
| 09-15 | 12 | 0 | 1 | 0 | 0 | 9 | 22 | 0 | 29 |
| 09-16 | 17 | 0 | 3 | 0 | 0 | 11 | 31 | 1 | 48 |
| 09-17 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 49 |
| 09-18 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 15 | 35 |
| 09-20 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 9 | 26 |
| 09-21 | 10 | 0 | 0 | 0 | 1 | 0 | 11 | 4 | 33 |
| 09-22 | 8 | 0 | 3 | 0 | 0 | 3 | 14 | 0 | 44 |
| 09-23 | 8 | 1 | 1 | 0 | 1 | 0 | 11 | 15 | 40 |
| 09-24 | 0 | 0 | 0 | 5 | 0 | 0 | 5 | 5 | 40 |
| 09-25 | 5 | 11 | 0 | 5 | 0 | 0 | 21 | 19 | 42 |
| 09-26 | 8 | 0 | 0 | 0 | 5 | 0 | 13 | 19 | 36 |
| 09-27 | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 1 | 36 |
| 09-30 | 1 | 1 | 0 | 0 | 0 | 0 | 2 | 1 | 37 |
| 10-01 | 4 | 0 | 0 | 0 | 0 | 0 | 4 | 2 | 39 |
| 10-02 | 6 | 0 | 0 | 0 | 0 | 0 | 6 | 7 | 38 |
| 10-03 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 35 |

The checks first run on each day are in the
[snapshot §5](../../docs/60-research/programme/paving-the-cowpaths-2026-09-27.md#5-defect-arrival).
Of the ids filed 09-30 to 10-02, BF-149 was found in review of #8788, and BF-153 and BF-154 in the
dependency advisory triage ([contents](contents.md#npm-audit-and-dependabot-triage)); BF-155 in review of
the BF-72 branch, and BF-156 while documenting the API v3 settings (BF-46); BF-157 while fixing
BF-124, BF-158 in BF-127's full-suite run, and BF-159 and BF-160 in the BF-124 and BF-127 browser
runs.

### Register totals

`node tools/queue/gates/register-exposure-legend.js` parses 159 status cells, 117 in §1 and 42 in
§1b/§1c. In §1: 22 `open`, 1 `partly merged` (BF-07), 3 `fixed` (on unmerged branches: BF-52,
BF-09, BF-156), 88 `merged` (in `dev`, not released), 3 not counted (BF-12, invalid; BF-41 and
BF-71, closed), 0 `landed`. The gate exits 1 by design while nothing is released: every
`fixed` and `merged` entry is still present for anyone running 15.0.8, so the exposure on the
shipping release is 114 entries until 15.0.9 is tagged and installed.

### What 15.0.9 closes, and what it carries

| figure | value | source |
|---|---:|---|
| register entries in scope marked `merged` | 99 (60 latent, 14 github, 9 connector, 9 review, 7 escaped), plus BF-110 `decided` and BF-71 `closed` | `defect-arrival.py --json`, by origin and status |
| in scope and not closed | 35 | the 10-03 row above; includes BF-07 and BF-63 (`partly merged`) and BF-52, BF-09 and BF-156 (`fixed` on unmerged branches) |
| rows in contents "What is NOT in 15.0.9" | 25 | [contents](contents.md#what-is-not-in-1509) |

The 25 rows are carried in the release notes as known issues, kept by decision, or deferred until
after 15.0.9. One of them is a defect live on 15.0.8 with no fix in 15.0.9: a class of expensive
search request can occupy the database for minutes (BF-72; its disposition is held privately).
BF-46 (`API3_AUTOPRUNE_*` settings that delete old records when set) is a known issue by decision
of 2026-10-02; #8799 documents the settings in 15.0.9.
BF-154 (a dependency advisory with no fixed release, in code Nightscout does not call) is named
in the release notes as well.

### What the open entries are

Every one of the 35 has a queue item, and every one is present on 15.0.8 or only on unreleased
branches and tooling, so none is a regression of 15.0.9. Each is in exactly one row below, as
recorded in the register and `queue/work-queue.yaml` on 2026-10-03.

| disposition | entries | count |
|---|---|---:|
| known issue, described in the 15.0.9 notes | BF-44, BF-45, BF-46, BF-67, BF-72, BF-86, BF-92, BF-93, BF-95, BF-132, BF-137, BF-145, BF-149, BF-152, BF-154, BF-156 | 16 |
| documentation merged for 15.0.9, code half later | BF-48, BF-49, BF-74, BF-78, BF-81 | 5 |
| fix prepared, after 15.0.9 | BF-09 | 1 |
| partly fixed in 15.0.9, the rest planned | BF-07, BF-52, BF-54, BF-63 | 4 |
| only on the modernization branches or in test tooling | BF-27, BF-53, BF-55, BF-88, BF-96, BF-158 | 6 |
| found in the BF-124 and BF-127 work, after 15.0.9 by decision | BF-159, BF-160 | 2 |
| found in the BF-124 work, not decided for 15.0.9 | BF-157 | 1 |
| **all** | | **35** |

- **Partly fixed:** BF-07's remainder is left by decision; BF-52's fix is ready and ships with
  BF-92's in a later release; BF-54 has no defect in shipped code and gets its regression test in
  cut 1's browser suite; BF-63's other half is on cut 4.
- **Documentation merged for 15.0.9, code half later** (#8799): BF-48 and BF-49 correct the README
  on the webhook settings and the HSTS setting's spelling; BF-74 says API v3 `settings` documents are
  stored as sent; BF-78 and BF-81 say which setting is the access boundary and which roles need
  `readable`. Each keeps a code half for after 15.0.9 (for BF-78, its boot warning). #8799 closed
  BF-50 and BF-51, and #8800 closed BF-94.
- **Fix prepared, after 15.0.9:** BF-09 makes a zero a real value in the live-update duplicate check
  where it carries meaning (a zero temp basal, a zero bolus), in #8797, deferred by decision because
  the path is AndroidAPS's legacy NSClient v1 and the trigger is two records within 2 s.
- **Found in the BF-124 and BF-127 work:** BF-157 (the chart and report place a treatment's
  glucose bubble as mg/dL when its units are spelled `mmol/L`; position only), BF-159 (the main page sometimes leaves for
  the Profile Editor while a profile exists, and drops the page's token on the way) and BF-160 (the
  clock designer's link target is written with curly quotes) are present on 15.0.8. BF-158 (the
  `count=0` tests assume an empty database) is in a test file added on `dev` and affects no site;
  whether its test-only fix goes into 15.0.9 is not decided. BF-124 and BF-127 merged as #8801 and
  #8802.
- **Closed:** BF-71 was closed on 2026-10-02 as working as intended and is not counted here.

<!-- chart: open -->

### Regressions caught before release

Seven defects were introduced on `dev` by merged fix PRs. All seven are absent from 15.0.8 and fixed
on `dev`; none reached a release. No register entry filed after 2026-09-27 (BF-147 to BF-160) is
described as a defect introduced on `dev` in code a site runs (BF-158 is in a test file added on
`dev`), and 14 merges have landed since the last regression fixes (#8781, #8783 on 09-26) with no
new one found.

| id | cause merged | filed | fix merged | family |
|---|---|---|---|---|
| BF-106 | #8737, 09-18 | 09-23 | #8771, 09-26 | a rule applied on one path and not its siblings |
| BF-140 | #8758, 09-25 | 09-26 | #8778, 09-26 | a rule applied on one path and not its siblings |
| BF-142 | #8758, 09-25 | 09-26 | #8783, 09-26 | a rule applied on one path and not its siblings |
| BF-141 | #8780, 09-26 | 09-26 | #8781, 09-26 | empty values: `""`, `null` and absent treated differently |
| BF-143 | #8780, 09-26 | 09-26 | #8781, 09-26 | empty values: `""`, `null` and absent treated differently |
| BF-144 | #8775, 09-26 | 09-26 | #8781, 09-26 | state held in the process and lost on restart |
| BF-80 | #8745, 09-21 | 09-21 | #8779, 09-26 | coupling to shared state (the failed-login delay list) |

<!-- chart: regressions -->

Each family is explained in the
[snapshot §6](../../docs/60-research/programme/paving-the-cowpaths-2026-09-27.md#6-the-regressions).
Source: the register entries; `escaped` ids in `defect-arrival.py`.

## 7. Process and methodology

The programme borrows the design-control vocabulary of medical-device quality systems as a working
method ([document control](../../docs/00-overview/DOCUMENT-CONTROL.md),
[definition of done](../../docs/00-overview/DEFINITION-OF-DONE.md); the ecosystem-wide proposal is
[QUALITY-SYSTEM](../../docs/00-overview/QUALITY-SYSTEM.md)). Borrowing the vocabulary is not a
claim of conformity with any standard.

| stage | control | where |
|---|---|---|
| design input | a register entry per defect (row and detail, status `open` / `merged` / `released`, mechanism only when live on 15.0.8); the [journey map](../../docs/60-research/remedial/journey-map-15.0.9.md); the 40-client census; maintainer decisions | backfix register; [consumer impact](../../docs/60-research/remedial/consumer-impact-15.0.9-2026-09-23.md); [decisions](decisions.md) |
| design output | each PR with a "What changes for you" section, its tests and register ids; release notes; tag message | [`releases/cgm-remote-monitor-15.0.9/`](./) |
| verification | six cells (Node 20.20.0 / 22.23.2 / 24.20.0 × MongoDB 4.4.24 / 7.0.43, version read from the server, one `mongod` per cell); additivity by test title; break-its, which count only when the failures show the defect; harness red controls; probes; A/B soak against 15.0.8 with expected-difference entries | [integration record §Method](../../docs/30-design/remedial/rc-15.0.9-integration-record.md#method); `tools/lab/` |
| validation | browser walk by the maintainer in Chrome on `ff93fa94` (2026-09-26), with the journey lab playing the phones and 15.0.8 side by side: 11 scenarios passed, no regression found; real sites running the candidate as the 24–72 h real-time soak, by the maintainer's decision of 2026-09-30 | [browser record](../../docs/60-research/remedial/journey-lab-browser-15.0.9-2026-09-26.md); [testing notes](testing-notes.md#where-testing-stands) |
| work control | 189 queue items in 6 parcels, 250 runnable gates and 244 explicit `no-gate: <reason>` markers; 38 gate scripts | `make queue-validate`; `ls tools/queue/gates \| wc -l`; [`queue/work-queue.yaml`](../../queue/work-queue.yaml) |
| review | 10 reviewer packets and an index, each generated from a queue item that wants a reviewer; `make packets-check` fails if one is stale or orphaned | [`reports/reviewer-packets/`](../../reports/reviewer-packets/README.md) |
| records | documents are corrected in place; records are dated and never edited; one living file per series; the verification record is generated. The 2026-09-16 record is marked superseded and no 15.0.9 record has been captured | DOCUMENT-CONTROL, DEFINITION-OF-DONE, [verification record](verification-record.md) |
| release decision | agents prepare and stop; people push, merge, tag and publish | [release README](../README.md) |

`make queue-status` (2026-10-03) reports PASS 95, FAIL 33, UNMEASURED 61 across the 189 items. FAIL
means a gate ran and said no; many are items not started or blocked, whose gate is their
acceptance test. UNMEASURED means nothing ran.

## 8. How this builds confidence

This section is for a reader outside the project: someone whose family relies on a Nightscout
site, or a developer of an app that reads from or writes to one. Nightscout is a secondary
display: it shows glucose and therapy data that other devices and apps produce. For each kind of
risk, the table says what was done and what it does not cover.

| risk | what addresses it | what it does not cover |
|---|---|---|
| **A fix breaks an app that talks to Nightscout** | A census of 40 client projects read what each sends and expects. A replay lab sent those exact requests to 15.0.8 and the candidate side by side; three findings that looked like breakages from reading the code did not reproduce. Where a fix would have broken a real client (oref0's and GluPredKit's `count`), the old behaviour is kept behind a named setting, on by default, with a deprecation warning. | Clients outside the 40, and private scripts. The census reads each client at its upstream tip, not every version in use. Some changes are deliberate corrections and are listed as such in the release notes. |
| **A fix introduces a new defect** | Every fix ships with tests (2,030 more passing than 15.0.8). Break-its undo a fix and check that its tests fail for the right reason. The suite runs in six cells of Node and MongoDB versions. An A/B soak runs 15.0.8 and the candidate on the same traffic and flags every difference not explained by an intended change. Seven defects introduced by fixes were caught and fixed before release. | Run 021, the six-cell run on the final candidate `1ad03e29`, is in progress; the thirteen merges since run 020 were each checked on one cell or in CI. The soak is compressed (minutes standing for hours) and synthetic. Break-its of most fixes ran on their own branches, not on the integrated tree. |
| **Behaviour on real devices** | The maintainer walked user journeys in a browser with 15.0.8 side by side (11 scenarios passed). Real sites ran the candidate as the real-time soak: as of 2026-09-29 one Loop, one Trio and one AndroidAPS user ran `7000eb18` for about two days with no errors, and on 2026-10-02 the maintainer reported stable behaviour from AndroidAPS, Trio and Loop users of `dev` through the week. | These reports are informal; how many sites and for how long is not recorded. Browser checks still owed include a remote bolus, LoopCaregiver from its own app, the clock views, the pump pill, alarm labels, reports during a percentage profile switch, the Day to Day report, the Food Editor on a touch screen, a temp basal cancelled while a page is open (BF-94), a treatment tooltip on an mmol/L site with an mg/dL profile (BF-124), and a clock opened from the menu with a token on a site that requires sign-in (BF-127). |
| **Security defects** | Fixes for defects live on 15.0.8 are merged: live-update access, the query operator allowlist, login hardening, error replies without internal detail, bounds on two little-used request types, storage errors that ended the process, and dependency advisories. This repository is public, so those defects are described by mechanism and outcome only until a release with the fixes ships. | One such defect has no fix in 15.0.9 (BF-72). Until 15.0.9 is installed, every fixed defect is still present on sites running 15.0.8. `npm audit` on the candidate reports 10 findings, triaged one by one in [contents](contents.md#npm-audit-and-dependabot-triage). |
| **What's left open** | 25 items are listed in "What is NOT in 15.0.9" and carried in the release notes as known issues or deferred by decision. 35 register entries in scope are not closed: 16 known issues, 5 whose documentation is merged for 15.0.9 with a code half later, 1 with a fix prepared for after 15.0.9, 4 partly fixed, 6 only on unreleased branches or tooling, and 3 found in the BF-124 and BF-127 work (2 after 15.0.9 by decision, 1 not decided) ([§6](#what-the-open-entries-are)). | |

### What is left open

Before the tag ([contents §Open items](contents.md#open-items-a-releaser-must-settle)):
run 021, the six-cell run on the final head `1ad03e29` (in progress); the browser hand checks
above; the version class of #8772, #8775 and #8780; re-approval of #8598 at its final head (both
approvals were given on `e3adc91d`); the `CHANGELOG.md` question; and the tag. The lab's 72-hour soak was not run, by decision.
Known test gaps are in [contents §Known test gaps](contents.md#known-test-gaps): 79 of the 227
`tests/*.test.js` files are reached only by `npm test` / `test-ci`.

## 9. Materials

Repository material used for the census-to-tests loop, counted with `git ls-files <dir> | wc -l`
(tracked files only; the snapshot counted the working tree with `find`, which includes untracked
and generated files):

| material | count | command |
|---|---:|---|
| upstream repository checkouts under `externals/` | 45 | directories under `externals/` containing `.git` |
| mapping projects | 23 directories, 123 files | `ls -d mapping/*/ \| wc -l`; `git ls-files mapping \| wc -l` |
| `specs/` | 114 files | `git ls-files specs \| wc -l` |
| `conformance/` | 483 files | `git ls-files conformance \| wc -l` |
| `traceability/` | 31 files | `git ls-files traceability \| wc -l` |
| `tools/lab/` | 333 files, 8 labs | `git ls-files tools/lab \| wc -l` |
| `tools/review/probes/` | 18 files | `git ls-files tools/review/probes \| wc -l` |
| `tools/queue/gates/` | 38 scripts | `git ls-files tools/queue/gates \| wc -l` |

Documents used for this page:

- [contents.md](contents.md), [decisions.md](decisions.md), [testing-notes.md](testing-notes.md), [release-notes.md](release-notes.md)
- [15.0.9 integration record](../../docs/30-design/remedial/rc-15.0.9-integration-record.md)
- [backfix register](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`queue/work-queue.yaml`](../../queue/work-queue.yaml)
- [quirks registry](../../specs/quirks/README.md)
- [consumer impact](../../docs/60-research/remedial/consumer-impact-15.0.9-2026-09-23.md) and [replay lab results](../../reports/consumer-impact-15.0.9/lab-results.md)
- [journey map](../../docs/60-research/remedial/journey-map-15.0.9.md) and [browser record](../../docs/60-research/remedial/journey-lab-browser-15.0.9-2026-09-26.md)
- [run 020 soak proof](../../tools/lab/rc-soak/results/proof-2026-09-27-run020.md)
- [DOCUMENT-CONTROL](../../docs/00-overview/DOCUMENT-CONTROL.md), [DEFINITION-OF-DONE](../../docs/00-overview/DEFINITION-OF-DONE.md), [QUALITY-SYSTEM](../../docs/00-overview/QUALITY-SYSTEM.md)
- [paving the cowpaths, 2026-09-27](../../docs/60-research/programme/paving-the-cowpaths-2026-09-27.md) (snapshot)

## 10. Method and history

**Paving the cowpaths.** 15.0.9 follows the rule that a specification describes what clients
actually do: take a census of what clients send, turn those shapes into tests and replay probes,
fix defects without breaking those shapes, and where a fix would break one, keep the old shape
behind a named setting with a deprecation signal. The examples and sources are in the
[snapshot §8](../../docs/60-research/programme/paving-the-cowpaths-2026-09-27.md#8-paving-the-cowpaths).

**The MongoDB driver upgrade.** 15.0.9 is the second release this year prepared this way; the
first was the MongoDB driver upgrade (#8421) that shipped in 15.0.7 on 2026-04-29. Figures and
links are in the
[snapshot §9](../../docs/60-research/programme/paving-the-cowpaths-2026-09-27.md#9-earlier-in-2026-the-mongodb-driver-upgrade).
