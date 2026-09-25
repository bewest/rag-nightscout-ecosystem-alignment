# nightscout-connect: profile sync from a Nightscout source

*Contributor-facing and technical. Status: **released** in `nightscout-connect` `0.1.0` (2026-09-24,
tag `v0.1.0` on connector `main` `4dde1ec`), merged as connector #79 (`977da8a`; commits `f6359b4`,
`f924de2`, `1d2ebc8`, `de3cee1`). Nightscout `dev` pins `0.1.0` exactly (#8762), so it reaches
Nightscout operators with 15.0.9. Defect facts: [backfix register](../../30-design/remedial/nightscout-backfix-register.md)
BF-97 (the stall) and BF-98 (the role-less reader subject). Measured 2026-09-23 in the connector
suite and in two labs; every figure is **reproduced** unless marked **read-derived**. All lab data
was synthetic.*

## Summary

On connector `0.1.0-dev.1` and `0.1.0-dev.2`, a Nightscout source that has a profile made every
poll fail from the second one on. Nothing was lost, but the receiving site (the sink) ran 20–35 min
behind (BF-97). In `0.1.0`:

| case | `0.0.13` | `0.1.0-dev.2` | `0.1.0` |
|---|---|---|---|
| the same profile, every poll | insert fails, error swallowed | insert fails, **poll fails** | skipped; the poll succeeds |
| a new profile on the source | stored if it sorts before the first duplicate (read-derived) | stored, but the poll still fails | stored |
| a profile edited on the source | never copied | never copied | **copied**, where the sink can replace it in place (a sink with #8758); elsewhere skipped, with one warning |
| profile data read per steady poll (501-profile source) | every profile | every profile (3,422,251 bytes raw) | the changes since the last poll plus the newest profile (6,851 bytes) |
| a reused reader subject with no roles (BF-98) | fails silently | fails silently | one plain-language warning naming the fix |

**Decided by the maintainer (2026-09-23), with no code change needed:**

1. Each poll reads only the changes since the bookmark and the newest profile. An API `PUT` to a
   profile that is not the newest is not seen.
2. No backfill on first sync. A new sink gets the profiles for the 2-day window it copies, then later
   changes, not the source's older profile history.
3. **The source wins.** On Nightscout-to-Nightscout sync the sink is a copy. A profile edited on the
   sink is overwritten when the source's copy changes.

**For operators (user-facing):** if you copy one Nightscout site into another, make profile changes
on the site you copy *from*. Changes made on the receiving site are overwritten when the profile
changes on the original. A receiving site running Nightscout 15.0.8 or earlier gets new profiles but
not edits to existing ones; that needs a Nightscout release that contains #8758. This is not medical
advice; if a profile on either site looks wrong, check it against the settings your care team gave
you.

## The defect (BF-97)

Read-derived from connector `fbd4e55` (tag `v0.1.0-dev.2`) and Nightscout `74fc6619`:

| step | where |
|---|---|
| The source read **every** profile, with its `_id`, on every poll (`profile.json?count=1000`, no `since`) | `lib/sources/nightscout.js` `fetchProfiles` |
| The sink stores profiles with `insertMany`, so a second insert of the same `_id` fails with E11000 | Nightscout `lib/server/profile.js` `create` |
| Up to `v0.0.13` the internal output swallowed that failure. From `808ab1c` (in `v0.1.0-dev.1`), a write that really failed fails the poll, in both outputs | `lib/outputs/internal.js`, `lib/outputs/nightscout.js` |
| The failed frame retries 3 × 10 s, then the loop backs off toward its 30 min cap | `lib/machines` |

`808ab1c`'s rule, that a write that really failed must fail the poll, is kept. The other
collections avoid the stall because their source queries read only newer records
(`find[dateString|created_at][$gt]=<bookmark>`) or the connector drops rows it knows are stored.
The Nightscout profile source had neither.

## How `0.1.0` syncs profiles

### Skip what is stored (`f6359b4`)

Profiles go through the check Glooko profiles already use, in both outputs. The output reads the
stored profiles once (`count: 1000`) and skips a row whose `identifier` **or `_id`** is already
stored; rows actually stored are added to the set. Nothing matches on error codes or text, so every
write failure still fails the poll. After a failed profile write the set is dropped and read again
on the next poll, so a profile another writer stored in between costs one failed poll.

### Read only what changed (`1d2ebc8`)

What the source endpoints return (Nightscout `dev` `1f9a9d10`, 501 profiles of about 6.8 KB):

| request | profiles | raw bytes |
|---|---:|---:|
| `profile.json?count=1000` (what `0.1.0-dev.2` sent every poll) | 501 | 3,422,251 |
| `profile.json?count=1000&find[created_at][$gt]=<now>` | 501 (`profile.json` ignores `find`) | 3,422,251 |
| `profile.json?count=1` | 1 | 6,849 |
| `profiles.json?count=1000` | 5 (adds `startDate >= now − 4 days` when the query names neither `startDate` nor `_id`) | 28,043 |
| `profiles.json?find[startDate][$gte]=<now − 2d>` | 2 | 13,693 |

`/api/v1/profiles` exists from Nightscout 14.x (read-derived: present in 14.2.6, 15.0.0 and 15.0.8;
absent in 13.0.1).

`fetchProfiles` now sends:

| case | requests |
|---|---|
| no profile bookmark | `profiles.json?find[startDate][$gte]=W&count=1000` and `profiles.json?find[startDate][$lt]=W&count=1`, with W = now − 2 days (the window the other collections start from) |
| bookmark B | `profiles.json?find[created_at][$gt]=B&find[startDate][$gte]=1970-01-01T00:00:00.000Z&count=1000` and `profile.json?count=1` |
| `profiles.json` answers 404 | `profile.json?count=1000` from then on, with one warning |

The two lists are merged and deduplicated by `_id`. The bookmark is the newest `created_at` the
output has stored or handled, and it only moves forward:

- **Internal output:** taken from storage the first time profiles arrive, and advanced over every
  row of a successful profile write. A failed write does not advance it. After a restart, the first
  poll is a first-window read.
- **REST output:** read at startup from `profile.json?count=1`, then advanced over the rows handled
  (`bookmark_newest`). Setting it the way the other collections do would move it backwards whenever
  a poll brought only the newest profile.

Why these reads:

- **The profile in use** is the newest by `startDate`. Reading it every poll is the only way to see
  an edit that leaves `created_at` alone, such as an API `PUT`.
- **Editor saves** set `created_at = now` (read-derived: `lib/profile/profileeditor.js:76,643`), so
  `created_at > B` catches a save of any profile.
- **New profiles** get a new `created_at`.

**What a fresh sink ends up with:** every source profile whose `startDate` is within the 2 days
before its first fetch, the one in effect when that window starts, and then every profile created or
saved after the newest `created_at` among those. That can include an older profile saved later. A
profile saved before that point and outside the window is never copied. The same window applies to
entries, treatments and device status, so the sink has a profile for all the data it holds. A sink
that already stores profiles takes its bookmark from them and re-reads nothing old.

| change on the source | seen? |
|---|---|
| new profile | yes |
| profile editor save, any profile | yes |
| API `PUT` of the newest profile, `created_at` unchanged | yes |
| API `PUT` of any other profile, `created_at` unchanged | **no** |
| profile deleted on the source | no (no version copies deletes) |
| a `created_at` in the future (clock error), or a sink-side profile newer than the source's | the bookmark jumps ahead; only the newest profile is seen until then (read-derived) |

### Copy edits where the sink can take them (`de3cee1`)

`lib/outputs/profile-sync.js`, used by both outputs:

- **Comparison.** Each profile has a fingerprint: SHA-1 of its JSON with keys sorted, without the
  top-level `_id`, `srvModified` and `srvCreated`. `created_at` counts as content, so an editor save
  is always a change, and an API `PUT` is caught by the content. Fingerprints are seeded from the
  sink's stored copies, so a server-side normalisation cannot cause a save every poll.
- **Plan.** A row with no stored key is created. A row whose `_id` is stored with a different
  fingerprint is a replace candidate. Glooko rows are skipped, as before.
- **Guard.** Before replacing, the output looks the profile up by `_id` (in process, or
  `GET /api/v1/profiles.json?find[_id]=` over REST) and replaces only if that returns it. The save
  upserts `new ObjectID(_id)`, so the lookup matches exactly what the save will replace:

| sink | stored `_id` | lookup by `_id` returns | the save would | the guard |
|---|---|---|---|---|
| without #8758 (15.0.8, `dev`) | string (every earlier connector copy) | nothing | add an ObjectId twin | **skips**, warns once |
| without #8758 | ObjectId | the profile | replace it in place | replaces |
| with #8758 | string (copied before the upgrade) | the profile | upsert the ObjectId form and delete the string form | replaces |
| with #8758 | ObjectId | the profile | replace it in place | replaces |

The guard does not look at the Nightscout version; the same read-only lookup tells either output
whether the save is safe. It runs only for a changed profile, once per version. A failed lookup or
save fails the poll. The REST output needs the sink's `api:profile:update` permission, which the API
secret has. The warning, logged once per output process with no content, `_id`, URL or credential:

> nightscout-connect: A profile changed on the source Nightscout was not copied, because the
> destination Nightscout cannot replace that profile without keeping a second, outdated copy of it.
> New profiles are still copied. Updating the destination Nightscout fixes this for later changes;
> after updating it, saving the profile again on the source copies it.

"Saving again" is needed because the bookmark may already be past the edit.

### The reader-subject warning (`f924de2`, BF-98)

When the source already has a `nightscout-connect-reader` subject with no roles (earlier connector
versions created it that way), or refuses it with HTTP 401, the connector logs once:

> nightscout-connect: The source Nightscout already has a subject named nightscout-connect-reader, and
> it has no roles, so it cannot read any data. Earlier versions of nightscout-connect created it that
> way. To fix this on the source Nightscout, open Admin Tools and either add the "readable" role to
> nightscout-connect-reader, or delete nightscout-connect-reader so nightscout-connect creates it
> again. nightscout-connect does not change the source site itself.

The 401 form says the source "refused to let the subject … read data (HTTP 401)", with the same fix.

## Evidence

### Suite (`npm test`, Node 20.20.0, 22.23.2 and 24.20.0 alike)

| tree | passing | added |
|---|---:|---|
| `fbd4e55` (`v0.1.0-dev.2`) | 292/292 | |
| `f6359b4` | 304/304 | `test/profile-duplicate.test.js`, 12; 0/12 pass on `fbd4e55` |
| `f924de2` | 308/308 | 4 reader-subject tests; 3 fail on `f6359b4` |
| `1d2ebc8` | 319/319 | `test/profile-sync-bounded.test.js`, 11; 10 fail on `f924de2` |
| `de3cee1` | 334/334 | `test/profile-update.test.js`, 15; 10 fail on `1d2ebc8` (the other 5 guard existing behaviour) |

`log-call-sites` and `privacy-canary` pass unchanged. The tests that use a fixed time freeze `Date`,
so the suite does not depend on the wall clock: it passed at faked times across four time zones and
a DST change day, and an hour-by-hour sweep of the bounded-read tests fails at no hour. Without the
freeze, 2 tests fail between 20:00 and 24:00 UTC.

**Break-its** (each alone, on the final tree; each turned the named tests red):

- **skip set:** a swallowed profile write error, and a stored set not dropped after a failure;
- **bounded reads:** no explicit `startDate`, a full first read, no profile in effect at the window
  start, no newest-profile read, no dedupe by `_id`, no 404 fallback or one retried every poll, the
  internal bookmark not advanced or not seeded or advanced before the write, REST skipped rows not
  advancing the bookmark, and the REST bookmark set like the other collections;
- **update on change:** a replace without the guard (internal and REST), a version not remembered, the
  warning repeated, a fingerprint without `created_at` or with `srvModified`, a failed replace
  swallowed, stored copies not fingerprinted, and no replace at all;
- **reader-subject warning:** without its per-condition dedupe.

### Lab 1: the stall, with a same-source control

Source Nightscout `74fc6619`, `AUTH_DEFAULT_ROLES=denied`, one profile. Two internal-output sinks read
it through a counting proxy for 96 min: F with `f924de2` (packed and installed with a verified
lockfile integrity), C with `0.1.0-dev.2` from npm. The source was stopped for 15 min, a new profile
was added, and the original was edited.

| | F (`f924de2`) | C (`0.1.0-dev.2`, control) |
|---|---|---|
| poll cycles | 17, median 5.0 min apart | 4, median 28.9 min apart |
| newest reading behind the source, outside the outage | 0 min | 25–30 min max |
| E11000 / `Error saving profile data` (a full profile in the log) | 0 / 0 | 16 / 16 |
| records missing, duplicated or with field differences | 0 | 0 lost |

The control stalled, so the lab reproduces BF-97. F's longest gap was the existing retry backoff
after the source outage. At that commit an edited profile was not copied by design; `de3cee1` adds
that. A second pair showed the reader-subject warning once over 96 min of HTTP 401s.

### Lab 2: bounded reads and update on change

Source Nightscout `dev` `1f9a9d10` with 500 generated profiles plus live data. Ten sinks for 46–80
min: internal and REST outputs; empty or pre-loaded with the 501 profiles as string `_id`s (what every
earlier connector left); on 15.0.8, `dev`, the BF-99 branch `9b8cc2f9` and the #8758 candidate
`597e2899`. Seven edits were made on the source: editor saves, API `PUT`s of the newest and of an
older profile, and a new profile.

- **No `_id` twins on any sink**, at any sample.
- **Sinks with the object-id fix** (the BF-99 branch and the #8758 candidate) received every edit they
  could see. On pre-loaded sinks each replaced profile went from a string to an ObjectId `_id`. The API
  `PUT` of a profile that stopped being the newest 0.1 s later was seen by none.
- **Sinks without it** (15.0.8, `dev`) got new profiles, copied no edit to a stored profile, and
  logged the warning once per process.
- **Restarts** re-saved nothing unchanged.
- **Profile bytes per steady poll:** 6,851 on every sink, against 3,422,251 before.
- **Other collections:** entries, treatments and device status matched the source on every sink, with
  no duplicates or twins (at most one device status in flight at the final sample). Polls were
  4.7–5.3 min apart, the newest reading was 0 min behind, and every proxied request answered 200.

### Credentials in logs

A canary scan of every container's logs in both labs, and of the host-run REST connectors' logs,
checked every lab secret and token (raw and SHA-1): **0 hits**. On a REST sink, Nightscout's own
`PUT /api/v1/profile` handler logs the whole saved profile (`lib/api/profile/index.js:137`); the
in-process save logs nothing.

## Not covered

- A source on 15.0.8 (read-derived: it has `profiles.json`), and a source before Nightscout 14 (the
  404 path is unit-tested only).
- A sink with more than 1000 profiles (the stored set is read with count 1000).
- A profile deleted on the sink while syncing: the cached set means it is not re-inserted until a
  restart or a failed profile write (read-derived).
- A real sink-side twin (string plus ObjectId) under the guard: unit-modelled only.
- Real profile sizes and compression; the lab profiles compress unusually well.
- Vendor sources, other than the LibreLinkUp fixture lab (passed on `f924de2`).
- A soak as long as the `0.1.0-dev.2` soak (4 h 23 min), or source outages in lab 2.
- **Open:** the update warning names no Nightscout version; once a release contains #8758, the
  release notes can name it.
