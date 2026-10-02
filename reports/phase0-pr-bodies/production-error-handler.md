<!-- Body of #8793, branch bf/production-error-handler at dc64e82d (one commit on dev 50bc1084). This comment is hidden on GitHub. -->
An error that reaches express's final handler no longer sends the client a stack trace or file paths from the server, unless the site runs with `NODE_ENV=development` (BF-73). One commit on `dev` `50bc1084`. The same code is in `v15.0.8`; the guard has been commented out since 2015 (`469d8687`, first in 0.7.0), so this is not a regression.

## What changes for you

*A plain-language summary for people who run their own Nightscout site, for themselves or for a family member. Nothing here is medical advice.*

**What was wrong.** When Nightscout hit an unexpected error, for example when an app sent a request it could not read, or when the database could not be reached, the error page or error reply it sent back included a technical trace of where in the program the error happened. That trace names folders on the computer or service where Nightscout is installed. Anyone who could reach your site could see it, without logging in, even with `AUTH_DEFAULT_ROLES=denied`. It did not reveal your glucose data, treatments or your API secret.

**What this change does.** Error replies now carry only the error code and a short message, such as "Unexpected end of JSON input" for a request that could not be read, or "Internal Server Error" for a fault inside Nightscout. The full details still go to your server's log, where you (or whoever helps you) can read them.

**Do you need to do anything?** No. Apps that send correct requests see no difference. If you develop Nightscout and run it with `NODE_ENV=development`, you still see the full trace as before.

## Technical detail

### The defect

`lib/server/app.js` mounted `errorhandler()` (the express development error handler) last in the chain with its `if (process.env.NODE_ENV === 'development')` guard commented out. `errorhandler` answers with the error message and `err.stack`: an HTML page, `text/plain`, or, when the client accepts JSON, `{"error":{"message", "stack", ...every enumerable property of err}}`. So every error passed to `next(err)` or thrown in a route showed absolute install and `node_modules` paths. Two classes reached it:

- body-parser failures, which run before authorization: a malformed JSON body answered 400 with 10 stack frames, under `AUTH_DEFAULT_ROLES=readable` and `denied` alike (body-parser's error also carries the raw request body, which `errorhandler`'s JSON copied back);
- storage faults passed to `next(err)` (for example the v1 entries by-id read and the v1 DELETE handlers), which answered 500 with the driver error and its stack.

### What the commit does

The final handler comes from a new `lib/server/error-handler.js`:

- `NODE_ENV=development`: express's `errorhandler()`, unchanged.
- Anything else, **including `NODE_ENV` unset**: a small production handler. The Docker image sets `NODE_ENV=production`, but other hosts may leave it unset, so only an explicit `development` shows stacks.
  - Status: `err.status` or `err.statusCode` if it is 400-599, else an existing 4xx/5xx `res.statusCode`, else 500 (the same order as `errorhandler`).
  - Message: for a 4xx whose error is marked safe to show (`err.expose === true`, as body-parser and http-errors set it) the error's own message; otherwise the standard reason phrase (`http.STATUS_CODES`). A 5xx always gets the reason phrase.
  - Shape: content-negotiated as `errorhandler` does (`html`, `json`, `text`, HTML by default). JSON keeps the top-level `error` object with `message`, so a client that reads `error.message` keeps working, and adds `status`: `{"error":{"message":"...","status":400}}`. Nothing else from the error object is copied. HTML is escaped. Text is `<status> <message>`. `X-Content-Type-Options: nosniff` is kept.
  - The full error is logged with `console.error` with the method and URL, except under `NODE_ENV=test` (as `errorhandler` did).
  - If headers have already been sent, the error is passed to `next(err)`, so express's own final handler closes the connection.

No test or document relied on stack output.

### Not changed here

Handlers that answer errors themselves through `res.sendJSONStatus(res, 500, 'Mongo Error', err)` (entries, profile, food, activity, devicestatus, authorization endpoints) or `'Query Error', err.message` (treatments) do not reach the final handler. They send no stack, but they do put the driver error object or its message in `description`; with MongoDB unreachable that is the topology description, or a message naming the database host and port. That is a separate follow-up.

## Tests

`tests/error-handler.test.js` (13 cases):

- Full app booted with `authDefaultRoles = 'denied'`: a malformed JSON POST to `/api/v1/treatments` answers 400 with no stack, no `node_modules`, no absolute path and no stack-frame line, as JSON (exactly `{error:{message,status}}`), HTML and text; a storage fault on an authorized v1 treatments DELETE answers a generic 500 in JSON and HTML without the error's message.
- Handler unit cases: exposed 4xx message kept (413); unexposed 4xx gets the reason phrase; a 5xx never shows its message even if marked exposed; a non-error value or out-of-range status gives 500; HTML is escaped; the full error is passed to the logger; headers already sent hands off to `next(err)`; `NODE_ENV=development` still returns `errorhandler` with the stack; `NODE_ENV` unset gets the production handler.

With `dev`'s `app.js` the four full-app cases fail on the stack in the response; the unit cases exercise the new module directly and pass on both.

### Validation (Node 22.23.2, MongoDB 7.0 in a dedicated container)

- Full suite (`ci.test.env` form, fresh database): 3502 passing, 0 failing, 3 pending; the 13 added are this commit's.
- A local server with `NODE_ENV=production` and `AUTH_DEFAULT_ROLES=denied`: a malformed JSON POST answers 400 with `{"error":{"message":"Unexpected end of JSON input","status":400}}` (JSON), a plain HTML page or a one-line text reply, and the server log has the full error. With MongoDB paused, the v1 entries by-id read answers `{"error":{"message":"Internal Server Error","status":500}}`.
- ESLint on the three changed files: no new findings (6 existing warnings in `app.js` on lines this change does not touch). `git diff --check` is clean.
