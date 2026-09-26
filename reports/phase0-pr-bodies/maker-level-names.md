<!-- Body draft for branch bf/maker-level-names at 2f50ada9 (tree 2489b490), one commit on dev e3adc91d. BF-125, issue #8104. This comment is hidden on GitHub. -->
IFTTT Maker alarm events are named `ns-warning`, `ns-urgent` and `ns-<level>-<name>` on every site, whatever its language. Fixes #8104 (BF-125, first half).

## What changes for you

*Plain-language summary for people running their own Nightscout site for themselves or a family
member. Nightscout is not a medical device and none of this is medical advice. Keep your phone's
and devices' own alarms on (for example the CGM app's low and high alarms); an IFTTT alert is an
extra, not a replacement.*

A few words used below:

- **IFTTT** ("If This Then That"): an outside service that can turn a message from Nightscout
  into a phone notification, a call, a smart-light flash, and so on.
- **Maker** (IFTTT "Webhooks"): the part of IFTTT that Nightscout sends to. Nightscout sends a
  named **event**, and each IFTTT **applet** you set up listens for one event name.
- **Language setting** (`LANGUAGE`): the language your Nightscout site shows its text in.

### What was wrong

If your Nightscout site's language is not English, the alarm events Nightscout sent to IFTTT
were named with the translated word for the alarm level. A Russian site sent `ns-осторожно`
instead of `ns-warning`; a German site sent `ns-warnung`. The Nightscout documentation tells you
to name your applets `ns-warning`, `ns-urgent`, `ns-warning-low`, `ns-urgent-high` and so on, so
those applets **never fired**. Only an applet on the general `ns-event` still worked.

### What this change does

- IFTTT alarm events on non-English sites now arrive under the documented names:
  `ns-event`, `ns-warning` / `ns-urgent`, and `ns-warning-low`, `ns-urgent-high` and the like.
  These are exactly the names an English site sends today.
- The text inside the alert (the title and message, sent as `value1` and `value2`) stays in your
  site's language.
- Nothing changes for English sites.

**What you should do:** nothing, if your applets use the names in the documentation. If you
renamed your applets to the translated names to work around this (for example `ns-осторожно`),
rename them back to `ns-warning` / `ns-urgent` after upgrading, or they will stop firing. Then
send a test alarm and check that it arrives. If you are unsure whether your alerts are set up
correctly, keep relying on your CGM app's own alarms and ask your care team how you should be
alerted.

**Not changed here:** when a send to IFTTT fails (IFTTT cannot be reached, or the connection
drops), Nightscout tries the same alarm again at its next check, about every 30 seconds to a
minute, until a send succeeds. This is how Nightscout has always handled a failed alert, and it
is kept on purpose so that a failed alarm is not silently dropped. See "Resend" below.

---

## Technical detail

### Mechanism

`lib/server/pushnotify.js` `sendMakerEvent` set `event.level = levels.toLowerCase(notify.level)`.
`lib/levels.js` `toLowerCase` is `toDisplay(level).toLowerCase()`, and `toDisplay` runs the
English label through `levels.translate`, which `lib/server/bootevent.js:247` points at
`ctx.language.translate`. `lib/plugins/maker.js` `makeRequests` then builds `ns-event`,
`'ns-' + event.level` and `'ns-' + event.level + '-' + event.name`.

The fix adds `levels.toKey(level)`: the untranslated lower-case label from the same
`level2Display` table (`urgent`, `warning`, `info`, `low`, `lowest`, `none`, and `unknown` for
anything else), and `sendMakerEvent` uses it. For every level, `toKey` equals what
`toLowerCase` returns with English translation, i.e. what English sites send on 15.0.8; the test
`levels.toKey equals the English toLowerCase for every level` pins that. The documented contract
is `README.md:789-790` and `docs/plugins/maker-setup.md:54-59`.

`event.name` (`notify.eventName || notify.plugin.name`) is already untranslated: `simplealarms`
and `ar2` set `'high'` / `'low'`, `boluswizardpreview` sets `'bwp'`, others fall back to the
plugin name. `ns-allclear` has no level.

### Other users of the translated level label (server side)

Checked every server-side caller of `levels.toDisplay` / `levels.toLowerCase` on dev `e3adc91d`
(`grep -rn "toDisplay(\|toLowerCase(" lib` filtered to levels):

| caller | output | kind | changed |
|---|---|---|---|
| `lib/server/pushnotify.js` `sendMakerEvent` | IFTTT event name | **machine contract** | **yes** |
| `lib/notifications.js` `getAlarm` (`Alarm.label`) | console log line only | display (log) | no |
| `lib/notifications.js` all-clear `message`, `notifyToView`, `snoozeToView` | notification text / console log | display | no |
| `lib/plugins/simplealarms.js`, `ar2.js`, `boluswizardpreview.js`, `dbsize.js`, `upbat.js`, `treatmentnotify.js` | notification `title` (also Pushover title, Maker `value1`) | display | no |
| `lib/client/index.js:732` | browser text | display (client) | no |

Pushover (`lib/plugins/pushover.js`) uses the numeric level for priority and retry, not the
label. The websocket and API v3 alarm socket (`lib/api3/alarmSocket.js:251-256`) emit the numeric
`level` and choose the event (`alarm` / `urgent_alarm`) from it. Alexa and Google Home speech is
built by the plugins' virtual-assistant handlers and does not call these functions; it stays
translated.

### Resend (BF-125 second half): unchanged, by design

`emitNotification` stores the alarm's dedup key for 30 s before sending (`pushnotify.js:50`);
only a successful Pushover send (`:100`) or Maker send (`:141`) extends it to 15 min. The code
comments from the original implementation (`f805633f`, `ea745065`, 2015) say this is intended:
"add the key to the cache before sending, but with a short TTL" and "after successfully sent,
increase the TTL". A failed send is retried; that is the safety property for an alarm path.
This PR keeps it and pins it with two tests. Options for a later change, each a trade-off:

1. Keep as is (this PR): failed delivery retried every check; nuisance repeats of any trigger
   that did succeed before the failing one.
2. Extend the key on failure too (to 15 min or the snooze period): stops repeats, but a failed
   alarm is silently not retried for that long.
3. Bounded back-off (30 s, 1 min, 2 min, ... capped): fewer repeats, retries continue; needs
   per-key failure state.
4. Retry only the triggers that failed: `makeRequests` would track per-event success instead of
   one `async.series` result.

In the reporter's case the failing call was the one with the non-ASCII event name; with ASCII
names that cause is removed. Why IFTTT or the reporter's Node failed that call was not reproduced.

## Tests

New file `tests/maker-level-names.test.js` (11 tests). It wires `lib/language`, `lib/levels`,
the real `lib/plugins/maker` and `lib/server/pushnotify` as `bootevent.js` does, and redirects
`https.get` for `https://maker.ifttt.com/` to a local HTTP stub on 127.0.0.1 (nothing reaches
IFTTT):

- en, ru, de: a WARN alarm triggers `ns-event`, `ns-warning`, `ns-warning-low`; an URGENT alarm
  `ns-event`, `ns-urgent`, `ns-urgent-high` (6 tests).
- ru: `value1` keeps the translated title `Осторожно LOW`.
- `levels.toKey` under `de` is untranslated while `toDisplay` / `toLowerCase` stay translated;
  `toKey` equals English `toLowerCase` for every level.
- A successful send suppresses the same alarm at 45 s and sends it again at 16 min.
- A failing stub (connection reset): only `ns-event` is attempted, the alarm is held within
  30 s and retried at 45 s.

No existing test expectation changed.

Full suite on `2f50ada9`, Node 22.23.2, MongoDB 7.0.43 (version read from the server),
`npm test` with a local `my.test.env`: **3181 passing, 3 pending, 0 failing** (dev `e3adc91d`:
3170 passing, 3 pending, 0 failing; +11 new).

Probe `tools/lab/triage-2026-09/maker-language.js` (alignment repo): exit 1 on `e3adc91d`
(`ru: ns-event, ns-осторожно, ns-осторожно-simplealarms`, `de: … ns-warnung …`), exit 0 on
`2f50ada9` (all three languages `ns-event, ns-warning, ns-warning-simplealarms`); its en control
and 200-stub resend control pass on both.

## Break-its

Each fix hunk reverted singly, then the tests run (`maker-level-names`, `levels`, `maker`,
`pushnotify`, 23 tests):

| break | result |
|---|---|
| `sendMakerEvent` back to `levels.toLowerCase` | 5 fail; `expected [ 'ns-event', 'ns-осторожно', 'ns-осторожно-low' ] to equal [ 'ns-event', 'ns-warning', 'ns-warning-low' ]`, and `ns-внимание` for urgent: the reported symptom |
| `toKey` made to return the translated `toLowerCase` | 6 fail (the 5 above plus the `toKey` unit test) |
| dedup key held 15 min before sending (option 2 above) | 1 fails: the failing-stub retry test |
| success no longer extends the key | 1 fails: the 15-minute suppression test |
| all restored | 23 pass |

## Client impact

The Maker event name goes from Nightscout to IFTTT only; no Nightscout client reads it. Read,
2026-09-25: no match for `ns-warning`, `ns-urgent` or `maker.ifttt` in AndroidAPS, xDrip,
xdripswift, Trio, LoopWorkspace, NightscoutKit, LoopFollow, nightguard, openaps or
nightscout-connect; `oref0/bin/oref0-ifttt-notify` calls IFTTT itself with its own event name
and does not go through Nightscout. The only people affected are non-English sites using IFTTT
Maker: applets on documented names start firing; applets renamed to translated names stop
firing and need renaming back (release note).
