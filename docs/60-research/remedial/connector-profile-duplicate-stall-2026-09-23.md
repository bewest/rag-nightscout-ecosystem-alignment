# nightscout-connect: profile duplicate stall fix and reader-subject warning

> **Snapshot: measured 2026-09-23, 14:59–16:36 UTC.** Connector branch `fix/profile-duplicate-stall` at `f924de2`
> (two commits on `fbd4e55` = tag `v0.1.0-dev.2`): `f6359b4` (profile fix) and `f924de2` (reader-subject warning).
> Nightscout `74fc6619` in every lab image, MongoDB 7, Node 22 in the images. Contributor-facing.
>
> Evidence for the maintainer's decision (2026-09-23: fix in the connector, then tag dev.3, then 0.1.0). It is not
> the decision. The defect is §5.1 of the [dev.2 soak](connector-0.1.0-dev.2-soak-2026-09-23.md); the warning
> addresses §5.2 of the same report (BF-98). Register and queue state are not changed here.

Every figure is **reproduced** (run in the lab or the suite) unless marked **read-derived**. All lab data was
synthetic, from the lab writer.

## 1. The defect and its cause

With the default collections, a Nightscout source syncing into a Nightscout sink fails every poll from the second one
on, as long as the source has a profile. Nothing is lost, but the sink runs 20–35 min behind (dev.2 soak §5.1).

Read-derived from the code at `fbd4e55` and Nightscout `74fc6619`:

| Step | Where |
|---|---|
| The source reads **every** profile, with its `_id`, on every poll (`/api/v1/profile.json?count=1000`, no `since`) | `lib/sources/nightscout.js` `fetchProfiles` |
| The sink stores profiles with `insertMany`, so a second insert of the same `_id` fails with E11000 | Nightscout `lib/server/profile.js` `create` |
| Up to `v0.0.13` the internal output swallowed that failure (`.catch(() => known)`). From `808ab1c` (2026-09-21, in `v0.1.0-dev.1` and `v0.1.0-dev.2`), `safePersist` rethrows `Nightscout internal write failed`, and the REST output's `recordingError` throws `Nightscout write failed` | `lib/outputs/internal.js`, `lib/outputs/nightscout.js` |
| The failed frame retries 3 × 10 s, then the loop backs off toward its 30 min cap; `frames_missing` resets only on a successful frame | `lib/machines`, dev.2 soak §5.1 |

`808ab1c`'s rule, that a write that really failed must fail the poll, is kept.

## 2. How the other collections avoid it (read-derived)

| Collection | Source query | Sink storage | What stops a duplicate |
|---|---|---|---|
| entries | `find[dateString][$gt]=<bookmark>` | bulk `updateOne` upsert, by `identifier` or `sysTime`+`type` | source reads only newer records; storage upserts |
| treatments | `find[created_at][$gt]=<bookmark>` | `replaceOne` upsert by `upsertQueryFor` | same |
| devicestatus | `find[created_at][$gt]=<bookmark>` | `insertMany` (no upsert) | the **connector** drops rows not strictly newer than what it knows is stored (`known.devicestatus` in the internal output, `bookmark.devicestatus` in the REST output) |
| profile, Glooko | not a Nightscout source | `insertMany` | the **connector** reads the stored profiles once and drops rows whose `identifier` is stored (`knownProfiles`) |
| profile, Nightscout source | **every profile, every poll** | `insertMany` | nothing, before this fix |

## 3. The fix (commit `f6359b4`)

Profiles now go through the check Glooko profiles already use, in both outputs: read the stored profiles once
(`count: 1000`), and skip a row whose `identifier` **or `_id`** is already stored. Rows actually stored are added to
the set. There is no matching on error codes or error text: every write failure, including a duplicate-key error the
connector did not predict, still fails the poll. After a failed profile write the set is dropped and read again on the
next poll, so a profile another writer stored in between costs one failed poll, not a stall until restart.

### Behaviour this chooses (for the maintainer)

| Case | 0.0.13 | dev.2 | this branch |
|---|---|---|---|
| same profile, same content, every poll | insert fails, error swallowed, poll continues | insert fails, **poll fails** | skipped, poll succeeds |
| **source edits a stored profile** (same `_id`) | never updated (insert fails) | never updated (insert fails, poll fails) | **never updated** (skipped) |
| new profile (new `_id`) | stored, if it sorts before the first duplicate in the ordered `insertMany` (read-derived) | stored in the lab (it sorted first), but the poll still fails | stored |
| profile deleted on the **sink** while the connector runs | re-inserted on the next poll (read-derived) | re-inserted, poll fails | **not re-inserted** until the connector restarts or a profile write fails (the set is cached) |
| sink holds more than 1000 profiles and a source profile matches one outside the newest 1000 | swallowed | poll fails | poll fails (read-derived; same limit as the Glooko path) |

The first three rows are the intent. Row 2 is **not a behaviour change**: an edited profile has never reached the sink.
Starting to overwrite sink profiles (upsert by `_id`, as entries and treatments do) was not done; it would be a
behaviour change and the maintainer's call. Row 4 **is** a small behaviour change against 0.0.13, from caching the set;
re-reading the stored profiles on every poll would remove it at the cost of one more read per poll.

Nightscout's profile editor saves with `PUT` (`save`, same `_id`), so an edit made in the source's editor is the
"edit" row, not the "new" row (read-derived; the lab edit in §5 used the same `PUT`).

## 4. Suite and unit evidence

### 4.1 New tests (`test/profile-duplicate.test.js`, 12 tests)

Both outputs run against a fake store that behaves like Nightscout's ordered `insertMany` with a unique `_id`.
Six cases per output: a second and third poll with the same profile; an already-stored profile after a restart; a new
profile next to a known one; a source edit (same `_id`) leaves the sink copy; storage down on a new-profile write
fails the poll, and the next poll stores it; a duplicate stored by another writer between the check and the insert
fails the poll, and the next poll recovers.

| Tree | Result |
|---|---|
| `fbd4e55` (fix absent) | **0/12 pass.** Internal: `Nightscout internal write failed`, `code: 11000`. REST: `Nightscout write failed`, `code: 'ERR_BAD_RESPONSE'` (the fake returns HTTP 500 as Nightscout does) |
| `f6359b4` | 12/12 |
| break-it 1: the profile write error swallowed (`return []` in both outputs) | 8/12: the two "really fails" tests per output go red, `Missing expected rejection.` |
| break-it 2: the stored set not dropped after a failure | 10/12: the "another writer" test per output goes red on the recovery poll |
| break-it 3: the internal output back to 0.0.13's catch-all (`return known` in `safePersist`) | the internal "really fails" pair go red, and so does the existing `failed storage rejects with a sanitised error and leaves no extra waiter` (`test/stop-cleanup.test.js`) |

### 4.2 Reader-subject warning (commit `f924de2`, 4 tests in `test/nightscout-source.test.js`)

| Tree | Result |
|---|---|
| `f6359b4` (warning absent) | the two trigger tests and the once-only test fail; the "reused subject that can read gives no warning" test passes |
| `f924de2` | 4/4 |
| break-it: per-condition dedupe removed | only the once-only test goes red |

### 4.3 Full suite (`npm test`, `n exec`)

| Node | `fbd4e55` | `f6359b4` | `f924de2` |
|---|---|---|---|
| 20.20.0 | 292/292 | 304/304 | 308/308 |
| 22.23.2 | 292/292 | 304/304 | 308/308 |
| 24.20.0 | 292/292 | 304/304 | 308/308 |

Additive only: +12 then +4, 0 fail, 0 skipped. `log-call-sites` and `privacy-canary` pass unchanged; the new call
site goes through `log.warn`.

### 4.4 LibreLinkUp lab

`npm run test:librelinkup:lab -- fixture` from the branch tree (Node 22.23.2): `ok: true`; mapping 4 readings; REST and
internal replay/restart and incremental all true; embedded plugin boot and restart true. `-- stop` removed its
containers and network.

## 5. Lab soak: profile arm with a same-source control

### 5.1 Setup

| | |
|---|---|
| Source S | Nightscout `74fc6619`, `AUTH_DEFAULT_ROLES=denied`, own MongoDB; the lab writer seeds 60 h (1 profile) and writes live sgv/devicestatus/treatments |
| Proxy | the lab's pass-through, counting proxy; both sinks read S through it |
| **F** | Nightscout `74fc6619` with the connector from `npm pack` of `f924de2`, installed as a `file:` dependency through a regenerated lockfile (`lab.sh build-local`). The lockfile `integrity` equals the tarball's sha512, and the installed `lib/` digest equals the packed tree's. Token credential as K1 (a `readable` subject, `?token=` on the endpoint), default collections, `CONNECT_DEBUG=false` |
| **C (control)** | the same, with `0.1.0-dev.2` from npm (the image the dev.2 soak built with the npm integrity check) |
| Sampler, stats | from each MongoDB every 60 s; RSS and fds from the host |

`lab.sh` gained `LAB_PREFIX` (container and network names; containers here were `ncfix-*`), `build-local <tarball>`
and `up-profile-arm <image> <control-version>`. `pollstats.py` takes `LAB_NET`.

### 5.2 Timeline (UTC)

| Time | Event |
|---|---|
| 14:59:41 / 14:59:43 | F / C first fetch |
| 15:40:38 → 15:55:42 | **S stopped 15 min 4 s**, then started |
| 15:56:38 | **new** profile added at S (new `_id`) |
| 16:08:00 | the original profile **edited** at S through `PUT` (`dia` 5 → 6, same `_id`) |
| 16:36:02 | final analysis from mongo; run 96 min |

### 5.3 Results

| | F (this branch) | C (dev.2, control) |
|---|---|---|
| poll cycles | 17 | 4 (14:59:43, 15:32:16, 16:01:07, 16:29:05) |
| poll interval, median (min–max) | **5.0 min** (1.8–23.6) | **28.9 min** (28.0–32.5) |
| — before the outage (15:00–15:40) | 9 cycles, 4.8–5.1 min, 1 attempt each | 2 cycles, 31.7 min apart, 4 attempts each |
| — after recovery (16:12–) | 5 cycles, 4.7–5.2 min | 1 cycle, 4 attempts |
| newest sgv behind S: max / median | 30 / 0 min | 30 / 10 min |
| — before the outage | **0** / 0 min | 30 / 10 min |
| — after recovery (16:12–) | **0** / 0 min | 25 / 15 min |
| minutes >10 / >20 min behind (82 live samples) | 15 / 6, all in the outage recovery | 36 / 16 |
| entry lag, source acknowledgement → first seen: p50 / p95 / max | 37 / 698 / 698 s | 757 / 1657 / 1657 s |
| missing (in the 48 h window + later) | **0** | 0 lost; 1 sgv and 1 devicestatus in flight at the end |
| duplicates (lab id / natural key), every collection | 0 / 0 | 0 / 0 |
| field differences, every common record | 0 | 0 |
| profiles on the sink at the end | 2 of 2 | 2 of 2 |
| new source profile (15:56:38) | received at 16:10:56, F's first cycle after the outage | received at 16:01:07, in a failing cycle (read-derived: it sorts first, newest `startDate`, so the ordered insert stored it before failing on the old one) |
| edited source profile (16:08:00) | **not updated** (`dia` 5) | not updated (`dia` 5) |
| `Error saving profile data` (a full profile document in the log) | **0** | 16 |
| E11000 / `Internal persistence failed` | 0 / 0 | 16 / 16 |
| `Polling frame failed` | 4, all during the outage (`EAI_AGAIN`) | 16 |
| sink log, lines / bytes | 500 / 29,717 | 956 / 38,464 |
| RSS first → last (max); fds | 114 → 126 MiB (128); 26–30 | 111 → 124 MiB (125); 26–27 |

The control stalled as in the dev.2 soak, so the lab still reproduces §5.1.

**The outage.** F's requests during the outage failed with `EAI_AGAIN` (last at 15:47:17), and its next successful
cycle was 16:10:56, 15 min after S returned. That is the existing retry backoff after failed frames, the same
behaviour the dev.2 soak measured for K3 (17.5 min), and not changed here. It accounts for F's 23.6 min maximum
interval and its 30 min maximum staleness. C did not poll during the outage.

### 5.4 Reader-subject warning in the lab (control (c) setup)

A separate pair: a denied source, a sink on `0.1.0-dev.1` in API-secret mode that created `nightscout-connect-reader`
(15:00:13; the subject list shows no `roles`), then removed and replaced by a sink on this branch (15:00:14) with the
same secret. Over 96 min the new sink logged `Polling frame failed (HTTP 401)` 16 times and the warning **once**. Its
proxy log shows only `GET` requests from it; the one `POST` (15:00:13.433) is dev.1's, before the new sink started.

The warning, as logged:

> nightscout-connect: The source Nightscout already has a subject named nightscout-connect-reader, and it has no
> roles, so it cannot read any data. Earlier versions of nightscout-connect created it that way. To fix this on the
> source Nightscout, open Admin Tools and either add the "readable" role to nightscout-connect-reader, or delete
> nightscout-connect-reader so nightscout-connect creates it again. nightscout-connect does not change the source
> site itself.

The 401 trigger (unit-tested, not seen in the lab, where the role-less message came first):

> nightscout-connect: The source Nightscout refused to let the subject named nightscout-connect-reader read data
> (HTTP 401). To fix this on the source Nightscout, open Admin Tools and either add the "readable" role to
> nightscout-connect-reader, or delete nightscout-connect-reader so nightscout-connect creates it again.
> nightscout-connect does not change the source site itself.

### 5.5 Credential canary

`canary.py` over the full `docker logs` of every non-mongo container (both pairs), after adding the reused
reader subject's token to the literal set: **21 literals, 0 hits** in every container. The scan self-tests on a
planted value. Other hits, all classified: `api-secret` = the startup `API_SECRET has N bits of entropy` line;
40-hex = `notify: <hash> has ALREADY been sent`; C's 24 lab record ids are inside its profile dumps; the sources log
created treatments (existing Nightscout behaviour, dev.2 soak §5.3).

## 6. Not covered

- **The REST output against a real Nightscout.** The lab sinks run the connector in-process (internal output). The
  REST output (`lib/outputs/nightscout.js`) has the same change and is covered only by the fake-transport tests.
- More than two profiles, a sink with more than 1000 profiles, and a profile deleted on the sink while syncing (§3,
  rows 4–5: read-derived).
- The 401 trigger in the lab; a source on 15.0.8; vendor sources (other than the LibreLinkUp fixture).
- A profile edit reaching the sink: by design it does not (§3).
