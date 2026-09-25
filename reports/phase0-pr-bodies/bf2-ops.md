# `bf2/ops`: the bundled database could abort, an Alexa request could hang, and two guards

**DRAFT. Not pushed, not opened.** Branch `bf2/ops` on `origin/dev` `74fc6619`, tip `e6a50e9a`,
four commits. No `CHANGELOG.md` edit. Merges clean into `dev`. Ships in 15.0.9 (decided
2026-09-23, backfix-2 plan §1a). The combined run with the other 15.0.9 additions is recorded in
`docs/30-design/remedial/rc-15.0.9-integration-record.md`. The section "Tested together with
the other 15.0.9 changes" below is its posting summary.

| commit | what it fixes | who can see it today |
|---|---|---|
| `03fba725` | `docker-compose.yml`: the bundled MongoDB container could run out of open files and abort (register BF-10) | anyone who runs Nightscout with the bundled Docker Compose file |
| `af8eee45` | the Alexa endpoint answered nothing at all to a request type it does not handle | Alexa users, when Alexa sends such a request |
| `e72ba30d` | `plugins.isPluginEnabled` said yes for every plugin name | nobody: nothing calls it yet |
| `e6a50e9a` | the start-up error page crashed on an error with only a description (register BF-63, renderer half) | nobody on `dev`: no current caller produces that shape |

---

## What changes for you

*Plain-language summary for people running their own Nightscout site. Nightscout is not a medical
device and none of this is medical advice.*

A few words used below:

- **Docker Compose**: a way of running Nightscout and its database together from one file,
  `docker-compose.yml`, which ships with Nightscout.
- **MongoDB**: the database Nightscout stores your readings and treatments in.
- **Open files**: every collection and index MongoDB keeps is a file it holds open. The operating
  system limits how many one program may hold at once.

### If you run Nightscout with the bundled `docker-compose.yml`

**Your database can stop by itself.** Docker lets a container hold 1024 open files unless told
otherwise. MongoDB recommends at least 64000 and prints a warning at start-up when it has fewer.
When it runs out, it does not fail one request; it stops completely. Nightscout then cannot read
or save anything until the database is started again. To you it can look like lost data, but it is
not: the data is still there once the database restarts.

This change sets the limit to 64000 for the database container in `docker-compose.yml`.

**What you should do:** if you copied `docker-compose.yml` into your own set-up, add the same four
lines under your `mongo:` service:

```yaml
    ulimits:
      nofile:
        soft: 64000
        hard: 64000
```

Then recreate the container (`docker compose up -d`). To check it worked, look at the database's
start-up log: the warning `Soft rlimits for open file descriptors too low` should be gone.

If you run MongoDB some other way (MongoDB Atlas, a hosting provider, or MongoDB installed directly
on a server), this change does not affect you.

### If you use Nightscout with Amazon Alexa

Now and then Alexa sends Nightscout a kind of request that Nightscout has no answer for; for
example, a notice that Alexa could not use an earlier reply. Until now Nightscout sent nothing back
at all, and the request stayed open until Alexa gave up. Nightscout now answers straight away. It
says nothing, because Amazon does not allow a spoken reply to these requests. Your normal Alexa
questions ("what's my blood sugar?") work exactly as before.

### Everything else

The other two changes are internal and change nothing you can see today. One fixes a check that
always answered "yes". The other stops the "Nightscout is having trouble" start-up page from
crashing on one kind of error message that no current version produces. Both are there so that
future changes do not trip over them.

---

## Technical detail

Node 20.20.0. Full suite (`mocha --timeout 5000 --require ./tests/hooks.js --exit ./tests/*.test.js`
under `tests/ci.test.env`, connection string pointed at a local container), run back to back on
2026-09-22:

| tree | MongoDB | passing | failing | pending |
|---|---|---:|---:|---:|
| `origin/dev` `74fc6619` | 7.0.43 | 2386 | 0 | 3 |
| `bf2/ops` `e6a50e9a` | 7.0.43 | 2392 | 0 | 3 |

The difference of 6 is the six new tests: 1 plugins, 1 Alexa, 4 boot error page.

### `03fba725`: `ulimits` on the `mongo` service (BF-10)

`docker-compose.yml`'s `mongo` service (`mongo:5.0.32` on `dev` and `master`) had no `ulimits:`
block. Added `nofile: {soft: 64000, hard: 64000}`, the minimum MongoDB's production notes
recommend and the `recommendedMinimum` mongod itself reports.

Measured, starting **only the `mongo` service** from each tree's own compose file (own project
name, data directory in a scratch location, a loopback-only port from an override file, and
`restart: "no"` so a crash stays visible):

| compose file | `ulimit -n` in container | rlimit warning | full suite against it |
|---|---|---:|---|
| `origin/dev` | 1024 (hard 524288) | 1 | **mongod aborted** about 35 s in, container exit 14 |
| `bf2/ops` | 64000 (hard 64000) | 0 | three consecutive full runs, 2386 passing each, mongod still up |

The abort, from the container log on `dev`'s compose file (mongod 5.0.32): `WiredTiger error`
`error: 24` `WT_SESSION.create: __posix_directory_sync ... Too many open files`, then
`Fatal assertion` `id 23089` `msgid 50853` at `wiredtiger_util.cpp:574`, then
`aborting after fassert() failure`, signal 6. This is the same sequence the register records on
mongod 7.0.43. It was reached on the **first** run, not only on a second one.

`docker compose config` renders the block on this branch and not on `dev`.

After three runs against this branch's compose file, the container log had zero `Too many open
files` lines and zero fatal assertions. Both sides ran `origin/dev`'s test code, so the only thing
that differed was the compose file. The `dev` side is one run, which aborted; it was not repeated.

### `af8eee45`: a default for the Alexa request-type switch

`lib/api/alexa/index.js` switches on `req.body.request.type` with cases for `SessionEndedRequest`,
`LaunchRequest` and `IntentRequest` and no `default`, so any other type called neither `res.json`
nor `next()`.

What the default returns is taken from Amazon's documentation, not invented. A skill "can't return
a response to" `System.ExceptionEncountered` (AudioPlayer interface reference). It "cannot return
a response to" `SessionEndedRequest` (request types reference). AudioPlayer requests do not accept
`outputSpeech`. So the unknown-intent speech that `buildSpeechletResponse` produces would be the
wrong answer. The default mirrors the existing `SessionEndedRequest` branch exactly:
`res.json('')`, then `next()`, plus one log line naming the type.

Test (`tests/api.alexa.test.js`): posts `System.ExceptionEncountered` with a 2 s superagent timeout.
On `dev`: `Error: Timeout of 2000ms exceeded`. On this branch: 200, body `''`.

Not measured: how often Alexa sends such requests to Nightscout's skill in practice.

### `e72ba30d`: `isPluginEnabled`

`lib/plugins/index.js`: `return (p !== null)` on the result of `Array.prototype.find`, which
returns `undefined` on a miss, so it always returned `true`. Now `p !== undefined`. **Nothing
in the tree calls `isPluginEnabled`** (`git grep` finds only the definition), so no current behaviour
changes.

Test (`tests/plugins.test.js`): with `enable: ['careportal']`, asserts `careportal` is armed and `cage`
is not (so the test is about enablement, not registration). `isPluginEnabled('careportal')` is
true; `'cage'` and `'no-such-plugin'` are false. On `dev`: `AssertionError: expected true to be false`
at the `cage` assertion.

### `e6a50e9a`: the boot error page on an entry with no `err` (BF-63, renderer half)

`lib/server/booterror.js` built each line with `pick(obj.err, Object.getOwnPropertyNames(obj.err))`.
The argument is evaluated before `pick()`'s null guard, so `err` missing or `null` threw
`TypeError: Cannot convert undefined or null to object` and Express served its generic error page
in place of `error.html`. Now `err == null` renders the description with an empty detail line.

**Not reachable on `dev`.** All seven `bootErrors.push` sites in `lib/server/bootevent.js` pass a
non-null `err`. That includes `{desc: synopsis.join(' '), err}` (ES6 shorthand) and the two Mongo
sites, which pass `err.message` from an `Error` that `mongo-storage.js`'s `wrapConnectionError`
always builds with a message. The two err-less sites that do reach it are on the branch that
removes the built-in CareLink connection (`bootevent.js:330`, `:335` there). **That branch still
needs its own call-site fix.** This commit is the renderer half only.

Test (`tests/booterror.test.js`): renders through Express and EJS with four shapes. A string `err`
and an `Error` `err` render on both trees (controls). `{desc}` and `{desc, err: null}` fail on `dev`
with that `TypeError` (`booterror.js:27`) and render on this branch.

### Not in this branch

- `lib/authorization/storage.js` `console.log('Loading',opts)` (follow-up 4) is on `bf/auth`
  (`ce82f0cd`) and is deliberately not repeated here.
- `booterror.js` inserts `desc` and `err` into the page without HTML-escaping. Every current
  source is server-side configuration or an error message, not request input. This is noted
  here, not changed here.

### Tested together with the other 15.0.9 changes

On a local integration branch cut from `dev` `74fc6619`, this branch was merged fifth of eight:
after #8750, #8749, #8748 and #8751, and before `bf2/auth-hardening`,
`bf2/subject-edit-keeps-fields` and the connector pin. The merge had no conflicts. The full suite
went from 2421 to 2427 passing, with 0 failing and 3 pending, on Node 20.20.0 and MongoDB 7.0.43.
The difference is the six tests above, and no other test changed state. After all eight merges,
the full suite passes on Node 20, 22 and 24 against both MongoDB 4.4.24 and 7.0.43
(2508/0/3 each).

On the final integrated tree, each library change was reverted by itself to `dev`'s version, and
its test failed with the symptom described above:

| reverted | failing | message |
|---|---|---|
| `lib/plugins/index.js` | 1 of 14 | `AssertionError: expected true to be false` |
| `lib/api/alexa/index.js` | 1 of 5 | `Error: Timeout of 2000ms exceeded` |
| `lib/server/booterror.js` | 2 of 4 | `TypeError: Cannot convert undefined or null to object` at `booterror.js:27`; the two controls pass |

`docker-compose.yml` on the integrated tree is identical to this branch's. The compose abort
measurement was not repeated there.
