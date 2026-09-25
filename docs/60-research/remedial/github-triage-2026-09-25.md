# GitHub triage of cgm-remote-monitor and nightscout-connect

*Snapshot, 2026-09-25, against cgm-remote-monitor official/dev 4f705217 (15.0.8 = 92d08342), #8758 head ab7b22d6, nightscout-connect v0.1.0 4dde1ec. Contributor-facing. Nothing here has been posted to GitHub. Item state lives in [queue/work-queue.yaml](../../../queue/work-queue.yaml), and defect facts in the [backfix register](../../30-design/remedial/nightscout-backfix-register.md).*

Every open pull request and every open issue in both repositories was triaged on 2026-09-25:
**42 PRs** (39 in cgm-remote-monitor, 3 in nightscout-connect) and **114 issues** (102 and 12).
Each PR head was fetched, trial-merged against `dev` and against #8758, and checked against the
register and the queue. Its own tests were run on `dev` with the PR merged where §8 says so. Each
issue was classified against both refs. Where a defect claim is marked **reproduced**, it was run on
both trees with a control; the rest are **read-derived**. The outcome: 3 PRs are carried into
15.0.9, 1 is refused, 11 defects are to be filed in the register, 9 issues get an update when
15.0.9 ships and 7 can be answered and closed. No open issue matches a withheld register entry. Not
medical advice.

## 1. Decisions

Made by the maintainer on 2026-09-25.

| decision | items | tracked |
|---|---|---|
| **Carry into 15.0.9** | #8568 (lejcey): an AAPS open-ended loop disable keeps the loop and pump alerts off after the loop is back on. The contributor is asked to also match the AAPS-dev shape and add an alert-level test | register BF-114, queue `BFQ-114` |
| | #8419 (je-l): tests for Loop push notifications and websockets | queue `RT-PR-8419` |
| | #8530 (alanshurafa): a 48-hour option in the focus range selector | queue `RT-PR-8530` |
| | #8730 (Crowdin, opened by sulkaharo): translation updates, 32 files; merges cleanly with `dev` `4f705217` and #8758 | queue `RT-PR-8730` |
| **Do not carry** | #8522 (stevoh6): with it merged, 13 existing tests fail on `dev` (§5.4) | — |
| **File in the register** | the 11 confirmed defects in §6: #5622, #7036, #7110, #8104, #6220, #5940, #7377, #7729, #7771, #8185, #8244. Filed 2026-09-25 as BF-118 to BF-128, each reproduced on 15.0.8 and dev with a control (probes in `tools/lab/triage-2026-09/`, except #7110's, held outside the repository) | register |
| **Direction** | these defects continue the backfix effort, methodically and completely, one at a time | — |

## 2. Update when 15.0.9 ships

No merged 15.0.9 PR uses a closing keyword, so none of these issues closes automatically. Each
comment below is written to be posted on the day 15.0.9 is released.

| issue | fixed by | status | keep open? |
|---|---|---|---|
| #8714 debug log volume after 15.0.8 | #8726 (debug logging opt-in); connector 0.1.0 pin, #8762 | merged | close after posting |
| #8584 Reports basal graph stops at the switch hour | #8701 (profile-switch schedule preprocessing) | merged; link to the report is probable, not confirmed | until the reporter confirms |
| #6066 Treatments report cannot be limited by event type | #8590 (row filter, day-filter labels) | merged; not measured here | close after posting |
| #8315 Bolus Wizard quick pick shows only (none) | #8756, #8735 | merged | close after posting |
| #7324 insulin age pill never turns red | #8739, #8732 | merged | close after posting |
| #8072 report readability (event-type filter part) | #8590 | merged | yes: readability requests remain |
| #8328 Node and dependency tracking | #8573 (D3 7.9.0), #8749 (qs 6.16.0), others in [contents.md](../../../releases/cgm-remote-monitor-15.0.9/contents.md) | merged | yes: tracking issue |
| connector #14 European Glooko accounts | connector #71, in 0.1.0, pinned by #8762 | merged | until reporters confirm |
| connector #21 CareLink "no reading" stored as 0 | connector 0.1.0 (drops `sg` 0), pinned by #8762 | merged; read-derived, not reproduced | close after posting |

**#8714.** DRAFT:

> Thank you for the detailed log comparison. Nightscout 15.0.9 turns routine debug output off by default, for the server and for the built-in Nightscout Connect data source. If you need the detailed output again while troubleshooting, set `DEBUG_LOGGING=true` (server) or `CONNECT_DEBUG=true` (Nightscout Connect), and turn it off afterwards. Please let us know if your log usage stays high after upgrading to 15.0.9.

**#8584.** DRAFT:

> Thank you for the report and the profile details. Nightscout 15.0.9 fixes a problem with profiles carried inside Profile Switch treatments, where a schedule could produce missing basal values after the switch time. We think this is the cause of the basal graph stopping at 09:00, but we have not confirmed it against your data. After upgrading to 15.0.9, could you check the affected dates in Reports and tell us whether the full 24-hour basal graph is back?

**#6066.** DRAFT:

> Thanks for reporting this. In Nightscout 15.0.9 the Treatments report has a new filter above the table that shows only the rows with the event type you choose. The existing filters at the top of the Reports page select which days are included, and they are now labelled that way (for example, "Days with event type"). Please reopen if this doesn't cover what you needed.

**#8315.** DRAFT:

> Thank you for reporting this. Nightscout 15.0.9 fixes the Bolus Wizard quick pick list: it is now rebuilt from your food database each time you open the Bolus Wizard, and hidden quick picks stay hidden. One limitation remains: if you add or change quick picks in another tab, reload the page to see them in the Bolus Wizard.

**#7324.** DRAFT:

> Thank you for reporting this and for the comparison with the other age pills. Nightscout 15.0.9 fixes the insulin age pill so that it turns red once the insulin age reaches your urgent setting (`IAGE_URGENT`, 72 hours by default). If you also use insulin age alerts (`IAGE_ENABLE_ALERTS=true`), the urgent alert now fires as well.

**#8072.** DRAFT:

> Part of this is addressed in Nightscout 15.0.9: the Treatments report has a new filter above the table that shows only the rows with a chosen event type, and the filters at the top of the Reports page are now labelled as selecting days (for example, "Days with event type"). The readability suggestions here, such as the exercise bar text and temporary target captions, are still open as feature requests, so we'll keep this issue open for them.

**#8328.** DRAFT:

> An update for this tracking issue: Nightscout 15.0.9 includes part of this work, among them D3 7.9.0, qs 6.16.0, and updates to axios, socket.io, express and body-parser. The full list is in the 15.0.9 release notes. The wider runtime and dependency modernisation in #8605 is not part of 15.0.9 and continues there, so we'll keep this issue open.

**connector #14.** DRAFT:

> Nightscout Connect 0.1.0 is now included with Nightscout 15.0.9. It adds explicit EU and DE/FR region selection, alternative login methods and a fallback for CGM readings. If you had trouble with a European Glooko account, please try again after upgrading and let us know whether it works, including which region setting you used. Please do not post your email address or password here.

**connector #21.** DRAFT:

> Thank you for reporting this. Nightscout Connect 0.1.0 no longer stores CareLink's "no reading" placeholder as a glucose value of 0. It is included with Nightscout 15.0.9. Readings of 0 that were already stored stay in your database; you can remove them if they affect your reports.

## 3. Answer and close

| issue | status | basis | provenance |
|---|---|---|---|
| #8075 profile.json ignores find | not a defect | `/profile` ignores `find` by design; `/profiles` honours it with a default `startDate` window | measured |
| #8105 ALARM_*_MINS and Pushover/IFTTT repeats | not a defect | the lists are snooze lengths; the repeat interval is fixed at 15 min | read-derived |
| #8167 Azure Cosmos DB and API v3 | not a defect | unsupported backend (missing index requirements); the reported path is caught on 15.0.8 | read-derived |
| #8097 AAPS full sync missing data | stale | the client path is gone: current AndroidAPS uses API v3 only, and no client in the corpus sends the socket update | static analysis |
| #8279 FerretDB compatibility | question | MongoDB only; FerretDB is not tested | — |
| #8074 TypeScript migration interest | question | discussion, not planned work | — |
| connector #24 CareLink polls on five-minute marks | not a defect | since v0.0.10 the poll is scheduled from the last reading time plus 68 s and up to 18 s of jitter | read-derived |

**#8075.** DRAFT:

> Thanks for the question. `/api/v1/profile.json` returns the most recent profiles and does not apply `find` parameters; that is by design. To search profiles by date, use `/api/v1/profiles.json` with a `find[startDate]` range, for example `find[startDate][$gte]=2011-11-25&find[startDate][$lte]=2012-03-20`. Note that `/api/v1/profiles` applies a default `startDate` window, so a filter on `created_at` alone can return nothing for old profiles. Closing as answered; please reopen if that doesn't work for you.

**#8105.** DRAFT:

> Thanks for the report. The `ALARM_*_MINS` settings set the snooze choices offered for each alarm, and the first value is the snooze applied when an alarm is acknowledged from Pushover. They don't change how often Pushover or IFTTT notifications repeat: that interval is fixed at 15 minutes. Closing as answered; we'll look at making the documentation clearer on this.

**#8167.** DRAFT:

> Thanks for the report. Azure Cosmos DB is not a supported database for Nightscout. Its MongoDB API needs indexes for sorted queries that Nightscout does not create, which is what causes these errors. Current versions answer that failure with an error instead of stopping the server, but API v3 queries will still fail on Cosmos DB. Please use MongoDB. Closing as an unsupported setup.

**#8097.** DRAFT:

> Thanks for the report. Current versions of AndroidAPS sync with Nightscout through API v3, and the update path described here is no longer used by AndroidAPS or any other uploader we know of. Closing as stale. If you see missing data after a full sync with current versions of AndroidAPS and Nightscout, please open a new issue with the versions you are using.

**#8279.** DRAFT:

> Thanks for asking. Nightscout supports MongoDB only, and its tests run against MongoDB 4.4, 5.0 and 6.0. FerretDB is not tested, so we can't say whether it works. Closing as answered; if you try it, notes on what worked and what didn't are welcome in a new discussion.

**#8074.** DRAFT:

> Thanks for raising this. We're closing it as a discussion item rather than tracking it as planned work. Current modernisation work is tracked in #8328 and #8605. If you'd like to propose a concrete, incremental approach, a new issue is welcome.

**connector #24.** DRAFT:

> Thanks for the report. Since version 0.0.10, the CareLink source schedules its next poll from the time of the last reading plus about 68 seconds and a small random delay, not on fixed five-minute marks. Polls that line up with :00 and :05 most likely follow the timestamps CareLink gives its readings. Closing for now; if you still see this with Nightscout Connect 0.1.0 (included with Nightscout 15.0.9), please reopen with the times you observe.

## 4. Open PRs

Relation: **a** superseded or addressed by merged or open 15.0.9 work; **b** overlaps open
programme work; **c** independent. File overlap with #8605 alone is not counted as a relation.

| PR | title | author | rel. | recommendation |
|---|---|---|---|---|
| #8758 | a record's own _id finds, edits and deletes it | bewest | b | leave: the open 15.0.9 PR |
| #8730 | Crowdin updates | sulkaharo (Crowdin) | b | carry into 15.0.9 (decided 2026-09-25); no draft needed |
| #8605 | modernize runtime, dependencies, memory | AndyLow91 | b | leave: programme vehicle |
| #8598 | new dev branch post 15.0.8 release | AndyLow91 | b | leave: dev → master release PR |
| **#8568** | fix loop status timeline | lejcey | c | **carried into 15.0.9** (decided) |
| #8580 | configurable custom notification webhooks | joshi-rushikesh | c | consider for a cut (15.1); security review |
| #8564 | telemetry emitter (WIP) | bewest | c | maintainer's own WIP |
| #8560 | fullscreen toggle | earldouglas | c | consider for a cut; retarget to dev |
| #8555 | seconds on dashboard clock | samuelpert | c | consider for a cut |
| #8542 | AGP summary and charts (draft) | tim2000s | c | consider for a cut; retarget |
| #8541 | modern browser targets, websocket | tim2000s | c | needs maintainer judgement (support policy); retarget |
| #8540 | Trio dark theme, TIR widget, a11y | tim2000s | c | consider for a cut; retarget |
| #8537 | clock page fields | tynbendad | c | consider for a cut; retarget |
| #8533 | mg vs mmol when displaying treatments | stevoh6 | c | needs maintainer judgement (unit guessing) |
| #8531 | smooth glucose line | alanshurafa | c | consider for a cut |
| **#8530** | 48-hour focus range | alanshurafa | c | **carried into 15.0.9** (decided) |
| #8526 | configurable Y-axis range | alanshurafa | c | consider for a cut |
| **#8522** | mmol vs mg/dL in BWP and profile editor | stevoh6 | c | **not carried** (decided) |
| #8501 | alarm snooze state in MongoDB | quarktwain | b | consider for a cut, after the tenancy ack design |
| #8498 | [master] backport CVE-2021-36755 | vulgraph | a | close as addressed (in 15.0.8) |
| #8493 | tests for week-to-week dates | bniels707 | c | needs maintainer judgement (tests fail per author) |
| **#8419** | tests for Loop push and websockets | je-l | c | **carried into 15.0.9** (decided) |
| #8405 | show device timezone | ryceg | c | consider for a cut; retarget from `wip/next-release` |
| #8402 | CSV exports | kelseyhuss | c | consider for a cut (review points open) |
| #8392 | show seconds | KelvinKramp | c | close as a duplicate of #8555 |
| #8385 | wake-lock toggle | earldouglas | c | consider for a cut |
| #8381 | Swagger: missing v1 endpoints | arfaomar | c | consider for a cut (review points open) |
| #8366 | 2025 reports | dburren | c | consider for a cut |
| #8348 | remove Moment | ryceg | b | needs maintainer judgement: post the Moment verdict |
| #8261 | multi-insulin API | gruoner | c | consider for a cut; ask for tests |
| #8236 | clock view colour option | JaredDRobbins | c | consider for a cut, or close as stale |
| #8084 | replace Google Fonts | gardenrobot | c | consider for a cut |
| #8083 | heart-rate storage | buessow | c | consider for a cut, with AAPS |
| #7887 | clock views: date, plugins, weather | tynbendad | c | close as superseded by #8537 |
| #7875 | Playwright and webpack experiments | bewest | b | close as superseded by #8605's Playwright suite |
| #7791 | remote commands (draft) | gestrich | c | needs maintainer judgement (Loop coordination) |
| #7656 | deploy to Azure button | charris-msft | c | close as stale |
| #7342 | glucose pentagon plugin | jgr-lab | c | close as stale, or consider for a cut |
| #7221 | disable Pushover emergency priority | hanoii | c | consider for a cut; retarget; default stays on |
| connect #81 | start 0.1.1 development | bewest | b | leave: standing dev → main PR |
| connect #52 | API v3 for the nightscout source | psonnera | a (partial) + c | needs maintainer judgement; ask for a v3-only PR |
| connect #54 | MiniMed OAuth2 PKCE, Mongo tokens | LeFrenchGuy | c | needs maintainer judgement (token storage) |

Counts: cgm-remote-monitor a 1, b 7, c 31; nightscout-connect a (partial) 1, b 1, c 1. Merge
results against `dev` and #8758 were identical for every PR.

### 4.1 Credit: no null merge is warranted

- **#8498** is a cherry-pick of the maintainer's own unmerged 2021 commit, opened by an automated
  backport account. The escaping it adds reached 15.0.8 by another route (`textAsHtml` in
  `lib/client/adminnotifiesclient.js`, from #8591/#8592), so there is no outside author to
  credit. It also targets `master`, so a null merge into `dev` would not show as merged until the
  release merge.
- **connector #52** still carries API v3 reads from the Nightscout source, the bridge-variable
  compatibility layer, the Docker/dotenv changes, failed-session propagation and the LibreLinkUp
  rework, none of which is on connector `dev`. A null merge would mark those as merged. Three of
  its fixes are on `dev` by other routes (the aligned-delay guard, devicestatus from a Nightscout
  source, opt-in debug logging). Whether the aligned-delay guard (connector `bbb73c6`) drew on #52
  could not be told from the code; if it did, a `Co-authored-by` on a future commit or a
  release-notes acknowledgement is the credit available.
- The three carried PRs are credited by a normal merge.

### 4.2 The carried PRs

- **#8568**: 0 behind `dev`, CI green, merges cleanly with `dev` and #8758; 20 new tests, 79
  passing in the wider set. It clears the marker for the released AAPS shape (2147483647 min) and
  not the AAPS-dev shape (10-year duration, `originalDuration` 0). The day-to-day report draws the
  bar from `duration` directly and is not covered. Defect facts:
  [BF-114](../../30-design/remedial/nightscout-backfix-register.md#bf-114--an-aaps-open-ended-loop-disable-keeps-alerts-off-after-the-loop-is-back-on).
- **#8419**: tests only; merges cleanly; `loopnotifications.test.js` 9 passing on `dev` with it merged.
- **#8530**: one line in `views/index.html`; merges cleanly; the client keeps about two days of
  entries, so a 48-hour focus shows the whole window. No tests.

**#8568.** DRAFT:

> Thank you for this, and for the thorough tests. We confirmed the behaviour: when AAPS turns the loop off with no end time and then back on, Nightscout keeps treating the loop as offline, and that also holds back the "not looping" and pump alerts until the old record ages out. Your change fixes that for current AAPS releases. The next AAPS version sends an open-ended disable as a ten-year duration with `originalDuration: 0`, which this check doesn't catch yet. Would you be willing to extend `isInfiniteDisabledLoop` to cover that shape, and add a test that the OpenAPS alert level comes back after re-enabling? We'd like to include this in the next patch release.

**#8419.** DRAFT:

> Thanks for your patience and for folding the two APNs test files together. The suite passes against current `dev`, and we'll include it in the next patch release.

**#8530.** DRAFT:

> Thanks. This is small and self-contained, and we've brought it up to date with `dev`. We'll include it in the next patch release.

### 4.3 #8522

The PR wraps every profile read in the Bolus Wizard Preview and profile editor in a mg/dL → display
conversion. Profiles keep their own `units`, and Loop and AAPS upload mmol profiles, so an mmol
profile is converted a second time. Measured on `dev` with it merged: `boluswizardpreview.test.js`
2 failures (both mmol low cases), `profileeditor*.test.js` 11; 16 passing and 13 failing against 29
passing on `dev` alone. A mg/dL profile shown on an mmol site may still be a real problem; a fix
would have to follow the profile's `units`.

**#8522.** DRAFT:

> Thank you for looking into this. Unit handling here matters. Profiles in Nightscout keep their own `units`, and many are stored in mmol/L, so converting every profile value from mg/dL changes the results for those sites: with this change, two existing bolus-wizard mmol tests and several profile-editor tests fail. If you saw wrong values, could you share the profile `units` and the display setting you were using? A fix that respects the profile's own units would be very welcome.

### 4.4 Mis-targeted PRs

`master` receives only the `dev` → `master` release merge, and `wip/next-release` is no longer used
(last commit 2026-05-07), so none of these can merge as filed.

| base | PRs |
|---|---|
| `master` | #8560, #8542, #8541, #8540, #8537, #8498, #7887, #7656, #7221 (besides the release PR #8598) |
| `wip/next-release` | #8405 |

Their drafts ask for a retarget to `dev` (appendix A, and §4.5 for #8541, #8498, #7887, #7656).

### 4.5 Other drafts that need a maintainer call

**#8498.** DRAFT:

> Thanks for flagging this. The admin-notification escaping this backport adds is already in 15.0.8 by a different route: title, message and the additional-info line all go through a text escaper, and the "readable by world" notice no longer carries HTML. Closing as already addressed.

**connector #52.** DRAFT:

> Thank you for all the work here. Since your last update, several of the same fixes have landed on `dev` by other routes: the aligned-delay guard, reading devicestatus from a Nightscout source, and opt-in debug logging. What's left and new is API v3 support for the Nightscout source, plus the bridge-variable compatibility layer. Would you be open to splitting those into smaller PRs on top of current `dev`? That would make them much easier to review and test.

**connector #54.** DRAFT:

> Thank you. MiniMed login is an area we know needs attention. `dev` has moved on a lot (logging in particular), so this needs a rebase. We'd also like to talk through where tokens are stored before merging. Could you rebase onto current `dev`?

**#8348.** DRAFT:

> Thank you for the work here and your patience. For now we've decided to keep a trimmed-down Moment, and to look again at replacing it when the runtime modernisation reaches that stage. At that point Temporal will be considered alongside Day.js. This PR can't merge in its current form after that work lands, so we'll close it for now. Your comparison has shaped that decision, and we'll link it from the plan.

**#8541.** DRAFT:

> Thanks for isolating these. Dropping older browsers and changing the client transport are policy decisions we'd like to make deliberately for a minor release. Could you retarget to `dev`?

**#8533.** DRAFT:

> Thanks. This needs a rebase on `dev`, since `treatmenttocurve.js` has changed. We'd also like to understand which uploaders send glucose without `units`. Guessing a unit from the value is a behaviour change we want to scope carefully, so examples, with identifying details removed, would help.

**#8493.** DRAFT:

> Thanks for these tests. You mentioned they fail because of how the request range uses the profile timezone. That sounds like it may be a real bug. Could you rebase on `dev` and note which cases fail? We'd like to look at that separately.

**#7791.** DRAFT:

> Thanks for this design. The push library upgrade discussed here has since been done, and `lib/server/loop.js` changed in the upcoming release. Is this still something you, or the Loop team, want to pursue? If so, a rebase on `dev` would be the next step.

**#8392.** DRAFT:

> Thank you for starting on this. #8555 builds on your approach for the same issue and is current with `dev`, so we'll carry the feature there and close this one. Your earlier work is appreciated.

**#7887.** DRAFT:

> Closing in favour of your newer #8537, which carries this work forward for v15. Thank you!

**#7875.** DRAFT:

> Closing: a working Playwright browser suite is now part of the modernization work in #8605.

**#7656.** DRAFT:

> Thanks. This has drifted from the current README and deploy files, and targets `master`. If you're still interested, please open a fresh PR against `dev`. Closing for now.

**#7342.** DRAFT:

> Thank you for this. It has been open a long time without review, and the same metric is available in Nightscout Reporter. If you'd still like it in Nightscout, a rebase with tests would help it along.

## 5. Defects to file

Placeholders are substituted with register ids from BF-118 up when each entry is filed. Every
entry below is `open` on both 15.0.8 `92d08342` and `dev` `4f705217`.

| issue | id | class | mechanism | provenance | checkable with |
|---|---|---|---|---|---|
| #5622 | BF-119 | safety: alarm | `PUMP_WARN_ON_SUSPEND` never raises a warning: `updateStatus` reads the preference from the wrong object and writes `result.status.level` before `result.status` exists (`lib/plugins/pump.js:286-298`); both must be fixed together | reproduced 2026-09-25 | `tests/pump.test.js` pattern; small |
| #7036 | BF-120 | safety: stale data shown as current | the clock view recomputes reading age and stale styling only after a successful fetch, so offline it keeps showing the last value and its last age (`lib/client/clock-client.js`) | reproduced 2026-09-25 | `tests/clock-client.test.js` with fake timers and a failing fetch; small |
| #8185 | BF-121 | safety-relevant data loss (carbs) | a v1 treatment upsert keys on `created_at` + `eventType` unless `identifier` or `_id` is present, so two carb entries at the same minute collapse; Loop sends `syncIdentifier`, not `identifier` (`lib/server/treatments.js:352-377`) | reproduced 2026-09-25 | `tests/api.treatments*` pattern; medium (API semantics) |
| #8244 | BF-122 | dosing-relevant data sync | v1 writes store no `srvModified`, so API v3 history, which AAPS polls after its first load, never returns them; v1 writes also emit no v3 storage-socket events | reproduced 2026-09-25 | API v3 history test; medium |
| #7771 | BF-123 | dosing-relevant display | a Profile Switch `percentage` is applied only with `CircadianPercentageProfile`, which AAPS never sends; AAPS uploads an unscaled `profileJson`, so the displayed scheduled basal ignores the percentage (`lib/profilefunctions.js:124-133`) | reproduced 2026-09-25 | `profilefunctions` unit test; small-medium |
| #5940 | BF-124 | dosing-relevant display | the treatment tooltip converts BG by the profile's units, ignoring the treatment's own `units`, so an mmol entry on a mg/dL-profile site is divided by 18 again (`lib/client/renderer.js:641-647`); chart position is correct | reproduced 2026-09-25 | client tooltip test; small |
| #8104 | BF-125 | alarm delivery | IFTTT event names use the translated level label, so applets keyed on the English names never fire in other languages; a failed maker call keeps a 30 s repeat key instead of 15 min (`lib/server/pushnotify.js:126-145`) | reproduced 2026-09-25 | `tests/maker.test.js` / `tests/pushnotify.test.js` with a language set; small |
| #7110 | BF-126 | availability | a subject stored without a `name` ends the process when subjects reload, and at every boot until the row is removed (`lib/authorization/storage.js:256`); a role without `name` would fail the same way (read) | reproduced 2026-09-25 | `tests/authsubjects.test.js` pattern; small |
| #7377 | BF-127 | follower view empty | clock views read a token only from their own URL and the Clock menu links carry none, so under `denied` the clock draws nothing | reproduced 2026-09-25 | clock client test; small |
| #6220 | BF-128 | watch display correctness | `/pebble` forces mmol when asked but never forces mg/dL, so on an mmol site a mg/dL request gets its delta in mmol (`lib/server/pebble.js:143-148`) | reproduced 2026-09-25 | pebble API test; tiny |
| #7729 | BF-118 | safety: alarm | threshold conversion from mmol is keyed on `BG_HIGH < 50` alone (`lib/settings.js:291`), so an mmol target pair with default `BG_HIGH`/`BG_LOW` is kept as mg/dL and `BG_LOW` is rewritten to 2.9 mg/dL: no low alarm can fire, and every reading, 45 mg/dL included, raises "Warning HIGH" | reproduced 2026-09-25 | `tests/settings.test.js` or the threshold-rewrite gate with a partial-mmol set; small, but the same decision as BF-67/BF-86 |

**Register matches.**

| issue | register entry | relation |
|---|---|---|
| #7729 | [BF-67](../../30-design/remedial/nightscout-backfix-register.md#bf-67--an-alarm-threshold-is-quietly-changed-and-only-the-server-log-says-so), [BF-86](../../30-design/remedial/nightscout-backfix-register.md#bf-86--an-mmoll-low-threshold-on-a-mgdl-site-is-kept-as-is-so-the-low-alarm-never-fires) | same family, new variant (the `BG_HIGH`-only trigger is in neither entry) |
| #8238, #8147 | [BF-94](../../30-design/remedial/nightscout-backfix-register.md#bf-94--a-kept-profile-instance-can-return-a-temp-basal-that-has-been-replaced) | public reports of the symptom; probable, since the browser was not measured |
| #7540 | CAP-01 (sub-path mounting) | the same capability gap |

## 6. Open issues by status

| status | cgm-remote-monitor | nightscout-connect |
|---|---:|---:|
| fixed in `dev` (merged, ships with 15.0.9) | 5 | 2 |
| matches the register | 4 | 0 |
| not addressed | 19 | 1 |
| needs info | 10 | 4 |
| not a defect | 4 | 1 |
| stale | 1 | 0 |
| question / support | 5 | 1 |
| feature | 53 | 3 |
| tracking | 1 | 0 |
| **total** | **102** | **12** |

No open issue is fixed only by #8758.

### 6.1 cgm-remote-monitor (102), newest activity first

| # | problem | status | recommendation |
|---|---|---|---|
| #8714 | debug output fills hosted log quotas after 15.0.8 | fixed in dev | §2 |
| #8328 | Node and dependency tracking | tracking | §2; keep open |
| #8584 | Reports basal graph cut off after a switch hour | fixed in dev | §2 |
| #7051 | Loop pill hover details in Day to Day | feature | keep open |
| #8192 | food editor list not scrollable on phones | not addressed | later cut; not verified |
| #8079 | self-host fonts instead of Google Fonts | feature | review #8084 |
| #8420 | activity collection in API v3 | feature | keep open |
| #8048 | clock view option to show seconds | feature | keep open (#8555) |
| #5742 | custom webhook for alarm events | feature | keep open (#8580) |
| #8535 | weekly/monthly insulin report | feature | keep open |
| #7729 | mmol target lines without BG_HIGH/BG_LOW read as mg/dL | matches register | §5 |
| #6236 | Loopalyzer gaps | not addressed | later cut; reporter reproduced, not here |
| #8368 | unauthenticated health-check endpoint | feature | keep open |
| #8370 | store and report HbA1c | feature | keep open |
| #8371 | bulk operations in API v3 | feature | keep open |
| #5622 | suspended-pump warning never raised | not addressed | §5 |
| #6916 | extra OpenAPS/AAPS pill details | feature | keep open, or close as done for COB |
| #8194 | snooze does not hold | not a defect | explain single-instance requirement; ask hosting setup |
| #6717 | metric for daily manual interventions | feature | keep open |
| #8403 | main clock in the uploader's time zone | feature | keep open |
| #8147 | temp basal history vanishes until restart | matches register | §5 (BF-94) |
| #8279 | FerretDB compatibility | question | §3 |
| #7540 | BASE_URL sub-path | matches register | CAP-01 |
| #7999 | larger glucose value and dots | feature | keep open |
| #8167 | Cosmos DB errors on API v3 | not a defect | §3 |
| #8072 | report readability | feature | §2; keep open |
| #8060 | Alexa routines | feature | keep open or close |
| #7638 | custom range colours | feature | keep open |
| #8129 | OpenAPS pill disappears between readings | needs info | reproduction on 15.0.8+ |
| #8087 | temp basal net insulin in IOB | feature | keep open or close |
| #8097 | AAPS full sync writes partial data | stale | §3 |
| #8105 | ALARM_*_MINS and IFTTT repeats | not a defect | §3 |
| #8130 | pump pill reservoir jumps | needs info | devicestatus sample |
| #8174 | CVGA report | feature | keep open |
| #8156 | Loopalyzer blank until cache cleared | not addressed | needs info / later cut |
| #7110 | subject without a name crashes every boot | not addressed | §5 |
| #5668 | fill temp basal rate from percent | feature | keep open |
| #5573 | target band in Day to Day | feature | keep open |
| #7199 | admin tool for duplicate readings | feature | keep open |
| #5830 | database export from the web UI | feature | keep open |
| #6061 | Grafana endpoints | feature | keep open |
| #5940 | mmol BG in tooltip divided by 18 | not addressed | §5 |
| #6486 | glucose value overlaps menu on small phones | not addressed | later cut; not verified |
| #6868 | long title pushes menu icons off screen | not addressed | later cut; not verified |
| #6870 | more Loop profile fields in Profile report | feature | keep open |
| #7036 | clock view shows an old reading as fresh | not addressed | §5 |
| #7096 | CGP diagram in reports | feature | keep open |
| #7071 | string-shaped `find` answers 500 instead of 400 | not addressed | later cut; reproduced |
| #7282 | IOB scale in Day to Day | feature | keep open |
| #7278 | more report date presets | feature | keep open |
| #7279 | responsive report graphs | feature | keep open |
| #7280 | prediction colours in Day to Day | feature | keep open |
| #7053 | five-band time in range | feature | keep open |
| #7040 | sanity limits on implausible treatments | feature | keep open |
| #7191 | LibreView data source | feature | keep open |
| #7064 | CGM accuracy report | feature | keep open |
| #7305 | COB missing from Day to Day | needs info | uploader and sample on 15.0.8+ |
| #7377 | clock views blank with a URL token | not addressed | §5 |
| #7391 | 5-minute data for Libre 3 | feature | keep open |
| #7458 | duplicate records from AAPS 3.0 | needs info | close if no current reproduction |
| #7068 | QR pairing with Loop | feature | keep open |
| #7195 | kcal on carb treatments | feature | keep open |
| #6066 | Treatments report cannot filter by event type | fixed in dev | §2 |
| #8238 | basal pill keeps a cancelled zero temp | matches register | §5 (BF-94) |
| #8315 | Bolus Wizard quick pick shows only (none) | fixed in dev | §2 |
| #7649 | pluggable storage / SQLite | question | discussion or close |
| #7698 | prediction-lines checkbox ignores server setting | not addressed | later cut; not verified |
| #7669 | Day to Day labels shifted by a day | needs info | profile time zone |
| #7659 | reading counts differ by one between reports | needs info | re-test on 15.0.9 (#8588) |
| #7771 | displayed basal ignores AAPS switch percentage | not addressed | §5 |
| #7847 | remove noisy CGM readings | feature | keep open |
| #8104 | IFTTT event names translated, repeat every minute | not addressed | §5 |
| #8185 | same-time carb entries collapse | not addressed | §5 |
| #8223 | duration events clipped at midnight in Day to Day | not addressed | later cut; not verified |
| #8358 | browser support targets | question | decide with the modernisation cuts |
| #7324 | insulin age pill never red | fixed in dev | §2 |
| #7161 | in-range IFTTT event | feature | keep open |
| #7350 | carbs with duration | needs info | current AAPS shape |
| #6774 | xDrip injection types | feature | keep open |
| #6882 | cleaner report charts | feature | keep open |
| #5635 | exercise, heart rate and sleep data | feature | keep open |
| #6220 | /pebble delta units | not addressed | §5 |
| #7824 | structured logging | feature | keep open |
| #7506 | exclude days by event type in reports | feature | keep open |
| #7852 | IFTTT triggers on both crossings | question | answer; keep as feature |
| #7868 | TDD statistics | feature | keep open |
| #7879 | basal injection logging | feature | keep open |
| #8074 | TypeScript migration interest | question | §3 |
| #8106 | PNG/JPG image API | feature | keep open |
| #7835 | weight and blood pressure events | feature | keep open |
| #8186 | clock view reading age out of sync | needs info | console output; may share #7036's mechanism |
| #8088 | xDrip predictive simulation | feature | keep open |
| #8244 | v1 writes absent from v3 history | not addressed | §5 |
| #8225 | crash at start after the database was recreated | needs info | crash log from a current version |
| #6676 | horizontal scroll with mouse wheel | feature | keep open |
| #8177 | remove a calibration from the UI | feature | keep open |
| #8075 | profile.json ignores find | not a defect | §3 |
| #7895 | upper and lower graph disagree | needs info | current reproduction |
| #7275 | honour NO_COLOR in logs | feature | keep open |
| #6807 | hourly insulin distribution | feature | keep open |
| #6028 | Loopalyzer IOB missing some days | not addressed | needs info |
| #6191 | IFTTT events for low battery | feature | keep open |

### 6.2 nightscout-connect (12)

| # | problem | status | recommendation |
|---|---|---|---|
| #14 | Glooko EU accounts cannot log in | fixed in dev (0.1.0) | §2; keep open pending reporters |
| #11 | Glooko meal bolus imported as two records | not addressed | keep open (needs a source identity rule) |
| #45 | more Omnipod 5 data from Glooko | feature | keep open (partly delivered by #71) |
| #43 | Dexcom follower with two profiles returns one | needs info | re-test on 0.1.0 |
| #7 | vendor account status to followers | feature | keep open |
| #33 | EU Dexcom Share returns no data | needs info | re-test on 0.1.0 |
| #42 | official Dexcom API | question | keep as discussion |
| #41 | CareLink configured, no data | needs info | logs on 0.1.0 |
| #40 | Dexcom Japan server | feature | later (small; `CONNECT_SHARE_SERVER` works) |
| #25 | CareLink follower login blocked by reCAPTCHA | needs info | not verified on 0.1.0 |
| #24 | CareLink polls on five-minute marks | not a defect | §3 |
| #21 | CareLink "no reading" stored as 0 | fixed in dev (0.1.0) | §2 |

## 7. Method and limits

**PRs.** Every head was fetched from `pull/N/head` (39 of 39 and 3 of 3). Files were listed against
the PR's merge-base with `dev`; conflicts come from `git merge-tree --write-tree` against `dev` and
against #8758; history from `git log` over `master..dev` and `-S`; programme relations from a grep
of the register, the 15.0.9 contents, the queue and the 2026-09-14 readiness document. Tests were
run in scratch worktrees on `dev` with the PR merged, against a fresh MongoDB 7 container, only for
#8568, #8522, #8501, #8419, #8580, #8555 and #8526; every other PR was not run. The AAPS wire shapes
for #8568 come from the AndroidAPS corpus at `7e1d537d49` (2026-09-23).

**Issues.** Lists came from `gh issue list --state open` on 2026-09-25. **Reproduced** means run on
both refs in scratch worktrees, either against a booted server with a throwaway MongoDB 7.0 or in
an in-process mocha harness with a positive control, with the same result on both unless stated.
**Read-derived** means from the code only; **static analysis** means a grep of the client corpora.
"Fixed in dev" rows cite the merge and, where stated, a `dev` test that fails when copied onto the
15.0.8 tree; the reasons those copied tests fail on 15.0.8 were not inspected one by one.

**Limits.**

- Nothing was written to GitHub: no comments, labels, closes, merges or pushes.
- Every read-derived claim is a hypothesis until reproduced, including the mechanisms and fixes for
  #7036, #5940, #8104, #7377, #6220 and #7771.
- The BF-94 matches (#8238, #8147) are probable: the browser was not measured.
- #8584's link to #8701 is probable, not confirmed against the reporter's data. #6066's fix was not
  measured here. Connector #21's fix was read, not reproduced.
- For #8244 the AAPS side was not run.
- Issue bodies were read for mechanism only; no names, addresses, site URLs or readings from them
  appear here.

## Appendix A. Drafts for PRs to consider for a cut

**#8580.** DRAFT:

> Thank you, and welcome! This is a feature rather than a fix, so it won't be in the upcoming patch release. We'll review it for the following minor release. Outbound webhooks also need a security review of how destinations are configured.

**#8501.** DRAFT:

> Thank you. The multi-instance diagnosis is right, and the tests are appreciated. Alarm acknowledgement is being redesigned alongside some wider changes to how alarms are evaluated, so we'd like to land this in a later release rather than the upcoming patch, and make sure the two designs agree. We'll follow up here when that work is ready for comparison.

**#8560.** DRAFT:

> Thanks! Could you retarget this to `dev`? `master` only receives release merges. It's a feature, so it's queued for the next minor release rather than the patch.

**#8385.** DRAFT:

> Thanks for updating the icon. This is queued for review in the next minor release.

**#8555.** DRAFT:

> Thanks! This is queued for the next minor release.

**#8542.** DRAFT:

> Thanks. The D3 7 upgrade this depended on has since landed in `dev` by another route, so this can be rebased onto `dev` (not `master`) whenever you're ready. It would then come in a minor release.

**#8540.** DRAFT:

> Thanks! Please retarget to `dev`. This is queued for the next minor release.

**#8537.** DRAFT:

> Thanks for refactoring this. Could you rebase onto `dev` (not `master`)? `clock-client.js` has a recent fix you'll need to merge around.

**#8236.** DRAFT:

> Thanks. This needs a rebase on `dev`, since the clock files have changed. Are you still interested in carrying it forward?

**#8531.** DRAFT:

> Thanks. The chart code moved to D3 7 recently, so this needs a rebase (renderer tests conflict). It's queued for a minor release.

**#8526.** DRAFT:

> Thanks. This is queued for the next minor release.

**#8405.** DRAFT:

> Thanks. `wip/next-release` is no longer used. Could you retarget to `dev` and rebase? `clock-client.js` has changed.

**#8402.** DRAFT:

> Thanks. The v1 API files this touches changed in the upcoming release, so it will need a rebase on `dev`, plus the review points from May, before it can be considered for a minor release.

**#8381.** DRAFT:

> Thanks. Both swagger files have changed on `dev`, so this needs a rebase and the fixes from the May review.

**#8366.** DRAFT:

> Thanks. We'd like to review this for a minor release after a rebase on `dev`.

**#8261.** DRAFT:

> Thanks. Could you add API tests and point us at the client builds that use this endpoint?

**#8084.** DRAFT:

> Thanks, and sorry for the long wait. Several people have asked for this for privacy reasons. It needs a rebase on `dev` (the CSP in `app.js` changed). We'd like to consider it for the next minor release.

**#8083.** DRAFT:

> Thanks. This needs a rebase on `dev`. We'd like to coordinate with AAPS on the upload side before merging.

**#7221.** DRAFT:

> Thanks. This is still relevant, since WARN and URGENT still go out as emergency priority. Could you retarget to `dev`? Pushover delivery is being reworked, so this may need a small rebase. We'd consider it for a minor release with the default unchanged.

No draft: #8758, #8605, #8598, connector #81 (leave), #8730 (bot PR), #8564 (maintainer's own WIP).
