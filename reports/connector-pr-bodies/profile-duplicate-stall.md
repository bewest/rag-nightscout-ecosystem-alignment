<!-- DRAFT: not yet opened as a pull request. Branch fix/profile-duplicate-stall, commits f6359b4 and f924de2, based on dev fbd4e55 (v0.1.0-dev.2). -->

# DRAFT: Skip profiles the sink already stores instead of failing the poll; say once how to fix a reader subject that cannot read

## Who this affects

This is for people who use nightscout-connect to **copy data from one Nightscout site into another**
(`CONNECT_SOURCE=nightscout`). It fixes a problem in the 0.1.0 prereleases (`0.1.0-dev.1` and `0.1.0-dev.2`). Released
versions up to 0.0.13 do not have it.

**What people saw.** If the source site has a profile (basal rates, insulin sensitivity, carb ratios),
the destination site fell **20 to 35 minutes behind** the source, and up to 55 minutes after the source had been
unreachable. Nothing was lost: every reading, treatment and device status arrived in the end, and none was
duplicated. But anyone following the destination site, or relying on its alarms, saw old glucose data. The site
itself showed no error. The connector's log showed `Internal persistence failed` and `Polling frame failed` on every
poll, and the destination Nightscout's log printed the whole profile each time.

With this change the destination keeps up at the normal 5-minute cadence. The measured workaround before it, leaving
profiles out with `CONNECT_SOURCE_COLLECTIONS=entries,treatments,devicestatus`, is no longer needed.

**Profile changes are still not copied.** If you edit a profile on the source site, the destination keeps the
version it already has, as every earlier version of the connector did. A newly created profile is copied.

The second commit is for sites that copy from a source that **does not allow anonymous reads**
(`AUTH_DEFAULT_ROLES=denied`) using the source's API secret. If an earlier connector version created the
`nightscout-connect-reader` subject on the source, that subject has no roles and every read is refused with HTTP 401.
Upgrading does not repair it, and the connector does not change the source site. It now logs one message saying what to
do (the exact wording is below).

This is a software fix, not medical advice. If late data on a destination site affected treatment decisions or alarms,
talk to your care team.

## Cause

`808ab1c` ("Complete Glooko sync…", in both prereleases) made a failed write fail the poll, instead of logging it and
carrying on. That is correct for a write that really failed, and it stays.

But the Nightscout source reads **every** profile, with its `_id`, on every poll. Nightscout stores profiles with
`insertMany`, so from the second poll on, inserting a profile the destination already has fails with a duplicate-key
error (E11000). Before `808ab1c` that error was swallowed. After it, every poll fails, the connector retries 3 times and
then backs off toward its 30-minute cap, and a successful poll that would reset the backoff never happens.

The other collections do not hit this. For entries and treatments, the source reads only records newer than its
bookmark, and Nightscout's storage upserts. For devicestatus, whose storage does not upsert, the connector skips rows
not newer than what it knows is stored. Glooko profiles already had a check like that: the output reads the stored
profiles once and skips any whose `identifier` is stored.

## What changed

**`f6359b4`: profiles.** In both outputs (`lib/outputs/internal.js`, in-process; `lib/outputs/nightscout.js`, REST),
profiles that carry an `_id` go through the same check the Glooko profiles use, keyed by `_id` as well as `identifier`.
A profile already stored is skipped, not updated. A new profile is stored. There is no matching on error codes or
error text: every write failure, including a duplicate-key error the connector did not predict, still fails the poll.
After a failed profile write the stored set is read again on the next poll, so a profile stored by another writer in
between costs one failed poll, not a stall until restart.

Two behaviours for the reviewer to confirm:

- **Edited profiles are skipped, not overwritten.** This matches 0.0.13 in effect: its insert failed. Upserting by
  `_id`, as entries and treatments do, would start copying edits. That would be a behaviour change, so it is not done
  here.
- **The stored set is cached.** A profile deleted on the destination while the connector runs is not copied again until
  the connector restarts or a profile write fails. 0.0.13 would have re-inserted it on the next poll. Re-reading the
  stored profiles on every poll would remove this difference, at the cost of one more read per poll.

**`f924de2`: reader-subject warning.** `lib/sources/nightscout.js` logs one warning when the
`nightscout-connect-reader` subject it reuses has no roles, or when reads with a reused subject are refused with 401.
Each is logged once per process, and a 401 from a subject already reported as role-less is not reported again. Nothing
is written to the source site, and the message has no token, secret or URL in it:

> nightscout-connect: The source Nightscout already has a subject named nightscout-connect-reader, and it has no
> roles, so it cannot read any data. Earlier versions of nightscout-connect created it that way. To fix this on the
> source Nightscout, open Admin Tools and either add the "readable" role to nightscout-connect-reader, or delete
> nightscout-connect-reader so nightscout-connect creates it again. nightscout-connect does not change the source
> site itself.

> nightscout-connect: The source Nightscout refused to let the subject named nightscout-connect-reader read data
> (HTTP 401). To fix this on the source Nightscout, open Admin Tools and either add the "readable" role to
> nightscout-connect-reader, or delete nightscout-connect-reader so nightscout-connect creates it again.
> nightscout-connect does not change the source site itself.

## Evidence

Full record: `docs/60-research/remedial/connector-profile-sync.md` in the alignment repository.

**Tests.** `test/profile-duplicate.test.js` (12 tests) runs both outputs against a store that behaves like Nightscout's
`insertMany`. On `fbd4e55` all 12 fail with `Nightscout internal write failed` (code 11000) or `Nightscout write
failed`. The tests that a real failure (storage down, or an unpredicted duplicate) still fails the poll go red when the
profile write error is swallowed, and when the internal output goes back to 0.0.13's catch-all. Four new tests in
`test/nightscout-source.test.js` cover both warning triggers, GET-only access to the source, one warning over five
polls, and no warning for a subject that can read. The once-only test goes red with the dedupe removed.

| Node | `fbd4e55` | this branch |
|---|---|---|
| 20.20.0 | 292/292 | 308/308 |
| 22.23.2 | 292/292 | 308/308 |
| 24.20.0 | 292/292 | 308/308 |

`npm run test:librelinkup:lab -- fixture` passes (`ok: true`).

**Lab, 96 min.** One denied source with a profile, two destinations reading it through the same proxy with a
`readable` token: F runs this branch (`npm pack`, installed through a regenerated lockfile), C runs `0.1.0-dev.2`
from npm. The source was stopped for 15 min; a new profile was added and the original was edited during the run.

| | this branch | 0.1.0-dev.2 |
|---|---|---|
| poll interval, median | 5.0 min | 28.9 min |
| newest glucose behind the source, outside the outage | 0 min | up to 30 min (median 10) |
| records lost / duplicated / changed | 0 / 0 / 0 | 0 / 0 / 0 |
| new profile copied | yes | yes |
| edited profile updated | no | no |
| whole-profile log dumps | 0 | 16 |
| credential literals in logs (21 checked) | 0 | 0 |

After the outage this branch took 15 min to resume, which is the existing retry backoff after failed polls (unchanged
here). A separate pair left a role-less subject behind with 0.1.0-dev.1 and then ran this branch: 16 polls refused with
HTTP 401, the first warning above logged once, and only GET requests to the source.

## Not in this change

- Copying profile edits, deletions, or edits of other records from the source (not done by any version).
- Repairing the reader subject on the source site.
- The REST output was not run against a real Nightscout; the lab destinations use the in-process output.
