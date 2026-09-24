# cgm-remote-monitor 15.0.9 — contents

**Status: DRAFT for maintainer review. Contributor-facing; full technical depth intended.**
Nothing here is tagged or released. Measured 2026-09-23 against `official/dev` `74fc6619`,
`official/master` `92d08342` (= tag `15.0.8`, the shipping release) and the local candidate
branch `rc/15.0.9-additions-c` `b9c9828b`.

> Complements the generated changelog. The changelog is authoritative for *what merged*;
> this file records what the release is made of, how each figure was measured, and what is
> unsettled.

15.0.9 is **everything on `dev` at `74fc6619`, plus eight additions** decided by the maintainer
on 2026-09-22 and 2026-09-23 ([backfix-2 plan](../../docs/30-design/remedial/backfix-2-plan-2026-09-22.md)
§1, §1a). The additions are not yet merged to `dev`: four are open PRs, four are local branches.
Their figures come from the candidate integration branch, recorded in
[`rc-15.0.9-additions-c-2026-09-23.md`](../../docs/30-design/remedial/rc-15.0.9-additions-c-2026-09-23.md).
**Every addition figure below is a candidate rc, pre-merge figure**: the merge commits into
`dev` do not exist yet, and the SHAs a release will carry will differ.

## Identity

| | |
|---|---|
| Merged part | `official/master..official/dev` |
| Base (shipping) | `92d08342` = `15.0.8` |
| `dev` head | `74fc6619` (merge of #8746, 2026-09-21) |
| Commits on `dev` | 308 — `git rev-list --count official/master..official/dev` |
| First-parent merges on `dev` | **48** — `git rev-list --first-parent --count official/master..official/dev` (every first-parent commit in the range is a PR merge) |
| Diff on `dev` | 200 files, +14381/−1262 — `git diff --shortstat official/master official/dev` |
| Candidate rc | `rc/15.0.9-additions-c` `b9c9828b`, local, not pushed: `74fc6619` plus 8 `--no-ff` merges, one per addition |
| Candidate rc size over `dev` | 34 commits (26 plus the 8 merges), 38 files, +2248/−137 — `git rev-list --count 74fc6619..b9c9828b`; `git diff --shortstat 74fc6619 b9c9828b` |
| Candidate rc size over 15.0.8 | 342 commits, 219 files, +16611/−1381 — `git rev-list --count official/master..b9c9828b`; `git diff --shortstat official/master b9c9828b` |
| `package.json` version | `15.0.9` on `dev` and on the candidate rc |
| Release PR | #8598 (`dev` → `master`): open, `REVIEW_REQUIRED` — `gh pr view 8598 --json state,reviewDecision` |
| Tag | none. No `15.0.9` tag exists |

The 48 `dev` merges are `merged`, none is `released`. The eight additions are neither.

## What 15.0.9 contains

### Additions not yet on `dev` (candidate rc, pre-merge)

Order is the merge order on the candidate rc. `tip` is the branch tip that was merged; the
open PRs' heads match it (`gh pr view <n> --json headRefOid`). Commits are
`git rev-list --count 74fc6619..<branch>`.

| # | branch | tip | commits | PR | register | what |
|---|---|---|---|---|---|---|
| 1 | `docs/mongodb-floor` | `aabce4b1` | 1 | #8750 (open) | — | README: MongoDB 4.4 **deprecated**, still tested, to be dropped in a later release; replaces #8516's "not supported" |
| 2 | `bf/qs-6.16` | `46b20b38` | 1 | #8749 (open) | BF-87 | `overrides.qs` and `overrides.request.qs` 6.15.1 → 6.16.0; clears GHSA-q8mj-m7cp-5q26, GHSA-x5fp-wj9c-mxmx, GHSA-4mjr-xmp4-gh2g |
| 3 | `bf/count-zero-empty` | `d19043b2` | 3 | #8748 (open) | — (RT-COUNT0) | **amends #8738**: v1 reads with `count=0` answer `[]`; saves and updates ignore `count`; DELETE keeps #8738's refusal (below) |
| 4 | `bf2/backports` | `b5038500` | 2 | #8751 (open) | — | two `cherry-pick -x` security fixes from #8605 (`31c354d8`, `d3ac8026`): alarm-socket credential logging; per-collection read grant on two shared routes. Withheld-style PR body |
| 5 | `bf2/ops` | `e6a50e9a` | 4 | not opened | BF-10, BF-63 (renderer half) | `docker-compose.yml` `mongo` `ulimits nofile 64000`; Alexa default for unhandled request types; `isPluginEnabled` miss; `booterror.js` null-`err` guard |
| 6 | `bf2/auth-hardening` | `29e6430e` | 13 | not opened | BF-17, BF-30, BF-47, BF-88 | `bf/auth` + `bf/throttle` + `client-ip.js` backport (`06c83f2f`, `395f3207`, port `8b975b41`); new setting `TRUST_PROXY`; subject/role field allow-list |
| 7 | `bf2/subject-edit-keeps-fields` | `7103f657` | 1 on #6 | not opened | BF-47 (admin-page loss) | `save()` keeps stored `notes` and `created_at` when the request leaves them out |
| 8 | `bf/connect-pin-0.1.0` | `338deb7f` | 1 | not opened | BF-34, BF-08, BF-42, BF-43, BF-85, BF-89, BF-91 (connector) | `nightscout-connect` exact pin; **the committed tip pins `0.1.0-dev.1`**; the release pins `0.1.0` <!-- PENDING: connector v0.1.0 tag --> |

`bf/qs-6.16`, `bf2/auth-hardening` and `bf/connect-pin-0.1.0` each edit `package.json` and
`package-lock.json`, in disjoint hunks. On the candidate rc `package.json` has `qs` 6.16.0 (both
overrides), `nightscout-connect` `0.1.0-dev.1`, `proxy-addr` `^2.0.7`, `forwarded-for` `^1.1.0`
(`git show b9c9828b:package.json`). `lib/api/index.js` is the one library file edited by two
additions (#3 and #6); the rc record measures the overlap as textual adjacency only.

**The connector pin.** npm `next` is `0.1.0-dev.2` (`npm view nightscout-connect dist-tags`),
published from connector `v0.1.0-dev.2` = `official/dev` `fbd4e55`, which is `v0.1.0-dev.1`
(`1946beb`) plus connector PRs #77 (BF-89, `dea2bec`) and #78 (BF-91, `894b132`). No `v0.1.0` tag
exists (`git -C externals/nightscout-connect tag`). The worktree of #8 has an uncommitted
`0.1.0-dev.2` edit; the candidate rc merged the committed `0.1.0-dev.1` tip, so **the rc is not
evidence for `0.1.0-dev.2` or `0.1.0`** <!-- PENDING: connector v0.1.0 tag -->. The swap is
queue `P0-PIN`/`P0-LOCK`, after `P0-TAG`.

### Merged to `dev`

#### Programme backfix PRs (12), plus #8741

Register ids refer to
[`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md),
which is the home of every defect fact; this table does not restate them.

| PR | Merge | Date | Register | What |
|---|---|---|---|---|
| #8733 | `77d153d2` | 2026-09-17 | — (queue P0-T01) | remove the two quadratic scans over the treatment window (`processDurations`, `calcdelta`); NaN-`mills` dedup restored as the one deliberate behaviour change |
| #8737 | `025f1310` | 2026-09-18 | BF-02, BF-03, BF-11, BF-32, BF-40, BF-68 | schema-driven query coercion (158 coercions, 5 collections); `$exists` operand read as a boolean for `true`/`false`/`1`/`0` only; digits-only `$type` operand kept numeric |
| #8738 | `d3358e91` | 2026-09-18 | BF-01, BF-05, BF-13, BF-14, BF-15, BF-33 | count endpoint uses each collection's `query_for`; count-path log removed; v3 paging tiebreak; v3 dotted `?fields=`; v1 `?count=` and v3 `?limit=` validation (new `lib/server/count.js`). Its v1 `count=0` rule is amended by #8748 below |
| #8734 | `fdd08706` | 2026-09-18 | BF-36 | client merge of a delete plus an unmatched update no longer throws and freezes the page |
| #8743 | `1a36f023` | 2026-09-18 | BF-04, BF-70 | v1 query-operator allowlist (new `lib/server/query-operator-allowlist.js`); URL-supplied aggregation pipeline refused; refused filters answer 400 naming the operator |
| #8740 | `49f562d8` | 2026-09-20 | BF-06, BF-07 (partly) | cache clone cost; BF-07 remains `partly merged` |
| #8735 | `ff0d506c` | 2026-09-20 | BF-16, BF-35 | quick-pick chooser index mismatch; `/api/v1/food/quickpicks` stops dropping non-editor quick picks; hidden and position ordering restored |
| #8736 | `2e94de1b` | 2026-09-20 | BF-37, BF-38, BF-39 | bare URL parameter no longer halts page load; `%10`+ translation slots; `_` no longer rewritten to a space in query parameters |
| #8739 | `7a5561f4` | 2026-09-20 | BF-28, BF-29, BF-31 | insulin-age URGENT comparison; unrecognised `ENABLE` entry suggestion; Alexa/Google Home request locale no longer changes process-global state |
| #8744 | `a9acd313` | 2026-09-21 | BF-79 | main-namespace `loadRetro` gated on read authorization (GHSA-gjhc-pc29-r3m6) |
| #8745 | `2b22c0ce` | 2026-09-21 | BF-75, BF-76 | `/alarm` namespace delivers only to a read-entitled room; access-token `ack` requires the ack permission (GHSA-8849-qjp5-vrrj). BF-76's unbounded `silenceTime` is left open deliberately |
| #8746 | `74fc6619` | 2026-09-21 | BF-77 | "readable by world" admin notice raised on role membership, so `TREATMENTS_AUTH=off` (`readable careportal`) now warns |
| #8741 | `bcd171cb` | 2026-09-20 | — (external contributor) | credential and identifier settings kept as strings (leading `+`, leading zeros) |

#### Other fixes (external and upstream contributors)

| PR | Merge | Date | What |
|---|---|---|---|
| #8732 | `59430336` | 2026-09-21 | profile and pill behaviour on sites with incomplete data (fixes #7324; also touches insulin age — reconciled with #8739 in merge `838537d8`) |
| #8729 | `1abc1aad` | 2026-09-20 | guard `chart.update()` against a 0-height container measurement |
| #8726 | `a8888f0d` | 2026-09-09 | routine log volume off by default; adds `DEBUG_LOGGING` and `CONNECT_DEBUG`; moves the connector pin to `234d47c` (fixes #8714). The pin is replaced by `bf/connect-pin-0.1.0` below |
| #8702 | `ca35f2a3` | 2026-09-06 | preserve valid unnamed profiles in conversion and editor |
| #8701 | `5a09befd` | 2026-09-06 | preprocess schedules imported by profile switches |
| #8699 | `6fbff0ec` | 2026-09-06 | clock view: worried emoji for low and falling readings |
| #8697 | `0ab266a3` | 2026-09-06 | failed treatments queries no longer crash the server (new `lib/api/shared/query-error.js`) |
| #8583 | `4f6151d7` | 2026-09-05 | actionable Loop remote-command errors without internal diagnostics (new `lib/api2/loop-notification-errors.js`) |
| #8602 | `57f45284` | 2026-09-05 | Daily Stats estimated A1c computed from mg/dL readings in both unit modes |
| #8588 | `c1943ced` | 2026-09-05 | report SGV one-minute de-duplication no longer cascades (new `lib/report/uniqsgv.js`) |
| #8567 | `948aafac` | 2026-09-05 | deleted documents no longer resurrected in the runtime cache |
| #8601 | `56ebbf30` | 2026-09-05 | npm 12 deployment: `.npmrc` `allow-remote=root` for the connector tarball; Node 24/npm 12 CI job |
| #8587 | `48441640` | 2026-09-04 | COB pill uses the COB reported by the uploading system (new `lib/client-core/devicestatus/cob.js`) |
| #8589 | `2af0aed9` | 2026-09-04 | report page built once per page load |
| #8590 | `101f51a0` | 2026-09-04 | treatments table filter by event type |

#### Dependency updates

| PR | Merge | What |
|---|---|---|
| #8573 | `e7c0cd6f` | **D3 5.16 → 7.9.0** with chart-interaction tests — see [Open items](#open-items-a-releaser-must-settle), item 3 |
| #8529 | `9205ea30` | UUID (retain patched UUID 11) |
| #8544 | `97d1aa1b` | jsdom and analyzer `ws` (dev dependencies) |
| #8550 | `7e71fb62` | Babel toolchain |
| #8565 | `eedc9439` | Axios |
| #8566 | `c5fd8054` | Socket.IO transports |
| #8571 | `6fb8db1c` | Express and body-parser |
| #8575 | `f7c7812c` | ip-address 10.7.0 |
| #8576 | `4b62921b` | fast-uri 3.1.7 |
| #8577 | `4b665293` | socket.io-parser 4.2.7 |
| #8578 | `3bb07409` | DOMPurify 3.4.14 (test reference only) |
| #8579 | `a363d760` | js-yaml 3.15.2 / 4.3.2 |
| #8581 | `02c63225` | Mocha 11.8.0 |
| #8582 | `1156aafd` | PostCSS 8.5.28 |
| #8586 | `d6e90d00` | brace-expansion (all compatible majors) |

All merged 2026-09-05.

#### Translations

#8599 `9f1b4d3a` (2026-09-05) and #8603 `b982e1e9` (2026-09-06), Crowdin.

#### Docs, CI and version

| PR | Merge | Date | What |
|---|---|---|---|
| #8597 | `5c26c9d2` | 2026-09-04 | start the 15.0.9 cycle (`package.json` → `15.0.9`) |
| #8516 | `85fed44b` | 2026-09-04 | README: MongoDB 4.4 no longer supported — amended by #8750 below |
| #7338 | `57d1cac9` | 2026-09-06 | js-beautify option in docs |

## Version number: 15.0.9

Decided 2026-09-22 (queue `RT-VERSION`; backfix-2 plan §1). The release is **15.0.9**, the number
`dev`'s `package.json` already carries. #8738 (as amended by #8748), #8743 and `bf2/auth-hardening`'s
subject/role field allow-list ship as **declared corrections** in the release notes, with no
compatibility flag. The facts the classification rests on, for the record:

- Under
  [`gt4-semver-classification-2026-09-15.md`](../../docs/60-research/modernization/gt4-semver-classification-2026-09-15.md)
  the `dev` content is at least a minor (`DEBUG_LOGGING`, `CONNECT_DEBUG`, routine debug logging
  off by default, new `lib/api2/loop-notification-errors.js`); the additions add `TRUST_PROXY`.
- #8738 and #8743 grade themselves major in their own bodies; so does #8739 (per-request locale
  on the Alexa and Google Home endpoints removed with no replacement). The auth-hardening
  allow-list was graded major in queue item P0-C before the maintainer ruled (2026-09-23) that
  the allow-list is the declared schema.
- Dev-channel deployments already report `15.0.9` from `/api/v1/status`
  (`lib/server/env.js` → `lib/api/status.js`). The release notes say so.
- The modernization cut branches also carry `15.0.9` in `package.json`; each cut is renumbered
  when it is rebased (backfix-2 plan §1a, "cut numbering").

## What is NOT in 15.0.9

| Item | State | Consequence |
|---|---|---|
| BF-69 — Bolus Wizard quick-pick chooser built once from an empty sandbox | fixed on a local branch (backfix 3); destination release not decided | the chooser can offer only "(none)"; the notes carry it as a known issue |
| BF-86 / BF-67 — thresholds in the wrong units | open | carried as a known issue in the notes |
| BF-76 — unbounded `silenceTime` | open, left open deliberately by #8745 | carried as a known issue |
| `TRUST_PROXY` planned flip | none planned (flag registry, backfix-2 plan §4) | unset is a permanent, documented setting; BF-30 is closed only where an operator sets it |
| Crowdin PR #8730 | open (`gh pr view 8730 --json state`) | translations after #8603 are not included |

Other `open` register entries that reach 15.0.9 are listed in the register's §1; this file
does not copy them.

## Open items a releaser must settle

1. **Connector tag.** `bf/connect-pin-0.1.0` moves from `0.1.0-dev.1` to `0.1.0` when `v0.1.0` is
   tagged and published (`P0-TAG`, then `P0-PIN`, `P0-LOCK`). The notes describe 0.1.0 and mark
   every dependent sentence `PENDING: connector v0.1.0 tag`. After the swap, re-run the suite and
   `TEST=debug-logging` against the new lockfile; the candidate rc does not cover it.
2. **The four unopened additions** (`bf2/ops`, `bf2/auth-hardening`, `bf2/subject-edit-keeps-fields`,
   `bf/connect-pin-0.1.0`) need PRs; whether `bf2/subject-edit-keeps-fields` is its own PR or the
   final commit of the auth-hardening PR is open (the rc record recommends folding it in). The
   auth-hardening PR body's posting style (full or withheld) is the maintainer's decision, since
   BF-17 and BF-30 are live on 15.0.8.
3. **D3 5.16 → 7.9 (#8573).** Decided (RT-D3, 2026-09-23): a manual browser check plus an
   automated browser test. The automated run exists
   ([browser evidence](../../docs/60-research/modernization/rt-d3-and-alarm-browser-evidence-2026-09-22.md));
   the manual check is still owed. `TEST=dependency-d3` passes (24) with both treatment-drag
   clamps in `lib/client/renderer.js` deleted, so the suite does not exercise that boundary.
4. **`/alarm` client path under `AUTH_DEFAULT_ROLES=denied`**: authenticate at the prompt, fire an
   alarm, confirm it arrives. No test covers this client path.
5. **Hand-written `CHANGELOG.md` `[Unreleased]` section on dev** (71 lines, 12 commits by
   upstream contributors) against the stated rule that the changelog is generated at release
   time. See [`../README.md`](../README.md#open-item-changelog-on-dev).
6. **Test-script coverage.** Several test files (e.g. `tests/query.operands.test.js`,
   `tests/api.count-where.test.js`, `tests/boluscalc.quickpick.test.js`, and from the additions
   `tests/client-ip.test.js`, `tests/authdelay.test.js`, `tests/authsubjects.test.js`,
   `tests/booterror.test.js`, `tests/storage-read-permissions.test.js`) match neither
   `npm run test:unit` nor `test:integration`; only `npm test` / `test-ci` (what `main.yml`
   runs) reaches them. A green `test:unit` is not evidence for those fixes.
7. **Missing end-to-end test**: a numeric filter on `count/devicestatus/where` returning rows
   from a live database. The #8737 + #8738 composition is measured at the constructed
   `$match` only.
8. **Untested line.** `bf2/auth-hardening`'s `app.set('trust proxy', …)` in `lib/api/index.js`
   has no test; removing it leaves the full suite at 2508/0/3 on the candidate rc, because the
   mounted sub-app inherits `lib/server/app.js`'s setting (rc record, "the overlap").

## Operator-visible behaviour changes (source for the release notes)

Each is described in its PR body's "What changes for you" section; the release notes carry
the user-facing form. Facts the notes must not lose:

- **Insulin age (#8739).** The URGENT level now applies at and beyond `IAGE_URGENT` (default
  72 h) for everyone. The notification still requires `IAGE_ENABLE_ALERTS` (default off) and
  fires only when `age === IAGE_URGENT` and `minFractions <= 20` — once, with no catch-up.
  Past the threshold the level had been understated as WARN the whole time.
- **`?count=` for real clients (bf/count-client-compat `b4ead206`, not yet a PR; RT-COUNT-COMPAT,
  decided 2026-09-24).** Amends the next bullet on v1 GET/HEAD: `N?<anything>` reads `N` (oref0);
  `count=0` with a `find` bounding one date field from both sides reads a limit of 2147483647
  (GluPredKit), and without one reads as no count. Both set `Deprecation: true` and a 299
  `Warning`, logged once per process without the value. DELETE is unchanged. Until it merges, dev
  behaves as the next bullet says.
- **`?count=` (#8738 amended by #8748).** On v1: `count=0` / `00` on a read answers `200 []`;
  `abc`, `1e2`, `-3`, `0x10`, `2.5` and integers above `Number.MAX_SAFE_INTEGER` answer
  `400 Bad count`; POST and PUT ignore `count`; DELETE with `0` or a malformed count answers 400
  and deletes nothing; DELETE with a valid count is accepted and does not limit the delete.
  Measured live on the candidate rc (rc record, "Count rules, live"). Routes that never apply
  `count` (`/entries/current`, `/count/:storage/where`, `/echo`, `/status`, `/food`) answer
  `count=0` normally. `/experiments` is mounted before the validator. v3 `?limit=` keeps #8738's
  rule: `0`, non-digits and values above `API3_MAX_LIMIT` answer 400 (`lib/api3/generic/collection.js`
  `parseLimit`). On 15.0.8, `?count=0` returned the whole collection on the database path.
- **Filters (#8737).** "Earlier results may have under- or over-reported delivered therapy"
  must survive into the notes. `$exists` reads only `true`/`false`/`1`/`0`; `null`, `no`,
  `off`, empty and others still mean "has the field".
- **Operator allowlist (#8743).** Refused operators answer 400 naming the operator instead of
  500. `$expr` on `/api/v1/profiles/` and the `pipeline` parameter on `/api/v1/count/…` are
  refused. A census of 14 client projects found no use of a refused operator. Declared
  correction.
- **Subject/role allow-list (`bf2/auth-hardening`, BF-47).** `create()` and `save()` write only
  `name`, `roles`, `notes`, `created_at` (subjects) and `name`, `permissions`, `notes`,
  `created_at` (roles). Other stored fields are dropped on the next save. Declared correction
  (maintainer, 2026-09-23). A corpus check found no open-source client storing other subject
  fields.
- **Subject edit (`bf2/subject-edit-keeps-fields`).** A save that omits `notes` or `created_at`
  keeps the stored values; `notes: ""` clears; `roles` is not filled in from storage, so removing
  the last role still works.
- **BF-17 (`bf2/auth-hardening`).** A save no longer writes `accessToken`/`accessTokenDigest`/
  `digest`. Existing rows keep them until the subject is next saved; clearing a row does not
  retire the token. Rotation text is P0-C-REMEDIATE's; the gate
  `node tools/queue/gates/bf17-remediation-note.js` guards the notes (17/0), and
  `tools/queue/gates/bf17-rename-row-control.sh` is its control (exits 1).
- **BF-30 and `TRUST_PROXY` (`bf2/auth-hardening`).** The delay sleeps only on the failure path;
  the list is swept and capped. Unset `TRUST_PROXY` resolves the client address as `dev` does
  (`forwarded-for`), and a boot message says the delay does not protect against guessing.
  `false` = direct-only; a list of IPs/CIDRs = trusted boundary. `true`, hop counts and named
  ranges are refused at boot. Setting it behind a TLS-terminating proxy that is not listed
  causes an https redirect loop.
- **Docker Compose (BF-10).** `mongo` service gains `ulimits nofile 64000`; on `dev`'s file
  mongod aborted with `Too many open files` (bf2/ops PR body). Not re-measured on the rc.
- **Legacy ingestion (RT-4).** No separate deprecation release. `MMCONNECT_*` (mmconnect) is
  reported not to work (maintainer, operational knowledge, not measured) and is to be retired;
  `BRIDGE_*` Dexcom settings are served by nightscout-connect by default since 15.0.8
  (`lib/server/bootevent.js` `migrateBridgeToConnect`), with `DEXCOM_BRIDGE_USE_LEGACY=true` as
  the escape hatch. The removal release is not numbered.
- **MongoDB 4.4 (#8750).** Deprecated, still in the CI matrix (`mongodb-version: [4.4, 5.0, 6.0]`)
  and passing on the candidate rc (4.4.24). The removal release is not numbered.
- **Connector (#8726 logging; `bf/connect-pin-0.1.0`).** Credential and payload logging ends for
  upgraders from v0.0.13 (BF-42), already at `dev`'s `234d47c`; `overrides['nightscout-connect'].axios`
  1.20.0 satisfies the connector's `^1.18.1` (BF-43 is master-only). With 0.1.0
  <!-- PENDING: connector v0.1.0 tag -->: BF-85 CareLink `sg: 0` filtered at ingestion
  (read-derived, not reproduced); BF-34/BF-08 backoff merge order, delay cap and jitter; listener
  release on stop; BF-89 reader subject created with `roles` (end-to-end run in `dea2bec`'s
  message; a subject created by an earlier connector is reused without roles); BF-91 `capture`
  mode only. New optional `CONNECT_START_JITTER_MS`, `CONNECT_INTERVAL_JITTER_MS`, default 0.
- **Live-update security (#8744, #8745), backports (#8751).** Mechanism only in public text;
  advisory write-ups are withheld until release.
- **World-readable notice (#8746).** Sites with `TREATMENTS_AUTH=off` now see the admin notice.
- **COB (#8587)**, **A1c (#8602)**, **report SGV filtering (#8588)**: displayed values may
  change on the same data.

## Evidence

- Merged part: per-PR test evidence, ablations and controls are in each PR body and in the
  register entry for each id.
- Additions: the candidate rc record,
  [`rc-15.0.9-additions-c-2026-09-23.md`](../../docs/30-design/remedial/rc-15.0.9-additions-c-2026-09-23.md):
  `npm test` 2386 → 2508 passing, 0 failing, 3 pending, additive per step and by test title,
  and 2508/0/3 on Node 20.20.0, 22.23.2 and 24.20.0 × MongoDB 4.4.24 and 7.0.43; break-its for
  every unit on the final tree. Not measured there: MongoDB 5.0/6.0, the connector at
  `0.1.0-dev.2` or `0.1.0`, the BF-10 compose abort, and break-its outside Node 20 / MongoDB 7.
- Queue items P0-A…P0-K, P0-T01, P0-TAG, P0-PIN, P0-LOCK, ADV-RETRO, ADV-ALARM and ADV-CONFIG
  hold the gates. Do not treat a local `test:unit` pass as coverage (open item 6).

---

*Draft, 2026-09-23. Requires maintainer review before release. Nothing tagged or published.
Addition figures are candidate rc, pre-merge.*
