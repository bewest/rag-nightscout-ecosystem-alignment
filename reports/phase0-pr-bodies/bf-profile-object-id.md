# `bf/profile-object-id`: a profile posted with its own `_id` can be edited, deleted and found by that `_id`

**DRAFT. Local branch, not pushed.** Branch `bf/profile-object-id` on `origin/dev` `1f9a9d10`, tip
`9b8cc2f9`, one commit. No `CHANGELOG.md` edit. Evidence:
[`docs/60-research/remedial/profile-object-id-2026-09-23.md`](../../docs/60-research/remedial/profile-object-id-2026-09-23.md).

| what changes | who can see it |
|---|---|
| a profile POSTed with a 24-hex `_id` is stored with an ObjectId `_id`, not a string | sites that receive profiles from the Nightscout connector's Nightscout source, and anyone restoring an export |
| editing (PUT) a profile stored with a string `_id` replaces it, leaving one profile, instead of adding a second one | the same sites, through the profile editor |
| `DELETE /api/v1/profile/:_id` and `find[_id]` work whichever form the `_id` is stored in | the same sites, and scripts that manage profiles |
| a POST without `_id`, and a POST with any other string `_id` (still 400), are unchanged | nobody; stated so a reviewer does not have to infer it |

---

## What changes for you

*Plain-language summary for people running their own Nightscout site. Nightscout is not a medical
device and none of this is medical advice. If your profile settings look wrong, check them with
your care team before relying on them.*

A few words used below:

- **Profile**: the saved settings Nightscout shows and uses for its reports and calculations,
  such as basal rates, insulin sensitivity and carb ratios. Nightscout keeps a history of them.
- **Profile editor**: the page in Nightscout where you view and change a profile.
- **Connector**: the part of Nightscout that copies data in from another service, including from
  another Nightscout site.
- **ID**: the label Nightscout gives each saved record so it can find it again.

### What was wrong

If your site received profiles **copied from another Nightscout site by the connector**, or you
**restored profiles from an export**, those profiles were saved with their ID written in a
different form from the one Nightscout uses to look profiles up. Nightscout could show them, but
could not find them again by that ID. So:

- **Editing** one of those profiles in the profile editor did not change it. It saved a
  **second copy** with your changes and **kept the old one** as well.
- **Deleting** it by its ID did not remove the old copy.

Nightscout's reports read every profile in the period you choose, so an old copy left behind can
be among the profiles a report reads. If you edited such a profile, the old settings may still be
stored next to the new ones.

### What this change does

- Profiles copied in or restored from now on are saved in the normal form.
- Profiles **already saved** the old way are fixed the first time you edit them: the edit replaces
  the old copy, and you are left with **one** profile holding your changes. Nothing is changed
  in your database until you edit or delete a profile yourself.
- Deleting such a profile now removes it, including a copy left by an earlier edit.

**What you should do:** nothing, for most sites. If your site receives profiles from another
Nightscout site through the connector, or you have restored profiles from an export, and you
have edited a profile there, look at your profile list after upgrading. If you see an old copy
of a profile beside the one you edited, you can now delete it from the profile editor. If you are
unsure which settings are correct, check with your care team.

---

## Technical detail

### The defect

`lib/server/profile.js` `create()` called `insertMany(docs)` with `_id` as given. The v1 route
accepts a 24-hex string `_id` (and refuses any other string with 400), so it was stored as a
string. `save()` (`PUT`) converts to ObjectId and upserts, so against a string-`_id` profile it
inserted a second document and left the original; `remove()` deleted only `{_id: ObjectId}`;
`find[_id]=<hex>` is converted to ObjectId by `lib/server/query.js` and answered `[]`.
`lib/server/treatments.js` has converted hex `_id`s to ObjectId for a long time; profiles never
did.

Reproduced on `origin/dev` `1f9a9d10` and on `15.0.8` `92d08342` with the new test file: stored
`_id` is a string, `find[_id]` returns 0, 2 documents after a PUT, 1 left after a DELETE (11 of
13 tests red on both trees, same assertions).

### What the commit does

All in `lib/server/profile.js`; no route changes.

- `create()`: a 24-hex string `_id` is stored as the ObjectId it names, unless that exact string
  is already a stored profile `_id`; then it stays a string, so the insert fails on the duplicate
  key as it always has instead of adding an ObjectId copy beside the original. This matters for
  a connector that re-sends every source profile on each poll to a sink that stored them on
  15.0.8. One indexed `find` on `_id` per create that carries hex ids.
- `save()`: after the ObjectId upsert, deletes the string form of the same id. Upsert first, so
  the profile is never absent between the two writes.
- `remove()`: `deleteMany` over the ObjectId and string forms.
- `query_for()` (behind `/api/v1/profiles`): an ObjectId `_id` equality also matches the string
  form.

No migration and no bulk write at boot. A string-`_id` profile is converted when it is next
edited.

**Non-hex string `_id`s** (for example a UUID) are unchanged: the v1 route refuses them with 400
before storage, as on dev and 15.0.8 (existing test). The storage layer leaves them as given
rather than dropping them as treatments does, because the connector calls `ctx.profile.create`
in-process and recognises already-stored profiles by `_id`; dropping it would copy every
source profile again on every poll.

### Tests

`tests/api.profiles.object-id.test.js`, 13 tests: create with a hex `_id` stores an ObjectId
(single and array); `find[_id]` finds it; PUT leaves one document with the new content; DELETE
removes it; POST without `_id` unchanged; profiles seeded with a string `_id` (lower and upper
case) are found, replaced by a PUT with one ObjectId document left, and deleted; a string
original plus an ObjectId twin collapses to one on PUT and is fully removed by DELETE; a re-sent
POST of an id stored as a string is refused and adds nothing.

Full suite, `mongo:7`:

| tree | Node 20.20.0 | Node 22.23.2 |
|---|---|---|
| `origin/dev` `1f9a9d10` | 2386 / 0 / 3 | 2386 / 0 / 3 |
| this branch `9b8cc2f9` | 2399 / 0 / 3 | 2399 / 0 / 3 |

No existing test expectation changed.

Breaking the fix:

| removed | red | symptom |
|---|---:|---|
| create conversion | 2 | stored `_id` is a string |
| save's delete of the string form | 3 | 2 documents after PUT |
| `find[_id]` dual match | 2 | 0 results |
| remove's dual match | 2 | 1 document left after DELETE |
| all three dual matches | 6 | the original symptoms |
| the "already stored as string" guard | 1 | re-sent POST answers 200 and adds a copy |

### Merges

No conflict with #8748, #8749, #8751, #8753, #8754, #8755, #8756 or `rc/15.0.9-additions-e`
`1b1977e0` (`git merge-tree`). #8748 and `1b1977e0` also edit `lib/server/profile.js`; both merge
cleanly, and the merged tree with `1b1977e0` passes the profile and count-parameter tests.
`chore/nightscout-modernization` has the same defect in the same code; `lib/server/profile.js`
auto-merges there.

### Not in this branch

- devicestatus, food and activity store a 24-hex `_id` as a string the same way (reproduced on
  dev and 15.0.8: a DELETE by id leaves the string document; food and activity PUT leaves two).
  Separate changes.
- APIv3's single-document filters (`filterForOne`, `identifyingFilter`) match `identifier` or
  an ObjectId `_id` only, so a profile still stored with a string `_id` is not found by
  `GET /api/v3/profile/<id>` until it has been edited through v1. Shared by every v3 collection.
- The websocket `dbAdd` path inserts `_id` as given for every collection. Not probed.
