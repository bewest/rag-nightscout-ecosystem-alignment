<!-- Body of #8795, branch bf/braces-expansion-cap (185e003a, merged with dev a143d507 as fdf88f4e). This comment is hidden on GitHub. -->
A brace pattern in `/api/v1/times` or `/api/v1/slice` that would expand to more than 2000 patterns is now refused with 400, before anything is expanded (BF-151). One commit on `dev` `50bc1084`. The same code is in `v15.0.8`, so this is not a regression.

## What changes for you

*A plain-language summary for people who run their own Nightscout site, for themselves or for a family member. Nothing here is medical advice.*

**What was wrong.** Nightscout has two little-used search addresses, "times" and "slice", that take a short pattern, such as "every day in July between 1 and 3 pm", and turn it into a list of searches. A pattern can be written so that it turns into millions of searches. Nightscout then spent seconds building them, and while it did, your site stopped answering everything else: the web page, your phone apps, uploads from your CGM uploader or closed-loop app. Anyone allowed to read your site's data could send such a pattern, which on sites that let anyone read (the default "readable" setting) means anyone with the address. No data was changed or exposed.

**What this change does.** A pattern that would turn into more than 2000 searches is refused straight away with a short error message saying so. Every pattern that turns into 2000 or fewer works exactly as before. The largest example in Nightscout's own documentation turns into 192; every minute of a whole day is 1440.

**Do you need to do anything?** No. If you have a tool or report of your own that uses these addresses with a very large pattern, split it into several smaller requests.

## Technical detail

### The defect

`lib/api/entries/index.js` `prep_patterns` serves `GET /api/v1/times/echo/:prefix?/:regex?`, `/api/v1/times/:prefix?/:regex?` and `/api/v1/slice/:storage/:field/:type?/:prefix?/:regex?`. It expands the `prefix` path parameter, and then `^prefix` joined with `.*regex`, with `braces.expand`, and compiles every result into a `RegExp` for an `$in` query. Chained brace groups multiply: N groups of ten alternatives give 10^N strings. braces 3.0.3 bounds each range (`rangeLimit`, 1000) and the input length (`maxLength`), but not the number of results, so a path of a few dozen characters could produce millions of patterns. The work is synchronous, so the event loop is blocked for the whole expansion and compilation.

Measured on `v15.0.8` and `dev` before this change: one request expanding to 10^6 patterns blocked the event loop for about 2 s. The routes sit behind `api:entries:read`, so they are reachable anonymously when `AUTH_DEFAULT_ROLES` includes `readable`, and by any read token under `denied`.

### What the commit does

Before each of its two `braces.expand` calls, `prep_patterns` counts the patterns the input would expand to, from the AST `braces.parse` returns, without expanding it:

- each brace list contributes its number of alternatives (commas + 1), and each range its length, found by expanding that one range on its own (so at most `rangeLimit` values);
- groups multiply; text, `${...}`, and groups braces itself treats as literal count as one;
- the count is exact for groups that are not nested; where a list contains another group, the inner group counts as if every alternative carried it, so the count is an upper bound there;
- counting stops as soon as it passes the limit, so a refused request does no expansion and compiles nothing.

If either count is over `MAX_BRACE_PATTERNS` (2000), the route answers through the router's `sendJSONStatus`, as the entries routes do for other bad input:

```json
{"status":400,"message":"Pattern too broad","description":"A brace pattern may expand to at most 2000 patterns"}
```

Under the limit the two `expand` calls receive the same strings as before, so the patterns, the query and the response are unchanged. Inputs braces already refuses (a single range over `rangeLimit`, input over `maxLength`) still fail as they did.

**Why 2000.** The documented examples in the route comments and `swagger.yaml` expand to at most 192 (`20{14..15}/T{13..18}:{00..15}`); the existing tests use at most 122 (`20{14..15}/T.*:{00..60}`). Every minute of one day, `{00..23}:{00..59}`, is 1440. 2000 is ten times the largest documented use and about 1/500 of the measured 10^6 case.

**Counter checked against braces.** Over about 435,000 generated patterns (lists, ranges with steps and padding, escapes, quotes, brackets, parentheses, `$`, unbalanced and nested braces), the count was never below `braces.expand(...).length`, matched it exactly for every pattern without nested groups, was higher for about 0.1% of the nested ones, and never threw where `expand` did not.

## Tests

`tests/api.entries.test.js`, a new `brace patterns are capped at 2000 expansions` block (the patterns are built in the test):

- a 10^6-pattern prefix on `/times/echo` and `/slice`, and a 10^6-pattern regex on `/times`, answer 400 naming the limit in under 500 ms;
- prefix and regex are counted together (100 × 60 is refused though each is allowed alone);
- 2001 patterns are refused; 2000 are expanded to exactly the list `braces.expand` gives;
- the documented example still gives its 192 patterns, first and last as before.

With `dev`'s `lib/api/entries/index.js` the five refusal tests fail: the three 10^6 cases take about 2.7 s each and answer 200 (`/times/echo`) or 500 (`/times`, `/slice`, after the expansion), and the two near-limit cases answer 200. The two at-limit tests pass on both.

### Validation (Node 22.23.2, MongoDB 7.0 in a dedicated container)

- Full suite (`ci.test.env` form): 3496 passing, 0 failing, 3 pending, against 3489 passing, 0 failing, 3 pending on `50bc1084`; the 7 added are this commit's.
- Local server, `NODE_ENV=production`, `AUTH_DEFAULT_ROLES=readable`, one large request with `/api/v1/status.json` sent 5 ms later:
  - this branch: 10^6- and 10^7-pattern inputs on `/times/echo`, `/times` and `/slice` each answer 400 in 1.0 to 3.0 ms; the concurrent `status.json` answers in 1.0 to 2.2 ms (1.3 to 7.4 ms with no other request);
  - `dev` `50bc1084`, same server: a 10^6-pattern input took 2.5 s on `/times/echo` (200) and 2.7 s on `/times` (500, the query too large for the driver), and `status.json` waited the same 2.5 to 2.7 s; a 10^7-pattern input ended the server process (JavaScript heap out of memory), on both routes tried.
- ESLint on the two changed files: no new findings (1 existing warning, on a line this change does not touch). `git diff --check` is clean.
