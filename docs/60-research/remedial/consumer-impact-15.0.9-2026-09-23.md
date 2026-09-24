# What 15.0.9 changes for the apps that talk to Nightscout

*Contributor-facing. Snapshot, 2026-09-23, against cgm-remote-monitor `origin/master`
`92d08342` (tag `15.0.8`, what operators run), `origin/dev` `ddd9b600`, and the 15.0.9 candidate:
`dev` merged with #8754 (`ef3404fd`) and #8758 (`6d120fa2`), tree `2ce67b27` (local commit
`1067e668`). Current as the consumer survey, except §2.1 and §2.2: those were decided 2026-09-24
(maintainer, `RT-COUNT-COMPAT`) and merged into `dev` as #8761, not released. A leading whole number
is read as 15.0.8 did, so oref0's `1?…` reads 1; a read with `count=0` returns everything in the
window when the find bounds a date field from both sides, and the endpoint default otherwise, with a
deprecation warning; each tolerance has its own setting, on by default. The fix reproduces 15.0.8 for
both clients in this lab. Current state of each item: `queue/work-queue.yaml`. Defect facts:
[backfix register](../../30-design/remedial/nightscout-backfix-register.md). Nothing here is
medical advice.*

**Method, and what kind of evidence each claim is.**

1. **Change inventory**, read-derived: every one of the 59 first-parent merges from 15.0.8 to `dev`,
   plus #8754 and #8758, classified, and 67 consumer-visible changes (C1–C67), each with its
   contract before and after and code anchors on both refs:
   [change-inventory.md](../../../reports/consumer-impact-15.0.9/change-inventory.md).
2. **Client usage maps**, read-derived: 40 client repositories at their upstream tips (the
   workspace lockfile as of `3a41a437`), each checked against the same 15 surfaces, with a
   positive control for every "not found":
   [clients/](../../../reports/consumer-impact-15.0.9/clients/).
3. **Consumer-replay lab**, reproduced: 13 probes sending the exact request shapes those clients
   send to all three builds side by side (mongod 7.0.43, Node 22.23.2), each with its well-formed
   control and a liveness check in the same run:
   [lab-results.md](../../../reports/consumer-impact-15.0.9/lab-results.md).

The lab is what grades severity here. Three findings that read as regressions from source did
not reproduce (§4), and one claim about 15.0.8's behaviour in the inventory was wrong (C55).

## 1. The answer

**No mainstream closed loop or uploader stops sending glucose or treatments on 15.0.9.** Loop,
Trio, AndroidAPS, xDrip, xDrip4iOS, LoopFollow, LoopCaregiver, nightguard, the connector's
sources and the vendor bridges send only `count` values, filter operators and id forms the
candidate accepts. What changes, in order of how much a person would notice:

| # | who | what changes on 15.0.9 | evidence | where it changes | tracked |
|---|---|---|---|---|---|
| 1 | **oref0 / OpenAPS rigs** | the rig's "latest treatment" lookup gets HTTP 400, so every loop re-uploads its last 24 h of treatments (57 writes instead of 1 in the lab). **No duplicates are stored.** A treatment edited in Nightscout within that 24 h is overwritten on the next loop | reproduced | `dev` (#8738/#8748) | `RT-COUNT-COMPAT` |
| 2 | **GluPredKit** | asks for `count=0` meaning "everything in this window" and now gets an empty list for entries, treatments and profiles, so its dataset build fails | reproduced | `dev` (#8748) | `RT-COUNT-COMPAT` |
| 3 | **follower and uploader apps that snooze alarms over the `/alarm` socket** (AndroidAPS v3 on master and dev; any client using an access token) | a snooze is honoured only for a token with `notifications:*:ack`, which among built-in roles only `admin` has. Anything else is dropped with no error, on the default `readable` setting too. Alarms still arrive for any token that can read | reproduced | `dev` (#8745) | release notes, security item 2 |
| 4 | **tools that delete or read by a list of more than 20 ids** | a `find[_id][$in]` list of 21–1000 values now works. On 15.0.8 it failed and deleted nothing, so **bulk deletes that silently did nothing now delete** | reproduced | `dev` (Express 4.22.2, #8571) | release notes (not yet stated) |
| 5 | **xDrip4iOS** | its bulk delete of readings by a list of timestamps answers 500 and deletes nothing, on every build including 15.0.8 | reproduced | none: open everywhere | `BFQ-108` (BF-108) |
| 6 | **any tool filtering activity by numeric `date`** | the filter answers 200 with no records. No client in the corpus does this | reproduced | `dev` (#8737) | `BFQ-106` (BF-106) |
| 7 | **xDrip, Loop, xDrip4iOS, the connector, tconnectsync** on sites with records stored by 15.0.6 or earlier, or copied from another site | an edit by `_id` updates the record instead of adding a copy, a delete by `_id` removes it, a lookup by `_id` finds it, and an entry re-sent with a different `_id` answers 200 instead of 500 | reproduced (improvement) | candidate (#8758) | `BFQ-102` |
| 8 | **Nightscout-served COB readers** (nightguard via `/api/v2/properties`) | COB now also appears without a full profile, and `treatmentCOB` is a number | read-derived | `dev` (#8587) | — |
| 9 | **any client, on 15.0.8** | one kind of failed treatment search ends the Nightscout process; 15.0.9 answers it with an error | reproduced | `dev` (#8697) | `BFQ-107` (BF-107) |

Row 9 is the fix operators most need and is filed only now: issue #8675 and PR #8697 predate this
survey, but the register had no id for it. The triggering request is withheld here because the
defect is live on the shipping release.

## 2. The findings that need a decision before the tag

### 2.1 oref0 sends a malformed `count`

`oref0-ns-loop.sh:242` calls `nightscout latest-openaps-treatment`, which runs
`ns-get 'treatments.json?find[enteredBy]=…&count=1' HOST SECRET`. `ns-get.sh` takes its third
argument as a query and appends `'?'${QUERY}`, so `count` arrives as `1?<credential>` (hashed-secret
mode) or `1?token=<t>` (token mode). The same code is on oref0 `dev` `d219baf9` and `master`
`88cf032a` (`bin/nightscout.sh:164`, `bin/ns-get.sh:9,29-35`). The defect is in the client, and on
15.0.8 it also puts the credential in a URL, where proxy and access logs keep it.

| | 15.0.8 | `dev` | candidate |
|---|---|---|---|
| oref0's request, either auth mode, `readable` or `denied` | 200, the latest treatment | **400** "Bad count" | **400** |
| control: plain `count=1` | 200 | 200 | 200 |
| treatments the rig then re-uploads per loop | 1 | **57** | **57** |
| records stored after three posts of that batch | 137 | 137 | 137 |

The upsert on `created_at` plus `eventType` is idempotent, so insulin and carbs are not counted
twice. A Nightscout-side edit to one of those treatments (a note added, for example) is replaced
by the rig's copy on the next loop; that replace-on-repost exists on 15.0.8 too, but there it
touches one record per loop. The options are in the
[versioning policy §3.2](../../30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md)
and in `RT-COUNT-COMPAT`: ship the rule as a declared correction naming the client, read a leading
whole number the way 15.0.8 did, or number the release as a major. Independently, oref0 should be
told; the fix there is one line in `nightscout.sh`.

### 2.2 GluPredKit sends `count=0`

`glupredkit/parsers/nightscout.py:66-91` sends `count: 0` with a date window, meaning "no limit".
Over a 50-hour window, 15.0.8 returned 1 profile, 137 treatments and 576 entries; `dev` and the
candidate return an empty list for all three, and a `count=100000` control returns the full set
everywhere. Its entries and treatments calls go through `python-nightscout`, which is not in the
corpus; the request shapes replayed are recalled from that library. Same decision as §2.1.

### 2.3 Alarm snoozes over the socket need `notifications:*:ack`

On 15.0.8 any valid access token could silence an alarm for everyone over `/alarm`, and on a
`denied` site a socket that never authenticated received alarms (both part of the published
socket advisories). On `dev` and the candidate, alarms go only to subjects that can read, and a
snooze is honoured only with `notifications:*:ack`; the refusal is written to the server log and
nothing is sent back. Measured: only the `admin` token's snooze cleared the alarm, under both
`readable` and `denied`.

The client-side consequence depends on which role each app's setup guide tells people to give
its token, which lives in those projects' documentation, not in the corpus. AndroidAPS v3 on
master (`NSClientV3Service.kt:184-199,343-346`) and on dev (`NsConnectHandler.kt:78-89`) subscribes
and snoozes this way. AndroidAPS v1 (3.4.x only) snoozes on the main namespace, which no Nightscout
version has ever handled, so it is unaffected. The release notes' security item 2 should say that a
token without that permission can no longer silence alarms, and that the app is not told.

### 2.4 Bulk deletes that did nothing now delete

Express 4.22.1 on 15.0.8 parsed a query-string array of more than 20 values as an object, so
`$in`, `$nin` and `$or` lists over 20 failed. Express 4.22.2 on `dev` raises the limit to 1000.
Measured with `DELETE /api/v1/treatments?find[_id][$in][]=…`: 5 and 20 ids delete on every build;
21 and 50 ids answer 500 and delete nothing on 15.0.8, and delete every match on `dev` and the
candidate. No client in the corpus sends a treatments `_id` list of that size. The release notes
say the query-string library update makes "no difference for any request a known app sends"; that
holds between `dev` and the candidate, not between 15.0.8 and 15.0.9.

## 3. Defects filed from this survey

- **BF-106**: the schema coercion (BF-03's fix) drops the default `date`/`sgv` conversion for
  `activity`, so a numeric-date filter matches nothing. 7 records on 15.0.8, 0 on `dev` and the
  candidate; `created_at` control 7 on all three. On `dev` only.
- **BF-107**: a failed treatments query ends the 15.0.8 process. Merged via #8697.
- **BF-108**: a list of two or more timestamps under the date field throws in `enforceDateFilter`
  and answers 500; xDrip4iOS's bulk delete of readings sends exactly that. Open on every build.

## 4. Read as a regression, not reproduced

| finding from source | lab result |
|---|---|
| Loop's override delete by an upper-case UUID `_id` could fail and hang its upload queue | 200 and deleted on every build with `UUID_HANDLING` unset or true. With `UUID_HANDLING=false` it answers 200 and deletes nothing, identically on all three builds |
| Trio's `find[eventType]=Temporary+Target` might stop matching under qs 6.16 | `+` decodes to a space on every build; 12 of 12 records |
| xDrip4iOS reads an empty `find[_id]` answer as "deleted remotely" and might see more of them | the candidate finds every record 15.0.8 finds, plus 24-hex string ids 15.0.8 missed |
| a devicestatus re-post over an ObjectId-stored record goes from "200 with a duplicate" to 500 (inventory C55) | 500 on 15.0.8, `dev` and the candidate alike; no build stored a duplicate |
| xDrip's follower could stop polling devicestatus on a 4xx | 200 on every build |
| LoopFollow's socket login on a `denied` site | `dataUpdate` arrives on every build |

## 5. Per-client summary

S-ids are the surfaces checked (count, operators, numeric comparison, shared reads, auth,
websocket, `_id`, treatment edits, food, profile, COB, query shape, API v3, other, error
handling); each client's file has the full table.

| client | ref read | effect of 15.0.9 |
|---|---|---|
| Loop (LoopWorkspace, NightscoutService, NightscoutKit) | `f841285`, NightscoutKit `4ec9fd1` | none adverse; `_id` round trips unchanged; a PUT onto a legacy string id now updates in place |
| Trio | `dev` `e41c9db3` | none |
| AndroidAPS | `master` `598e2eb3`, `dev` `7e1d537d` | §2.3 (`/alarm` snooze); v1 socket unchanged; v3 limits and paging unaffected |
| xDrip (Android) | `1ed76004` | improvement (#8758 PUT/DELETE by its own hex `_id`) |
| xDrip4iOS | `c268542e` | improvement (`find[_id]`); BF-108 affects its bulk delete on every build |
| LoopFollow | `4a74b781` | none; subject creation fields are within the candidate's allow-list |
| LoopCaregiver | `dev` `2305718` | none; its opt-in remote-commands v2 call targets an endpoint Nightscout does not have (pre-existing) |
| nightguard | `75404bd` | COB from `/api/v2/properties` can differ (§1 row 8) |
| DiaBLE | `e6a909c` | none |
| nightscout-connect (`0.1.0-dev.3`) | `977da8a` | in-process writes skip the HTTP checks; copied records gain from #8758; reader subject fields unaffected |
| oref0 | `dev` `d219baf9` | §2.1 |
| tconnectsync | `7c4b2f4` | improvement in its non-default replace mode |
| cgmsim-lib | `c09f9c0` | a caller-supplied negative or fractional count now gets 400, which the library ignores |
| nightscout-librelink-up, share2nightscout-bridge, minimed-connect-to-nightscout, glooko-nightscout-eu | tips in the lockfile | none |
| GluPredKit | `e5bd635` | §2.2 |
| nightscout-reporter | `518d61f` (the retired AngularDart app) | none in the frozen code; the maintained Angular successor is not in the corpus |
| nightscout-roles-gateway | `replit` `90840ac` | no data-path change; behind a TLS-terminating proxy a wrong `TRUST_PROXY` loops redirects |
| GlycemicGPT, oref-digital-twin, nightscout-cgm-skill | tips in the lockfile | none |
| osaid-keymanager, trio-telemetry, babelbetes, glooko2nightscout, openaps, xdrip-js, GlookoServiceKit | tips in the lockfile | no Nightscout requests (positive controls in each file) |

## 6. nocturne parity

nocturne (`42275c81`) implements the Nightscout API, and its parity suite runs against Nightscout
15.0.3. It already matches the candidate on `count=0` for entries, treatments, devicestatus and
activity, on numeric comparison and on `$exists=false`. It differs on:

| behaviour | candidate | nocturne |
|---|---|---|
| negative `count` | 400 | 200 `[]` |
| profile `count=0` | `[]` | 1 profile |
| unsupported operator | 400 naming it | 200 `[]` |
| `$exists` with an empty or `null` value | "has the value" | "does not have the value" |
| `pipeline` on `/count` | 400 | ignored |
| subject notes on edit | kept | never stored |
| edit with no roles | roles cleared | roles unchanged |
| v3 `limit=0` | 400 | clamped to 1 |

Its two `count=-1` parity tests will fail once the suite moves to 15.0.9. A security question
about its `/alarm` handling is being raised with the project privately.

## 7. Release-note statements the code contradicts

From the inventory's 22 mismatches, the ones an operator or app author would act on wrongly:

1. The #8754 sections (security items 6 and 7, `TRUST_PROXY`, stored user and role fields, notes
   and creation date, plain-text tokens) carry no pending marker, although #8754 is open.
2. Security item 2 does not say that the snooze change applies on `readable` too, needs a
   permission only `admin` has, and is silent (§2.3).
3. The query-string line is false against 15.0.8 (§2.4).
4. The `count` table omits `devicestatus` (10 records on 15.0.8 for `count=0`, now `[]`), a repeated
   `count`, and that every v1 route checks `count`.
5. The COB item overstates the change: 15.0.8 already preferred the looping app's COB when the
   profile allowed it.
6. The #8758 section says nothing changes in the database until a record is edited or deleted; a
   new record posted with its own 24-hex `_id` is now stored as an ObjectId.
7. `TRUST_PROXY=false` is case-sensitive, and a refused value stops the process at start rather
   than showing a start-up page.

The inventory's remaining items concern PR bodies and code comments. All 22 are listed with
anchors in the change inventory's first section.

## 8. What this does not cover

- Clients not in the corpus: the maintained nightscout-reporter (Angular), `python-nightscout`,
  Sugarmate, Spike, and any closed-source app.
- A client's runtime-built filters: the maps read source, which is a lower bound.
- Each app's documented token role, which decides how many people §2.3 reaches.
- The pin to exact connector `0.1.0`; the replay ran against `0.1.0-dev.3`.

## 9. Reproduce

- Gates: `node tools/queue/gates/bf106-activity-date-coercion.js` and
  `node tools/queue/gates/bf108-date-in-list.js` (each with `--ref <ref>`, and each with 15.0.8 or
  a one-value list as its control); `make queue-status ID="RT-COUNT-COMPAT BFQ-106 BFQ-107 BFQ-108"`.
- The lab: three worktrees (`externals/work/crm-6a-replay-{a,b,c}`), one mongod, and a seeded data
  set described in [lab-results.md](../../../reports/consumer-impact-15.0.9/lab-results.md). The
  probe scripts are kept outside version control, because two probes exercise defects live on the
  shipping release.
