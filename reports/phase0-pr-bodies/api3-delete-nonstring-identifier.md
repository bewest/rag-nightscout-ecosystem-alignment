<!-- Draft body for branch bf/api3-delete-nonstring-identifier at 1c3aeb8c (one commit on dev ce7d754a), 2026-09-26. This comment is hidden on GitHub. Not opened; not pushed. -->
API v3 can delete a record whose stored identifier is `0` or `false` again (BF-142). One commit (`1c3aeb8c`, on `dev` `ce7d754a`). This is a regression from #8758 (the BF-117 fix) that was never released: `v15.0.8` deletes these records. Found while reviewing #8778. The maintainer decided on 2026-09-26 to fix it for 15.0.9. Storage, v3 reads, PUT and PATCH are not changed.

## What changes for you

*A plain-language summary for people who run their own Nightscout site, for themselves or for a family member. Nightscout is not a medical device, and nothing here is medical advice. Nothing here tells you how to dose. If your carb or insulin numbers look wrong, check them against the app that entered them and talk to your care team before you rely on them.*

A few words used below:

- **Record**: one saved item on your site, such as a glucose reading, a treatment (a carb entry, insulin dose, temporary target or note) or a device status from your pump or phone.
- **Identity**: a label an app stores on a record so that it can find the record again later. Usually it is a long string of letters and numbers.
- **API v3**: one of the ways apps talk to Nightscout. AndroidAPS uses it to add, change and delete records.
- **Soft delete**: Nightscout marks the record as deleted instead of erasing it, so it stops showing and stops counting.

**What was wrong.** Only in the development version of Nightscout: if a record had been stored with the number `0` or the value `false` as its identity, API v3 showed the record, but refused to delete it ("not found"). An app such as AndroidAPS that deletes a carb entry or insulin dose through API v3 would see its delete refused, and the record would keep showing on the site and keep counting in carbs on board and insulin on board.

No released version has this problem, and no app we checked stores these values: AndroidAPS sends a normal identity or none at all.

**What this change does.** API v3 now deletes a record by the id it shows for it, whenever the stored identity is empty in this way (missing, empty, `0` or `false`), as 15.0.8 did. A record with a real identity of its own is still only deleted by that identity, and a delete still never touches a different record.

**One case still refused, as before this fix.** If a record's identity was stored as a list (for example `[""]`), API v3 shows the list as its identity and still does not delete it by its other id. 15.0.8 did delete it. No app is known to store a list.

**Do you need to do anything?** No.

## Technical detail

### The defect

API v3 reads pass every record through `normalizeDoc`, which shows a falsy stored identifier (`!doc.identifier`) as the `_id`. GET and the delete's existence check use `filterForOne`, which matches the `_id` whatever the identifier is. The delete itself (`updateEveryForm` and `deleteEveryForm`) uses `filterForEveryForm`, whose `_id` fallback #8758's `cb7d4110` limited to records without an identifier of their own (BF-117) and #8778 widened to `null` and `""`, excluding arrays. A stored `0` or `false` is neither, so the soft and permanent DELETE matched nothing and answered 404 after the existence check had found the record. API v1 entries and devicestatus store any `identifier` value they are sent; v1 treatments refuse a non-string one, so a treatment gets there only by a direct write. `v15.0.8` `92d08342` used `filterForOne` for the delete and reached any record through its `_id`.

### What the commit does

`filterForEveryForm`'s `_id` fallback now takes exactly the stored identifiers `normalizeDoc` replaces by the `_id`: `{$in: [null, "", 0, false, NaN]}` (MongoDB's `null` also matches an absent field, and `0` matches every numeric zero, `-0` included). The values `normalizeDoc` keeps are the record's own identifier, which v3 GET shows, and they stay out of the fallback: a non-empty string (BF-117), arrays (#8778; `$in` would otherwise match their elements, so an array holding `""` or `null` is excluded by `$type`) and Decimal128 (the driver returns it as an object, which is truthy, so `normalizeDoc` keeps it). Every fallback clause still requires the `_id` to equal a form of the requested id, so no record under another `_id` can match. The rule: when v3 GET shows the `_id` as a record's identifier, soft and permanent DELETE by that `_id` find it; when GET shows a stored identifier, DELETE by the `_id` does not.

## Tests

`tests/api3.delete-every-form.test.js`, 30 new tests on a real MongoDB (v1 and v3 through supertest):

- **Fail on `dev` `ce7d754a` with the original symptom** (18; each failure read: `expected 200 "OK", got 404 "Not Found"` after GET answered 200 with the `_id` as the identifier): soft and permanent DELETE of a treatment stored with `0`, `-0`, `false` or `NaN`, and of an entry and a devicestatus written through v1 with `0` or `false` (JSON cannot carry `-0` or `NaN`); then GET answers 410 or 404. Also the two bystander tests below, whose target is stored with `0`.
- **Pass on both** (the controls): a treatment whose own identifier is `[null]`, `[""]`, `["","other"]`, `[0]`, Decimal128 `0` or a string is refused through its `_id`, soft and permanent, and is left valid (12); a DELETE of one record leaves records with identifier `null`, `""`, `0`, `false`, `NaN`, `[null]`, `[""]`, `["","other"]`, `[0]` or none under other `_id`s untouched (2, soft and permanent). #8778's tests for absent, `null` and `""` identifiers and for a matching `_id` with its own string or array identifier pass unchanged.

### Break-it

One change at a time, with the tests above: without `0` in the list, 10 red; without `false`, 6; without `NaN`, 2; without the array exclusion, 12 (#8778's four array tests and eight new ones); without the Decimal128 exclusion, 2; without the `_id` clause, 4 (the two bystander tests and the two twin-copy tests). Restored, 61 passing.

### Full suite

`npm test` on `1c3aeb8c`, fresh database: **3458 passing, 0 failing, 3 pending** (Node 22.23.2, MongoDB 7.0.43 read from the server). `dev` `ce7d754a` is 3428/0/3; the difference is the 30 new tests.

### Harness (alignment repo, `tools/lab/triage-2026-09/api3-empty-identifier-delete.js`)

Same probe on three trees:

| stored identifier | `v15.0.8` `92d08342` | `dev` `ce7d754a` | this branch `1c3aeb8c` |
|---|---|---|---|
| `0`, `false`: treatments stored directly, entries and devicestatus through v1 | GET shows `_id`; soft and permanent DELETE 200 | GET shows `_id`; DELETE 404 | GET shows `_id`; DELETE 200 |
| `[null]`, `[""]`, `["","other"]`, the same collections | GET shows the array; DELETE 200 | GET shows the array; DELETE 404 | GET shows the array; DELETE 404 |
| a record with its own string identifier, addressed by its `_id` | DELETE 200 | DELETE 404 (BF-117) | DELETE 404 |
| records under other `_id`s | - | untouched | untouched |

Every other line of the probe is the same on `ce7d754a` and `1c3aeb8c`.

### Not changed

API v3 PATCH and PUT look a record up with `identifyingFilter`, whose `_id` fallback needs the identifier absent. For a record stored with identifier `null`, `""` or `0`, PATCH by the `_id` GET shows answers 404 and PUT inserts a second record. That is the same on `v15.0.8`, `ce7d754a` and this branch, so it is not a regression, and it is left for a separate change.

## Client impact

AndroidAPS is the only client in the corpus that deletes through API v3; it sends string identifiers and omits a null one (read), so its deletes are matched as on `ce7d754a`. No client in the corpus is known to store an identifier of `0`, `false` or an array.
