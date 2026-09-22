# cgm-remote-monitor 15.0.9 — contents

**Status: DRAFT for maintainer review. Contributor-facing; full technical depth intended.**
Nothing here is tagged or released. Measured 2026-09-22 against `official/dev` `74fc6619`
and `official/master` `92d08342` (= tag `15.0.8`, the shipping release).

> Complements the generated changelog. The changelog is authoritative for *what merged*;
> this file records what the release is made of, how each figure was measured, and what is
> unsettled.

## Identity

| | |
|---|---|
| Release content | `official/master..official/dev` |
| Base (shipping) | `92d08342` = `15.0.8` |
| Head | `74fc6619` (merge of #8746, 2026-09-21) |
| Commits | 308 — `git rev-list --count official/master..official/dev` |
| First-parent merges | **48** — `git log --first-parent --merges --oneline official/master..official/dev \| wc -l` (every first-parent commit in the range is a PR merge) |
| Diff | 200 files, +14381/−1262 — `git diff --shortstat official/master official/dev` |
| `package.json` version on dev | `15.0.9` |
| Release PR | #8598 (dev → master): open, mergeable, CI green on Node 20/22/24 × MongoDB 4.4/5.0/6.0 plus CodeQL and Docker build; review required, zero approving reviews |
| Tag | none. No `15.0.9` tag exists |

Every item below is `merged` (in dev), none is `released`.

## What 15.0.9 contains

### Programme backfix PRs (12), plus #8741

Register ids refer to
[`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md),
which is the home of every defect fact; this table does not restate them.

| PR | Merge | Date | Register | What |
|---|---|---|---|---|
| #8733 | `77d153d2` | 2026-09-17 | — (queue P0-T01) | remove the two quadratic scans over the treatment window (`processDurations`, `calcdelta`); NaN-`mills` dedup restored as the one deliberate behaviour change |
| #8737 | `025f1310` | 2026-09-18 | BF-02, BF-03, BF-11, BF-32, BF-40, BF-68 | schema-driven query coercion (158 coercions, 5 collections); `$exists` operand read as a boolean for `true`/`false`/`1`/`0` only; digits-only `$type` operand kept numeric |
| #8738 | `d3358e91` | 2026-09-18 | BF-01, BF-05, BF-13, BF-14, BF-15, BF-33 | count endpoint uses each collection's `query_for`; count-path log removed; v3 paging tiebreak; v3 dotted `?fields=`; v1 `?count=` and v3 `?limit=` validation (new `lib/server/count.js`) |
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

### Other fixes (external and upstream contributors)

| PR | Merge | Date | What |
|---|---|---|---|
| #8732 | `59430336` | 2026-09-21 | profile and pill behaviour on sites with incomplete data (fixes #7324; also touches insulin age — reconciled with #8739 in merge `838537d8`) |
| #8729 | `1abc1aad` | 2026-09-20 | guard `chart.update()` against a 0-height container measurement |
| #8726 | `a8888f0d` | 2026-09-09 | routine log volume off by default; adds `DEBUG_LOGGING` and `CONNECT_DEBUG`; moves the connector pin to `234d47c` (fixes #8714) |
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

### Dependency updates

| PR | Merge | What |
|---|---|---|
| #8573 | `e7c0cd6f` | **D3 5.16 → 7.9.0** with chart-interaction tests — see [Open items](#open-items-a-releaser-must-settle) |
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

### Translations

#8599 `9f1b4d3a` (2026-09-05) and #8603 `b982e1e9` (2026-09-06), Crowdin.

### Docs, CI and version

| PR | Merge | Date | What |
|---|---|---|---|
| #8597 | `5c26c9d2` | 2026-09-04 | start the 15.0.9 cycle (`package.json` → `15.0.9`) |
| #8516 | `85fed44b` | 2026-09-04 | README: MongoDB 4.4 no longer supported — see open items |
| #7338 | `57d1cac9` | 2026-09-06 | js-beautify option in docs |

## Version number: not settled

Held by queue items **RT-VERSION** (not-started) and **RT-D3** (needs-decision) in
`queue/work-queue.yaml`. The facts a decision rests on:

- **It cannot be a patch** under the classification in
  [`gt4-semver-classification-2026-09-15.md`](../../docs/60-research/modernization/gt4-semver-classification-2026-09-15.md):
  `lib/server/env.js` gains `DEBUG_LOGGING` and `CONNECT_DEBUG`; routine debug logging flips
  to **off** by default; a new API module, `lib/api2/loop-notification-errors.js`, appears.
  Those make it at least a minor, independent of anything else.
- **Three merged PRs grade themselves major in their own bodies**: #8738 (`?count=` values
  previously accepted now return 400, on writes as well as reads), #8739 (per-request locale
  on the Alexa and Google Home endpoints removed with no replacement), and #8743 (v1 refuses
  operators outside a fixed allowlist, including `$expr` on `/api/v1/profiles/`, which worked
  before).
- The policy draft
  [`semver-and-release-versioning-policy-2026-09-15.md`](../../docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md)
  §8 proposes splitting the breaking rows into a later release; it was written when those rows
  were unmerged branches, and all three are now merged to dev. Neither document is adopted.
- **Version collision:** `package.json` on dev and on the modernization cut branches all say
  `15.0.9` with different Node floors (RT-VERSION, gate `tools/queue/gates/version-collision.js`).
- Dev-channel deployments already report `15.0.9` from `/api/v1/status`
  (`lib/server/env.js` → `lib/api/status.js`), although no `15.0.9` has been released. A
  renumber must say so, so that a report from "15.0.9" is understood.

## What is NOT in 15.0.9

| Item | State (queue) | Consequence |
|---|---|---|
| `bf/auth` — BF-17 plaintext access token (P0-C) | gate-not-met, no PR | admin-UI edits still write a derived token into the database on 15.0.9. Operator remediation text is P0-C-REMEDIATE |
| `bf/throttle` — BF-30 failed-auth throttle bypass (P0-J) | gate-not-met, no PR | not fixed in 15.0.9 |
| `bf/connect-pin` — pin to connector `v0.0.14` (P0-PIN) | blocked on P0-TAG | dev pins connector `234d47c`, which is v0.0.13 plus one commit (debug logging opt-in, an 18-file logging rewrite). The three log-redaction *commits* are not ancestors of it, although its log surface already matches `v0.0.14`'s. The MiniMed sentinel/timestamp fix (`8406edf`) and the backoff-and-jitter fix (BF-34, BF-08; connector PR #68, queue P0-F) are **not** in 15.0.9 |
| BF-72 — unbounded `$regex` cost on API v1 | open, **no fix** | unauthenticated availability defect on the shipped default; live on 15.0.8 and dev. Mechanism only in public text; whether the security-contact process is invoked is pending |
| BF-69 — Bolus Wizard quick-pick chooser built once from an empty sandbox | open | the chooser offers only "(none)"; #8735 (BF-35) was its prerequisite, so the one-line fix may now ship |
| Crowdin PR #8730 | open | translations after #8603 are not included |

Other `open` register entries that reach 15.0.9 are listed in the register's §1; this file
does not copy them.

## Open items a releaser must settle

1. **MongoDB 4.4.** README on dev (from #8516) says MongoDB 4.4 or lower is *not supported*
   and that 15.0.7 is the last version that works with it. `.github/workflows/main.yml` on
   dev still tests `mongodb-version: [4.4, 5.0, 6.0]`, and the #8598 run passes on 4.4. The
   release must either drop 4.4 from CI or correct the README; the notes cannot state a
   support policy until one of those happens.
2. **Connector pin is not a tag.** Dev pins
   `nightscout-connect/archive/234d47c8….tar.gz`, a commit in connector `dev` (since `d208c7d`,
   2026-09-22) that no connector release names yet. master pins `v0.0.13`. Releasing 15.0.9
   as-is ships that untagged commit; the connector release is queue item `P0-TAG`.
3. **D3 5.16 → 7.9 (#8573).** `TEST=dependency-d3` passes (24), but deleting both
   treatment-drag clamps in `lib/client/renderer.js` leaves it at 24/24: the boundary is never
   exercised. The clamps bound a user-initiated rewrite of a treatment's `created_at`, which
   IOB/COB key off. Gate `tools/queue/gates/d3-drag-clamp-covered.js` fails until covered
   (RT-D3).
4. **COB source change (#8587)** alters the number a user reads when deciding about food and
   correction. It has no line of its own in the release decision (RT-D3 no-gate note). The
   release notes carry it.
5. **Hand-written `CHANGELOG.md` `[Unreleased]` section on dev** (71 lines, 12 commits by
   upstream contributors) against the stated rule that the changelog is generated at release
   time. See [`../README.md`](../README.md#open-item-changelog-on-dev).
6. **Test-script coverage.** Several new test files (e.g. `tests/query.operands.test.js`,
   `tests/api.count-where.test.js`, `tests/boluscalc.quickpick.test.js`,
   `tests/api.alexa.test.js`) match neither `npm run test:unit` nor `test:integration`; only
   `npm test` / `test-ci` (what `main.yml` runs) reaches them. A green `test:unit` is not
   evidence for those fixes.
7. **Missing end-to-end test**: a numeric filter on `count/devicestatus/where` returning rows
   from a live database. The #8737 + #8738 composition is measured at the constructed
   `$match` only.

## Operator-visible behaviour changes (source for the release notes)

Each is described in its PR body's "What changes for you" section; the release notes carry
the user-facing form. Facts the notes must not lose:

- **Insulin age (#8739).** The URGENT level now applies at and beyond `IAGE_URGENT` (default
  72 h) for everyone. The notification still requires `IAGE_ENABLE_ALERTS` (default off) and
  fires only when `age === IAGE_URGENT` and `minFractions <= 20` — once, with no catch-up.
  Past the threshold the level had been understated as WARN the whole time.
- **`?count=` (#8738).** `0`, `abc`, `1e2`, `-3`, `0x10`, `2.5` and integers above
  `Number.MAX_SAFE_INTEGER` return `400 Bad count`, on every v1 route after the validator
  (reads and writes); `/experiments` is mounted before it and is not covered. `?count=0`
  returned the whole collection on the database path and an empty list on the cache path.
- **Filters (#8737).** "Earlier results may have under- or over-reported delivered therapy"
  must survive into the notes. `$exists` reads only `true`/`false`/`1`/`0`; `null`, `no`,
  `off`, empty and others still mean "has the field".
- **Operator allowlist (#8743).** Refused operators answer 400 naming the operator instead of
  500. A census of 14 client projects found no use of a refused operator.
- **Quick picks (#8735).** Hidden quick picks disappear from the chooser, ordering follows
  position numerically, plain foods are no longer offered. Visible only once BF-69 is fixed.
- **`_` in URLs (#8736).** No longer rewritten to a space; bookmarked links containing `_` may
  behave differently.
- **Credentials (#8741).** Credential/identifier settings stay strings; numeric and
  `on`/`off` conversion is unchanged for all other settings.
- **Logging (#8726).** Heartbeat, data-reload and connector diagnostics off by default;
  `DEBUG_LOGGING=true` and `CONNECT_DEBUG=true` turn them on. The dev pin `234d47c` replaces
  the connector's payload and credential logging with fixed-message summaries in
  `lib/logging.js` (debug or not), so 15.0.9 ends BF-42's unconditional credential logging for
  upgraders from v0.0.13 — source census of `git archive` extractions, 112/101 live/dynamic
  `console.*` sites at v0.0.13 against 22/20 at `234d47c` (identical to `v0.0.14`); not run
  against a live vendor. BF-42's register status should be re-read against this.
- **Live-update security (#8744, #8745).** On `AUTH_DEFAULT_ROLES=denied`, unauthenticated
  sockets received device status and alarm/notification events. On the documented
  `readable` default the marginal content disclosure was zero. Fixed in dev; live on 15.0.8.
  **Mechanism only in public text**; advisory correspondence is tracked outside this file.
- **World-readable notice (#8746).** Sites with `TREATMENTS_AUTH=off` now see the admin notice.
- **COB (#8587)**, **A1c (#8602)**, **report SGV filtering (#8588)**: displayed values may
  change on the same data.

## Evidence

Per-PR test evidence, ablations and controls are in each PR body and in the register entry
for each id. Queue items P0-A…P0-K, P0-T01, ADV-RETRO, ADV-ALARM and ADV-CONFIG hold the gates. Do not treat a local
`test:unit` pass as coverage (open item 6).

---

*Draft, 2026-09-22. Requires maintainer review before release. Nothing tagged or published.*
