# cgm-remote-monitor 15.0.9 — contents

**Status: DRAFT for maintainer review. Contributor-facing; full technical depth intended.**
Nothing here is tagged or released. Measured 2026-09-25 against `official/dev` `4f705217`
(merge of #8754) and `official/master` `92d08342` (= tag `15.0.8`, the shipping release), in
`externals/cgm-remote-monitor-official` after `git fetch official`.

> Complements the generated changelog. The changelog is authoritative for *what merged*;
> this file records what the release is made of, how each figure was measured, and what is
> unsettled.

15.0.9 is **everything on `dev` at `4f705217`, plus the open PRs the maintainer has decided ship in
it** ([decisions](decisions.md)): #8758, and four outside contributors' PRs carried by decision on
2026-09-25, #8568 (BF-114), #8419 (tests), #8530 (a 48-hour chart option) and #8730 (Crowdin
translations). Every PR merged to `dev` is `merged`; none is `released`. The carried PRs are `open`.

## Identity

| | |
|---|---|
| Merged part | `official/master..official/dev` |
| Base (shipping) | `92d08342` = `15.0.8` |
| `dev` head | `4f705217` (merge of #8754, 2026-09-24) |
| Commits on `dev` | 384 — `git rev-list --count official/master..official/dev` |
| First-parent merges on `dev` | **62** — `git rev-list --first-parent --count official/master..official/dev`; every first-parent commit in the range is a PR merge (`git log --first-parent --format=%s official/master..official/dev \| grep -vc '^Merge pull request'` prints 0) |
| Diff on `dev` | 226 files, +18167/−1403 — `git diff --shortstat official/master official/dev` |
| `package.json` version | `15.0.9` on `dev` — `git show official/dev:package.json \| grep '"version"'` |
| Connector pin | `nightscout-connect` exactly `0.1.0` from npm on `dev` (#8762); `15.0.8` pins the `v0.0.13` tag tarball — `git show official/<ref>:package.json \| grep nightscout-connect` |
| Open additions | #8758 (head `ab7b22d6`) — `gh pr view <n> --json state,headRefOid` |
| Release PR | #8598 (`dev` → `master`, head `4f705217`): open, `REVIEW_REQUIRED`, zero reviews — `gh pr view 8598 --json state,reviewDecision,reviews` |
| Tag | none. No `15.0.9` tag exists |

## What 15.0.9 contains

### Open addition (not merged)

Sizes are against `dev`: `git rev-list --count official/dev..<head>` and
`git diff --shortstat official/dev...<head>`. #8758's merge base with `dev` is `4f705217` (#8754), `dev`'s tip: #8758 is 0 commits behind (2026-09-25).

| PR | branch | head | commits not on `dev` | diff | register | what |
|---|---|---|---|---|---|---|
| #8758 | `bf/object-id-crud` | `ab7b22d6` | 19 | 28 files, +3328/−80 | BFQ-102 | a record keeps its own `_id` across API v1, v3 and the websocket: one helper for the rule that a 24-hex `_id` is stored as an ObjectId and matched in either form; find, edit and delete by `_id` for profiles, devicestatus, food, activity, treatments and entries; a CRUD-by-`_id` matrix test |

**#8758 and the connector.** Connector 0.1.0's profile update-on-change (`de3cee1`) replaces a
changed profile only on a sink that has #8758.

### Merged to `dev`

Merge SHAs and dates: `git log --first-parent --format='%h %ad %s' --date=short official/master..official/dev`.
Register ids refer to
[`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md),
which is the home of every defect fact; these tables do not restate them.

#### Programme backfix PRs (23), plus #8741

| PR | Merge | Date | Register | What |
|---|---|---|---|---|
| #8733 | `77d153d2` | 2026-09-17 | — (queue P0-T01) | remove the two quadratic scans over the treatment window (`processDurations`, `calcdelta`); NaN-`mills` dedup restored as the one deliberate behaviour change |
| #8737 | `025f1310` | 2026-09-18 | BF-02, BF-03, BF-11, BF-32, BF-40, BF-68 | schema-driven query coercion (158 coercions, 5 collections); `$exists` operand read as a boolean for `true`/`false`/`1`/`0` only; digits-only `$type` operand kept numeric |
| #8738 | `d3358e91` | 2026-09-18 | BF-01, BF-05, BF-13, BF-14, BF-15, BF-33 | count endpoint uses each collection's `query_for`; count-path log removed; v3 paging tiebreak; v3 dotted `?fields=`; v1 `?count=` and v3 `?limit=` validation (new `lib/server/count.js`). Its v1 count rule is amended by #8748 and #8761 |
| #8734 | `fdd08706` | 2026-09-18 | BF-36 | client merge of a delete plus an unmatched update no longer throws and freezes the page |
| #8743 | `1a36f023` | 2026-09-18 | BF-04, BF-70 | v1 query-operator allowlist (new `lib/server/query-operator-allowlist.js`); URL-supplied aggregation pipeline refused; refused filters answer 400 naming the operator |
| #8740 | `49f562d8` | 2026-09-20 | BF-06, BF-07 (partly) | cache clone cost; BF-07 remains `partly merged` |
| #8735 | `ff0d506c` | 2026-09-20 | BF-16, BF-35 | quick-pick chooser index mismatch; `/api/v1/food/quickpicks` stops dropping non-editor quick picks; hidden and position ordering restored |
| #8736 | `2e94de1b` | 2026-09-20 | BF-37, BF-38, BF-39 | bare URL parameter no longer halts page load; `%10`+ translation slots; `_` no longer rewritten to a space in query parameters |
| #8739 | `7a5561f4` | 2026-09-20 | BF-28, BF-29, BF-31 | insulin-age URGENT comparison; unrecognised `ENABLE` entry suggestion; Alexa/Google Home request locale no longer changes process-global state |
| #8744 | `a9acd313` | 2026-09-21 | BF-79 | main-namespace `loadRetro` gated on read authorization (GHSA-gjhc-pc29-r3m6) |
| #8745 | `2b22c0ce` | 2026-09-21 | BF-75, BF-76 | `/alarm` namespace delivers only to a read-entitled room; access-token `ack` requires the ack permission (GHSA-8849-qjp5-vrrj). BF-76's unbounded `silenceTime` is left open deliberately |
| #8746 | `74fc6619` | 2026-09-21 | BF-77 | "readable by world" admin notice raised on role membership, so `TREATMENTS_AUTH=off` (`readable careportal`) now warns |
| #8748 | `42c5e21e` | 2026-09-23 | — (RT-COUNT0) | **amends #8738**: v1 reads with `count=0` answer `[]`; saves and updates ignore `count`; DELETE with `0` or a malformed count is refused and deletes nothing. The read rule is amended again by #8761 |
| #8749 | `9fd4600e` | 2026-09-23 | BF-87 | `overrides.qs` and `overrides.request.qs` 6.15.1 → 6.16.0; clears GHSA-q8mj-m7cp-5q26, GHSA-x5fp-wj9c-mxmx, GHSA-4mjr-xmp4-gh2g |
| #8751 | `4011193e` | 2026-09-23 | — | two security fixes backported from #8605: alarm-subscription credential logging (`9c50788e`); per-collection read grant on two shared storage routes (`b5038500`). Withheld-style PR body |
| #8753 | `3a38c6f2` | 2026-09-23 | BF-10, BF-63 (renderer half) | `docker-compose.yml` `mongo` `ulimits nofile 64000`; Alexa answers unhandled request types; `isPluginEnabled` miss; `booterror.js` null-`err` guard |
| #8755 | `728351e3` | 2026-09-23 | — | an alarm reaching a page with no reading no longer throws in its handler (the page still does not sound it; known issue) |
| #8756 | `c11888ed` | 2026-09-23 | BF-69 | Bolus Wizard quick-pick chooser rebuilt when the drawer opens; ships with #8735 |
| #8757 | `d0d6b433` | 2026-09-23 | — (RT-4) | the MiniMed deprecation warning names the `CONNECT_*` settings that replace `MMCONNECT_*` |
| #8760 | `ddd9b600` | 2026-09-24 | BF-103 | a treatment moved or split by drag in the web UI stores the new time in `mills` and `date`, so IOB and COB follow it |
| #8761 | `f1591069` | 2026-09-24 | — (RT-COUNT-COMPAT) | v1 reads tolerate the count shapes oref0 (`N?…`) and GluPredKit (`count=0` in a date window) send, with a deprecation warning; each tolerance has its own setting, on by default (`b4ead206`, `516f971a`) |
| #8754 | `4f705217` | 2026-09-24 | BF-17, BF-30, BF-47, BF-88 | login security fixes and the new `TRUST_PROXY` setting, with #8763 and #8765 folded in (below). Withheld-style PR body |
| #8741 | `bcd171cb` | 2026-09-20 | — (external contributor) | credential and identifier settings kept as strings (leading `+`, leading zeros) |

**#8754** (`bf2/auth-hardening`, head `bae655a0`, merged as `4f705217`; 34 commits, 25 files,
+2167/−105 against `153e5658`). Besides `bf/auth`, `bf/throttle` and the `client-ip.js` backport it
carries `f6f361b1` (the delay's position), `607d51b0` (the proxy guide,
`docs/proposals/trusted-proxy-migration.md`), `9c6cde72` (forwarded addresses with a port),
`b5f61f19` (the proxy guide recommends `TRUST_PROXY=1` on Azure App Service), #8763 (`d0a3d628`,
`e3354218`) and #8765 (bringing #8764, `71987bb4`). What it carries:

- **BF-17.** A subject save no longer writes `accessToken`/`accessTokenDigest`/`digest`. Existing
  rows keep them until the subject is next saved; clearing a row does not retire the token. The
  gate `node tools/queue/gates/bf17-remediation-note.js` guards the notes' rotation text (17 checked,
  0 failing on 2026-09-24), and `tools/queue/gates/bf17-rename-row-control.sh` is its control (exits 1).
- **BF-30, the failed-login delay.** The wait comes before the credential check, as in earlier
  releases. Failures are counted per client address and also per credential. The list is bounded
  and swept on a schedule (`lib/authorization/delaylist.js`).
- **`TRUST_PROXY` (BF-30, BF-88).** Unset resolves the client address as `dev` does
  (`forwarded-for`, pinned by `8b975b41`), and a boot message says the delay does not protect
  against guessing. `false` = direct connection only; a comma-separated list of IPs/CIDRs = the
  trusted boundary; a whole number = that many hops; `true` = every hop (Express's meaning,
  `81623f9b`). The subnet aliases `loopback`, `linklocal`, `uniquelocal` are refused at boot
  (`lib/server/client-ip.js`). Setting it behind a TLS-terminating proxy that is not
  trusted causes an https redirect loop. Explicit `TRUST_PROXY` settings accept forwarded addresses
  that carry a port (the form Azure App Service is reported to send); unset is unchanged
  (`9c6cde72`).
- **BF-47.** Subject and role `create()`/`save()` write only an allow-list of fields (declared
  correction, below); a save that omits `notes` or `created_at` keeps the stored values (`7103f657`).
- Every read of the auth collections stopped printing its query options to stdout (`ce82f0cd`).
- **One `TRUST_PROXY` policy** (#8763, RT-TRUST-ONE-SOURCE). Every client-address consumer reads
  one policy compiled per `env`; `lib/server/client-ip.js` exports only `trustFor(env)` and
  `clientIPFor(env)`; API v3 logins key from `env`, not the mounted app's `trust proxy`. No
  behaviour change.
- **Loop remote-command sender address** (#8764 via #8765, RT-LOOP-REMOTE-ADDRESS). The
  `remote-address` in Loop pushes follows `TRUST_PROXY` through `clientIPFor(env)` instead of the
  connecting address. Loop stores it on remote overrides, so the caregiver's address is kept in
  treatments, readable by anyone with read access to the site. The release notes say so.

#### Connector pin

| PR | Merge | Date | Pin |
|---|---|---|---|
| #8752 | `f0954a6a` | 2026-09-23 | `nightscout-connect` exactly `0.1.0-dev.2` from npm |
| #8759 | `feafa533` | 2026-09-23 | exactly `0.1.0-dev.3` |
| #8762 | `153e5658` | 2026-09-24 | exactly `0.1.0`; this is the pin 15.0.9 ships |

Connector 0.1.0 was released 2026-09-24: tag `v0.1.0` on connector `main` `4dde1ec` (the merge of
connector #70), published to npm `latest` with provenance, `gitHead` `4dde1ec`
(`npm view nightscout-connect dist-tags`; `git -C externals/nightscout-connect rev-parse v0.1.0^{commit}`).
Its code equals `v0.1.0-dev.3` `977da8a`; `git diff 977da8a 4dde1ec` touches only `docs/releasing.md`.
It carries BF-42, BF-85, BF-08/BF-34, BF-89, BF-91, BF-97 and BF-98 (connector #64 with #61/#66/#67,
#68, #77, #78, #79). #79's bounded profile fetch (`1d2ebc8`) and update-on-change (`de3cee1`) were
lab-run on 2026-09-23 for 80 min (46 min against 15.0.9-candidate sinks), on code identical to 0.1.0's
([connector profile sync](../../docs/60-research/remedial/connector-profile-sync.md));
no multi-hour soak and no source outage.

#### Other fixes (external and upstream contributors)

| PR | Merge | Date | What |
|---|---|---|---|
| #8732 | `59430336` | 2026-09-21 | profile and pill behaviour on sites with incomplete data (fixes #7324; also touches insulin age — reconciled with #8739 in merge `838537d8`) |
| #8729 | `1abc1aad` | 2026-09-20 | guard `chart.update()` against a 0-height container measurement |
| #8726 | `a8888f0d` | 2026-09-09 | routine log volume off by default; adds `DEBUG_LOGGING` and `CONNECT_DEBUG`; moved the connector pin to `234d47c` (fixes #8714). The pin is now #8762's |
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
| #8573 | `e7c0cd6f` | **D3 5.16 → 7.9.0** with chart-interaction tests; the drag check is by hand and in a browser (RT-D3, below) |
| #8529 | `9205ea30` | UUID (retain patched UUID 11) |
| #8544 | `97d1aa1b` | jsdom and analyzer `ws` (dev dependencies) |
| #8550 | `7e71fb62` | Babel toolchain |
| #8565 | `eedc9439` | Axios |
| #8566 | `c5fd8054` | Socket.IO transports |
| #8571 | `6fb8db1c` | Express and body-parser. Express 4.22.1 → 4.22.2: 4.22.2's `lib/utils.js` query parser passes `arrayLimit: 1000` to qs, 4.22.1's passes none (qs default 20), so a query-string list of more than 20 values parses as a list (read-derived from both packages) |
| #8575 | `f7c7812c` | ip-address 10.7.0 |
| #8576 | `4b62921b` | fast-uri 3.1.7 |
| #8577 | `4b665293` | socket.io-parser 4.2.7 |
| #8578 | `3bb07409` | DOMPurify 3.4.14 (test reference only) |
| #8579 | `a363d760` | js-yaml 3.15.2 / 4.3.2 |
| #8581 | `02c63225` | Mocha 11.8.0 |
| #8582 | `1156aafd` | PostCSS 8.5.28 |
| #8586 | `d6e90d00` | brace-expansion (all compatible majors) |

All merged 2026-09-05. #8749 (qs) is in the backfix table above.

#### Translations

#8599 `9f1b4d3a` (2026-09-05) and #8603 `b982e1e9` (2026-09-06), Crowdin.

#### Docs, CI and version

| PR | Merge | Date | What |
|---|---|---|---|
| #8597 | `5c26c9d2` | 2026-09-04 | start the 15.0.9 cycle (`package.json` → `15.0.9`) |
| #8516 | `85fed44b` | 2026-09-04 | README: MongoDB 4.4 no longer supported — amended by #8750 |
| #8750 | `1f9a9d10` | 2026-09-23 | README: MongoDB 4.4 **deprecated**, still tested, to be dropped in a later release |
| #7338 | `57d1cac9` | 2026-09-06 | js-beautify option in docs |

## Version number: 15.0.9

Decided 2026-09-22 (queue `RT-VERSION`; [decisions](decisions.md)). The release is **15.0.9**, the number
`dev`'s `package.json` already carries. #8738 (as amended by #8748 and #8761), #8743 and #8754's
subject/role field allow-list ship as **declared corrections** in the release notes.

Decided 2026-09-24 (maintainer, relayed via -59; queue `RT-COUNT-COMPAT`): tolerate the count shapes
real clients send and keep 15.0.9 a patch. #8761 implements it: `API_V1_COUNT_LEADING_NUMBER` and
`API_V1_COUNT_ZERO_WINDOW`, each on by default (`lib/server/env.js`), expected to default to `false`
in a future release.

The facts the classification rests on, for the record:

- Under
  [`gt4-semver-classification-2026-09-15.md`](../../docs/60-research/modernization/gt4-semver-classification-2026-09-15.md)
  the `dev` content is at least a minor (`DEBUG_LOGGING`, `CONNECT_DEBUG`, routine debug logging
  off by default, new `lib/api2/loop-notification-errors.js`, the two `API_V1_COUNT_*` settings);
  #8754 adds `TRUST_PROXY`.
- #8738 and #8743 grade themselves major in their own bodies; so does #8739 (per-request locale
  on the Alexa and Google Home endpoints removed with no replacement). The auth-hardening
  allow-list was graded major in queue item P0-C before the maintainer ruled (2026-09-23) that
  the allow-list is the declared schema.
- Dev-channel deployments already report `15.0.9` from `/api/v1/status`
  (`lib/server/env.js` → `lib/api/status.js`). The release notes say so.
- The modernization cut branches also carry `15.0.9` in `package.json`; each cut is renumbered
  when it is rebased ([decisions](decisions.md)).

## What is NOT in 15.0.9

| Item | State | Consequence |
|---|---|---|
| BF-72 — a class of expensive search request can occupy the database for minutes, with no credentials on a default install | open; no fix; disposition decided privately (`BFQ-72`) | described by mechanism only |
| BF-86 / BF-67 — thresholds in the wrong units (a mmol/L low threshold on a mg/dL site is stored so the low alarm can never fire; an out-of-order threshold is silently rewritten) | open | carried as a known issue in the notes |
| BF-76 — unbounded `silenceTime` | open, left open deliberately by #8745 | carried as a known issue |
| BF-92 — a page with no glucose reading presents no server alarm, including device alarms | open; #8755 removes only the handler error | carried as a known issue |
| BF-95 — an uploader clock running ahead delays the stale-data alarm by about the size of the error | open | carried as a known issue |
| BF-44 / BF-45 — MiniMed ingestion divergences | open, graded low: legacy mmconnect does not work, so only one path ingests in practice | the legacy bridges are removed on cut 1 |
| `TRUST_PROXY` planned flip | none planned ([versioning policy §5.7](../../docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md#57-compatibility-flags)) | unset is a permanent, documented setting; BF-30 is closed only where an operator sets it |

Other `open` register entries that reach 15.0.9 are listed in the register's §1, and the queue
items for everything present on 15.0.8 are in the operator-exposure table on
[PROGRAMME-STATUS](../../docs/00-overview/PROGRAMME-STATUS.md#status-words-merged-is-not-released);
this file does not copy them. Nightscout is not a medical device: an operator who relies on its
alarms should always have a second way to see readings.

## Open items a releaser must settle

The queue-tracked items are listed, generated and current, in
[ROADMAP §1](../../docs/00-overview/ROADMAP.md#1-the-next-release-1509) (queue `RT-0`'s open
blockers: #8758, the carried outside PRs, `RT-VERSION`). Beside them:

1. **The Loop remote-command browser checks.** #8764 changed `lib/api2/index.js` and
   `lib/api2/notifications-v2.js` after the hand-checked `8d797ba4`, so a remote override, carbs
   and bolus from careportal and from LoopCaregiver each need a 200 and a delivered push, by hand
   (`client-unchanged-since-hand-check.js` is red until then).
2. **Release notes** (`release-notes.md`): the passages marked `PENDING: #8758 merge` are finalised
   when it merges.
3. **#8598 review.** The release PR has zero reviews and review is required.
4. **Hand-written `CHANGELOG.md` `[Unreleased]` section on dev** (lines 5–75 of
   `git show official/dev:CHANGELOG.md`; 12 commits, `git log --no-merges official/master..official/dev -- CHANGELOG.md`)
   against the stated rule that the changelog is generated at release time. See
   [`../README.md`](../README.md#open-item-changelog-on-dev).
5. **The tag**, by the maintainer.

Housekeeping: Dependabot #8747 targets `master` with an axios bump `dev` already contains (#8565);
it is moot once #8598 merges.

## Known test gaps

Not blockers by decision; recorded so a green suite is not read as covering them.

- **Test-script coverage.** 66 of the 190 `tests/*.test.js` files on `dev` `4f705217` match neither
  `npm run test:unit` nor `test:integration` (compare the files against the two globs in
  `git show official/dev:package.json`). Among them: `query.operands`, `boluscalc.quickpick`,
  `boluscalc.quickpick-rebuild`, `booterror`, `client.alarm-no-reading`, `treatmenttime`,
  `debug-logging`, `dependency-d3`, and #8754's `authdelay`, `authsubjects` and `client-ip` (63 of
  187 on `153e5658`). Only `npm test` / `test-ci` (what `main.yml` runs) reaches them. A green
  `test:unit` is not evidence for those fixes.
- **D3 drag clamps.** `TEST=dependency-d3` passes with both treatment-drag clamps in
  `lib/client/renderer.js` deleted, so the suite does not exercise that boundary. RT-D3 was
  answered 2026-09-24 (maintainer, session -6a): the drag check passed by hand and in automation
  ([browser evidence](../../docs/60-research/modernization/rt-d3-and-alarm-browser-evidence-2026-09-22.md));
  the suite gap is queue `RT-D3-SUITE`.
- **`/alarm` under `AUTH_DEFAULT_ROLES=denied`.** No automated test drives the client path. Checked
  by hand 2026-09-23 on the combined rc `ec70aab0` (queue `ADV-ALARM`).
- **`count/devicestatus/where`.** No end-to-end test runs a numeric filter on it against a live
  database; the #8737 + #8738 composition is measured at the constructed `$match` only.

## Operator-visible behaviour changes (source for the release notes)

Each is described in its PR body's "What changes for you" section; the release notes carry
the user-facing form. Facts the notes must not lose:

- **Insulin age (#8739).** The URGENT level now applies at and beyond `IAGE_URGENT` (default
  72 h) for everyone. The notification still requires `IAGE_ENABLE_ALERTS` (default off) and
  fires only when `age === IAGE_URGENT` and `minFractions <= 20` — once, with no catch-up.
  Past the threshold the level had been understated as WARN the whole time.
- **`?count=` (#8738, amended by #8748 and #8761).** On v1 GET/HEAD (`lib/api/index.js`
  `validateCount`, `lib/server/count.js`): `N?<anything>` reads `N` (oref0); `count=0` with a `find`
  bounding one date field from both sides reads a limit of 2147483647 (GluPredKit), and without one
  reads as no count (the endpoint default). Both set `Deprecation: true` and a 299 `Warning`, logged
  once per process without the value. `API_V1_COUNT_LEADING_NUMBER=false` refuses `N?…` with
  `400 Bad count`; `API_V1_COUNT_ZERO_WINDOW=false` answers every `count=0` read with `200 []`.
  `abc`, `1e2`, `-3`, `0x10`, `2.5` and integers above `Number.MAX_SAFE_INTEGER` answer
  `400 Bad count`, with or without a following `?`. POST and PUT ignore `count`. DELETE with `0` or
  a malformed count (including `N?…`) answers 400 and deletes nothing; DELETE with a valid count is
  accepted and does not limit the delete. Routes that never apply `count` (`/entries/current`,
  `/count/:storage/where`, `/echo`, `/status`, `/food`) answer `count=0` normally. `/experiments` is
  mounted before the validator. v3 `?limit=` keeps #8738's rule: `0`, non-digits and values above
  `API3_MAX_LIMIT` answer 400 (`lib/api3/generic/collection.js` `parseLimit`). On 15.0.8,
  `?count=0` returned the whole collection on the database path, and devicestatus answered it
  with 10 (`git show official/master:lib/api/devicestatus/index.js`, `numCount <= 0` → 10).
- **Filters (#8737).** "Earlier results may have under- or over-reported delivered therapy"
  must survive into the notes. `$exists` reads only `true`/`false`/`1`/`0`; `null`, `no`,
  `off`, empty and others still mean "has the field".
- **Operator allowlist (#8743).** Refused operators answer 400 naming the operator instead of
  500. `$expr` on `/api/v1/profiles/` and the `pipeline` parameter on `/api/v1/count/…` are
  refused. A census of 14 client projects found no use of a refused operator. Declared
  correction.
- **Filters with more than 20 values (#8571).** Parse as a list on 15.0.9, where 15.0.8 refused
  them, so a tool deleting by such a list now deletes (read-derived; the notes carry it under
  "Other fixes").
- **Subject/role allow-list (#8754, BF-47).** `create()` and `save()` write only
  `name`, `roles`, `notes`, `created_at` (subjects) and `name`, `permissions`, `notes`,
  `created_at` (roles). Other stored fields are dropped on the next save. Declared correction
  (maintainer, 2026-09-23). A corpus check found no open-source client storing other subject
  fields.
- **Subject edit (#8754, `7103f657`).** A save that omits `notes` or `created_at` keeps the stored
  values; `notes: ""` clears; `roles` is not filled in from storage, so removing the last role
  still works.
- **BF-17 and BF-30 / `TRUST_PROXY` (#8754).** As described under
  [#8754](#programme-backfix-prs-23-plus-8741), including the Loop remote-command sender address
  that is now stored on remote overrides.
- **Docker Compose (BF-10, #8753).** `mongo` service gains `ulimits nofile 64000`; without it mongod
  aborted with `Too many open files` (reproduced 2026-09-21 on mongod 7.0.43, register BF-10).
- **Legacy ingestion (RT-4, #8757).** No separate deprecation release. `MMCONNECT_*` (mmconnect) is
  reported not to work (maintainer, operational knowledge, not measured) and is to be retired;
  its warning names the `CONNECT_*` replacements. `BRIDGE_*` Dexcom settings are served by
  nightscout-connect by default since 15.0.8 (`lib/server/bootevent.js` `migrateBridgeToConnect`),
  with `DEXCOM_BRIDGE_USE_LEGACY=true` as the escape hatch. The removal release is not numbered.
- **MongoDB 4.4 (#8750).** Deprecated, still in the CI matrix (`mongodb-version: [4.4, 5.0, 6.0]`
  in `.github/workflows/main.yml`) and passing in the latest combined run. The removal release is
  not numbered.
- **Connector (#8726 logging; #8762 pin to 0.1.0).** Credential and payload logging ends for
  upgraders from v0.0.13 (BF-42); `overrides['nightscout-connect'].axios` 1.20.0 satisfies the
  connector's `^1.18.1` (BF-43 is master-only). BF-85 CareLink `sg: 0` filtered at ingestion
  (read-derived, not reproduced); BF-34/BF-08 backoff merge order, delay cap and jitter; listener
  release on stop; BF-89 reader subject created with `roles` (a subject created by an earlier
  connector is reused without roles, and the connector logs how to fix it); BF-91 `capture` mode
  only; profile fetch bounded to new or changed profiles, and update-on-change only against a
  sink with #8758. New optional `CONNECT_START_JITTER_MS`, `CONNECT_INTERVAL_JITTER_MS`, default 0.
- **Treatment drag (#8760, BF-103).** Moving or splitting a treatment by drag in the web UI stores
  the new time; a raw v1 PUT still leaves a stale `mills` (register BF-103).
- **Live-update security (#8744, #8745), backports (#8751).** Mechanism only in public text;
  advisory write-ups are withheld until release.
- **World-readable notice (#8746).** Sites with `TREATMENTS_AUTH=off` now see the admin notice.
- **COB (#8587)**, **A1c (#8602)**, **report SGV filtering (#8588)**: displayed values may
  change on the same data.

## Evidence

- Merged part: per-PR test evidence, ablations and controls are in each PR body and in the
  register entry for each id.
- `dev` `4f705217` itself (the merge of #8754, 2026-09-25): 2577 passing, 0 failing, 3 pending on
  Node 20.20.0, 22.22.0 and 24.15.0 against MongoDB 7.0.43, and in all nine CI jobs (Node 20/22/24
  × MongoDB 4.4/5.0/6.0). Without #8758.
- Freeze candidate, 2026-09-25
  ([15.0.9 integration record](../../docs/30-design/remedial/rc-15.0.9-integration-record.md)):
  `dev` `4f705217` + #8758 `ab7b22d6`, tree `25ab7afc` (#8758 is 0 behind `dev`). CI's `test-ci`
  gives 3066 passing, 0 failing, 3 pending, and `test:core` gives 286, on Node 20.20.0, 22.23.2 and
  24.20.0 × MongoDB 4.4.24 and 7.0.43. The `lib/api2` browser checks are owed (#8764).
- Queue items P0-A…P0-K, P0-T01, ADV-RETRO, ADV-ALARM and ADV-CONFIG hold the gates. Do not treat
  a local `test:unit` pass as coverage ([Known test gaps](#known-test-gaps)).

---

*Draft, 2026-09-25. Requires maintainer review before release. Nothing tagged or published.*
