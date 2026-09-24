# Three alarm-delivery defects, fixed: one alarm that could never fire, one that could be off
# without anyone being told, and one request that re-languages the server

> **Snapshot, 2026-09-15, against `origin/dev` `a8888f0d` (branch `bf/alarms`). Historical: the fixes are merged into `dev` as PR #8739 (BF-28, BF-29, BF-31), not released. Contributor-facing. Current facts: [backfix register](../../30-design/remedial/nightscout-backfix-register.md).**

**Date**: 2026-09-15
**Under test**: `cgm-remote-monitor` @ `a8888f0d` (`origin/dev`), worktree
`externals/work/crm-bf-alarms`, branch **`bf/alarms`**
**Commits**: `8714093b` (BF-28) · `99e46a52` (BF-29) · `5dcf783f` (BF-31) — one per defect, each
independently landable and independently revertable
**Environment**: Node v24.15.0, `mongod` on port 27034, `mocha` against the shipping test harness
(`tests/hooks.js`), client bundle built so the suite is comparable to CI
**Confidence**: **measured**. Every claim below was produced by running the shipping modules, and
every check was ablated — the fix reverted, the test watched go red — before it was believed.
**Register**: [BF-28, BF-29, BF-31](../../30-design/remedial/nightscout-backfix-register.md)

---

## Verdict

All three reproduce. Two reproduce exactly as the register describes them; **BF-31 does not, and
the part that does not is the part the register calls safety-relevant.**

- **BF-28 is worse than the register says.** The dead branch does not only withhold the
  notification. Above the urgent threshold the plugin reports level `WARN` *forever*, so the
  reported severity is wrong for as long as the reservoir is overdue, not just for the one hour
  in which the notification would have fired.
- **BF-29 covers six plugins, not five.** `basalprofile` → `basal` is a sixth file-name/plugin-name
  mismatch the register does not list.
- **BF-31's alarm claim does not hold.** A Google Home or Alexa request does *not* change alarm
  text. `language.set` only records a language code; the translation catalogue is read once at
  boot and never reloaded, so `levels.toDisplay(URGENT)` still returns `Urgent` after a German
  request. What does leak process-wide, permanently and measurably, is `moment`'s global locale
  and the shared instance's `lang`/`speechCode`. The defect is real; the consequence is not the
  one written down. §7a item 5 inherits the same wrong claim and is corrected below.

A fourth thing was found and is **not** fixed here: `plugins.isPluginEnabled` always returns
`true`. See §5.

---

## 1. BF-28 — `insulinage`'s urgent branch had never executed

### Reproduction

`lib/plugins/insulinage.js:92` compared `insulinInfo.age >= insulinInfo.urgent`. `urgent` is
assigned on `prefs` (`:19`, `sbx.extendedSettings.urgent || 72`) and nowhere else, so the
comparison was `age >= undefined`, which is always `false`. Line 93, one line below, already read
`prefs.urgent`; `cannulaage:87`, `sensorage:141` and `batteryage:87` read `prefs.urgent` on both
lines.

Driven through the real `sandbox`, `ddata` and `notifications` with `IAGE_ENABLE_ALERTS` on and
the default `IAGE_URGENT` of 72, one insulin-change treatment at each age:

| reservoir age | level before | notification before | level after | notification after |
|---|---|---|---|---|
| 24 h | `NONE` | none | `NONE` | none |
| 48 h | `WARN` | `Insulin reservoir age 48 hours` / *Time to change insulin reservoir* | `WARN` | unchanged |
| **72 h** | **`WARN`** | **none** | **`URGENT`** | **`Insulin reservoir age 72 hours` / *Insulin reservoir change overdue!*** |
| **80 h** | **`WARN`** | none | **`URGENT`** | none |

The 72 h row is the register's claim, confirmed: at the urgent threshold the plugin requested
nothing at all. The 80 h row is the part the register does not mention — the level stays `WARN`
indefinitely past the threshold, because the branch that would have set `URGENT` is the dead one.
A notification fires only in the hour in which `age === prefs.urgent`, but the *level* is wrong
for every hour after it, and the level is what the pill, the status class and any consumer of the
plugin's reported severity use.

### Fix

`insulinInfo.urgent` → `prefs.urgent`. One identifier, matching three siblings.

### Non-vacuity

Two tests added to `tests/insulinage.test.js`: the 72 h urgent notification, and the level at
80 h. With the fix reverted:

```
1) trigger an urgent alarm when insulin reservoir is 72 hours old:
   TypeError: Cannot read properties of undefined (reading 'level')
   -- findHighestAlarm('IAGE') returned nothing at all
2) stay at the urgent level past the urgent threshold:
   AssertionError: expected 1 to be 2      -- WARN where URGENT was expected
```

The plugin is armed through `sbx.extendedSettings.enableAlerts`, not through `ENABLE`, so these
tests are not exposed to the BF-29 trap; the pre-existing 48 h test in the same file passes
throughout and is the control.

### Should it ship with a grace period?

**No, and the evidence is in the README.** The brief asked this to be argued rather than decided
silently.

The argument for a grace — only honour the threshold for operators who set `IAGE_URGENT`
explicitly — is that repairing the branch starts emitting an URGENT alarm nobody has ever
received. That is true. It is also true of a default `IAGE_URGENT` of 72, which is the value an
operator never touched.

Against it, and decisively:

1. **The gate is already explicit.** The notification is emitted only when `prefs.enableAlerts`
   is set (`:107`), i.e. only when the operator set `IAGE_ENABLE_ALERTS=true`. That is an opt-in
   to insulin-reservoir alarms, not to one of them. Those operators already receive the 48 h
   `WARN` from the same plugin.
2. **README documents the behaviour being restored.** `IAGE_URGENT` (`72`) — *"If time since last
   `Insulin Change` matches `IAGE_URGENT`, user will be issued a persistent warning of overdue
   change."* The fix makes the code do what the documentation has always promised.
3. **The sibling with the identical default already does this.** `CAGE_URGENT` also defaults to
   72 and `cannulaage` has always fired at it.
4. **A grace would preserve the bug for the people most exposed to it.** An operator who set
   `IAGE_ENABLE_ALERTS` and left the threshold alone is exactly the person who believes the
   overdue alarm is armed. Conditioning on an explicitly-set threshold would leave that person
   where they are now — silently unprotected — and would add a second invisible rule to a plugin
   whose defect was an invisible rule.

So: fix it plainly, and release-note it. Release-note text in §4.

---

## 2. BF-29 — an `ENABLE` entry that names the file is silently ignored

### Reproduction

`lib/plugins/index.js:140` matched `enable.indexOf(plugin.name)`. Scanning every plugin module
that `lib/plugins/index.js` requires and comparing the file name to the `name:` it registers gives
**six** mismatches, not five:

```
boluswizardpreview -> bwp      cannulaage -> cage      sensorage  -> sage
insulinage         -> iage     batteryage -> bage      basalprofile -> basal
```

`ENABLE=cannulaage insulinage sensorage batteryage boluswizardpreview basalprofile` registers
**zero** plugins and, before this change, produced no warning, no log line and no error.

`basalprofile` is the entry the register does not list. Its practical impact is smaller than the
others — `basal` is in `DEFAULT_FEATURES`, so it is on anyway — but the silence is identical.

### Fix

Warn at registration for an `ENABLE` entry that matches no plugin name, naming the plugin that
was probably meant: from an explicit file-name table, or from an edit-distance near-miss against a
registered name or a table entry.

```
ENABLE lists "cannulaage", which is not a plugin name, so nothing was enabled for it. Did you mean "cage"?
```

**The suggestion is deliberately conservative, and this is the part that took the work.** A first
cut warned about every unmatched entry. Measured against the full set of `ENABLE` features README
documents, plus the defaults `settings.js` adds, that produces **six warnings on a stock install**
— `delta`, `devicestatus`, `profile`, `bolus`, `basal`, `careportal` are either not plugins at all
or are registered on only the other side of the client/server split. A warning that fires on every
healthy install is noise, and noise is the mechanism by which the next defect of this shape gets
missed. So an entry with no plausible plugin behind it is passed over in silence.

A second cut, suggestion-only, still produced two false positives on a stock install: `food`
suggesting `loop` and `cors` suggesting `cob`, both at edit distance 2. Two edits is half of a
four-letter word. The tolerance now scales with the length of the entry (1 for ≤ 4 characters,
2 above), which removes both.

Measured after that change, over the 35 `ENABLE` features README documents plus the 13
`DEFAULT_FEATURES` plus `pushover`/`maker`/`webhook`, on **both** client and server registration:
**zero warnings**, 23 plugins armed on the server and 25 on the client. The six file names: six
warnings, each naming the right plugin, zero armed. Typos `cannualage`, `insulnage`, `careporta`,
`ar3`: four warnings, each naming the right plugin. `somethingnobodyshipped`: silence.

### Non-vacuity, including the proof the plugins were armed

This is the defect that makes alarm measurement lie, so the checks are ablated three ways.

1. **Remove the warning call** (restores today's silent behaviour): **7 of 13 tests fail.**
2. **Delete `batteryage` from the file-name table**: 2 fail — the `batteryage` case, and the
   table-completeness test that walks `lib/plugins/*.js` and asserts every file whose name differs
   from its registered name has an entry. That test is what stops a seventh mismatch from quietly
   reopening this.
3. **The corpus-vacuity trap itself.** The "stays quiet about every documented feature" tests
   assert that `cage`, `iage` and `bwp` are actually in the enabled list, because a run that armed
   nothing would also produce no warnings and would pass for the wrong reason. Re-arming that
   fixture by **file** name instead of plugin name — the exact mistake this guard exists to catch
   — turns both tests red:

   ```
   AssertionError: expected Array [ ... ] to ...   (armed list no longer contains cage/iage/bwp)
   ```

   So the guard catches the trap it was written for.

---

## 3. BF-31 — one assistant request re-languages the process, but not the alarms

### Reproduction, and where the register is wrong

`lib/server/server.js:31-33` builds **one** language instance for the process.
`lib/api/googlehome/index.js:22-28` and `lib/api/alexa/index.js:22-29` — the register names only
the first; **both routes carry the identical code** — took the caller's locale out of the request
body and wrote it into two pieces of process-wide state:

```js
ctx.language.set(locale);   // assigns lang + speechCode on the one shared instance
moment.locale(locale);      // global state inside the library
```

Driven directly: build the language instance and load localisation as `server.js` does, wire
`levels.translate = language.translate` as `bootevent.js:218` does, then run the two lines of the
Google Home handler for `de-DE`.

| | before | after the request | a later, unrelated caller |
|---|---|---|---|
| `language.lang` | `en` | **`de`** | **`de`** |
| `language.speechCode` | `en-US` | **`de-DE`** | **`de-DE`** |
| `levels.toDisplay(URGENT)` | `Urgent` | `Urgent` | `Urgent` |
| `levels.toDisplay(WARN)` | `Warning` | `Warning` | `Warning` |
| `translate('Carbs')` | `Carbs` | `Carbs` | `Carbs` |
| `moment(...).format('dddd')` | `Monday` | **`Montag`** | **`Montag`** |
| `moment(...).format('LLLL')` | `Monday, September 14, 2026 5:00 AM` | **`Montag, 14. September 2026 05:00`** | **`Montag, 14. September 2026 05:00`** |

**The leak is real and permanent** — nothing sets it back, so the process stays in the last
caller's locale until another caller changes it.

**The alarm-text claim is not.** `language.set` assigns `lang` and `speechCode` and nothing else;
the catalogue is loaded by `loadLocalization`, which runs once at boot and is never called again
on the server. `levels.translate` closes over the catalogue, so level names are unaffected. The
register's *"alarm level names included"* and §7a item 5's *"that is how alarm text reaches a push
notification"* do not survive the measurement.

**What the `moment` leak does reach**, traced rather than assumed. `moment` and `moment-timezone`
are the same object (`require('moment') === require('moment-timezone')` is `true`, verified), and
`ctx.moment` is `moment-timezone` (`bootevent.js:17`), so the global locale reaches every plugin.
Every locale-sensitive format in the server tree — `.from()`, `.format('LT'|'LLLL'|'dddd')` — was
enumerated. All of them are inside **virtual-assistant handlers** (`ar2`, `loop`, `openaps`,
`xdripjs`, `bgnow`, `basalprofile`, `virtAsstBase`). **No notification message built anywhere in
`lib/plugins` passes a date through `moment`**: `timeago` does not use `moment` at all; the three
age plugins use only `a.diff(b,'hours')`, which is a number; `pump`'s `buildMessage` concatenates
battery and reservoir displays. Pill text with `LT` and relative times is rendered client-side,
against the browser's own `moment`.

So the honest severity is: **one caller's locale changes the relative times in every later
assistant answer in the process, and permanently re-points the shared language instance.** It is a
cross-request state leak, not an alarm-text defect. Under multitenancy it becomes a cross-tenant
leak, which is why it belongs in §7a at all — but as a shared-state item, not as the alarm-text
item.

### Fix, and what is deliberately not fixed

The locale belongs to the request. It **cannot be scoped to one today**, and the reason is
structural: every virtual-assistant handler captures `var moment = ctx.moment;` at plugin *init*
(`ar2.js:18`, `loop.js:9`, `openaps.js:9`, `xdripjs.js:6`, `bgnow.js:9`, `basalprofile.js:6`,
`virtAsstBase.js:4`). A per-request locale cannot reach a closure captured at boot, so scoping it
properly means threading a locale through every handler in six plugins — several of which are
alarm producers. **That is a wider blast radius than the register's one-line framing, and it is
reported rather than done**, per the programme's first rule.

What this commit does: remove both process-wide mutations, from **both** routes. Nothing that
worked is lost — `language.set` never changed any text, and the relative times in an assistant
answer were only ever in the caller's language if that caller happened to be the most recent one.
The assistant now answers in the server's configured language, which is what every other response
in the process already does.

### Non-vacuity

`tests/api.googlehome.test.js` (new) and `tests/api.alexa.test.js` boot the real server through
`bootevent`, POST a `de-DE` request through `supertest`, and assert `ctx.language.lang`,
`ctx.language.speechCode` and `moment.locale()` are all unchanged.

Three guards against passing for the wrong reason: the test asserts the values were *not* already
German before the request; it asserts the response body is the expected English text, which proves
the route ran and handled the request rather than 404ing; and the route is reached only because
the test enables the plugin, without which `lib/api/index.js:71,74` does not mount it.

With the shipping route code restored, both go red:

```
Uncaught AssertionError: expected 'de' to be 'en'
Uncaught AssertionError: expected 'de' to be 'en'
```

---

## 4. Release note for BF-28

> **`insulinage` can now raise its urgent alarm. It never could before.**
>
> If you have `IAGE_ENABLE_ALERTS` turned on, you will now get an *"Insulin reservoir change
> overdue!"* notification when your reservoir reaches the age set by `IAGE_URGENT` — 72 hours
> unless you changed it. **You have not been getting this notification, on any previous version.**
> A single wrong word in the code meant the check could never be true, so the alarm was never
> sent, even though the setting was there and the documentation described it.
>
> You may also notice that the insulin-age pill now turns urgent, rather than staying at the
> warning colour, once the reservoir is past the urgent age. That is the same fix: the plugin was
> reporting the wrong severity for as long as the reservoir stayed overdue.
>
> Nothing else changes. The "Time to change insulin reservoir" warning at `IAGE_WARN` behaves
> exactly as before, and if you have not turned `IAGE_ENABLE_ALERTS` on you will see no new
> notifications. If the new alarm arrives at a time that does not suit you, `IAGE_URGENT` is the
> setting to adjust — and if you are unsure what reservoir-change interval is right for you, that
> is a question for your care team rather than for a configuration file.

---

## 5. Found and not fixed: `plugins.isPluginEnabled` always returns `true`

```js
plugins.isPluginEnabled = function isPluginEnabled (pluginName) {
  var p = enabledPlugins.find(plugin => plugin.name === pluginName);
  return (p !== null);
}
```

`Array.prototype.find` returns `undefined`, not `null`, when nothing matches, and
`undefined !== null` is `true`. The function therefore reports every plugin as enabled.

**No `BF-` id allocated, and it is not fixed here**, because it has no caller — it is exported on
the `plugins` object and referenced nowhere in `lib/` or `tests/`, so it fails the register's
first criterion (it does not affect anyone running the current release). It is recorded because
it is a **loaded gun pointed at exactly this area**: it is the obvious thing for the next
instrument to reach for when asking "is this alarm plugin armed?", and it would answer "yes"
every time. The armed-plugin assertions in §2 deliberately use `eachEnabledPlugin` instead.

---

## 6. Consequences for the multitenancy plan §7a

- **Item 5 (BF-31)** — the *defect* stands and the fix lands here, but **the stated consequence
  does not.** `language` and `levels.translate` being process-wide is not how alarm text reaches a
  push notification; alarm text does not move, because the catalogue is never reloaded after boot.
  Item 5 should be read as a shared-state leak (`moment`'s global locale, plus `lang`/`speechCode`
  on the shared instance), which is a genuine cross-tenant leak under `multi` and is what T3.3
  named. The row's wording is corrected in place.
- **Item 6 (BF-29)** — settled. An unmatched `ENABLE` entry now says so and names the plugin it
  thinks was meant. This does not by itself make per-tenant arming trustworthy; it removes the
  silence that made an untrustworthy answer indistinguishable from a correct one.
- **Neither item can be marked done by this work alone.** §7a's own rule applies: alarms go back
  on when a test shows tenant A's alarm reaching A and not B through the real producer path.
  What these two remove is the ability of such a test to pass vacuously.
- **A remaining §7a-adjacent hazard, unlisted**: scoping a locale per request is blocked by
  plugins capturing `ctx.moment` at init. Any per-tenant `ctx` will hit the same wall — a
  per-tenant `ctx.moment`, `ctx.language` or `ctx.levels` cannot reach a closure that captured the
  boot-time value. That is worth naming in phase 3/4 before a per-tenant `ctx` is designed.

---

## Honest limits

- **No live server was driven for BF-28.** The plugin was exercised through the real `sandbox`,
  `ddata`, `notifications` and `levels`, which is the whole of the path from data to a requested
  notification, but the delivery legs beyond that — `pushover`, `maker`, the web push path — were
  not exercised. The claim is that the plugin now *requests* the URGENT notification; that it is
  then *delivered* rests on the same machinery that already delivers its 48 h `WARN`.
- **BF-31's route tests do run against a booted server**, but only the unknown-intent and launch
  paths. No virtual-assistant handler that actually formats a relative time was driven end to end,
  so the assistant-answer degradation described in §3 (relative times now in the server's
  language rather than the last caller's) is reasoned from the enumeration of `moment` call sites,
  not observed in a response body.
- **The `moment` call-site enumeration is a grep, not a proof.** It covered `lib/server`,
  `lib/api`, `lib/api3`, `lib/plugins` and `lib/*.js` for `.format(`, `.from(`, `.fromNow(` and
  `.calendar(`. A locale-sensitive format reached by a path those patterns miss — a format string
  assembled at runtime, or a dependency formatting dates itself — would not have been seen.
- **`nightscout-connect` and the client bundle were not examined.** The client has its own
  `language` instance built from its own settings, so the server-side leak does not reach it, but
  that was read rather than measured.
- **The `ENABLE` false-positive measurement used README's documented feature list plus
  `DEFAULT_FEATURES`.** An operator using an `ENABLE` token that is neither documented nor a
  default — a fork's plugin, or a feature name that has since been removed — could still draw a
  spurious suggestion if it lands within the edit-distance tolerance of a registered name.
- **The suite has 21 pre-existing failures in this environment, and they are pre-existing.** On
  `bf/alarms` the unit selection is **332 passing, 21 failing**; the failures are `careportal`
  (a missing client bundle in a `before all` hook), `purifier` (13, all
  `InvalidCharacterError`), `security` (2 timeouts) and `verifyauth` (4 timeouts). The same four
  files checked out at pristine `a8888f0d` produce **the same 21 failures**, so none is caused by
  this work. The integration selection (`api`, `api.alexa`, `api.googlehome`, `notifications`)
  is green. The unit selection was not re-run on pristine `a8888f0d` in full — only the four
  failing files were — so the claim is "these 21 are pre-existing", not "the pristine unit
  selection is exactly 332/21".
- **Nobody has received the BF-28 alarm yet.** The strongest statement available is that the
  plugin now requests it in a test. The first real evidence will come from an operator with
  `IAGE_ENABLE_ALERTS` set, and that is the population the release note is for.
