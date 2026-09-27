# Paving the cowpaths: the 15.0.9 release candidate as a quality record

*Contributor- and maintainer-facing. Snapshot, 2026-09-27, against cgm-remote-monitor `official/dev`
`295f1177` (the 15.0.9 candidate, release PR #8598) and `official/master` `92d08342` (tag `15.0.8`,
the shipping release), and this repository at `366366f0`. **DRAFT for maintainer review.** Nothing
here is tagged or released. What 15.0.9 contains lives in
[`releases/cgm-remote-monitor-15.0.9/contents.md`](../../../releases/cgm-remote-monitor-15.0.9/contents.md),
defect facts live in the [backfix register](../../30-design/remedial/nightscout-backfix-register.md), and
test runs live in the [integration record](../../30-design/remedial/rc-15.0.9-integration-record.md). This
record measures the candidate and does not restate those files. Published view:
<https://claude.ai/artifact/QgCm2hpc9KFugXu5c6v4wE> (private until shared).*

## 1. Readiness

| question | answer on 2026-09-27 |
|---|---|
| Ready for confirmation on real AID rigs? | **Yes.** Every PR decided for 15.0.9 is merged except Crowdin #8730 (held out, BF-132). Run 020: 3473 passing / 0 failing / 3 pending in six cells. #8598 on `295f1177`: open, mergeable, CI 27 passed and 3 skipped. |
| Checked on real AID rigs? | **No.** The 2026-09-26 browser walk on `ff93fa94` used the journey lab in place of the phones ([browser record](../remedial/journey-lab-browser-15.0.9-2026-09-26.md)). |
| Ready to tag? | **No.** Five items are owed ([contents §Open items](../../../releases/cgm-remote-monitor-15.0.9/contents.md#open-items-a-releaser-must-settle)): the remaining browser checks, the 24–72 h real-time soak, `npm audit` triage (17: 1 low, 13 moderate, 3 high), re-approval of #8598 at `295f1177` (both approvals, 2026-09-26 00:39Z, are on `e3adc91d`) with the version class of #8772/#8775/#8780, and the tag. |
| Open defects in scope | 35. Each is carried in the release notes as a known issue or deferred until after 15.0.9 by decision. |

## 2. Size of the release

| figure | value | command (in `externals/cgm-remote-monitor-official`) |
|---|---|---|
| time frame | 2026-09-04 (15.0.8 tag, first merge) to 2026-09-27 | `git log --first-parent --format=%ad --date=short official/master..official/dev \| sort \| sed -n '1p;$p'` |
| PR merges | 85 | `git rev-list --first-parent --count official/master..official/dev` |
| commits | 505 (316 non-merge, 16 authors) | `git rev-list [--no-merges] --count official/master..official/dev`; `git log --no-merges --format=%an … \| sort -u \| wc -l` |
| files | 296 of 885 changed (122 added, 171 modified, 1 deleted, 2 renamed); 589 unchanged | `git diff --name-status official/master official/dev`; `git ls-tree -r --name-only official/dev \| wc -l` |
| lines | +28,279 / −1,703 | `git diff --shortstat official/master official/dev` |

By directory (changed / files on `dev`): `tests` 134/312, `lib` 101/240, `translations` 34/34,
`docs` 11/84, root 10/30, `views` 2/15, `static` 2/133, `.github` 1/6, `bin` 0/12, other 1/19.
New modules under `lib/` (17) each open with a comment giving the rule they implement and the
client or register id behind it, for example `lib/server/srv-dates.js` (v3 history clock, BF-122,
BF-144) and `lib/server/treatment-fallback-key.js` (same-time treatments, BF-121).

## 3. Timeline

PR merges per phase: `git log --first-parent --format=%ad --date=short official/master..official/dev | sort | uniq -c`.

| dates | merges | what happened |
|---|---:|---|
| 09-04 – 09-06 | 32 | 15.0.9 cycle opens (#8597); Dependabot batch (15 updates including D3 5 → 7); outside contributors' fixes (COB, A1c, report SGV, cache resurrection, Loop remote-command errors) |
| 09-09 | 1 | #8726: routine logging off by default; connector pin to `234d47c` |
| 09-14 – 09-16 | 0 | code audit; register opens with BF-01 to BF-68 |
| 09-17 – 09-21 | 15 | Phase 0 backfix PRs (#8733–#8741, #8743) and the three socket advisory fixes (#8744–#8746) |
| 09-22 – 09-24 | 14 | backfix 2 (#8748–#8757), connector 0.1.0 pin (#8762), count compatibility (#8761), treatment drag (#8760), auth hardening (#8754) |
| 09-25 – 09-27 | 23 | #8758 (records keep their own `_id`); GitHub triage fixes (#8766–#8777); the carried outside PRs (#8568, #8419, #8530); regression fixes (#8778, #8779, #8781, #8783); #8784; #8785 (test only) |

## 4. Delta in testing

| figure | 15.0.8 | 15.0.9 candidate | command |
|---|---:|---:|---|
| `it(` calls under `tests/` | 1,288 | 2,290 | `git grep -cE '^\s*it\(' <ref> -- tests`, summed |
| `*.test.js` files | 157 | 245 | `git ls-tree -r --name-only <ref> tests \| grep -c '\.test\.js$'` |
| lines, `tests/` | — | +20,159 / −132 (134 files) | `git diff --shortstat official/master official/dev -- tests` |
| lines, `lib/` | — | +4,819 / −765 (101 files) | `git diff --shortstat official/master official/dev -- lib` |
| passing / failing / pending, full suite | 1533 / 0 / 3 | 3473 / 0 / 3 (six cells, run 020) | 15.0.8: below; candidate: integration record |

15.0.8 measured 2026-09-27 in `externals/work/crm-6a-rc-1508` (clean checkout of `92d08342`), Node
24.15.0, a fresh `mongo:7.0.43` container with `--ulimit nofile=64000:64000`, one cell:
`NODE_ENV=test npx env-cmd -f <env> mocha --timeout 5000 --require ./tests/hooks.js --exit ./tests/*.test.js`,
with `<env>` = `tests/ci.test.env` pointed at that container. The candidate passes 1,940 more tests
(2.27×).

Passing tests by run, from the integration record's run history (19 runs, every one 0 failing
except 016, 4–5 failing from the Crowdin merge):

| run | bf2 | a | b | c | d | e | 36b | 59 | 010 | 011 | 012 | 013 | 014 | 015 | 016 | 017 | 018 | 019 | 020 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| date (09-) | 23 | 23 | 23 | 23 | 23 | 23 | 23 | 23 | 24 | 25 | 25 | 25 | 25 | 25 | 25 | 25 | 26 | 26 | 27 |
| passing | 2480 | 2416 | 2421 | 2508 | 2520 | 2534 | 3015 | 3028 | 3046 | 3066 | 3090 | 3094 | 3097 | 3106 | 3139 | 3170 | 3396 | 3458 | 3473 |

Each run is a candidate tree (`dev` plus the units under test), so a count can fall when a unit is
removed. Known test gaps are listed in
[contents §Known test gaps](../../../releases/cgm-remote-monitor-15.0.9/contents.md#known-test-gaps);
the largest is that 73 of 219 `tests/*.test.js` files are reached only by `npm test` / `test-ci`.

## 5. Defect arrival

Reproduce with `python3 tools/programme/defect-arrival.py` (about 35 s). A defect's filing date is
the first commit under `docs/` that mentions its id. Origins:

| origin | ids | closed | meaning |
|---|---:|---:|---|
| latent | 84 | 51 | present on 15.0.8, found by audit, lab or survey |
| github | 12 | 10 | reproduced from upstream GitHub issues (BF-107, BF-118–128) |
| connector | 9 | 9 | eight in nightscout-connect 0.1.0, which 15.0.9 pins exactly; BF-43 by the axios override (#8565) |
| review | 10 | 10 | found in review of #8758 before it merged; nine fixed on the branch, BF-110 kept by decision |
| escaped | 7 | 7 | introduced on `dev` by a merged fix PR (§6) |
| seam, cuts, invalid | 24 | — | not part of 15.0.9 |

| date | latent | github | connector | review | escaped | not in 15.0.9 | total | closed (scope) | open (scope) | check first run that day |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 09-14 | 15 | 0 | 1 | 0 | 0 | 1 | 17 | 0 | 16 | code audit |
| 09-15 | 12 | 0 | 1 | 0 | 0 | 9 | 22 | 0 | 29 | code audit, tenancy seam |
| 09-16 | 17 | 0 | 3 | 0 | 0 | 11 | 31 | 1 | 48 | code audit, cut branches |
| 09-17 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 49 | |
| 09-18 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 15 | 35 | |
| 09-20 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 9 | 26 | |
| 09-21 | 10 | 0 | 0 | 0 | 1 | 0 | 11 | 4 | 33 | security advisory review |
| 09-22 | 8 | 0 | 3 | 0 | 0 | 3 | 14 | 0 | 44 | consumer survey (40 clients) |
| 09-23 | 8 | 1 | 1 | 0 | 1 | 0 | 11 | 15 | 40 | consumer replay lab |
| 09-24 | 0 | 0 | 0 | 5 | 0 | 0 | 5 | 5 | 40 | #8758 review |
| 09-25 | 5 | 11 | 0 | 5 | 0 | 0 | 21 | 19 | 42 | GitHub triage, #8758 review |
| 09-26 | 7 | 0 | 0 | 0 | 5 | 0 | 12 | 19 | 35 | RC runs, soak, journey lab |
| 09-27 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 35 | — (only #8785, test only) |

Findings:

- The daily count rises when a new kind of check is first run and falls once that check stops
  finding new defects. It is not a smooth decline.
- Since the last four merges (#8781, #8783, #8784, #8785), no id has been filed and no regression
  found. That covers one day.
- Real AID rigs are a check that has not been run yet. By the pattern above, it may produce a new burst.

## 6. The regressions

Seven defects were introduced on `dev` by merged fix PRs. All seven are absent from 15.0.8 and fixed
on `dev`; none reached a release.

| id | cause merged | filed | fix merged | family |
|---|---|---|---|---|
| BF-106 | #8737, 09-18 | 09-23 | #8771, 09-26 | a rule applied on one path and not its siblings |
| BF-140 | #8758, 09-25 | 09-26 | #8778, 09-26 | a rule applied on one path and not its siblings |
| BF-142 | #8758, 09-25 | 09-26 | #8783, 09-26 | a rule applied on one path and not its siblings |
| BF-141 | #8780, 09-26 | 09-26 | #8781, 09-26 | empty values: `""`, `null` and absent treated differently |
| BF-143 | #8780, 09-26 | 09-26 | #8781, 09-26 | empty values: `""`, `null` and absent treated differently |
| BF-144 | #8775, 09-26 | 09-26 | #8781, 09-26 | state held in the process and lost on restart |
| BF-80 | #8745, 09-21 | 09-21 | #8779, 09-26 | coupling to shared state (the failed-login delay list) |

- **A rule applied on one path and not its siblings.** #8737's schema-driven coercion dropped the
  default `date`/`sgv` walker for collections whose schema is empty (`activity`), so their numeric
  filters matched nothing. #8758's v3 reads showed a falsy `identifier` as the `_id`, and the v3
  DELETE filter reached a record by `_id` only when `identifier` was absent.
- **Empty values.** The same-time treatment key (#8780) read `""` as no identity on the incoming write
  but not on the stored record. The replacement pre-read (#8775) compared `null` as unequal to an
  absent field, which MongoDB's `{$eq: null}` matches.
- **State lost on restart.** The v3 history clock (#8775) lived only in the process; after a restart
  it began again from wall time, below a reader's cursor.
- **Coupling to shared state.** Scoping `/alarm` delivery to an entitlement (#8745) made it wait on
  the failed-login delay list, which a household behind one public address shares.

Detection: five of the seven were filed on the day their cause merged or the day after; BF-106 took
five days. Five came from the 2026-09-25/26 wave (#8758, 38 files, then ten PRs in one day; 13 PR
merges on 2026-09-26). Each fix PR adds tests for its family on the other paths as well; #8783 adds
30 and #8781 adds 32 (integration record, "How each unit adds to the suite count").

## 7. Process controls

The programme borrows the design-control vocabulary of medical-device quality systems as a working
method ([document control](../../00-overview/DOCUMENT-CONTROL.md)).

| stage | control | where |
|---|---|---|
| design input | a register entry per defect (row + detail, status word open / merged / released, mechanism only when live on 15.0.8); the journey map; the 40-client usage census; maintainer decisions | backfix register; [journey map](../remedial/journey-map-15.0.9.md); [consumer impact](../remedial/consumer-impact-15.0.9-2026-09-23.md); [decisions](../../../releases/cgm-remote-monitor-15.0.9/decisions.md) |
| design output | PR with "What changes for you", its tests and register ids; release notes; tag message | `releases/cgm-remote-monitor-15.0.9/` |
| verification | six cells (Node 20.20.0 / 22.23.2 / 24.20.0 × MongoDB 4.4.24 / 7.0.43, version read from the server, one `mongod` per cell); additivity by test title; break-its; harness red controls; probes; A/B soak against 15.0.8 with expected-difference entries | integration record §Method; `tools/lab/` |
| validation | browser walk by the maintainer with 15.0.8 side by side; real rigs over real days not yet run | browser record |
| work control | 171 queue items; each has a gate or an explicit `no-gate: <reason>`; 36 gate scripts | `queue/work-queue.yaml`, `make queue-status` |
| records | documents are corrected in place; records are dated and never edited; one living file per series; the verification record is generated. The 2026-09-16 record is marked superseded and no 15.0.9 record has been captured | DOCUMENT-CONTROL, DEFINITION-OF-DONE |
| release decision | agents prepare and stop; people push, merge, tag and publish | release train |

## 8. Paving the cowpaths

Ian Hickson, [Power dynamics in web specifications](https://ln.hixie.ch/?start=1721260117&count=1)
(2024-07-17): the WHATWG was founded on the rule that a specification must describe what
implementations and their users actually do, because clients depend on behaviour, not on documents.
The 2011 *Diabetes Data Bus* note (`t1pal-mobile-workspace/externals/diabetes/README`) describes one
store fed by many devices, with apps the user chooses subscribing to it. Nightscout, a secondary
display for CGM and pump data, is now that store, and several dozen independent clients depend on
how it actually behaves.

15.0.9 applies the rule in four steps. It takes a census of what clients send, turns those shapes
into tests and replay probes, fixes defects without breaking those shapes, and, where a fix would
break one, keeps the old shape behind a named setting with a deprecation signal:

| what clients do | 15.0.9 |
|---|---|
| oref0 sends `count=N?…`; GluPredKit sends `count=0` with a date window | #8761: both accepted with `Deprecation` / `Warning` headers; `API_V1_COUNT_LEADING_NUMBER`, `API_V1_COUNT_ZERO_WINDOW`, on by default; 15.0.9 stays a patch |
| earlier releases and clients stored string `_id`s | #8758: find, edit and delete by either form across v1, v3 and the websocket; +489 tests |
| AndroidAPS syncs through v3 history and deletes with `isValid: false` | #8775: v1 writes appear in v3 history; soft-deleted records stop counting; v1 hard delete kept by decision and documented |
| mmol/L sites mix units across thresholds | #8766: each threshold read on its own |
| operators sit behind proxies (Azure App Service) | `TRUST_PROXY` with a migration guide; unset is a documented permanent setting |
| clients use operators outside the new allowlist | #8743: a census of 14 client projects found none; refused operators answer 400 naming the operator; declared correction |

Material in this repository for that loop: 44 upstream repository checkouts under `externals/`,
mappings for 23 projects (`mapping/`), 118 files in `specs/`, 521 in `conformance/`, and 42 in
`traceability/`.

## 9. Earlier in 2026: the MongoDB driver upgrade

15.0.9 is the second release this year prepared this way. The first was the MongoDB driver upgrade
that shipped in 15.0.7.

| | |
|---|---|
| earlier attempt | #7344, "Upgrade MongoDB driver version for compatibility with MongoDB 5", opened 2022-02-16 by an outside contributor; closed unmerged 2026-05-01 as superseded by the work on `dev` |
| readiness work | [MongoDB update readiness report](../mongodb-update-readiness-report.md) and [impact assessment](../mongodb-modernization-impact-assessment.md) (2026-01-19): a test baseline first, then storage-layer analysis, then the driver change; ecosystem client patterns checked (Loop and Trio UUID `_id`s, re-upload deduplication) |
| the change | #8421 (`wip/bewest/mongodb-5x`), opened 2026-01-19, merged to `dev` 2026-03-16 (`cdef1e7c`); 147 files, +36,208 / −4,655; [reviewer's guide](../../PR-8421-reviewers-guide.md) |
| release | 15.0.7, tagged 2026-04-29 (release PR #8444, `7e0e77f8`): `mongodb` `^3.6.0` → `^5.9.2`; 15.0.6..15.0.7 is 237 commits, 180 files, +42,765 / −5,197 |
| commands | `gh pr view 7344 --json createdAt,closedAt`; `gh pr view 8421 --json createdAt,mergedAt,changedFiles,additions,deletions`; `git show <tag>:package.json \| grep '"mongodb"'`; `git diff --shortstat 15.0.6 15.0.7` |

The two releases share the method: census the clients, fix the baseline tests before the change,
land the change with the tests that pin the client shapes, and record what was measured.
