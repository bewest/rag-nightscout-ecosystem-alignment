# Upstream note (draft): tconnectsync, drop `identifier` when copying a profile

*Contributor-facing outreach draft, 2026-10-30, from a measurement on cgm-remote-monitor (identity work, slice 3
`c9b74404`). Not sent. Companion to the [questions for controller and uploader authors](README.md).*

**To:** tconnectsync maintainers
**Pins:** tconnectsync `7c4b2f4` (`tconnectsync/sync/update_profiles.py:208-215`)

## What happens

In its default add mode, tconnectsync adds a profile by deep-copying the site's current profile
(`GET /api/v1/profile/current`), deleting `_id`, setting a new `startDate`, `created_at` and `enteredBy`, and
POSTing the copy to `/api/v1/profile`. When the current profile was created over API v3, it carries the
server-computed `identifier`, and the copy keeps it. Measured: each add then stores another record holding the
same `identifier` (2 records, then 3); the source record is unchanged.

## What Nightscout 16.0.0 does

Nightscout 16.0.0 matches re-sent records on `identifier`, and adds a unique index on it. So that profile history is
kept, a v1 profile create that matches a stored profile by `identifier` but carries a different `startDate` is
stored as a new profile without the copied identifier, with a server-side warning (maintainer decision,
2026-10-30). tconnectsync keeps working unchanged.

## What we ask

When copying a profile to add a new one, delete `identifier` as well as `_id`, so each added profile is a new
record by design and no warning is logged.
