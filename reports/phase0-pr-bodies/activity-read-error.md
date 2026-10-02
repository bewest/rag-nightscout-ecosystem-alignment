<!-- Draft, not opened. Branch bf/activity-read-error at e20b66ba (one commit on dev 25fc41d9). This comment is hidden on GitHub. -->
When a database read fails on `GET /api/v1/activity` or `GET /api/v1/profile/current`, the request now gets an error reply and Nightscout keeps running (BF-155). Before, the failure ended the Nightscout process. One commit on `dev` `25fc41d9`. The same code is in `v15.0.8`, so this is not a regression.

## What changes for you

*A plain-language summary for people who run their own Nightscout site, for themselves or for a family member. Nothing here is medical advice.*

**What was wrong.** If Nightscout could not read from its database while answering a request for activity data or for the current profile, the error stopped Nightscout completely. Your site, and everything that reads from it (phones, watches, followers), was unavailable until Nightscout restarted. Most hosting services restart it automatically, but readings and alarms were missing in the meantime.

**What this change does.** That request now gets an error reply, and Nightscout carries on serving everything else. The details of the database error are written to the server log, not sent back in the reply.

**Do you need to do anything?** No.

## Technical detail

Both read callbacks are called from the promise handler in `lib/storage/run-with-callback.js`. When the read fails, the callback receives an error and a `null` result.

- `lib/api/activity/index.js` checked only for a refused query (`sendQueryValidationError`), then called `results.forEach`.
- `lib/api/profile/index.js` (`/profile/current`) read `records.length` without checking the error.

In both, the `TypeError` was thrown inside the promise handler. It became an unhandled rejection, and Node ended the process.

Each callback now checks the error first:
- a refused query still answers 400 as before;
- any other error is logged and answered with `500 Internal Server Error`, without the storage error's text.

A successful read is unchanged.

The food and profile list routes (`/api/v1/food`, `/api/v1/profile`) answer `null` with HTTP 200 when their read fails. That is wrong but does not end the process, so it is left for a separate change.

## Tests

`tests/api.read-storage-failure.test.js` replaces each storage read with one that rejects, delivered through `run-with-callback` exactly as the storage modules deliver a failure. For each route it checks that:
- the request is answered with a 500;
- the reply does not contain the error text;
- the server still answers `/api/status.json` afterwards.

With `dev`'s handlers, both requests are never answered: the test times out, which is the defect.

### Validation (Node 22.23.2, MongoDB 7.0.43 in a dedicated container)

- Full suite (`ci.test.env` form): 3534 passing, 0 failing, 4 pending, against 3532 on `25fc41d9`; the 2 added are this commit's.
- `tests/api.activity.test.js` and `tests/api.profiles.test.js` pass unchanged.
- ESLint on the changed files: no new findings (one existing unused-argument error at `lib/api/profile/index.js:31`, a line this change does not touch). `git diff --check` is clean.
