# cgm-remote-monitor 15.0.9 — contents

**Status: DRAFT for maintainer review. Contributor-facing; full technical depth intended.**
Nothing here is tagged or released. Measured 2026-09-30 against `official/dev` `3014f883`
(merge of #8788) and `official/master` `92d08342` (= tag `15.0.8`, the shipping release), in
`externals/cgm-remote-monitor-official` after `git fetch official`.

> Complements the generated changelog. The changelog is authoritative for *what merged*;
> this file records what the release is made of, how each figure was measured, and what is
> unsettled.

15.0.9 is **everything on `dev` at `3014f883`**. Every PR the maintainer decided ships in it
([decisions](decisions.md)) is merged, except Crowdin #8730, which the maintainer held out on
2026-09-25 because its sync reverts translations `dev` corrected (BF-132). Every PR merged to `dev`
is `merged`; none is `released`.

## Identity

| | |
|---|---|
| Merged part | `official/master..official/dev` |
| Base (shipping) | `92d08342` = `15.0.8` |
| `dev` head | `3014f883` (merge of #8788, 2026-09-30 22:38Z), tree `3549306b`, the same tree as #8788's head `bbc6e75e` |
| Commits on `dev` | 509 — `git rev-list --count official/master..official/dev` |
| First-parent merges on `dev` | **87** — `git rev-list --first-parent --count official/master..official/dev`; every first-parent commit in the range is a PR merge (`git log --first-parent --format=%s official/master..official/dev \| grep -vc '^Merge pull request'` prints 0) |
| Diff on `dev` | 298 files, +28617/−1819 — `git diff --shortstat official/master official/dev` |
| `package.json` version | `15.0.9` on `dev` — `git show official/dev:package.json \| grep '"version"'` |
| Connector pin | `nightscout-connect` exactly `0.1.0` from npm on `dev` (#8762); `15.0.8` pins the `v0.0.13` tag tarball — `git show official/<ref>:package.json \| grep nightscout-connect` |
| Held out | Crowdin #8730 (head `f99c0e54`, open; BF-132) — `gh pr view 8730 --json state,headRefOid` |
| Release PR | #8598 (`dev` → `master`, head `3014f883`, author AndyLow91): open, mergeable, `reviewDecision` `APPROVED`; both approvals (the maintainer, 2026-09-26 00:39Z) were given on `e3adc91d`. CI on `3014f883`: 27 checks passed, 3 skipped (read 2026-09-30) — `gh pr view 8598 --json state,reviewDecision,reviews`, `gh pr checks 8598` |
| Tag | none. No `15.0.9` tag exists |

## What 15.0.9 contains

### Held out

| PR | branch | head | diff | register | why |
|---|---|---|---|---|---|
| #8730 | `nightscout:crowdin_incoming` | `f99c0e54` | 32 files, +518/−454 | BF-132 | Crowdin translation updates. Decided 2026-09-25 (maintainer) to carry, then held out the same day: the sync puts back translations `dev` corrected (for example Traditional Chinese "ml" shown as grams). A reconciled translations branch is an option |

### Merged to `dev`

Merge SHAs and dates: `git log --first-parent --format='%h %ad %s' --date=short official/master..official/dev`.
Register ids refer to
[`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md),
which is the home of every defect fact; these tables do not restate them.

#### Programme backfix PRs (40), plus #8741

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
| #8766 | `e812a68c` | 2026-09-25 | BF-118 | fixes #7729. On a `DISPLAY_UNITS=mmol` site each of `BG_HIGH`, `BG_TARGET_TOP`, `BG_TARGET_BOTTOM`, `BG_LOW` is judged on its own in `lib/settings.js`: below 30 = mmol/L, converted (`Math.round(v * MMOL_TO_MGDL)`); 30 or more = mg/dL, kept; one `console.info` line per converted threshold. Replaces the all-or-nothing conversion gated on `bgHigh < 50`, under which a site setting only the two targets in mmol/L stored them as mg/dL, `verifyThresholds` rewrote `bgLow` to 2.9, no low alarm could fire and every reading raised "Warning HIGH". README bullet under Alarms. `verifyThresholds` (BF-67) and mg/dL sites (BF-86) unchanged |
| #8767 | `ecb63223` | 2026-09-25 | BF-119 | fixes #5622. `PUMP_WARN_ON_SUSPEND` (with `PUMP_ENABLE_ALERTS`) raises a WARN "Pump Suspended" notification while the latest devicestatus reports `pump.status.suspended` and the pump is not bolusing (`lib/plugins/pump.js` `updateStatus`); it never did before. With `PUMP_WARN_ON_SUSPEND` on, the pill class follows WARN while suspended. A devicestatus reporting only `status.status: 'suspended'` shows "suspended" on the pill without the warning. Public text says only that the setting now works |
| #8758 | `4d9ecc3b` | 2026-09-25 | BF-99–BF-102, BF-109, BF-111–BF-113, BF-115–BF-117, BF-130, BF-131 | a record keeps its own `_id` across API v1, v3 and the websocket: one helper for the rule that a 24-hex `_id` is stored as an ObjectId and matched in either form; find, edit and delete by `_id` for profiles, devicestatus, food, activity, treatments and entries; an entries POST that matches a stored reading answers with the stored `_id`; a CRUD-by-`_id` matrix test. Head `f1e8398b`; 38 files, +4194/−107 |
| #8768 | `e2bbeb66` | 2026-09-25 | BF-120 | fixes #7036. The clock views' 20 s timer redraws from the last data before fetching, so a reading's age and stale state keep moving while fetches fail (`lib/client/clock-client.js`) |
| #8769 | `fbaa4a2a` | 2026-09-25 | BF-126 | fixes #7110. Subject and role create and save refuse a missing or unusable name (400); a stored one without a name is skipped at load with a log line, so a site already in that state boots |
| #8770 | `e3adc91d` | 2026-09-25 | BF-134 | each Loop remote command builds its APNs provider just before the send and shuts it down when the push settles; 15.0.8 left one provider, its session and a 60 s heartbeat open per command (`lib/server/loop.js`) |
| #8771 | `ab9c96e6` | 2026-09-26 | BF-106 | a `dev`-only regression from #8737. With a named collection and no `walker`, `lib/server/query.js` again reads `date` and `sgv` as numbers (`coercion.toNumber`, no truncation) unless the collection's schema types them; `lib/server/profile.js` sets `walker: {}` as on 15.0.8. Numeric `date`/`sgv` filters on v1 `/activity` and `sgv` filters on v1 `/devicestatus` match again, and a devicestatus DELETE by `sgv` deletes again. Head `20c197bb` |
| #8772 | `f1151832` | 2026-09-26 | BF-129 | `GET /api/v1/entries/<24-hex id>` for an id that names no entry answers `200 []` (an empty body for `.csv`/`.tsv`) instead of `500 "Mongo Error"`; a storage error still answers 500; `lib/server/swagger.{yaml,json}` state it. 15.0.8 answered 500 for a lower-case unknown id; #8758 made the upper-case form reach the 500 too. Head `b18c4a1e` |
| #8773 | `e759a989` | 2026-09-26 | BF-125 (first half) | fixes #8104. `sendMakerEvent` (`lib/server/pushnotify.js`) names IFTTT Maker events with the new `levels.toKey(level)`, the untranslated label, so a non-English site sends `ns-warning`, `ns-urgent` and `ns-<level>-<name>`; `value1`/`value2` stay translated. The resend after a failed send (a 30 s dedup key, extended to 15 min only on success) is kept by decision and pinned by two tests. Head `54bf05d2` |
| #8774 | `f0174d05` | 2026-09-26 | BF-123 | fixes #7771. `lib/profilefunctions.js` `getValueByTime`, for an AAPS 3.x Profile Switch (an embedded `profileJson`, a numeric `percentage` > 0, no `CircadianPercentageProfile`): basal × pct/100, ISF and carb ratio × 100/pct, targets, DIA and `carbs_hr` unscaled; `timeshift` (ms, truncated to whole hours) reads the schedule at `t − timeshift`. The CircadianPercentageProfile path and `spec_profile` requests are unchanged; `/api/v2/summary` still returns the unscaled profile. Head `9d2e9c24` |
| #8775 | `1157a8de` | 2026-09-26 | BF-122, BF-135 | fixes #8244. v1, websocket and in-process writes stamp `srvModified`/`srvCreated` from one strictly increasing server clock (new `lib/server/srv-dates.js`, which the v3 handlers use too), so they appear in `/api/v3/<col>/history`; `replaceOne` upserts keep the stored `srvCreated` and `identifier`, so a v1 PUT no longer strips a v3 record's `identifier`. Records with `isValid: false` are left out of v1 reads, the dataloader, the cache and the websocket dedup lookups (new `lib/server/soft-deleted.js`); `find[isValid]=false` still returns them and a v1 DELETE still removes them. v1 DELETE stays a hard delete by decision. BF-135 is the journey lab's JL-1. Head `4658b233` |
| #8776 | `13f235e9` | 2026-09-26 | BF-136 | `lib/api3/generic/update/validate.js`: a field the stored record does not have no longer counts as a change to an immutable field, so a v3 POST that deduplicates onto a record written through v1, a v3 PUT of one, and an AAPS PATCH with `isValid: true` are accepted instead of answering 400 (which AAPS does not retry). In the same-millisecond, same-`eventType` case the v3 write replaces the v1 record. Head `962d189b` |
| #8777 | `d613c35f` | 2026-09-26 | BF-128, BF-139, BF-138 | fixes #6220. `lib/server/pebble.js`: `bgdelta` in the requested units (`aa224c69`); the `/pebble` sandbox scales its own copies of the readings, so a request in the other units no longer changes the values the server's alarm checks, `/api/v2/properties`, Alexa and Google Home read (`b58b937c`; BF-139 is live on 15.0.8 and described by mechanism only); `bwp` computed against the profile in the site's units, `bwpo` returned in the requested units (`b3db0f36`). Head `4864d679` |
| #8779 | `750801a9` | 2026-09-26 | BF-80 | a `dev`-only regression from BF-75's fix (#8745). New `authorization.resolveAnonymous`: the `/alarm` connect-time admission, and a `subscribe` that presents no credential, get `AUTH_DEFAULT_ROLES` without consulting the failed-login delay list; a credentialed `subscribe` still waits out the delay before its check. On `readable` every `/alarm` socket is admitted at once; on `denied` a socket without a credential gets nothing (BF-75 holds) and a signed-in socket on a delayed address is admitted only after the delay. `resolve()`, HTTP and the main namespace unchanged. Mechanism only in public text. Head `1b243f14` |
| #8780 | `ff93fa94` | 2026-09-26 | BF-121 | fixes #8185. New `lib/server/treatment-fallback-key.js` (option 3): the v1 and websocket `dbAdd` exact-match fallback requires equal client identity (`syncIdentifier`, `id`, `uuid`, `NSCLIENT_ID`; a write carrying none matches only a record carrying none and no `identifier`); for v1 writes without identity `carbs` and `insulin` join the key; the websocket ±2 s similar match always keys on `eventType`. API v3 and the websocket exact match's no-identity key are unchanged. Head `f3eb68de` (`fc821024` merged with `dev` `13f235e9`) |
| #8783 | `699eb5fa` | 2026-09-26 | BF-142 | a `dev`-only regression from #8758 (`cb7d4110`, BF-117). `lib/api3/storage/mongoCollection/utils.js` `filterForEveryForm`: the v3 DELETE's `_id` fallback, soft and permanent, takes exactly the stored identifiers `normalizeDoc` shows as the `_id` (`null`, `""`, `0`, `false`, `NaN`), so a record whose identifier is `0` or `false` is deleted again; a list identifier is still refused, because v3 GET shows the list as the record's identifier (15.0.8 deleted it; known issue). Head `1c3aeb8c` |
| #8784 | `ce30a94d` | 2026-09-26 | BF-146, BF-133 | `lib/api3/storage/mongoCachedCollection/index.js` `updateInCache`: treatments and device status written through API v3 pass through `ddata.processRawDataForRuntime`, the helper the v1 emitters use, before they enter the in-memory cache, so they carry `mills` (and `endmills` where the helper adds it); nothing stored changes, entries are passed on as before. A late or edited v3 treatment counts in the treatment-based IOB and COB on the server and in the page data; the dataloader's sort puts treatments in time order, so the COB total and `cob.lastCarbs` follow time (BF-133); a late v3 device status is placed by time in the in-memory `GET /api/v1/devicestatus`. The same code is on 15.0.8. Heads `db99bba4` (treatments), `d235bdf6` (device status) |
| #8785 | `295f1177` | 2026-09-27 | — | test only. `tests/boluswizardpreview.test.js`: the sandbox reads the same `now` the test data is stamped with (`sbx.time = now` after `serverInit`; `clientInit(ctx, now, data)`), so two IOB tests no longer fail (49.95 against 50) when the test files before this one take more than about a minute. Nothing that runs on a site changes. Head `a9b77d1e` |
| #8786 | `7000eb18` | 2026-09-27 | BF-147 | `package.json` overrides: `ajv@^6` 6.12.6 → 6.14.0 and `request > form-data` 2.5.5 → 2.5.6; lockfile refresh of `browserslist`, `baseline-browser-mapping` and `postcss-selector-parser` within their ranges (9 versions, patch or minor); new `tests/dependency-overrides.test.js`. `npm audit` 17 → 7, no highs. The production bundle is byte-identical. Head `64a9cc13` |
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
| #8788 | `3014f883` | 2026-09-30 | BF-148, by awss1i (fixes #8223): the Day to Day report draws an event with a duration (Exercise, Note, OpenAPS Offline, Temporary Override, and other events such as a Temporary Target) on every day it covers, clipped to each day, with its label centred on the part shown; events that began the day before a shown day are drawn from `datastorage.treatments`. `lib/report_plugins/daytoday.js` (the five band copies become `appendDurationBand`), `tests/report-daytoday-durations.test.js` (jsdom), `CHANGELOG.md`, `docs/test-specs/manual-smoke-checklist.md`. Head `bbc6e75e`; 4 files, +254/−97. It makes BF-149 (cancellations not applied to report bands, as on 15.0.8) visible on the next day's chart |
| #8530 | `c3d42d4e` | 2026-09-25 | a `48` choice in the main (focus) chart's hour selector, between `24` and `...` (one line in `views/index.html`); no default changes. Carried by the 2026-09-25 decision |
| #8568 | `99689bf9` | 2026-09-25 | BF-114: `lib/data/ddata.js` ends an AAPS open-ended loop disable at the next running-mode record from the same source, so the offline marker no longer keeps the "not looping" and pump alerts off after re-enable; covers the released-AAPS shape and, with the follow-up `1fd09446`, the AAPS development-build shape (`originalDuration` 0, a 10-year duration). Carried by the 2026-09-25 decision |
| #8419 | `96a2c948` | 2026-09-25 | tests only: iOS Loop push-notification and websocket integration tests (`tests/loopnotifications.test.js`, replacing `tests/loop-server.test.js`), fixtures, `.nycrc.json`; head `8cffc05e` includes the maintainer's hook cleanup. Carried by the 2026-09-25 decision |
| #8781 | `ce7d754a` | 2026-09-26 | BF-141, BF-143, BF-144, by AndyLow91; three `dev`-only regressions: a v1 treatment re-sent with `identifier: ""` is matched as a record without identity and stored once (from #8780, `lib/server/treatment-fallback-key.js`); a re-send without identity keeps the stored `srvCreated` (from #8780 on #8775); the v3 history clock is restored from the highest stored `srvModified` at boot, so records written after a restart that follows a large batch appear in `/api/v3/<col>/history` (from #8775, `lib/server/srv-dates.js`, `lib/server/bootevent.js`). Supersedes #8782. Head `a28fcecb` |
| #8778 | `aa1111b2` | 2026-09-26 | BF-140, by AndyLow91: an API v3 DELETE, soft or permanent, of a record whose `identifier` is `null` or `""` falls back to its `_id`, as for an absent `identifier`; arrays are excluded (`lib/api3/storage/mongoCollection/utils.js` `filterForEveryForm`). A `dev`-only regression: the absent-only condition came with #8758 (`cb7d4110`), and 15.0.8's `filterForOne` has no identifier condition on its `_id` fallback (read). Head `18141136` |

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

All merged 2026-09-05. #8749 (qs) and #8786 (BF-147, the `ajv` and `form-data` overrides) are in the backfix table above.

#### Translations

#8599 `9f1b4d3a` (2026-09-05) and #8603 `b982e1e9` (2026-09-06), Crowdin.

#### Docs, CI and version

| PR | Merge | Date | What |
|---|---|---|---|
| #8597 | `5c26c9d2` | 2026-09-04 | start the 15.0.9 cycle (`package.json` → `15.0.9`) |
| #8516 | `85fed44b` | 2026-09-04 | README: MongoDB 4.4 no longer supported — amended by #8750 |
| #8750 | `1f9a9d10` | 2026-09-23 | README: MongoDB 4.4 **deprecated**, still tested, to be dropped in a later release |
| #7338 | `57d1cac9` | 2026-09-06 | js-beautify option in docs |

### Credits for the carried PRs

The outside contributors whose PRs the 2026-09-25 decision carries into 15.0.9, by GitHub login
(`gh pr view <n> --json author`):

- **lejcey** — #8568, the AAPS loop-status timeline fix
- **je-l** — #8419, the iOS Loop push-notification and websocket tests
- **alanshurafa** — #8530, the 48-hour chart choice
- **awss1i** — #8788, Day to Day events past midnight (merged 2026-09-30)

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
| BF-86 / BF-67 — thresholds in the wrong units (a mmol/L low threshold on a mg/dL site is stored so the low alarm can never fire; an out-of-order threshold is silently rewritten) | open; #8766 (BF-118) fixes only the partial-mmol/L case on a `DISPLAY_UNITS=mmol` site | carried as a known issue in the notes |
| BF-76 — unbounded `silenceTime` | open, left open deliberately by #8745 | carried as a known issue |
| BF-92 — a page with no glucose reading presents no server alarm, including device alarms | open; #8755 removes only the handler error | carried as a known issue |
| BF-95 — an uploader clock running ahead delays the stale-data alarm by about the size of the error | open | carried as a known issue |
| BF-44 / BF-45 — MiniMed ingestion divergences | open, graded low: legacy mmconnect does not work, so only one path ingests in practice | the legacy bridges are removed on cut 1 |
| Crowdin #8730 — translation updates after early September | held out (BF-132) | translations are those of #8599 and #8603 |
| BF-122's delete half — a v1 or websocket delete (careportal, Loop, Trio, xDrip+) removes the record and never appears in v3 history, so AndroidAPS keeps counting its copy | kept by decision (hard delete, 2026-09-26) | carried as a known issue; the notes tell people to delete in AndroidAPS too |
| BF-121's remaining cases — AAPS v3 bolus and carbs in the same millisecond, both `Meal Bolus`, stored as one; two careportal entries in one minute with the same amount stored as one | left by decision (option 3, 2026-09-26) | carried as a known issue |
| BF-121 × BF-136 — after an AAPS v3 write takes over a v1 record at the same `created_at` and `eventType`, a later re-send of the v1 entry is stored again (a duplicate when the amounts are equal) | accepted as a known issue (2026-09-26) | carried as a known issue |
| BF-124 — a treatment tooltip's BG in the wrong units when the profile's and display units differ; display only | open; not selected for 15.0.9 (2026-09-25) | carried as a known issue |
| BF-127 — a clock view opened from the menu is blank for a token viewer on a denied site; `/clock/<face>?token=…` opened directly works | open; not selected for 15.0.9 (2026-09-25) | carried as a known issue |
| BF-125's resend half — a failed IFTTT Maker send is retried at every check | kept by design (2026-09-26) | unchanged from 15.0.8 |
| BF-123 on CircadianPercentageProfile switches (AAPS 2.x) — the timeshift is not applied | left by decision (2026-09-26) | unchanged from 15.0.8 |
| BF-137 — with several IFTTT Maker keys an alarm's calls run out of order and a failed key is not retried | after 15.0.9 (`BFQ-137`) | unchanged from 15.0.8 |
| BF-142's list case — a record whose identifier is a list (`[null]`, `[""]`, `["", "other"]`) cannot be deleted through API v3, where 15.0.8 deleted it; v3 GET shows the list as its identifier | kept by decision (2026-09-26, #8783) | carried as a known issue |
| BF-145 — API v3 PATCH and PUT by the id v3 GET shows miss a record stored with identifier `null`, `""` or `0` (PATCH 404, PUT stores a second copy) | after 15.0.9 (`BFQ-145`); the same on 15.0.8 | carried as a known issue |
| `OID-V3-EDIT-MERGE`, `OID-WS-EDIT-MERGE` — an edit through v3 or the websocket of a record stored twice leaves both copies | after 15.0.9 | as described under #8758 |
| `TRUST_PROXY` planned flip | none planned ([versioning policy §5.7](../../docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md#57-compatibility-flags)) | unset is a permanent, documented setting; BF-30 is closed only where an operator sets it |

Other `open` register entries that reach 15.0.9 are listed in the register's §1, and the queue
items for everything present on 15.0.8 are in the operator-exposure table on
[PROGRAMME-STATUS](../../docs/00-overview/PROGRAMME-STATUS.md#status-words-merged-is-not-released);
this file does not copy them.

## Open items a releaser must settle

What the queue tracks is generated, and current, in
[ROADMAP §1](../../docs/00-overview/ROADMAP.md#1-the-next-release-1509). As generated on
2026-09-26 it lists one open blocker of queue `RT-0`, `RT-VERSION`, whose red gate is on the cut
branches, which are renumbered when they are rebased. Beside that:

1. **The browser checks.** `node tools/queue/gates/client-unchanged-since-hand-check.js --base 3014f883 --with ''`
   names 15 files changed since the hand-checked `8d797ba4` (12 on `e3adc91d`; #8773 adds
   `lib/levels.js`, #8774 adds `lib/profilefunctions.js` and #8788 adds `lib/report_plugins/daytoday.js`; #8781, #8783, #8784 and #8785 add none). #8786 adds no file; the gate also lists the 11 package entries it changes (the two overrides and nine locked versions), and the production bundle built from `295f1177` and from `7000eb18` is byte-identical, so they need no hand check. The browser-side ones need the checks
   repeated by hand: the Loop remote-command path (`lib/api2/index.js`,
   `lib/api2/notifications-v2.js`, a remote override, carbs and bolus from careportal and
   LoopCaregiver each needing a 200 and a delivered push), the clock views
   (`lib/client/clock-client.js`), the page data load (`lib/data/ddata.js`, `lib/data/calcdelta.js`,
   `lib/data/dataloader.js`, a first load and live updates, including a treatment deleted while the
   page is open), the pump pill (`lib/plugins/pump.js`), the profile editor, `lib/settings.js`,
   `views/index.html`, the alarm level labels (`lib/levels.js`) and, during an AAPS percentage
   Profile Switch, the basal line, Bolus Wizard Preview pill and reports (`lib/profilefunctions.js`;
   #8774's body records these as not measured in a browser).
   **Done by hand on `ff93fa94` on 2026-09-26** (the maintainer in Chrome, the journey lab playing
   the phones, 15.0.8 side by side; [browser record](../../docs/60-research/remedial/journey-lab-browser-15.0.9-2026-09-26.md)):
   careportal Temporary Override, Remote Carbs and Temporary Override Cancel each delivered a push
   to the right device (the drawer closes silently on success, as on 15.0.8); the page data load,
   first load and live updates, including an AAPS delete and a Reports delete while the page was
   open; the Profile Editor; during a 150% AAPS Profile Switch, the basal pill, ISF and carb ratio.
   No regression was found. **Still owed:** a remote bolus; LoopCaregiver from its own app (only
   scripted); the clock views; the pump pill; the alarm level labels (`lib/levels.js`); the Bolus
   Wizard Preview pill and the reports during a percentage switch; the Day to Day report (#8788),
   by the new "Day to Day events with a duration past midnight" section of
   `docs/test-specs/manual-smoke-checklist.md`. #8781, #8783, #8784, #8785 and #8786
   (after `ff93fa94`) change no browser-side file. #8784 changes what the server sends to the page (late or
   edited v3 treatments now carry `mills` in the page data, so the page's IOB and COB count them);
   that was not checked in a browser.
2. **The 24 to 72 h real-time soak** on `7000eb18`: **done**; #8788 (browser-side, the Day to Day report) came after it. Run 020's compressed A/B soak against 15.0.8 is
   in the [integration record](../../docs/30-design/remedial/rc-15.0.9-integration-record.md).
   Real sites are running the candidate (the `dev_7000eb18…` image or the `dev` branch at
   `7000eb18`, per the [testing notes](testing-notes.md)). On 2026-09-30 the maintainer decided
   that these real-site runs count as the real-time soak, and reported that they have shown no
   visible regression so far. The testing notes record, as of 2026-09-29, one Loop, one Trio and one AndroidAPS user running `7000eb18` for about two days with no errors ([testing notes](testing-notes.md#where-testing-stands)); no later count is recorded. The lab
   real-time soak (`lab.sh soak --hours 72`) was not run.
   **The `npm audit` triage is done** ([below](#npm-audit-and-dependabot-triage), 2026-09-27): of
   the 17 findings (1 low, 13 moderate, 3 high) on `295f1177`, 10 are cleared by BF-147's fix (two
   override values and a lockfile refresh), merged as #8786 (`7000eb18`); `dev` now audits at 7,
   all moderate, and `3014f883` is the same (#8788 changes no package file). The other 7 are a deliberate pin, legacy ingestion and dev dependencies, all
   removed on the modernization line.
3. **Hand-written `CHANGELOG.md` `[Unreleased]` section on dev** (lines 5–75 of
   `git show official/dev:CHANGELOG.md` at `4f705217`; `git log --no-merges official/master..official/dev -- CHANGELOG.md`)
   against the stated rule that the changelog is generated at release time. See
   [`../README.md`](../README.md#open-item-changelog-on-dev).
4. **Re-approval of #8598 at the final head and the semver decision**, by the maintainer (the
   approvals were given on `e3adc91d`; the version class of #8772, #8775 and #8780 is undecided,
   see [decisions](decisions.md)).
5. **Whether the BF-108 fix goes in**, by the maintainer. A v1 filter listing two or more dates
   under the date field answers 500, so xDrip4iOS bulk deletes remove nothing (on 15.0.8 too). The
   fix is one commit on `3014f883`, local branch `bf/date-filter-list` `350f6f09`, not pushed
   (queue `BFQ-108`; PR body draft `reports/phase0-pr-bodies/date-filter-list.md`). Taking it moves
   `dev` once more; it changes `lib/server/query.js` only, server-side, so no browser check.
6. **The tag**, by the maintainer.

#8598's two approvals were given on `e3adc91d`; its head is now `3014f883`. The release notes and
tag body are drafted for `3014f883`.

Housekeeping: Dependabot #8747 targets `master` with an axios bump `dev` already contains (#8565);
it is moot once #8598 merges.

## `npm audit` and Dependabot triage

**Summary.** 15.0.8 (the release operators run today) has 49 `npm audit` findings (19 high). 15.0.9
(`dev` `7000eb18`) has 7, all moderate: a deliberate pin whose advisories need elements the sanitizer does not allow
(tested), the legacy `request` chain, loaded only when a legacy bridge is switched on (read from
`lib/server/bootevent.js`), and two test-only packages. **After the
modernization pass (cut 4 onward, including cut 5 `b1bdaca0`) there are none:** `npm audit` reports
0 findings with dev dependencies included, and none of the 80 open Dependabot alerts matches a
version in cut 5's lockfile. The work that gets there was planned in the open:

| date | what |
|---|---|
| 2026-01-18 | [modernization roadmap](https://github.com/nightscout/cgm-remote-monitor/blob/dev/docs/meta/modernization-roadmap.md) on `dev` and `master` (`14f92611`); §3.1.1 is replacing the deprecated `request` library, the source of most findings still in 15.0.9 |
| 2026-03-16 | #8421, MongoDB driver `^3.6.0` → `^5.9.2`, released in 15.0.7 (2026-04-29) |
| 2026-05-10 | #8517 (runtime dependency advisories) and #8514 (jsdom) |
| 2026-06-28 | #8518 (development and test tooling) |
| 2026-09-05 | 15 Dependabot updates merged together (above); the modernization branch begins (`6a6dd7a5`, with `docs/plans/nightscout-modernization.md`), 498 commits by Andy Low to `b1bdaca0` (2026-09-21) |
| 2026-09-23 to 27 | #8749 (qs, BF-87) and #8786 (BF-147) |

Since 15.0.7, 38 merges to `dev` changed the lockfile, 20 of them Dependabot's
(`git log --first-parent --oneline 15.0.7..official/dev -- package-lock.json`). Alerts on the
default branch fall only when a release merges to `master`; 74 of the 80 open today are already
fixed on `dev` (below).

Measured 2026-09-27 on `official/dev` `295f1177` and `7000eb18` with `npm audit --package-lock-only` (npm 11.12.1,
advisory data as of that day). Build tooling (webpack, its loaders, `browserslist`) is in
`dependencies`, not `devDependencies`, because the bundle is built at install time (`postinstall`),
so `--omit=dev` does not separate build-time from run-time packages.

| tree | total | high | moderate | low |
|---|---:|---:|---:|---:|
| `v15.0.8` `92d08342` | 49 | 19 | 28 | 2 |
| `dev` `295f1177` | 17 | 3 | 13 | 1 |
| `dev` `295f1177` `--omit=dev` | 13 | 3 | 9 | 1 |
| `dev` `7000eb18` (#8786, BF-147) | 7 | 0 | 7 | 0 |
| `dev` `7000eb18` `--omit=dev` | 5 | 0 | 5 | 0 |
| `rh/cut2` `02205d91` | 6 | 0 | 6 | 0 |
| `rh/cut4` `135faa3b`, `rh/cut35` `cd93d8e8`, cut 5 `b1bdaca0` | 0 | 0 | 0 | 0 |

### Reading these counts

A vulnerability count on its own does not say whether Nightscout is exposed. Each count above
measures something narrower than it looks:

- **One advisory is counted once for every package that depends on it.** `npm audit` reports a
  finding for the vulnerable package and one for each package above it in the tree. On
  `295f1177`, one `ajv` advisory accounts for 6 of the 17 findings, and one `request` advisory,
  with the `form-data` and `uuid` advisories beneath it, accounts for 5.
- **Build tools are counted as run-time packages.** The bundle is built at install time, so
  webpack, its loaders and `browserslist` are in `dependencies`. Their findings (6 of the 17: `ajv`, `schema-utils`, `style-loader`, `browserslist`,
  `baseline-browser-mapping`, `postcss-selector-parser`)
  concern input those tools read from the repository's own configuration, not anything a
  Nightscout site receives.
- **An advisory counts whether or not Nightscout reaches the vulnerable code.** Both
  `sanitize-html` advisories need an element the sanitizer's configuration does not allow, and
  the `request` findings apply only when a legacy bridge is switched on.
- **Dependabot measures the default branch, which is the last release.** Of its 80 open alerts,
  68 are already fixed on `dev` and stay open until the release merges to `master`.
- **Advisories arrive after the code ships.** `form-data` 2.5.6 was released on 2026-06-12, after
  the 2.5.5 pin was written on 2026-05-10, so a count taken on a fixed tree rises without any
  change to the code.

What a count does show is the backlog to triage. The measured result for 15.0.9 is the table
below: which findings reach a running site, and what is done about each.

### The 17 findings on `295f1177`

| finding | severity | class | reach in 15.0.9 | disposition |
|---|---|---|---|---|
| `ajv` 6.12.6 (GHSA-2g4f-4pwh-qvx6), with `har-validator`, `schema-utils`, `style-loader`, `eslint`, `@eslint/eslintrc` | moderate (6) | held by an override | build and lint time; `har-validator` inside `request` | **BF-147**: override to 6.14.0 |
| `form-data` 2.5.5 under `request` (GHSA-hmw2-7cc7-3qxx) | high | held by an override | only through `request` (below); neither caller sends multipart | **BF-147**: override to 2.5.6 |
| `browserslist` 4.28.2 (GHSA-c83g-rgw3-j3cx, GHSA-73wf-gq98-2v4g) | high | stale lockfile | build time; reads the repository's own configuration | lockfile refresh with BF-147 (4.29.1) |
| `baseline-browser-mapping` 2.10.29 (GHSA-w5vr-8v7q-w6rv) | moderate | stale lockfile | build time | lockfile refresh with BF-147 (2.11.26) |
| `postcss-selector-parser` 7.1.1 (GHSA-w9m9-85wc-3x92) | low | stale lockfile | build time (`css-loader`); the repository's own CSS | lockfile refresh with BF-147 (7.1.6) |
| `sanitize-html` 2.17.5 (GHSA-g8qq-57p8-ggw5, GHSA-jxwj-j7wr-gfrw) | moderate | deliberate pin | server-side write sanitizer (`lib/server/purifier.js`) | **Not changed in 15.0.9.** 2.17.7 requires Node ≥22.12 and 15.0.9 supports Node 20 (`lib/server/purifier.js:38`). Both advisories need an element the configuration does not allow (SVG animation elements; `textarea`). Each advisory's published case was run through `purifier.purifyObject` on `295f1177` and came out with no markup left; `tests/security.test.js:359-382` locks the allow-list. Cut 2 takes 2.17.7 |
| `request` 2.88.2 (GHSA-p8p7-x288-28g6), `uuid` (GHSA-w5hq-g745-h8pq; 3.4.0 under `request`, 8.3.2 under `istanbul-lib-processinfo`), `minimed-connect-to-nightscout`, `share2nightscout-bridge` | high (1), moderate (3) | legacy ingestion | loaded only when mmconnect is enabled or `DEXCOM_BRIDGE_USE_LEGACY=true` (`lib/server/bootevent.js`); both contact fixed vendor endpoints | **Not changed in 15.0.9.** No fixed `request` exists. Removed by retiring the legacy bridges on the modernization line (`rh/cut1-retire-legacy`, cut 4) |
| `csv-parse` 4.16.3 (GHSA-8cw4-87c7-c6xx) | moderate | dev dependency | `tests/api3.renderer.test.js` parses the renderer's own output | **Not changed in 15.0.9.** The fix is 7.0.2, a major; cut 4 takes `^7.0.2` |
| `istanbul-lib-processinfo` (through `uuid` 8.3.2) | moderate | dev dependency | coverage tooling (`nyc`) | **Not changed in 15.0.9.** Gone at cut 4 |

What BF-147's fix changes, and what was run on it, is in the
[register](../../docs/30-design/remedial/nightscout-backfix-register.md#bf-147--two-overrides-hold-ajv-and-requests-form-data-inside-advisory-ranges).
In short: two override values and a refresh of three build-tool packages, 9 lockfile versions
(patch or minor), `npm audit` 17 → 7, bundle builds, suite 3473/0/3 on one cell (Node 24.15.0,
MongoDB 7.0.43). It merged to `dev` as #8786 (`7000eb18`, 2026-09-27).

### Dependabot

Dependabot's 80 open alerts on `nightscout/cgm-remote-monitor` (2026-09-27) are measured against
the default branch, `master` (`v15.0.8` `92d08342`). Each alert's vulnerable range was checked
against every version of that package in both lockfiles:

- **74 are fixed on `dev` `7000eb18`**: axios 22, dompurify 10, js-yaml 7, fast-uri 6,
  brace-expansion 5, ip-address 3, qs 3, ws 3, browserslist 2, form-data 2, nanoid 2, postcss 2,
  and one each for socket.io-parser, d3-color, body-parser, @babel/core, ajv,
  baseline-browser-mapping and postcss-selector-parser. They close when #8598 merges to `master`.
  On `295f1177` the figure was 68; #8786 fixed the other 6.
- **6 remain on `dev`**, all packages in the table above that 15.0.9 does not change:
  sanitize-html 2, csv-parse 2 (the manifest and the lockfile), uuid and request.
- Every alert matches a version on `master`; none is stale.

No Dependabot pull request is open (2026-09-27).

## Known test gaps

Not blockers by decision; recorded so a green suite is not read as covering them.

- **Test-script coverage.** 75 of the 221 `tests/*.test.js` files on `dev` `3014f883` match neither
  `npm run test:unit` nor `test:integration` (compare the files against the two globs in
  `git show official/dev:package.json`; 66 of 190 on `4f705217`, 69 of 205 on `e3adc91d`, 72 of 216
  on `ff93fa94`, 73 of 219 on `295f1177`, 74 of 220 on `7000eb18`; #8786 adds `dependency-overrides`, #8788
  `report-daytoday-durations`). Among
  them: `query.operands`, `boluscalc.quickpick`, `boluscalc.quickpick-rebuild`, `booterror`,
  `client.alarm-no-reading`, `treatmenttime`, `debug-logging`, `dependency-d3`, #8754's `authdelay`,
  `authsubjects` and `client-ip`, and 2026-09-26's `maker-level-names` (#8773),
  `profile-switch-percentage` (#8774), `soft-deleted.jl1` (#8775) and #8781's
  `bootevent-history-clock`. Only `npm test` / `test-ci`
  (what `main.yml` runs) reaches them. A green
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
  [#8754](#programme-backfix-prs-40-plus-8741), including the Loop remote-command sender address
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
- **mmol/L thresholds (#8766, BF-118).** On a `DISPLAY_UNITS=mmol` site each `BG_` threshold is
  read on its own: below 30 = mmol/L, converted; 30 or more = mg/dL, kept; unset thresholds keep
  their mg/dL defaults (260/180/80/55). A site with only the targets in mmol/L now gets its low and
  urgent-low alarms back and stops getting "Warning HIGH" on every reading. The one stored-value
  change: `BG_HIGH` in mmol/L with `BG_TARGET_TOP` in mg/dL (e.g. 14 and 180) now stores 252 / 180 /
  80 / 55, where 15.0.8 stored 3244 / 3243 / 1441 / 991 after `verifyThresholds`. All-mmol/L and
  all-mg/dL sites are unchanged. The server log has one `Threshold <key> <value> taken as mmol/L,
  converted to <n> mg/dl` line per converted threshold; the notes tell mmol/L users to check their
  thresholds and keep device alarms on. mg/dL sites (BF-86) and `verifyThresholds` (BF-67) are
  unchanged.
- **Pump suspended (#8767, BF-119).** `PUMP_WARN_ON_SUSPEND` with `PUMP_ENABLE_ALERTS` now raises a
  WARN "Pump Suspended" notification (group `Pump`, sound `echo`, the usual pump snooze rules; an
  OpenAPS offline marker suppresses it). With `PUMP_WARN_ON_SUSPEND` on, the pill takes the warning
  colour while suspended, independent of `PUMP_ENABLE_ALERTS`. Sites without the setting see no
  change. Public text: the setting now works, nothing about the old failure.
- **48-hour chart (#8530).** A `48` choice in the main chart's hour selector; defaults unchanged.
- **AAPS loop re-enable (#8568, BF-114).** After an AAPS open-ended "disable loop" and a later
  re-enable, the "not looping" and pump alerts return, for the released-AAPS record shape and the
  AAPS development-build shape (`1fd09446`). The Day to day report reads treatments another way and
  is not changed by it.
- **Records keep their own `_id` (#8758).** Records stored with a string `_id` are found, edited and
  deleted by it through v1, v3 and the websocket; an edit of a record stored twice leaves both
  copies unless it is made in the profile editor or the Reports treatment list, and a delete removes
  both. An entries POST that matches a stored reading now answers with the stored `_id` (15.0.8
  answered with the sent `_id` or none). Connector 0.1.0's profile update-on-change works against a
  15.0.9 sink.
- **`/api/v2/properties` COB (#8587, `34e9b2da`).** `cob.treatmentCOB` was a nested object on the
  Care Portal path in 15.0.8. In 15.0.9 it is a number, present only beside a current uploader COB
  and only when the treatment-derived COB is not zero. The notes carry it under "Corrections".
- **Clock views (#8768, BF-120).** A clock page whose fetch is failing keeps ageing the last reading
  and turns stale, as when readings stop.
- **Subjects without a name (#8769, BF-126).** Refused with 400; one already stored no longer stops
  the server at boot.
- **Loop remote commands (#8770, BF-134).** Each command's APNs provider is shut down when the push
  settles; the soak saw 575 of 575 left open on 15.0.8 (fds 30 → 604) and 0 on `e3adc91d`.
- **Unknown entry id (#8772, BF-129).** `GET /api/v1/entries/<id>` for an id naming no entry answers
  `200 []`; 15.0.8 answered 500 for the lower-case form. The notes carry it under "Corrections".
- **IFTTT Maker event names (#8773, BF-125).** Non-English sites send the documented untranslated
  names. A site that renamed its applets to the translated names must rename them back. The
  resend after a failed send is unchanged.
- **AAPS percentage and time-shifted Profile Switch (#8774, BF-123).** The basal pill, chart basal
  line, Bolus Wizard Preview, Nightscout's IOB and COB and the reports use the scaled basal, ISF and
  carb ratio AAPS uses. AAPS's own dosing was never affected. With Dynamic ISF the ISF AAPS doses
  with can still differ from the profile ISF shown.
- **API v3 history and AAPS deletes (#8775, BF-122, BF-135).** AndroidAPS on NSClient v3 now
  receives careportal, bolus wizard and caregiver treatments, other uploaders' readings and v1
  edits through history. A looping AAPS applies carbs and insulin from Nightscout only with
  "accept carbs"/"accept insulin" on in its NSClient settings (both off by default); AAPSClient
  always applies them (read, AAPS `7e1d537d49`). A meal entered both in careportal and on the phone
  can now appear twice in AAPS. A careportal, Loop, Trio or xDrip+ delete still does not reach
  AAPS. A record AAPS deletes stops counting in COB, IOB, the chart, reports, v1 reads,
  `/api/v2/properties` and `/profile/current`. v1 responses now carry `srvModified` and
  `srvCreated`.
- **v3 writes to v1-born records (#8776, BF-136).** AAPS edits of careportal records, and AAPS
  entries that collide with one, are accepted instead of refused and lost. In the
  same-millisecond collision the AAPS version replaces the careportal entry.
- **`/pebble` (#8777, BF-128, BF-138, BF-139).** The delta and the expected BWP outcome come back in
  the requested units; `bwp` is computed in the site's units. A `/pebble` request can no longer
  change the units of the readings the server's alarm checks and other readers use (mechanism only
  in public text). A watch face adjusted to compensate (for example × or ÷ 18) needs undoing.
- **`/alarm` and the failed-login delay (#8779, BF-80).** `dev`-only; relative to 15.0.8, the
  behaviour to describe is that on a `denied` site a signed-in page on an address with recent
  failed logins receives alarms only after the delay. Mechanism only in public text.
- **Same-time treatments (#8780, BF-121).** Two treatments at the same time are kept apart when a
  client identity or, for v1 writes without one, the carbs or insulin amount tells them apart.
  Re-sends still update one record.
- **v3 DELETE with an empty `identifier` (#8778, BF-140).** `dev`-only; no change against 15.0.8 to
  describe.
- **v1 `/activity` and `/devicestatus` numeric filters (#8771, BF-106).** `dev`-only; they answer as
  on 15.0.8.
- **Late or edited v3 treatments in IOB and COB (#8784, BF-146, BF-133).** A treatment AndroidAPS
  (or any API v3 client) uploads dated before the dataloader's 15-minute refetch window, or an older
  one it edits, now counts in the server's and the page's treatment-based IOB and COB at once; on
  15.0.8 it counted only after a restart. Treatments are held in time order, so a COB total that the
  out-of-order carb decay chain made too high (34.5 g against 10 g in #8784's test) can drop, and
  `cob.lastCarbs` names the newest carb entry. `GET /api/v1/treatments` served from memory carries
  `mills` on v3 records too. A late v3 device status is placed by time in the in-memory
  `GET /api/v1/devicestatus` (on 15.0.8 it sorted last and could fall outside the count). Where the
  uploader reports a current IOB or COB in device status, the pills show that value. The notes carry
  it under "AndroidAPS, the careportal and caregivers" and in "Numbers that may look different".
- **Empty-identity re-sends, `srvCreated` and the history clock (#8781, BF-141, BF-143, BF-144).**
  `dev`-only; no change against 15.0.8 to describe.
- **v3 DELETE with an identifier of `0` or `false` (#8783, BF-142).** `dev`-only for `0` and
  `false`, which delete as on 15.0.8. A list identifier is refused where 15.0.8 deleted it; the notes
  carry it as a known issue.
- **Day to Day events past midnight (#8788, BF-148).** An event with a duration that runs past
  midnight is drawn on each day it covers, clipped to each day's chart; on 15.0.8 it was drawn only on
  its start day and ran off the chart's edge. Same-day events are drawn as before. BF-149 (a cancelled
  or replaced temporary target, and likely an override ended early, is drawn for its entered length,
  as on 15.0.8) now also shows on the next day's chart; the notes carry it as a known issue. The notes
  carry the change under "Other changes you may notice".

## Evidence

- Merged part: per-PR test evidence, ablations and controls are in each PR body and in the
  register entry for each id.
- **The candidate, `dev` `3014f883`**: `7000eb18` plus #8788 (BF-148), which changes only
  `lib/report_plugins/daytoday.js` among files a site runs (browser-side, the Day to Day report), adds
  `tests/report-daytoday-durations.test.js` and edits `CHANGELOG.md` and the manual smoke checklist.
  Full suite on its head `bbc6e75e` (same tree): 3481 passing, 0 failing, 3 pending (Node 22.23.2,
  MongoDB 7.0.43, local, 2026-09-30); its test passes 3 of 3 and 1 of 3 with `7000eb18`'s
  `daytoday.js`. #8788's own CI: 14 checks passed, 2 skipped.
- **`dev` `7000eb18`**: `295f1177` plus #8786 (BF-147), which changes
  `package.json` (two override values), `package-lock.json` (9 versions, patch or minor: `ajv` 6,
  `request`'s `form-data`, and build tooling) and adds `tests/dependency-overrides.test.js`. No file
  under `lib/`, `views/` or `static/` changed, and the production bundle built from `295f1177` and
  from `7000eb18` is byte-identical (all 7 files under `node_modules/.cache/_ns_cache/public`; Node
  24.15.0, webpack 5.106.2, `browserslist` 4.28.2 and 4.29.1). Run 020 did not run on the new
  dependencies. The suite runs that did: #8786's CI on `64a9cc13`, whose tree `7000eb18` has, green
  in all nine cells (Node 20/22/24 × MongoDB 4.4/5/6, 3478 passing, 0 failing, 3 pending in each) plus
  the npm 12 install-and-build check; and
  one local cell, 3473 passing, 0 failing, 3 pending (Node 24.15.0, MongoDB 7.0.43), before the test
  file was added. `tests/dependency-overrides.test.js` passes 5 of 5 on the branch and fails 5 of 5
  on `295f1177`'s installed tree.
- **`dev` `295f1177`**: `ce30a94d` plus #8785, which changes only
  `tests/boluswizardpreview.test.js` (the test's data and its sandbox now read one clock; the
  test failed when the files before it took more than about 60 s, as on #8784's CI). No file that
  runs on a site changed, so run 020 stands for it. #8785's CI passed in all nine cells on
  `a9b77d1e`, whose tree `295f1177` has; the file passes 12 of 12 on `295f1177` (Node 22.23.2).
- **`dev` `ce30a94d`** (tree `d300bee9`, run 020,
  [15.0.9 integration record](../../docs/30-design/remedial/rc-15.0.9-integration-record.md)):
  3473 passing, 0 failing, 3 pending on Node 20.20.0, 22.23.2 and 24.20.0 × MongoDB 4.4.24 and
  7.0.43, each version read from the server, cells run one at a time; the 15 tests added since
  `699eb5fa` are #8784's. The BF-146 probe (`tools/lab/rc-soak/probe-v3-late-mills.js`) exits 0 on
  it and 1 on `699eb5fa` and 15.0.8; run 019's probes give the same results as on `699eb5fa`. In the
  compressed A/B soak against 15.0.8, #8784's intended differences have expected-difference entries
  (checked against dumped replies and captured values); with them the 48 h run passes and the 72 h run with restarts
  fails only on BF-135's intended page-load change.
- The previous candidate, `dev` `699eb5fa` (tree `0b727dc5`, run 019): 3458 passing, 0 failing,
  3 pending in the same six cells.
- CI on #8598 at `3014f883`: 27 checks passed, 3 skipped (read 2026-09-30); at `7000eb18` and `295f1177`, 27 checks passed, 3 skipped. At `e3adc91d` it was
  27 green and 3 skipped (Node 20/22/24 × MongoDB 4.4/5.0/6.0, CodeQL, Docker).
- Queue items P0-A…P0-K, P0-T01, ADV-RETRO, ADV-ALARM and ADV-CONFIG hold the gates. Do not treat
  a local `test:unit` pass as coverage ([Known test gaps](#known-test-gaps)).

---

*Draft, 2026-09-30. Requires maintainer review before release. Nothing tagged or published.*
