# `bf/alarms` — an urgent insulin-age alarm that could never fire, and two delivery defects

Three commits on `origin/dev` `a8888f0d`, tip `5dcf783f`. 8 files, +400/−22, of which four are
test files. No `CHANGELOG.md` edit. Merges clean against `dev` and against every other open Phase 0
branch.

> **This one needs an explicit yes, not just a review.** It makes an alarm start firing that has
> never fired in any deployment, **and it removes a capability with no replacement** (per-request
> locale on the Alexa and Google Home endpoints). Both are the intended end state, but they are
> decisions rather than typo fixes, and an operator cannot undo either through configuration.

## What changes for you

**If you use the Insulin Age plugin with alerts turned on, you will start getting an URGENT
alarm you have never received before.**

Nightscout lets you set an age — by default 72 hours — after which your insulin reservoir is
"urgently" overdue for a change. Because of a one-word mistake in the code, that urgent alarm
has **never** been sent, in any release, to anyone. You may have set that threshold years ago
and never seen it honoured. After this change it works as documented.

Two things follow from that, and both are worth knowing before you upgrade:

- **There is no grace period.** If your reservoir is already past the threshold when you
  upgrade, the urgent alarm fires. That is deliberate, and the reasoning is under
  "Why no grace period" below.
- **The severity of what you already saw was also wrong.** Past the threshold the plugin was
  reporting the lower "warning" level for as long as the reservoir stayed overdue — not only
  during the hour the urgent notification would have fired. So this is not just a missing
  alarm; it is a level that was understated the whole time.

This alarm only reaches you if you have already turned Insulin Age alerts on
(`IAGE_ENABLE_ALERTS`). If you have not, nothing about your alarms changes.

**Two smaller changes in the same branch:**

- **A plugin name in `ENABLE` that Nightscout does not recognise is no longer silently
  ignored.** If you wrote `insulinage` where Nightscout expects `iage`, the plugin simply did
  not load and nothing told you. You now get a suggestion in the server log naming the plugin
  it thinks you meant. **Your existing settings are not changed and nothing is renamed for
  you** — this only adds a message.
- **Voice assistant replies (Alexa, Google Home) are now always in your Nightscout's
  configured language.** Previously a request could be answered in the language that request
  asked for. That sounds like a feature, and it was removed on purpose — see below.

> **Read this if you use Alexa or Google Home with Nightscout.** Before this change, a single
> voice request that named a language **re-pointed the language for the whole Nightscout
> process** — not just for that one answer. Every later page render, every later alarm text
> and every later voice reply used that language until something changed it back. So one
> request in French could leave your alarms in French. The fix removes per-request language
> handling entirely: replies now always use your server's configured language. **If you
> relied on asking in a second language, that no longer works.** There is no replacement in
> this changeset.

Nightscout is not a medical device and none of this is medical advice. If a change in when you
are alerted about insulin or site age affects how you manage your therapy, talk it through with
your care team.

---

## The commits

| commit | what |
|---|---|
| `8714093b` | `insulinage`'s urgent branch tested a field that is never set (**BF-28**) |
| `99e46a52` | an `ENABLE` entry naming the plugin's file instead of the plugin is silently ignored (**BF-29**) |
| `5dcf783f` | one assistant request re-languages the whole process (**BF-31**) |

Each lands alone; there is no ordering constraint inside the branch.

### BF-28 — the urgent branch is unreachable

```
lib/plugins/insulinage.js:92    if (insulinInfo.age >= insulinInfo.urgent) {
lib/plugins/insulinage.js:93      sendNotification = insulinInfo.age === prefs.urgent;
```

`urgent` is assigned on `prefs` (`:19`, `sbx.extendedSettings.urgent || 72`) and never on
`insulinInfo`. Line 92 evaluates `age >= undefined`, which is always `false`. Line 93, one line
below, reads `prefs.urgent` correctly. All three sibling age plugins — `cannulaage`,
`sensorage`, `batteryage` — use `prefs.urgent` on both lines. The fix is that one identifier.

Measured through the real sandbox at four ages: at 72 h the plugin requested nothing before, and
the URGENT overdue notification after. At 80 h, and at every age past the threshold, it reported
level **WARN** rather than URGENT — so the severity was wrong for the whole time the reservoir
stayed overdue, not only at the boundary.

**Why no grace period**, argued from evidence rather than taste:

- the notification is already gated on the operator having set `IAGE_ENABLE_ALERTS`;
- the README documents `IAGE_URGENT` as issuing exactly this warning;
- `cannulaage` has always fired on the identical default of 72, so the behaviour is not novel
  to the product, only to this plugin;
- a grace keyed on "the threshold was set explicitly" would leave the most exposed operators —
  the ones who enabled alerts and trusted the default — exactly where the bug left them.

### BF-29 — an unrecognised `ENABLE` entry is silently ignored

Matching is against `plugin.name` (`bwp`, `cage`, `iage`, `sage`, `bage`, `basal` — six aliases),
not against the file name. `ENABLE=insulinage` loads nothing and says nothing. The branch adds a
suggestion based on edit distance.

**Known limitation, measured.** The suggester is silent on a stock settings string — `food`,
`bridge`, `delta`, `devicestatus` and `cors` produce no suggestion — while all six file-name
aliases and near-misses such as `pushove` do. It helps the case it was built for and does not
chatter on correct configuration.

### BF-31 — a voice request re-languages the whole process

`ctx.language.set(locale)` and `moment.locale()` are process-global, and `POST /api/v1/alexa` and
`POST /api/v1/googlehome` called them per request.

Worth stating because it narrows the claim: this is a **shared-state** defect, not an alarm-text
one. The alarm catalogue is loaded once at boot, so the leak does not reach alarm text through the
catalogue. It reaches every later render and reply that resolves a string at request time.

## Verifying it

```
TEST=insulinage       npm run test-single    #  5 passing   (no database)
TEST=plugins          npm run test-single    # 13 passing   (no database)
TEST=api.alexa        npm run test-single    #  4 passing   (needs MongoDB)
TEST=api.googlehome   npm run test-single    #  2 passing   (needs MongoDB)
```

Re-measured 2026-09-16 on `5dcf783f`, all four green.

Each is ablated, restoring the file it covers to `dev` and re-running:

| restore to `dev` | result |
|---|---|
| `lib/plugins/insulinage.js` | `TEST=insulinage` → 3 passing / **2 failing** |
| `lib/plugins/index.js` | `TEST=plugins` → 5 passing / **8 failing** |
| `lib/api/alexa/index.js` | `TEST=api.alexa` → 3 passing / **1 failing** |
| `lib/api/googlehome/index.js` | `TEST=api.googlehome` → 1 passing / **1 failing** |

The first two are database-free and give the same counts against a dead mongo port.

**`tests/api.alexa.test.js` and `tests/api.googlehome.test.js` are in neither `npm run test:unit`
nor `npm run test:integration`** — they are among the files only `npm run test-ci` reaches, which
is what `main.yml` runs. So a green `test:unit` is not evidence for BF-31, which is the commit that
makes this branch a major.

## Semver: major

The driver is not the alarm. It is the **removal of per-request locale handling from two HTTP
endpoints** with no replacement in the same changeset: a request carrying `request.locale` used to
be answered in that language and is now answered in the server's configured language. The removal
is correct — the mechanism was process-global — but it is a capability removal on a declared HTTP
surface, and that is what grades it.

**If Phase 0 should land as a minor, this is one of exactly three changes that would have to be
split out.** Dropping `5dcf783f` leaves BF-28 and BF-29, which are a clean minor.

The "What changes for you" text above is the release-note source; this branch adds no
`CHANGELOG.md` entry. **Three paragraphs must not be dropped from it:** the no-grace-period
warning, the note that the severity you already saw was understated, and the Alexa/Google Home
block — that last is the only part of this branch that takes something away from an operator who
was relying on it.

## Follow-ups deliberately not in this PR

- **The alexa `switch` has no `default`.** An unrecognised `request.type` calls neither
  `res.json()` nor `next()`, so the request hangs until the client times out. Low reachability,
  but it sits beside the `ctx.language.set(locale)` line this branch already changes, so **it
  would be cheaper to take it here than on its own** — flagged so the reviewer can ask for it now.
- **`plugins.isPluginEnabled` always returns `true`** — `find` returns `undefined`, compared
  against `!== null`. No caller today, so nothing observable.
- **`lib/authorization/storage.js:84` has an unguarded `console.log` on a request path**, printing
  request-derived values. Not introduced by this branch and not in a file it touches. It is
  repaired on the `bf/auth` branch, which is not yet open as a PR, so it is still live on `dev`.
