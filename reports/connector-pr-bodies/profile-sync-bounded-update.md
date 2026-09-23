<!-- DRAFT: not yet opened as a pull request. Branch fix/profile-sync-bounded-update, commits 1d2ebc8 and de3cee1, on fix/profile-duplicate-stall f924de2 (itself on dev fbd4e55 = v0.1.0-dev.2). Stacked: review after, or together with, fix/profile-duplicate-stall. -->

# DRAFT: Read only the profiles a poll needs from a Nightscout source; copy a changed profile when the destination can replace it in place

## Who this affects

This is for people who use nightscout-connect to **copy data from one Nightscout site into another**
(`CONNECT_SOURCE=nightscout`). A *profile* is the set of therapy settings Nightscout keeps (basal rates, insulin
sensitivity, carb ratios, targets). The destination site's reports use the profile that applied at each time.

**Less data on every poll.** Until now the connector downloaded **every** profile from the source site every five
minutes. On a site with 500 profiles that is about 3.4 MB each time. Now it downloads only the profiles that are new or
were saved since the last poll, plus the one in use: in the lab, about 7 KB per poll.

**Profile changes are now copied, on a destination that can take them.** When you save a profile in the source site's
profile editor, the destination gets the new version at the next poll. This needs the destination Nightscout to include
the profile `_id` fix (register BF-99; planned for 15.0.9). On an older destination (15.0.8, or the current dev branch),
copying the change would leave two versions of the same profile, one of them out of date, so the connector does not copy
it, and logs once:

> nightscout-connect: A profile changed on the source Nightscout was not copied, because the destination Nightscout
> cannot replace that profile without keeping a second, outdated copy of it. New profiles are still copied. Updating
> the destination Nightscout fixes this for later changes; after updating it, saving the profile again on the source
> copies it.

New profiles are copied either way.

**What a new destination starts with.** A destination that has no profiles yet gets the profiles that apply to the
same two days of history the connector copies for glucose and treatments: the one in use two days ago, and every one
that started since. It does not get the source's older profile history, and the source's older data is not copied
either.

**Make profile changes on the source site.** On Nightscout-to-Nightscout sync, profile edits made on the receiving
site are overwritten when the profile changes on the source, and can also be overwritten when the connector restarts.

**One limit to know about.** A profile changed on the source *without* the profile editor (for example by a script
that updates it through the API) is only noticed if it is the newest profile.

This is a software change, not medical advice. If a destination site's profile does not match the source, check the
profile on both sites before relying on the destination's reports, and talk to your care team about any settings
questions.

## What changed

**`1d2ebc8`: bounded profile reads** (`lib/sources/nightscout.js`, both outputs' profile bookmark).

`/api/v1/profile.json` ignores `find`; `/api/v1/profiles.json` applies it but adds `startDate >= now - 4 days` to any
query that does not name `startDate` (measured). So every read goes to `profiles.json` and names `startDate`:

| Situation | Reads per poll |
|---|---|
| no profile bookmark (the destination stores no profiles) | profiles with `startDate >=` the 2-day window start; the one profile with `startDate <` it |
| bookmark known | profiles with `created_at >` bookmark and `startDate >= 1970-01-01`; `profile.json?count=1` (the newest) |
| source has no `/api/v1/profiles` (HTTP 404; Nightscout before 14) | `profile.json?count=1000` as before, with one warning |

The bookmark is the newest `created_at` the output has stored or already handled. It only moves forward. The internal
output takes it from storage the first time profiles arrive; the REST output reads it at startup.

**`de3cee1`: update on change** (`lib/outputs/profile-sync.js`, both outputs).

Each output keeps a fingerprint per stored profile: a SHA-1 of its content without `_id`, `srvModified`, `srvCreated`.
`created_at` counts as content, since the editor sets it and an API `PUT` may not. A source profile with a stored `_id`
and a different fingerprint is replaced through the destination's profile save (`ctx.profile.save`, or `PUT
/api/v1/profile.json`), but only if a find by that `_id` (`ctx.profile.list_query`, or `profiles.json?find[_id]=`)
returns it. That find matches exactly the document the save will replace. On Nightscout without BF-99 it matches the
ObjectId form only, and connector copies there have string `_id`s, so nothing is replaced and nothing is duplicated.
On a Nightscout with BF-99 it matches both forms, and the save converts the string copy. Each version is checked once. A
failed find or save fails the poll. Glooko profiles (matched by `identifier`) are still skipped.

## Evidence

Full record: `docs/60-research/remedial/connector-profile-sync-bounded-update-2026-09-23.md`.

**Suite**, Node 20.20.0 / 22.23.2 / 24.20.0: 308 at `f924de2`, **319** at `1d2ebc8` (+11), **334** at `de3cee1` (+15),
0 fail, 0 skipped, on the real clock and under three faked system times and time zones. An earlier draft of the new
tests depended on the time of day (they failed between 20:00 and 24:00 UTC); they now freeze `Date` at their fixture
time. The code was not at fault. Ten of the 11 new tests in the first commit fail on `f924de2`. Ten of the 15 in the second fail on
the first commit, and the other five guard behaviour it already had. Every hunk was broken once and the matching test
went red (22 break-its, re-run at two faked times, plus one for the clock freeze).

**Lab**, synthetic data only. One source (dev `1f9a9d10`, 502 synthetic profiles of about 6.8 KB each, live glucose,
treatments and device status). Ten destinations: in-process and REST output, on BF-99 Nightscout (`9b8cc2f9` and the
15.0.9 candidate `597e2899`) and on Nightscout without it (dev `1f9a9d10`, `15.0.8`), both fresh and holding 501
string-`_id` copies from an earlier connector.

| | before (f924de2) | this branch |
|---|---|---|
| profile JSON read per steady poll | 3,422,251 bytes (measured, `count=1000`) | 6,847–6,851 bytes |
| first poll, fresh destination | same | 20,528–27,372 bytes (3–4 profiles) |
| editor save of a stored 41-day-old profile | not copied | copied at the next poll on the BF-99 destinations that held it; one profile, ObjectId `_id` |
| API `PUT` of the newest profile | not copied | copied on every BF-99 destination |
| any edit, destination without BF-99 | not copied | not copied, **0 twins**, warning once per process |
| duplicate `_id`s, every destination and collection | — | 0 |
| entries / treatments / device status on `597e2899` | — | all source records present (the newest device status in flight on one), none duplicated |
| poll interval | — | 4.7–5.3 min in steady state |

## Decided (maintainer, 2026-09-23)

- **The bound stays as built:** changes since the bookmark plus the newest profile each poll. An API `PUT` to a profile
  that is not the newest is not seen.
- **No backfill on first sync:** a new destination gets the profiles for the window it copies, and later changes.
- **The source wins:** edits made on the destination are overwritten when the source's copy changes (and at a restart
  if the profile is among those read then).

None of these needs a code change.

## Still open

- The warning text names no Nightscout version, because the BF-99 fix is not released yet.
