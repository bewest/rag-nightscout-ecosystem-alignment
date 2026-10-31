# Compatibility notes (draft): re-sent treatments and profiles in Nightscout 16.0.0, every path

*Contributor-facing outreach draft, 2026-10-31, from the maintainer's decisions of that day
([decisions](../../../../releases/cgm-remote-monitor-16.0.0/decisions.md), "Slice 6, socket treatments" and "Slice 6, socket
profiles"). Not sent. Companion to the [questions for controller and uploader authors](README.md) and the
[tconnectsync note](tconnectsync-profile-copy.md). Behaviour described here is decided and being built in the identity
work (cgm-remote-monitor draft PR #8879, slice 6); it is not on `dev` yet.*

**To:** maintainers of apps that upload treatments or profiles to Nightscout, over API v1, API v3 or the
websocket (AndroidAPS, including 3.4.2.x's older Nightscout client; Loop; Trio; xDrip+; xDrip4iOS; tconnectsync;
nightscout-connect)

## What changes in 16.0.0

Nightscout 16.0.0 matches a re-sent record to the stored one by its `identifier` first, on every write path
(API v1, API v3, the websocket and in-process). The rules below are the same whichever path your app uses.

1. **Treatments: a re-send replaces the stored treatment.** When a treatment you send carries the `identifier` of
   one already stored, the stored record is replaced by what you sent, not merged with it. A field you leave out
   is gone from the stored record. This is how API v1 already behaved; 16.0.0 makes the websocket and API v3 the
   same. Reason: apps re-send whole records and show a cleared field by leaving it out (for example, an ended
   override). Under a merge, the old field stayed, and caregivers' charts showed an ended override as still
   running.
   - **What to check:** if your app sends a partial treatment as an update, send the whole record instead.
   - **A consequence:** a field someone added to your app's treatment in the Nightscout careportal is lost when
     your app re-sends that treatment, as it already is over API v1.

2. **Profiles: a create with a different `startDate` is a new profile.** When a profile you create carries the
   `identifier` of a stored profile but a different `startDate`, Nightscout stores it as a new profile without
   that `identifier`, and logs a warning (with no values). With the same `startDate`, it is a re-send, and the
   stored profile is updated (its `store` replaced whole). This keeps profile history as it is today.
   - **What to check:** when you add a profile by copying the current one, delete `identifier` as well as `_id`,
     so the new profile is new by design and no warning is logged.

3. **Every other collection merges on match** (device status, entries, food, activity), as decided on 2026-10-29.
   A `null` in a merge removes that field.

## What we ask

- Tell us if your app relies on a socket treatment re-send being merged into the stored record.
- Tell us if your app sends a profile create that is meant to update an existing profile while changing its
  `startDate`.

Short answers are fine, and so is "we need to look".

## Open

Whether a re-created profile on the websocket revives a deleted one (Q-R) is not decided yet.
