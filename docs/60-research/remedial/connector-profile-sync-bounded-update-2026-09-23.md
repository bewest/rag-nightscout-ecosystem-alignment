# nightscout-connect: bounded profile reads and update on change

> **Snapshot: measured 2026-09-23, 18:43–20:17 UTC; clock check 20:19–21:00 UTC.** Connector branch `fix/profile-sync-bounded-update` at `de3cee1`
> (two commits on `fix/profile-duplicate-stall` `f924de2`; its `lib/` is identical to the `9dbef9e` the lab ran, only `test/profile-sync-bounded.test.js` changed since, §5.4): `1d2ebc8` (bounded reads) and `de3cee1` (update on change).
> Worktree `externals/work/nc-profile-sync`, local only. Lab: Nightscout dev `1f9a9d10` (source), BF-99 branch
> `bf/profile-object-id` `9b8cc2f9`, the 15.0.9 candidate `bf/object-id-consistency` `597e2899`, dev `1f9a9d10` and
> `15.0.8` `92d08342` (sinks), MongoDB 7, Node 22 in the images, Node 22.23.2 on the host. Contributor-facing.
>
> Historical: evidence for the maintainer's decisions of 2026-09-23 (bound the profile reads; copy profile edits). Both
> commits merged as connector #79 and are in nightscout-connect `0.1.0`, released 2026-09-24 and pinned exactly by
> Nightscout `dev` (#8762). Update-on-change works only against a sink that has #8758 (open). The combined runs'
> lab arm did not include these two commits ([15.0.9 integration record](../../30-design/remedial/rc-15.0.9-integration-record.md)).
> Current facts: [backfix register](../../30-design/remedial/nightscout-backfix-register.md) (BF-97).

Every figure is **reproduced** (run in the lab or the suite) unless marked **read-derived**. All lab data was
synthetic: the lab writer's glucose, treatments and device status, and 500 generated profiles. No real person's data was
used.

## 1. What the source endpoints return (measured)

Source: dev `1f9a9d10`, 501 profiles (500 generated, about 6.8 KB each, one every 20 h over 417 days, `created_at` one
second after `startDate`; plus the lab writer's one), read with the API secret on 2026-09-23 18:43 UTC. "Raw" is the JSON
body; "wire" is what crossed the connection with compression.

| Request | Profiles | Raw bytes | Wire bytes |
|---|---:|---:|---:|
| `profile.json?count=1000` (what `f924de2` sends every poll) | 501 | 3,422,251 | 30,318 |
| `profile.json?count=1000&find[created_at][$gt]=<now>` | 501 | 3,422,251 | 30,318 |
| `profile.json?count=1` | 1 | 6,849 | 842 |
| `profile.json` (no count) | 10 | 62,267 | 1,939 |
| `profiles.json` (no find, no count) | 5 | 28,043 | 1,400 |
| `profiles.json?count=1000` | 5 | 28,043 | 1,400 |
| `profiles.json?find[startDate][$gte]=<now-2d>` | 2 | 13,693 | 970 |
| `profiles.json?find[startDate][$lt]=<now-2d>&count=1` | 1 | 6,835 | 860 |
| `profiles.json?find[created_at][$gt]=<now>&find[startDate][$gte]=1970-…` | 0 | 2 | 2 |

- `profile.json` **ignores `find`** (row 2).
- `profiles.json` **applies `find`**, and when the query names neither `startDate` nor `_id` it adds `startDate >= now
  - 4 days` (rows 5–6: 5 profiles, not 501). After an editor-style save of an 83-day-old profile (`created_at` set to
  now, same `_id`), `find[created_at][$gt]=<10 min ago>` alone returned 1 profile (the lab writer's), and the same query
  with `find[startDate][$gte]=1970-01-01T00:00:00.000Z` returned 2, including the edited one.
- The wire figures are unusually small because the generated profiles repeat each other almost exactly. The raw figure
  is the one to compare. Real profiles compress less well (not measured).
- `/api/v1/profiles` exists from 14.x (read-derived: present in `14.2.6`, `15.0.0`, `15.0.8`; absent in `13.0.1`).

## 2. The bound (commit `1d2ebc8`)

`lib/sources/nightscout.js` `fetchProfiles`:

| Case | Requests |
|---|---|
| no profile bookmark (`last_known.profiles` unset) | `profiles.json?find[startDate][$gte]=W&count=1000` and `profiles.json?find[startDate][$lt]=W&count=1`, W = now − 2 days, the same window the other collections start from |
| bookmark B | `profiles.json?find[created_at][$gt]=B&find[startDate][$gte]=1970-01-01T00:00:00.000Z&count=1000` and `profile.json?count=1` |
| `profiles.json` answers 404 | `profile.json?count=1000`, as before, from then on; one `log.warn` |

The two lists are merged, deduplicated by `_id`. Any other read failure fails the poll, as before.

The bookmark is the newest `created_at` the output has stored or already handled, and it only moves forward:

- internal output (`lib/outputs/internal.js`): `known.profiles`. It is taken from storage (`ctx.profile.list`, 1000)
  the first time profiles arrive, and advanced over every row in a successful profile write, whether it was stored or
  skipped. A failed write does not advance it. After a restart the first poll is therefore a first-window read.
- REST output (`lib/outputs/nightscout.js`): `bookmark.profiles`, read at startup as before (`created_at` of
  `profile.json?count=1`), then advanced over the rows handled. The lab found that setting it the way the other
  collections are set (`bookmark_collection`, newest of the batch) moved it **back** whenever a poll brought only the
  newest-by-`startDate` profile. Every other poll then re-read the profiles saved since, 7,511 extra raw bytes (§4.3).
  It now only moves forward (`bookmark_newest`).

Why these reads:

- **The profile in use.** Nightscout's active profile is the newest by `startDate`. `profile.json?count=1` reads it
  every poll (one profile, about 6.8 KB raw here). That is the only way to see an edit that leaves `created_at` alone,
  such as an API `PUT`.
- **Editor saves.** The profile editor lists the 20 newest profiles (`profile.json?count=20`) and sets
  `created_at = now` on save (read-derived: `lib/profile/profileeditor.js:76,643`). `created_at > B` catches a save of
  any of them, and of any other profile, whatever its `startDate`.
- **New profiles.** A new profile has a new `created_at` (the source sets it if absent).
- **No per-poll full read.** A steady poll reads `[]` plus one profile.

### 2.1 What a fresh sink ends up with

A sink with no profiles gets (a) every source profile whose `startDate` is within the 2 days before its first fetch, (b)
the one profile in effect when that window starts, and then (c) every profile created or saved on the source after the
newest `created_at` among (a) and (b). The same window applies to entries, treatments and device status, so the sink has
a profile for all the data it holds. It does **not** get older history: reports on the sink for periods before the
window have no glucose data on the sink either.

(c) can pull in an older profile: in the lab the four fresh sinks started before 19:00 (`ff`, `uf`, `r15`, `rdev`) also
received profile 400 (`startDate` 83 days back), which
had been saved on the source after the newest window profile was created. A profile saved on the source **before** that
point, and not in the window, is never copied.

**No backfill is added.** A backfill of older profiles would only matter if older data were copied too, and it is not.
If the maintainer wants sinks to hold the full history, the first-window read is the place for it: a one-time
`profile.json?count=1000` costs the same as one poll of `f924de2`.

A sink that already stores profiles (every sink that ran an earlier connector) takes its bookmark from them. It reads
nothing old again.

### 2.2 What the bound does not see

| Change on the source | Seen? |
|---|---|
| new profile | yes |
| profile editor save, any profile | yes (`created_at` changes) |
| API `PUT` of the newest profile, `created_at` unchanged | yes (the newest is read every poll) |
| API `PUT` of any other profile, `created_at` unchanged | **no**. The lab's case: profile 499 edited by API at 19:15:49, then a newer profile 500 posted 0.1 s later, so 499 was no longer the newest. No sink saw the edit until 499 was saved in the editor at 19:22:02 |
| profile deleted on the source | no (not copied by any version) |
| a source `created_at` in the future (clock error) | the bookmark jumps ahead; only the newest profile is seen until then (read-derived) |
| a sink-side profile with a newer `created_at` than the source's | the same: the bookmark is taken from the sink's storage, whoever wrote it (read-derived) |

## 3. Update on change (commit `de3cee1`)

`lib/outputs/profile-sync.js`, used by both outputs:

- **Comparison.** A fingerprint per profile: SHA-1 of the JSON with keys sorted, without the top-level `_id`,
  `srvModified` and `srvCreated`. `created_at` is content. The editor sets it, so an editor save always counts as a
  change. An API `PUT` leaves it alone and is still caught by the content. Fingerprints are seeded from the sink's
  stored copies, and updated to the source version once it is handled, so a server-side normalisation cannot cause a
  save every poll. At most one save per restart could happen that way. None was seen: the upgraded sinks, which held
  string-`_id` copies written straight into MongoDB from the source documents, made no profile write after a restart.
- **Plan.** A row with no stored key is created, as before. A row whose `id:<_id>` is stored with a different
  fingerprint is a replace candidate. Glooko rows (keyed by `identifier`) are skipped, as before.
- **Guard.** Before replacing, the output looks the profile up by `_id`: `ctx.profile.list_query({find: {_id}})` in
  process, `GET /api/v1/profiles.json?find[_id]=` over REST. It replaces only if that returns the profile. The save
  (`ctx.profile.save`, or `PUT /api/v1/profile.json`) upserts `new ObjectID(_id)`. The find matches exactly what the
  save will replace:

| Sink | stored `_id` | find by `_id` returns | save does | guard |
|---|---|---|---|---|
| without BF-99 (dev `1f9a9d10`, 15.0.8) | string (every connector copy there) | nothing (`updateIdQuery` makes it an ObjectId) | would add an ObjectId twin | **skip**, warn once |
| without BF-99 | ObjectId | the profile | replaces it in place | replace |
| with BF-99 (`9b8cc2f9`, `597e2899`) | string (copied before the upgrade) | the profile (`query_for` matches both forms) | upserts the ObjectId form, deletes the string form | replace |
| with BF-99 | ObjectId (copied after it; `create` converts hex) | the profile | replaces it in place | replace |

  On a sink without BF-99 that already has a twin (a string original plus an ObjectId copy from an edit in the sink's
  own editor), the find returns the ObjectId copy and the save replaces that. The string original stays as it was. The
  guard adds no document; it does not remove the existing twin (read-derived, unit-modelled only).
- **Detection is behavioural, not by version.** The guard does not look at the Nightscout version or at code. The same
  read-only find tells both outputs whether the save is safe. It runs only for a changed profile, once per version.
- **Failure.** A failed find or save fails the poll, and the stored set is read again next time (as in `f6359b4`).
- **Warning** (once per output process, `log.warn`, no content, `_id`, URL or credential):

> nightscout-connect: A profile changed on the source Nightscout was not copied, because the destination Nightscout
> cannot replace that profile without keeping a second, outdated copy of it. New profiles are still copied. Updating
> the destination Nightscout fixes this for later changes; after updating it, saving the profile again on the source
> copies it.

  "Saving again" is stated because the bookmark may already be past the edit. The API `PUT` of the newest profile is
  also picked up after a restart without a save, since it is read every poll.

### 3.1 The remote Nightscout output

The REST output has the same plan and guard, over HTTP. Against a 15.0.8 or dev sink, `POST /api/v1/profile.json` with
the source's hex `_id` stores it as a string (BF-99, reproduced here: `r15`, `rdev` in §4). `find[_id]` then returns
`[]`, so no `PUT` is sent and the sink keeps one copy. Without the guard, a `PUT` would add a second copy (BF-99 §2,
reproduced there). The REST output needs the sink's `api:profile:update` permission for the `PUT`. With the API secret it
has it.

## 4. Lab

### 4.1 Setup

| | |
|---|---|
| Source S | dev `1f9a9d10`, `AUTH_DEFAULT_ROLES=denied`, lab writer (60 h seed plus live sgv every 5 min, treatments, device status), plus 500 generated profiles |
| Proxies | one pass-through proxy per sink, in front of S. It logs method, path, query (token values redacted), status, wire bytes and decoded bytes |
| Internal sinks | Nightscout image with the branch from `npm pack`, installed as a `file:` dependency through a regenerated lockfile (`lab.sh build-local`); the installed `lib/` digest equals the packed tree's. Readable token, default collections, `CONNECT_DEBUG=false` |
| REST sinks | plain Nightscout; the connector runs on the host from the packed tree (`bin/nightscout-connect forever`, Node 22.23.2) with the sink's API secret |
| Upgraded sinks | MongoDB pre-loaded with the source's 501 profiles, `_id` as the hex string, which is what every earlier connector left on a sink; or (`ou`) run first on dev for two polls, then moved to `597e2899` on the same database |
| Counting | from MongoDB: profile counts, `_id` types, `_id`s held by more than one document, `dia` of the edited profiles, `$collStats` write counts on `profile`; per collection, source against sink by the writer's `soakId` |

| Arm | Nightscout | Output | Start state | Connector tree |
|---|---|---|---|---|
| `ff` | `9b8cc2f9` (BF-99) | internal | empty | pack `aa555b90` |
| `fu` | `9b8cc2f9` | internal | 501 string copies | pack `aa555b90` |
| `uf` | dev `1f9a9d10` | internal | empty | pack `aa555b90` |
| `uu` | dev `1f9a9d10` | internal | 501 string copies | pack `aa555b90` |
| `r15` | `15.0.8` | REST | empty | `aa555b90`, then `9dbef9e` from 19:09:22 |
| `rdev` | dev `1f9a9d10` | REST | empty | same |
| `rfix` | `9b8cc2f9` | REST | 501 string copies | same |
| `of` | `597e2899` (15.0.9 candidate) | internal | empty | pack `f5536621` = `9dbef9e` |
| `ou` | dev, then `597e2899` at 19:36:35 | internal | what dev stored in two polls | pack `f5536621` |
| `rok` | `597e2899` | REST | empty | `9dbef9e` |

`9dbef9e` has the same `lib/` as `de3cee1`. Pack `aa555b90` is the tree before the REST bookmark fix (§2). It differs from `9dbef9e` only in
`lib/outputs/nightscout.js` (`bookmark_newest`). The internal arms on it run the final internal-output code.

### 4.2 Timeline (UTC)

| Time | Event |
|---|---|
| 18:43–18:44 | S up and seeded; profile 400 (83 days old) saved in editor style (`dia` 7, `created_at` 18:44:15) while measuring §1 |
| 18:56:12–18:56:21 | `ff`, `fu`, `uf`, `uu` first fetch |
| 18:59:41 | `r15`, `rdev`, `rfix` first fetch |
| 19:09:22 | REST connectors restarted on `9dbef9e` (bookmark fix) |
| 19:15:48.9 | **E1** editor save of profile 450 (`startDate` 41 days back): `dia` 8, `created_at` now |
| 19:15:49.3 | **E2** API `PUT` of profile 499 (then the newest): `dia` 6.5, `created_at` unchanged |
| 19:15:49.4 | **E3** new profile 500, newest `startDate` |
| 19:22:01.8 | **E4** API `PUT` of profile 500 (newest): `dia` 4 |
| 19:22:02.1 | **E5** editor save of profile 499: `dia` 6.6 |
| 19:30:47–19:30:49 | `of`, `ou` (on dev) and `rok` first fetch |
| 19:36:35 | `ou` moved to `597e2899`, same database |
| 19:42:35.5 | **E6** editor save of profile 499: `dia` 6.7 |
| 19:42:35.8 | **E7** API `PUT` of profile 500 (newest): `dia` 3.5 |
| 19:49:28 | `ff` and `uu` restarted (`docker restart`) |
| 20:16:30 | final measurement |

### 4.3 Profile results

`dia` after each edit, as stored on each sink (`o` ObjectId `_id`, `s` string `_id`, `-` not on the sink); source
values after E7: 400 → 7, 450 → 8, 499 → 6.7, 500 → 3.5.

| Sink | Nightscout | profiles (source 502) | string `_id` | `_id` twins | 400 | 450 | 499 | 500 | profile writes | warnings |
|---|---|---:|---:|---:|---|---|---|---|---:|---:|
| `ff` | `9b8cc2f9` | 7 | 0 | 0 | o7 | o8 | o6.7 | o3.5 | 11 | 0 |
| `fu` | `9b8cc2f9` | 502 | 499 | 0 | s7 | o8 | o6.7 | o3.5 | 12 | 0 |
| `rfix` (REST) | `9b8cc2f9` | 502 | 499 | 0 | s7 | o8 | o6.7 | o3.5 | 12 | 0 |
| `of` | `597e2899` | 4 | 0 | 0 | - | - | o6.7 | o3.5 | 5 | 0 |
| `ou` | dev → `597e2899` | 4 | 2 | 0 | - | - | o6.7 | o3.5 | 5 | 0 |
| `rok` (REST) | `597e2899` | 4 | 0 | 0 | - | - | o6.7 | o3.5 | 5 | 0 |
| `uf` | dev | 7 | 7 | 0 | s7 | s8 | s5.5 | s4.5 | 3 | 1 |
| `uu` | dev | 502 | 502 | 0 | s7 | s5 | s5.5 | s4.5 | 2 | 2 (one per process) |
| `r15` (REST) | 15.0.8 | 7 | 7 | 0 | s7 | s8 | s5.5 | s4.5 | 3 | 1 |
| `rdev` (REST) | dev | 7 | 7 | 0 | s7 | s8 | s5.5 | s4.5 | 3 | 1 |

"Profile writes" is `$collStats` `latencyStats.writes.ops` on the sink's `profile` collection, including the
pre-load insert on `fu`, `uu`, `rfix`. The fresh sinks hold 7 or 4 profiles: the first window, profile 400 and the lab
writer's profile (both saved after the window's newest was created), 450 (E1, saved after they started) and 500. `of`,
`ou`, `rok` started after E1, so 400 and 450 were saved before their bookmark and are not on them (§2.1).

- **No twins anywhere.** No `_id` was held by more than one document on any sink, at any sample.
- **BF-99 sinks** (`ff`, `fu`, `rfix`, `of`, `ou`, `rok`) received every edit they could see. E1 was not in their
  window, so `ff` created 450 new; on `fu` and `rfix` it converted the string copy to one ObjectId document. E3 was
  created. E4, E5, E6 and E7 were replaced. On the upgraded ones each replaced profile went from string to ObjectId
  (`fu`, `rfix`: 499 → 502 − 3 string; `ou`: 2 of 4 string). E2 was seen by none: profile 500 became the newest 0.1 s
  later (§2.2).
- **Sinks without BF-99** (`uf`, `uu`, `r15`, `rdev`) got the new profile and the out-of-window E1 as a new profile
  (`uf`, `r15`, `rdev`). They copied no edit to a stored profile, and logged the warning once per process (`uu`: once,
  and once more after its restart; the others once).
- **Restart.** After `ff` restarted, its profile write count stayed at 11 (no re-save). `ou` after its image change:
  1 write before and after its first poll on `597e2899`, so nothing unchanged was re-saved.
- **Profile writes.** On both BF-99 builds each replacement is two writes (the upsert, then the delete of the string
  form, which finds nothing when the copy is already an ObjectId).

Profile JSON read per poll (decoded bytes, all profile requests of a poll, from the proxies):

| Poll | `ff` / `uf` (fresh) | `fu` / `uu` (upgraded) | `of`, `rok` | REST fresh (`r15`, `rdev`) |
|---|---:|---:|---:|---:|
| first | 20,528 (3 profiles; replayed) | 20,528 (replayed) | 27,372 (4) | 20,528 |
| second | 14,360 (profile 400 and the writer's, saved after the window's newest; plus the newest) | 6,851 | 6,847 | 14,360 |
| steady | **6,851** | **6,851** | **6,847** | **6,851** |
| after E1–E3 | 20,538 | 20,538 | — | 20,538 |
| after E4/E5 | 13,694 | 13,694 | — | 13,694 |
| after E6/E7 | 13,698 | 13,698 | 13,698 | 13,698 |
| first after a restart | 27,376 (first window) | 27,376 | 27,372 (`ou`) | — |

Before the change every poll read 3,422,251 bytes (§1). The REST arms' first run (before 19:09:22) alternated 6,851 and
14,360 bytes, the backwards bookmark of §2. After the fix, `rfix` read 6,851 per steady poll.

### 4.4 Other collections and poll cadence

Final measurement 20:16:30, from MongoDB, per sink: records of the source inside the sink's window (from its oldest
record), against the sink. "twins" = an `_id` held by more than one document; "dup" = a lab `soakId` held by more than
one document.

| Sink | Nightscout | entries src / sink, missing, dup, twins | treatments src / sink, missing, dup, twins | devicestatus src / sink, missing, dup, twins (string `_id`) |
|---|---|---|---|---|
| `of` | `597e2899` | 592 / 592, 0, 0, 0 | 227 / 227, 0, 0, 0 | 195 / 194, 1*, 0, 0 (0) |
| `ou` | dev → `597e2899` | 592 / 592, 0, 0, 0 | 227 / 227, 0, 0, 0 | 195 / 195, 0, 0, 0 (192, stored by dev) |
| `rok` (REST) | `597e2899` | 592 / 592, 0, 0, 0 | 227 / 227, 0, 0, 0 | 195 / 195, 0, 0, 0 (0) |
| `ff` | `9b8cc2f9` | 599 / 599, 0, 0, 0 | 230 / 230, 0, 0, 0 | 198 / 197, 1*, 0, 0 (197) |
| `fu` | `9b8cc2f9` | 599 / 599, 0, 0, 0 | 230 / 230, 0, 0, 0 | 198 / 197, 1*, 0, 0 (197) |
| `rfix` (REST) | `9b8cc2f9` | 599 / 599, 0, 0, 0 | 230 / 230, 0, 0, 0 | 198 / 197, 1*, 0, 0 (197) |
| `uf` | dev | 599 / 599, 0, 0, 0 | 230 / 230, 0, 0, 0 | 198 / 197, 1*, 0, 0 (197) |
| `uu` | dev | 599 / 599, 0, 0, 0 | 230 / 230, 0, 0, 0 | 198 / 198, 0, 0, 0 (198) |
| `r15` (REST) | 15.0.8 | 599 / 599, 0, 0, 0 | 230 / 230, 0, 0, 0 | 198 / 198, 0, 0, 0 (198) |
| `rdev` (REST) | dev | 599 / 599, 0, 0, 0 | 230 / 230, 0, 0, 0 | 198 / 197, 1*, 0, 0 (197) |

\* In flight: in each case the one missing record is the source's newest device status, written at 20:15:37, at or just
after that sink's last poll (20:15:27–20:15:41).

- **On `597e2899` device status is stored with an ObjectId `_id`** (`of`, `rok`: 0 string), where dev and `9b8cc2f9`
  store the connector's copies with string `_id`s (BF-100). `ou` keeps the 192 string records dev stored before the
  image change, and stored the 3 written after it as ObjectId. No twins either way. Entries and treatments have ObjectId
  `_id`s on every sink.
- **Poll cadence.** Steady-state intervals from each sink's `entries.json` requests: 4.7–5.3 min on every sink (`of`
  9 intervals, `ou` 10, `rok` 9; the rest 16–17). The shorter gaps are the start or restart alignment: 0.8–1.3 min
  after a REST connector start, and 0.9–1.0 min after the `ff` / `uu` restarts and the `ou` image change. Newest sgv
  behind the source at the final sample: 0 min on every sink. Every proxied request answered 200. No sink logged
  `Polling frame failed`, `Internal persistence failed`, `E11000` or `Error saving profile data`.
- The run is 80 min on the first sinks and 46 min on the `597e2899` ones. It is not a soak of the length of the dev.2
  soak (4 h 23 min). Outages and restarts of the source were not repeated here.

### 4.5 Credential canary

`canary.py` over the full `docker logs` of the 22 non-mongo containers, with every lab secret and token as literals
(53 checked, raw and SHA-1): **0 literal hits** in every container. A separate scan of the host-run REST connectors'
log files (8 files, 42 literals): 0 hits. Shape hits, all classified: `api-secret` and 40-hex are the startup `API_SECRET
has N bits of entropy` line and `notify` hashes. `soakId` and carbs/insulin are the source's and REST sinks' own
logging of created treatments (existing Nightscout behaviour; synthetic data). A REST sink's `PUT /api/v1/profile` also
logs the whole saved profile (`Profile saved`, existing Nightscout behaviour, `lib/api/profile/index.js:137`); the
in-process save logs nothing.

## 5. Suite and break-its

### 5.1 Suite (`npm test`, `n exec`)

| Node | `f924de2` | `1d2ebc8` | `de3cee1` |
|---|---|---|---|
| 20.20.0 | 308/308 | 319/319 | 334/334 |
| 22.23.2 | 308/308 | 319/319 | 334/334 |
| 24.20.0 | 308/308 | 319/319 | 334/334 |

0 fail, 0 skipped. Three existing tests changed with commit 1: two in `test/nightscout-connectivity.test.js` that list
or serve the source's requests now expect `profiles.json`, and the reader-subject fake in `test/nightscout-source.test.js`
also answers `profiles.json`. With commit 2, one test in `test/profile-duplicate.test.js` was renamed ("…is not copied
where the sink cannot replace it by _id"); its body is unchanged and it still passes.

### 5.2 New tests, red first

| File | Tests | On the previous commit |
|---|---:|---|
| `test/profile-sync-bounded.test.js` | 11 | 10 fail on `f924de2`. The eleventh (the REST bookmark never moves back) passes there, because the skip returned nothing, and was written after the lab found the regression. Break-it B9 shows it goes red |
| `test/profile-update.test.js` | 15 | 10 fail on `1d2ebc8`. The other five guard existing behaviour: no check or save for an unchanged profile, also after a restart (2); Glooko rows still skipped (2); the fingerprint unit test (1) |

The source fake models both profile endpoints, including `profiles.json`'s implicit 4-day `startDate` filter. The
update tests model both storages, with the string and ObjectId forms of an `_id` as different keys, as MongoDB treats
them.

### 5.3 Break-its (each alone, on the final tree)

| Break | Red |
|---|---|
| B1 poll query without the explicit `startDate` | editor save of an old profile; fresh-sink round trip |
| B2 first sync reads every profile | first-window read; 404 fallback count; "other failures fail"; round trip |
| B2b first sync without the profile in effect at the window start | first-window read; round trip; 404 fallback (by request count, a different reason) |
| B3 no newest-profile read | bookmark read; editor-save test; round trip |
| B4 no dedupe by `_id` | "new and newest returned once" |
| B5 no 404 fallback | fallback test |
| B5b fallback retried every poll | fallback test |
| B6 internal bookmark not advanced by handled rows | internal bookmark; round trip |
| B6b internal bookmark not seeded from storage | internal bookmark |
| B7 REST skipped rows do not advance the bookmark | REST bookmark |
| B8 internal bookmark advanced before the write | "failed write does not move the bookmark" |
| B9 REST bookmark set as the other collections (the lab regression) | "REST bookmark does not move back" |
| C1 / C2 internal / REST replace without the find | unfixed: no twin (internal / REST) |
| C3 a version not replaced is not remembered | unfixed: checked once per version |
| C4 REST warning every time | unfixed: said once |
| C5 fingerprint without `created_at` | fingerprint test |
| C6 fingerprint with `srvModified` | fingerprint test |
| C7 / C8 internal / REST failed replace swallowed | failed replace fails the poll |
| C9 stored copies not fingerprinted | unchanged profile after a restart (both outputs) |
| C10 no replace at all | all 10 replace tests |

### 5.4 Wall-clock independence (after a reported failure)

The coordinator ran `9dbef9e` at 20:19 UTC and got 332/334. Two tests failed: "without a profile bookmark only the
profiles for the first window are read" was missing the profile in effect at the window start, and the fresh-sink
round trip expected 3 profiles and got 2.

**Cause: the tests, not the code.** The source's first window is `now − 2 days` by the process clock
(`sinceFor`, the same as entries, treatments and device status), which is right in production, where there is one
clock. The tests built their fake site around a fixed `2026-09-23T12:00Z` but let the source read the real clock. The
fixture's profiles start every 20 h back from 12:00, so the one at 20:00 the day before is inside the window only
while the wall-clock time is before 20:00 UTC. Reproduced with a `--require` shim that moves `Date` to a chosen time
(`FAKE_NOW`; no libfaketime on the host). An hour-by-hour sweep of `test/profile-sync-bounded.test.js` on `9dbef9e`
(`HH:30`, Node 22.23.2) failed at 20:30, 21:30, 22:30 and 23:30 UTC (2 tests each) and passed at the other 20 hours.

**Fix** (folded into `1d2ebc8`, test file only): each test with a fixed time freezes `Date` there with
`t.mock.timers.enable({ apis: ['Date'], now })`, 10 tests. The other test in that file checks no time. The
update-on-change tests read no clock. After the fix the same sweep fails at no hour.

**Suite under faked system times** (`FAKE_NOW` shim through `NODE_OPTIONS`, which the test runner's per-file child
processes inherit, plus `TZ`):

| Tree | Node | 2026-09-23T20:19Z, UTC | 2026-09-24T03:10Z, America/Los_Angeles | 2027-02-28T23:59:30Z, Asia/Kolkata | real clock |
|---|---|---|---|---|---|
| `1d2ebc8` | 20.20.0 / 22.23.2 / 24.20.0 | 319/319 | 319/319 | 319/319 | 319/319, 0 skipped |
| `de3cee1` | 20.20.0 / 22.23.2 / 24.20.0 | 334/334 | 334/334 | 334/334 | 334/334, 0 skipped |

`de3cee1` also passed 334/334 at 2026-03-08T10:30Z America/New_York (a DST change day) on all three.

**Break-its redone** under the shim at 2026-09-23T20:19Z and 2026-09-24T03:10Z (Node 22.23.2): B1–B9 as in §5.3, each
with the same red tests at both times. B7 was re-expressed for the final REST code (`return stored` instead of the
handled rows). C1–C10 were also re-run: the same red counts at both times. New B10 removes the clock freeze: 2 red at
both times, the two tests that failed for the coordinator.

## 6. Decided (maintainer, 2026-09-23)

1. **The bound stays as built.** Each poll reads the changes since the bookmark and the newest profile only. An API
   `PUT` to a profile that is not the newest is not seen (§2.2).
2. **No backfill on first sync.** A new sink gets the profiles for the 2-day window it copies, and later changes (§2.1),
   not the source's older profile history.
3. **The source wins.** On Nightscout-to-Nightscout sync the receiving site is a copy: a profile edited there is
   overwritten when the source's copy of it changes, and after a restart if it is among the profiles read then.

None of the three needs a code change.

**For operators:** on Nightscout-to-Nightscout sync, profile edits made on the receiving site are overwritten when the
profile changes on the source. Make profile changes on the source site.

Open points, not decided here:

- **Warning text.** It names no Nightscout version, since BF-99 is not released. Once 15.0.9 ships with
  `bf/object-id-consistency`, the release notes can name it.
- **Sinks without BF-99 keep stale profiles.** The guard avoids twins; it does not copy edits there. Every existing
  connector sink holds string-`_id` copies, so edits start to flow only after that sink runs a Nightscout with BF-99.
- **Stacking.** This branch sits on `fix/profile-duplicate-stall` (`f6359b4`, `f924de2`) and should be reviewed with it
  or after it. It changes `f6359b4`'s behaviour row 2 ("source edits a stored profile": never updated) to "updated where
  the sink can replace it in place".

## 7. Not covered

- A source on 15.0.8 (the lab source is dev). The source code reads `profiles.json`, which 15.0.8 has (read-derived).
- A source before 14 (the 404 path is unit-tested only).
- A real destination-side twin (string plus ObjectId) under the guard: modelled in the unit tests, not run.
- Sinks with more than 1000 profiles (the stored set is read with count 1000, as in `f6359b4`).
- Real, non-synthetic profile sizes and compression.
