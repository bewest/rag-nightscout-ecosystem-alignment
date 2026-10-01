<!-- Body of #8791, branch bf/date-filter-list at 350f6f09 (one commit on dev 3014f883). This comment is hidden on GitHub. -->
A list of dates under a collection's date field is now read one date at a time, so a v1 request that filters on several dates at once works instead of answering 500 (BF-108). One commit on `dev` `3014f883`. The same code is in `v15.0.8`, so this is not a regression. Found on 2026-09-23 by the 15.0.9 consumer-impact survey, which replays what known clients send.

## What changes for you

*A plain-language summary for people who run their own Nightscout site, for themselves or for a family member. Nothing here is medical advice.*

**What was wrong.** xDrip4iOS can delete glucose readings from your Nightscout site in bulk, up to 50 at a time, by listing the time of each reading. Nightscout answered every such request with an error and deleted nothing, so readings you deleted in the app stayed on your site, in the chart and in reports. Deleting one reading at a time, or a range of time, worked. No reading was changed or lost.

**What this change does.** Nightscout now deletes the listed readings, and only those. Any other app that asks for several readings or treatments by their times at once gets them, where it got an error before.

**Do you need to do anything?** No. Readings you deleted in xDrip4iOS before this update are still on your site. Delete them again from the app, or in Nightscout, if you want them gone.

## Technical detail

### The defect

`lib/server/query.js` `enforceDateFilter` rewrites every operand under the collection's date field (`opts.dateField`) to an ISO UTC string unless it reads as a number (`isNaN`). It treated each operand as a single date. For `$in` or `$nin` the operand is an array:

- a list of two or more values is `NaN`, so the function called `.replace` on the array, which threw `dateString.replace is not a function`; the request answered 500 and a DELETE removed nothing;
- a one-value list of timestamps passed only because `Number(['1758600000000'])` is a number;
- a list of ISO dates (for example `find[created_at][$in][]=…` on treatments) failed even with one value.

xdripswift sends `DELETE /api/v1/entries.json?find[type]=sgv&find[date][$in][]=<ms>&…` in chunks of 50 (`NightscoutSyncManager.swift`).

### What the commit does

The single-date rewrite moves into `normalizeDate`, unchanged, and `enforceDateFilter` applies it to each element when the operand is an array and to the operand itself otherwise. Numbers and numeric text are kept as they are (the schema walker has already made entries' `date` values numbers), other text is repaired and normalized to ISO UTC, and an invalid date in a list is refused with the same error as a single invalid date. Single operands take exactly the path they took before. An operand that is an object (for example `$not`) is handled as before.

## Tests

- `tests/query.test.js`: a 50-timestamp `$in` on entries keeps its numbers; an ISO `$in` and `$nin` on `created_at` are normalized element by element (cases taken from the existing single-date table, including the unescaped `+02:00` repair); a list holding an invalid date is refused.
- `tests/api.entries.test.js`: three readings are posted, a DELETE with two of their dates in `find[date][$in]` answers 200, and only the third remains.

With `dev`'s `query.js` all four fail (`dateString.replace is not a function`, and a 500 on the DELETE); the existing single-date cases pass on both.

### Validation (Node 22.23.2, MongoDB 7.0.43 in a dedicated container)

- Full suite (`ci.test.env` form): 3485 passing, 0 failing, 3 pending, against 3481 on `3014f883`; the 4 added are this commit's.
- A DELETE listing 50 of 60 posted readings deletes exactly those 50 (`deletedCount: 50`, 10 remain).
- `tools/queue/gates/bf108-date-in-list.js` (this repository's gate, building the entries query from a ref's own `query.js`): passes on this branch, fails on `dev` `3014f883`; its one-timestamp control passes on both.
- ESLint on the three changed files: no new findings (3 existing warnings on lines this change does not touch). `git diff --check` is clean.
