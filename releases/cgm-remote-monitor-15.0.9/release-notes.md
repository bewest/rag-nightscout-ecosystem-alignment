# Nightscout 15.0.9 — release notes

**DRAFT — not yet released. Prepared for maintainer review; wording and version number may change.**

*For people who run a Nightscout site for themselves or a family member. Nightscout is not a
medical device, and nothing in these notes is medical advice or advice about insulin doses.
Where a change could affect decisions about your therapy, talk it through with your care team.*

> These notes complement the automatically generated changelog. The changelog lists what
> changed; these notes say what you will **notice**, what you must **do**, what to **check
> afterwards**, and what is **still broken**.

This is a bug-fix and security release. Most of what is in it is something that should
already have worked. A few fixes change what you see on screen, and one changes which alarms
can reach your phone, so please read the first section even if you usually skip release notes.

---

## Read this first: the insulin-reservoir urgent alarm starts working

Nightscout's **insulin age** feature (shown as the "IAGE" box on your page) tracks how long it
has been since you last recorded an insulin reservoir or cartridge change. It has a setting
for when the reservoir is "urgently" overdue — **72 hours unless you changed it** (the setting
is `IAGE_URGENT`).

**The urgent level has never worked, on any release.** A mistake in the code meant the check
could never be true. Past the threshold, the box showed the lower "warning" level for as long
as the reservoir stayed overdue. This release fixes that.

What changes, and for whom:

| | Who | What |
|---|---|---|
| **The IAGE box shows URGENT** | everyone who uses insulin age | From the threshold onward, and for as long as the reservoir stays overdue. No sound and no phone notification on its own. |
| **A notification: "Insulin reservoir change overdue!"** | **only** if insulin-age alerts are turned on (`IAGE_ENABLE_ALERTS`, which is **off unless you turned it on**) | A real alert, sent with the "persistent" sound on services that support sounds. |

**The notification is sent once and does not repeat.** It is sent only during the hour your
reservoir reaches the threshold, and only in the first 20 minutes of that hour. If your site
was not running then, or you upgrade after that window, **no catch-up alert is sent.** The
URGENT box on the page stays up while the reservoir is overdue — **the box is the thing to
watch**, not an alarm that will keep reminding you. This matches how the cannula, sensor and
battery age alerts already behave.

**What to do:**

- If you have insulin-age alerts turned on, **tell everyone who receives your Nightscout
  alerts** (a parent, partner, school nurse) that a new urgent alert may arrive, what it says,
  and that it is about the reservoir, not glucose.
- If you do not want the notification, turn `IAGE_ENABLE_ALERTS` off or raise `IAGE_URGENT`.
  Turning alerts off does **not** stop the box turning URGENT.

Nothing about your pump or insulin changes — only whether Nightscout tells you. This is not a
schedule for changing a reservoir; if you are unsure what interval is right for you, ask your
care team.

---

## Security fixes

**These fixes are in this release. Earlier releases, including 15.0.8 (the release most sites run today), are affected.**

1. **Sites set to require login could still send some data to visitors who had not logged
   in.** If you set `AUTH_DEFAULT_ROLES=denied` so that only people you have given access can
   see your site, the live-update connection could still send some device information (such
   as pump and phone battery, reservoir and loop status) and alarm and treatment notices to a
   visitor who had not logged in. If your site uses the standard setting where anyone with
   the address can already read it, this did not reveal anything new.
2. **A way to silence alarms for everyone was too permissive.** Any valid access token, even
   one meant only for reading, could silence alarms for every viewer. Silencing now requires
   the permission meant for it.
3. **The older web interface accepted some database commands it should have refused**,
   including ones that ask the database to run code, and one setting that let a request read
   from parts of the database it was not meant to reach. These are now refused. On a
   standard site this did not need a password.
4. **The "Nightscout readable by world" warning now appears when it should.** If you use the
   older `TREATMENTS_AUTH=off` setting, anyone with your address can read your data **and add
   treatments** without logging in. That is what the setting does and this release does not
   change it — but the admin warning that should tell you this was never shown. It is now.

**What to do:** upgrade. If you rely on `AUTH_DEFAULT_ROLES=denied` to keep your data private,
this release is the one that makes the live-update connection respect it. If you use
`TREATMENTS_AUTH=off`, read the new warning and decide whether you still want it.

---

## Other changes you may notice

### Bolus calculator quick picks

A *quick pick* is a saved meal in Nightscout's food editor (for example "Breakfast, 45 g of
carbs") that you can choose in the bolus calculator instead of typing carbs in.

**The list you choose from and the record that was loaded did not line up**, so choosing one
quick pick could load a different food's carbohydrate amount into the calculation, with
nothing on screen to say so. The list also offered plain foods that are not quick picks, and
choosing the last entry did nothing. This release fixes the mismatch. Hidden quick picks stay
hidden, the order follows the position numbers you set, and quick picks saved by other apps
are no longer left out of the list other apps can read.

**Known issue in the same place:** on this release the quick-pick list in the bolus
calculator may still show only "(none)", because the list is built before your food data has
loaded. A fix for that is being worked on; it depends on the fix above, which is why the two
are being released in this order. Until then, add foods from the database one at a time.

The bolus calculator is a calculator, not a recommendation, and this release does not change
that. **Always check that the carbohydrate amount shown is the one you meant.** If you think a
past calculation used an amount you did not choose, raise it with your care team.

### Searches, reports and filters return the right records

Some filters compared numbers as if they were words, so "temp basals of 30 minutes or more"
matched nothing and the site answered with an empty list instead of an error. Decimal amounts
such as "1.5 units or more" were rounded down to 1. A filter for records *without* a value
returned the records *with* it. Counting endpoints could return zero for everything. Paging
through newer-API results could skip some records and repeat others.

**What you will notice:** reports, dashboards and tools that use these filters may show
different numbers — often many more records than before.

> **Earlier results may have under- or over-reported delivered therapy.** If you have used a
> report or tool built on these filters to look back at insulin, carbs or temp basals, the
> numbers it showed may have been wrong. Nothing stored in your database was wrong; the
> question was being asked wrongly. This is not medical advice. If a corrected figure changes
> your understanding of a past period, discuss it with your care team rather than acting on it
> alone.

For a filter asking whether a value is present, only `true`, `false`, `1` and `0` are
understood. Other spellings, such as `null` or leaving the value empty, still mean "has the
value".

### Some requests now get a clear error instead of a wrong answer

This affects **apps and tools that talk to your site**, not the pages you look at.

- A request for "zero records" (or a count that is not a whole number, such as `abc`, `2.5` or
  `-3`) could return your **entire** history. These now get an error saying "Bad count".
  Ordinary counts such as 10 or 288 are unchanged.
- Filter conditions outside a fixed, supported list now get an error naming the condition,
  instead of a server error or a silent empty answer. A survey of 14 Nightscout apps found none
  that use a refused condition.

**What to do:** after upgrading, check that everything that sends data to or reads from your
site — uploader, phone app, watch, follower apps, scripts — still works. If one stops with an
error like "Bad count" or a refused filter, report it to that tool's author with the tool's
name and version (not your data). **If your glucose data stops arriving, use your meter or
CGM app and your usual routine while it is sorted out.**

### Pages that would not load

- A web address with a setting that has no value — `?mute` instead of `?mute=true`, or a
  stray `&` at the end — could leave the page stuck on "Loading" with nothing on screen. It now
  loads.
- Deleting one treatment while another update arrived could freeze the page until you
  reloaded. The "time since last reading" kept counting, so a frozen page looked stale rather
  than current. If your page ever stops advancing, reload it and check your pump, meter or CGM
  directly.
- On a first load the main chart could briefly render blank. That is guarded against.

**One side effect:** an underscore `_` in a web address is no longer turned into a space. If you
have a bookmarked link containing `_`, open it once and check it still does what you expect.

### Passwords and account names with leading zeros or a plus sign

Settings such as your Dexcom Share account name and password were converted to numbers if they
looked like numbers. A phone-number account name lost its leading `+`, and a password like
`007700` became `7700`, so logins failed. Credential settings are now kept exactly as typed.
Nothing needs changing in your settings.

### Quieter logs, and two new switches

Nightscout and its built-in CGM connector no longer write routine "heartbeat" and data-reload
messages to the log by default. Warnings and errors still appear. Two new settings turn the
detail back on when you are troubleshooting:

- `DEBUG_LOGGING=true` — more detail from Nightscout and the connector.
- `CONNECT_DEBUG=true` — more detail from the connector only (`CONNECT_DEBUG=false` turns the
  connector detail off even when `DEBUG_LOGGING` is on).

**The connector also stops writing your CGM account details and readings to the log.** On
15.0.8 and earlier, the built-in connector printed your CGM account login details, session
information and glucose data to the log every time it started, with no way to turn that off.
In this release it logs short summaries instead, with or without the debug switches.

> **If you have ever pasted a Nightscout log from an earlier release into a public place**
> (a forum, an issue, a chat), consider changing your CGM account password. Whatever release
> you run, read a log before sharing it, and turn debugging off again when you are done.

### Numbers that may look different on the same data

- **COB (carbs on board)** now shows the value reported by your looping app (Loop, AndroidAPS,
  Trio, OpenAPS) rather than Nightscout's own estimate, and appears on sites without a full
  profile. The tooltip says where the number came from. It may differ from what you saw before.
  COB is an estimate either way; how you use it is a question for your care team.
- **Daily Stats estimated A1c** was inflated in mg/dL mode. It is now calculated the same way in
  both units, so the figure may drop. It is an estimate, not a lab result.
- **Reports** no longer throw away valid readings after two closely spaced ones, so charts,
  averages and time-in-range may change slightly.

### Other fixes

Faster data loading on sites with many treatments; deleted records no longer reappear; failed
treatment searches no longer crash the server; clearer error messages when a Loop remote
command fails (the form keeps what you entered); profile switches and unnamed profiles handled
correctly; a site with no profile no longer shows an alert that cannot be dismissed; the clock
view shows the worried face for low and falling readings; voice assistants (Alexa, Google Home)
always answer in your site's configured language (a language requested by the assistant is no
longer used, and one assistant request can no longer change the language of the whole site); a misspelled plugin name in `ENABLE` now gets
a suggestion in the server log; deployment with npm 12 no longer fails; updated translations and
many software library updates.

---

## What you must do

1. **Node.js 20 or later** is required (as for 15.0.8). Versions 20, 22 and 24 are tested.
2. **MongoDB:** the documentation for this release lists MongoDB 5.0.32 or later, or 6.0.27
   or later. **MongoDB 4.4 is an open question** — the documentation says 4.4 is not
   supported, while the automated tests for this release still run and pass on it.
   *[Maintainer: settle this before publishing, and replace this item with one statement.]*
3. **If insulin-age alerts are on**, tell whoever receives your alerts about the new urgent
   alert (see the first section).
4. **After upgrading, check that everything connected to your site still works**, and watch for
   a day.
5. **If you use `TREATMENTS_AUTH=off`**, read the new admin warning and decide whether to keep it.
6. **If you get MiniMed CareLink data through the old built-in connection** (settings that
   start with `MMCONNECT_`): that connection no longer works, and it will be removed in a
   future release. Move to the built-in CGM connector by choosing CareLink as its source and
   setting your CareLink country; see the connector's documentation for the exact settings.
   **If you get Dexcom data** with `BRIDGE_` settings, the connector has already handled them
   since 15.0.8. If you set `DEXCOM_BRIDGE_USE_LEGACY=true` to keep the old Dexcom bridge,
   plan to remove it, because that option also goes in a future release. Check that your
   readings are arriving after any change, and keep a second way to see them.
7. **If you have saved users in the admin screen and think a token may have been exposed**,
   retire it by deleting and re-creating the user, or by changing `API_SECRET` — see
   [Access tokens stored in plain text](#access-tokens-stored-in-plain-text). Note that
   **renaming the user does not retire its token**, even though the token's appearance changes.

## What to check afterwards

- Your glucose readings are arriving and the page updates.
- Uploaders, phone and watch apps, and follower apps still connect.
- Any report or filtered view you rely on — expect numbers to change; that is the fix.
- The IAGE box, if you use insulin age: it may now show URGENT.
- Bookmarked links that contain an underscore.

---

## Known issues — not fixed in this release

- **A class of expensive search request can make the site slow or unresponsive.** Restricting
  access to your site at your proxy or hosting provider helps. A fix is being worked on.
- **The bolus calculator's quick-pick list may show only "(none)"** (see above).
- **Editing a user in the admin screen stores that user's access token in the database in
  plain text.** See [Access tokens stored in plain text](#access-tokens-stored-in-plain-text)
  below. A fix is prepared but is not in this release.
- **The delay that slows repeated failed logins can be bypassed.** A fix is prepared but is not
  in this release.
- **The built-in CGM connector** in this release is an interim version. Fixes that correct how
  it retries after a Dexcom or CareLink outage, and that stop MiniMed CareLink gaps being
  recorded as a zero reading, are not included yet. **If you use MiniMed CareLink through the
  built-in connector:** while such a zero is the newest reading, Nightscout does not check your
  high and low glucose alarms. Keep your pump's or CGM app's own alarms on, and do not rely on
  Nightscout as your only alarm.
- **Alarm thresholds entered in the wrong units are not caught.** Unless you have set
  Nightscout to mmol/L, it reads alarm thresholds (`BG_LOW`, `BG_HIGH` and the target range)
  as mg/dL. A low alarm entered as `3.9` (meaning mmol/L) is kept as 3.9 mg/dL, a level no
  reading ever reaches, so **that low alarm can never go off**, and nothing warns you. A high
  alarm entered as `14` is instead quietly changed to a different number, and only the server
  log says so. Check that the thresholds on your settings page are the numbers you meant, keep
  your device's own alarms on, and talk through your alarm settings with your care team. This
  is not medical advice.
- Filters asking "is this value present" understand only `true`, `false`, `1` and `0`.
- Silencing an alarm from an app has no upper limit on how long it can be silenced for.

### Access tokens stored in plain text

An **access token** is the password-like string that lets a person or an app use your
Nightscout site with the roles you gave them. It is supposed to be worked out fresh each time
and never stored. On 15.0.8, and still on this release, **saving a user in the admin screen
writes that user's token into your database in plain text.** Anyone who can read your database,
or a backup, replica or hosting snapshot of it, can read the token.

**Upgrading does not delete it.** This release does not remove stored copies, and saving a user
still writes one. The fix that stops new copies being written is not in this release; even when
it ships, it will not make an existing token stop working.

**Why a code change cannot retire a token.** Your tokens are worked out from the user's internal
id and your site's key (`API_SECRET`). The same inputs always give the same working token. To
retire a token, one of those two inputs has to change, and only you can do that.

**If you think a token may have been exposed, there are exactly two ways to retire it:**

| What you do | What happens |
|---|---|
| **Delete the user and create a new one** with the same roles | That user's old token stops working, because the new user gets a new internal id. Give the person or app the new token. |
| **Change your site's `API_SECRET`** | **Every token on your site stops working at once**, and everything that connects with the old secret — uploaders, watches, phone apps — stops until you update it. |

Use the first if you are worried about one user; use the second if you think your database
contents were exposed. Plan either for a time when you can update everything that connects to
your site. If your glucose data stops arriving while you do this, use your meter or CGM app and
your usual routine, and talk to your care team about what you rely on Nightscout for.

Renaming the user is **not** a third way, even though it looks like one. Renaming changes
the short word at the front of the token, but the part Nightscout actually checks comes from
the internal id and `API_SECRET`, so the old token keeps working. If you rename a user and stop
there, you have not retired anything.

**Who this applies to:** anyone who has saved a user through the Nightscout admin screen. If you
have only ever used your `API_SECRET` and never created separate users, there is nothing to
retire. **Never paste a token or your `API_SECRET` into an issue, forum post, screenshot or
chat** — those values are the credential itself. Treat any database backup or export as
containing working credentials.

## About the version number

Sites that follow the development channel may already report `15.0.9`, but no `15.0.9` has been
released until this one. If a maintainer decides a different number, it will be noted here, and
a report from "15.0.9" before the release will still be understood.

---

*DRAFT, 2026-09-22. Requires maintainer review before publishing. Nightscout is not a medical
device, and nothing in these notes is medical advice or guidance about insulin dosing. Where a
change here could affect decisions about your therapy, discuss it with your care team.*
