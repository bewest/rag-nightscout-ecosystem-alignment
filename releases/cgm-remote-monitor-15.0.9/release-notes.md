# Nightscout 15.0.9 — release notes

**Draft: 15.0.9 is not yet released, and the wording may change before it is.**

*For people who run a Nightscout site for themselves or a family member. Nightscout is a
secondary display, nothing in these notes is advice about insulin doses, and you should talk
with your care team before changing therapy settings.*

The changelog lists every change; these notes say what you will notice, what you must do, what
to check afterwards, and what is still not fixed.

This is a bug-fix and security release. Most of what is in it is something that should
already have worked. A few fixes change what you see on screen, some change which alarms can
reach your phone, and some requests from apps and scripts are now answered differently. Please
read the first three sections even if you usually skip release notes.

**A few words used throughout these notes:**

- **API** — the web addresses that apps (uploaders, phone and watch apps, follower apps,
  reporting tools, scripts) use to read from and save to your Nightscout site. You do not see
  it in the browser, but almost everything connected to your site uses it.
- **Admin page** — the "Admin tools" page, reached from your site's menu, where you create
  **users** for people and devices. The page calls them *subjects*. Each one gets its own
  **access token**: a password-like string that lets that person or app use your site with the
  roles you gave them, without knowing your site's main password (`API_SECRET`).
- **Proxy** — a server that sits in front of Nightscout and passes visitors' requests on to it.
  Many hosting set-ups have one without you having set it up yourself: a hosting platform's
  router, a CDN, nginx, Apache, a Kubernetes ingress.
- **Setting** — one of the environment variables you configure your site with, written here in
  `CAPITALS`.

---

## Before you upgrade: what to check

Work through this list first. Most people will find that nothing applies to them except the last
item.

1. **Which MongoDB version your database runs.** MongoDB is the database Nightscout keeps your
   readings and treatments in. **MongoDB 4.4 is deprecated in this release.** It still works and
   is still tested, but support for it will be removed in a later release (the version that
   removes it has not been decided). MongoDB itself stopped supporting 4.4 in February 2024. The
   supported versions are 5.0.32 or later and 6.0.27 or later. If you are on 4.4, plan to
   upgrade one major version at a time (4.4 to 5.0, then 6.0). If you use a hosted database
   (such as MongoDB Atlas), your provider decides this and you may have nothing to do.
2. **`TRUST_PROXY`, a new setting: nothing to do unless you want the stronger protection.**
   If you leave it unset, Nightscout behaves exactly as it does today. Setting it turns on a
   stronger protection against password guessing, but setting it wrongly can stop your site
   loading. See [The new `TRUST_PROXY` setting](#the-new-trust_proxy-setting).
3. **If you have ever edited a user on the admin page**, a readable copy of that user's access
   token may be stored in your database. **Upgrading does not remove it, and does not make the
   token stop working.** Read [Access tokens stored in plain text](#access-tokens-stored-in-plain-text)
   and decide whether to retire any tokens.
4. **If you get MiniMed CareLink data through settings that start with `MMCONNECT_`**, or
   **Dexcom Share data through settings that start with `BRIDGE_`**, those old built-in
   connections are being retired. Move to the built-in CGM connector's settings. See
   [The old MiniMed and Dexcom connections are being retired](#the-old-minimed-and-dexcom-connections-are-being-retired).
5. **If you run apps, scripts or reports against your site's API**, some requests are now
   answered differently or refused with an error. See
   [Corrections: requests answered differently](#corrections-requests-answered-differently).
   This includes asking for zero records, badly formed record counts, unsupported filter
   conditions, and extra fields a tool stores on a user.
6. **If you run Nightscout with the bundled `docker-compose.yml` file**, or a copy of it, see
   [If you run Nightscout with Docker Compose](#if-you-run-nightscout-with-docker-compose).
7. **If insulin-age alerts are turned on** (`IAGE_ENABLE_ALERTS`), a new urgent alert can reach
   your phone. Tell whoever receives your Nightscout alerts. See the next section.
8. **If your site shows glucose in mmol/L** (`DISPLAY_UNITS=mmol`), write down the alarm levels
   you expect before you upgrade, and check them afterwards: some sites' alarm levels are read
   differently now, and on some sites low alarms start working. See
   [Low alarms on sites that use mmol/L](#low-alarms-on-sites-that-use-mmoll).
9. **If you turned on `PUMP_WARN_ON_SUSPEND`**, a "Pump Suspended" warning can now reach your
   phone; it never did before. See
   [The "pump suspended" warning now works](#the-pump-suspended-warning-now-works).
10. **If you use AndroidAPS**, carbs and insulin entered in the careportal or by a caregiver can
    now reach the phone, deleting an entry anywhere except AndroidAPS still does not reach the
    phone, and during a percentage Profile Switch the numbers on your site change to match the
    phone. See [AndroidAPS, the careportal and caregivers](#androidaps-the-careportal-and-caregivers).
11. **If you get Nightscout alarms through IFTTT on a site that is not in English**, and you renamed
    your IFTTT applets to translated names to make them work, rename them back. See
    [IFTTT alerts on sites not set to English](#ifttt-alerts-on-sites-not-set-to-english).
12. **Have a second way to see your readings** while you upgrade and for a day afterwards —
    your CGM app, your pump or your meter — in case something that connects to your site stops
    working.

Node.js 20 or later is still required (as for 15.0.8). Versions 20, 22 and 24 are tested.

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

## Alarm fixes: mmol/L alarm levels, pump and loop alerts, watch faces and IFTTT

These fixes change which alarms Nightscout raises. None of them changes anything on your pump,
CGM or looping app. **Nightscout is a secondary display: keep the alarms on your CGM, pump and
phone app switched on, and do not rely on Nightscout alone to warn you.** This is not medical
advice; if you are unsure what your alarm levels should be, talk to your care team.

### Low alarms on sites that use mmol/L

Glucose is measured in one of two units, **mmol/L** or **mg/dL**, depending on the country and
the meter. Your site shows mmol/L if its
`DISPLAY_UNITS` setting is `mmol`. Nightscout's glucose alarms use four **alarm levels**, each a
setting:

- `BG_HIGH` — the urgent high alarm;
- `BG_TARGET_TOP` — the top of your target range, where the high warning starts;
- `BG_TARGET_BOTTOM` — the bottom of your target range, where the low warning starts;
- `BG_LOW` — the urgent low alarm.

Any you leave unset use a built-in default, written in mg/dL (260, 180, 80 and 55).

**What was wrong.** On a site set to mmol/L, Nightscout converted the alarm levels you wrote in
mmol/L only if `BG_HIGH` was also written in mmol/L, and then it converted all four. If you set
only your target range in mmol/L (for example `BG_TARGET_TOP=8.5` and `BG_TARGET_BOTTOM=3.9`) and
left `BG_HIGH` unset, nothing was converted. Your targets were read as 8.5 and 3.9 **mg/dL**, far
below any real reading, and the urgent low level was then lowered to 2.9 mg/dL to sit beneath
them. As a result **the low and urgent-low alarms could never go off, and every reading, even a
low one, raised "Warning HIGH".** This was the same on 15.0.8 and earlier.

**What changes.** Nightscout now looks at each of the four alarm levels on its own. A number
**below 30** is read as mmol/L and converted; a number of **30 or more** is read as mg/dL and kept
as you wrote it. Levels you leave unset keep their defaults. So a site that sets only some of its
levels in mmol/L gets working low alarms. **The server log shows one line for each level it
converts**, for example `Threshold bgTargetTop 8.5 taken as mmol/L, converted to 153 mg/dl`, so
you can see what Nightscout did with each one.

- **If you set all four levels in mmol/L, or all four in mg/dL,** nothing changes for you.
- **One uncommon mix is now stored differently.** If you set `BG_HIGH` in mmol/L and a target in
  mg/dL (for example `BG_HIGH=14` and `BG_TARGET_TOP=180`), the mg/dL number is now kept as you
  wrote it. Before, it was converted by mistake into a very large number, and your alarm levels
  did not make sense.

**What to do after upgrading, if your site uses mmol/L:**

1. **Check your alarm levels.** Look at the target lines on your chart and the alarm levels your
   site uses, and make sure they are the numbers you meant. The start-up lines in your server log
   show each level Nightscout converted.
2. **If you had set only some levels in mmol/L, expect low alarms to start** and "Warning HIGH" to
   stop appearing on in-range and low readings. Tell whoever receives your Nightscout alerts.
3. **Keep your CGM's and pump's own low alarms on.** Do not rely on Nightscout alone for low
   alerts.

If you are not sure what your alarm levels should be, talk to your care team. This is not medical
advice.

This fix is only for sites set to mmol/L. On a site set to mg/dL, an alarm level typed in mmol/L
is still not caught; see [Known issues](#known-issues--not-fixed-in-this-release).

### The "pump suspended" warning now works

A pump is **suspended** when it has stopped delivering insulin, whether you stopped it or the
pump did. Nightscout has a setting meant to warn you when that happens, `PUMP_WARN_ON_SUSPEND`,
used together with `PUMP_ENABLE_ALERTS` (which turns on Nightscout's pump alerts). **It never
worked:** the pump box on your page showed "suspended", but no warning was sent.

In this release, with both settings on, Nightscout raises a **"Pump Suspended"** warning for as
long as your pump reports that it is suspended. It is sent, snoozed and sounded like Nightscout's
other pump warnings. With `PUMP_WARN_ON_SUSPEND` on, the pump box on your page also turns the
warning colour while the pump is suspended. **If you have not turned `PUMP_WARN_ON_SUSPEND` on,
nothing changes for you.**

Things to know:

- If you turned this setting on some time ago, a warning you have never seen may now reach your
  phone. Tell whoever receives your Nightscout alerts what it means.
- The warning depends on your phone app or uploader sending your pump's status to Nightscout, and
  on how your site sends notifications. It can arrive late or not at all. Some apps report a
  suspended pump in a way that shows "suspended" in the pump box without raising the warning.
- Like Nightscout's other pump alerts, it is not sent while your looping app has marked the loop
  as offline.
- **Keep the alerts on your pump and your phone app switched on.** Do not rely on Nightscout alone
  to tell you your pump is suspended.

This is not medical advice. If you are unsure how you should be alerted to a suspended pump, talk
to your care team.

### AndroidAPS: loop and pump alerts return when you turn the loop back on

In **AndroidAPS** (AAPS), you can turn the loop off ("disable loop") with no end time. While the
loop is off on purpose, Nightscout does not raise its "not looping" alert (`OPENAPS_ENABLE_ALERTS`)
or its pump alerts (`PUMP_ENABLE_ALERTS`), if you have turned those on.

On 15.0.8 and earlier, when you later turned the loop back on in AAPS, **Nightscout kept treating
the loop as switched off**, so those alerts stayed silent, with nothing on screen to say so, for
as long as the "disable" record stayed among the recent records Nightscout looks at. In this
release, Nightscout sees that the loop was turned back on, and those alerts work again.

- This covers the way **released versions of AAPS** record turning the loop off and on, and the
  different way **current development builds** of AAPS record it.
- Loop and Trio are not affected.
- Keep the alerts in AAPS and on your pump switched on. This is not medical advice; talk to your
  care team about how you are alerted.

### Watch faces, and a false low alarm on sites that use mg/dL

Some watch faces and small displays get the latest reading from an older address on your site,
`/pebble` (first written for Pebble watches). They can ask for the reading in mg/dL or in mmol/L,
whatever your site uses.

**A false low alarm.** On a site that shows mg/dL, a watch face asking `/pebble` for mmol/L could
change the reading your site's own alarm check looks at, so that the check judged the reading in
the wrong units. That could raise a **low alarm when your glucose was not low**, and the alarm
message could show the wrong number. The values some apps and watch faces read from your site
(`/api/v2/properties`), and what Alexa and Google Home said, could also be wrong until your site
next loaded new data. This depended on timing and did not happen on every request. It is fixed:
a watch-face request can no longer change what the rest of your site sees. The same was true on
15.0.8 and earlier.

If your site raised a low alarm that did not match your sensor, and a watch face on your site asks
for mmol/L, this may have been the cause. **Always check a surprising alarm against your meter or
CGM.**

**Two more `/pebble` fixes:**

- **The change since the last reading** (the *delta*, for example "falling 2") now comes back in the
  same units as the reading. On a site that shows mmol/L, a watch face asking for mg/dL got the
  reading in mg/dL but the change in mmol/L, so a fall looked about 18 times smaller than it was.
- **The bolus estimate** some watch faces show (Nightscout's *Bolus Wizard Preview*, available when
  insulin on board is turned on) is now worked out the same way your site works it out for itself,
  whatever units the watch face asks for, and its expected glucose result comes back in the units
  the watch face asked for. Before, a watch face asking for the other units could get a different
  estimate from the one your site shows. The estimate is a rough indicator, not a dosing
  recommendation.

If you adjusted a watch face to make these numbers look right, for example by multiplying or
dividing by 18, undo that adjustment after upgrading. Keep the alarms on your CGM, pump and phone
app switched on. This is not medical advice; talk to your care team about how you are alerted.

### IFTTT alerts on sites not set to English

**IFTTT** ("If This Then That") is an outside service that can turn an alert from Nightscout into a
phone notification, a call or a smart-light flash. Nightscout sends it a named *event* for each
alarm, and each IFTTT *applet* you set up listens for one event name. Nightscout's documentation
tells you to name your applets `ns-warning`, `ns-urgent`, `ns-warning-low`, `ns-urgent-high` and
so on.

On a site whose language (`LANGUAGE`) is not English, Nightscout translated the alarm level in the
event name, for example `ns-warnung` on a German site, so applets named as the documentation says
**never fired**. In this release every site sends the documented names, whatever its language.
The text of the alert itself stays in your site's language. English sites see no change.

**What to do:** if your applets use the documented names, nothing. **If you renamed your applets to
the translated names** to make them work, rename them back to `ns-warning`, `ns-urgent` and the
other documented names after upgrading, or they will stop firing. Then send a test alarm and check
that it arrives.

Not changed: when a send to IFTTT fails, Nightscout tries the same alarm again at its next check
until a send succeeds, so a failed alarm is not silently dropped. An IFTTT alert is an extra, not a
replacement for your CGM app's own alarms. This is not medical advice.

---

## AndroidAPS, the careportal and caregivers

These changes are about how treatments (carbs, insulin, temporary targets, notes) move between
your Nightscout site and the apps connected to it. They matter most if you use **AndroidAPS**
(AAPS), an automated insulin delivery app for Android phones, together with Nightscout's
**careportal** (the form on your site for entering treatments) or a caregiver who enters
treatments for you. AndroidAPS talks to Nightscout through its **NSClient** settings. Nightscout's
web pages, Loop, Trio, xDrip+ and OpenAPS use Nightscout's older interface (API version 1);
AndroidAPS uses the newer one (API version 3).

**None of these changes alters how any app doses insulin.** They change what Nightscout stores,
shows and passes on. This is not medical advice; if the carbs or insulin on your site and on your
phone do not match, go by the app that doses and by your meter, and talk to your care team before
relying on the Nightscout numbers.

### Careportal and caregiver entries now reach AndroidAPS

Before, after its first sync AndroidAPS asked Nightscout only for "what changed since last time",
and Nightscout left out everything written through the older interface: carbs, insulin, temporary
targets and notes entered in the careportal or bolus wizard, including a caregiver's entries,
readings uploaded by other apps, and edits made that way. AndroidAPS never received them unless
someone ran a full sync.

In this release they reach AndroidAPS at its next regular check. **What the phone does with them
depends on its own settings:**

- On a phone that loops, AndroidAPS takes carbs and insulin from Nightscout only if **"accept
  carbs"** and **"accept insulin"** are switched on in its NSClient settings. **Both are off unless
  you turned them on.**
- The **AAPSClient** follower app always takes them, and does not show these two settings.
- **If you have been entering the same meal both in the careportal and on the phone** as a
  workaround, the phone may now see it **twice**. Check the phone's treatment list after the
  update.
- Entries written before the update are not sent again.

When an app using the older interface edits a record that AndroidAPS created, the record keeps the
label AndroidAPS knows it by, so AndroidAPS updates its copy instead of adding a second one.

### Deleting a treatment

- **A treatment you delete in AndroidAPS now stops counting on your site.** AndroidAPS deletes by
  marking a record as deleted rather than removing it. Nightscout used to ignore that mark, so a
  deleted entry kept counting in carbs on board (COB) and insulin on board (IOB), on the chart, in
  reports and in what followers and other apps read. It now disappears from all of them, and a
  deleted profile is no longer taken as the current one.
- **Deleting a treatment in the careportal, Loop, Trio or xDrip+ still does not reach AndroidAPS.**
  This stays as it is by decision. An entry deleted that way keeps counting on the phone. **Delete
  it in AndroidAPS as well.**

### AndroidAPS changes to careportal entries are no longer lost

When AndroidAPS changed a treatment that had been entered in the careportal (for example a
temporary target entered on your site), Nightscout refused the change and AndroidAPS did not try
again, so your site kept the old version and nothing said so. An AndroidAPS entry recorded at
exactly the same moment, to the thousandth of a second, as an existing entry of the same kind was
refused the same way and never reached your site. Both are now accepted. In the same-moment case,
the AndroidAPS version replaces the existing entry; it does not add a second one. Entries that were
refused in the past are not sent again.

### Two treatments at the same time are no longer stored as one

When two treatments of the same kind had exactly the same time, Nightscout kept only one of them,
with no error. In the report behind this fix, a caregiver sent 16 g and then 4 g of carbs through
Loop, both back-dated to the same time, and Nightscout kept only the 4 g. The 16 g disappeared from
the chart, the reports and the daily totals, and from what followers saw. The app that entered the
carbs kept both and dosed from its own records.

Now two entries at the same time are kept apart when anything tells them apart: the app's own label
for each entry (Loop, Trio, xDrip+ and NSClient each send one), or, for entries that arrive without
one (such as the careportal), a different carb or insulin amount. An app that sends the same entry
again, or an updated version of it, still updates the one record. Entries lost before this update
are not brought back. Some cases are still stored as one; see
[Known issues](#known-issues--not-fixed-in-this-release).

### Late or edited AndroidAPS entries now count in insulin and carbs on board

Nightscout works out its own **insulin on board** (IOB: insulin from earlier doses that is still
expected to act) and **carbs on board** (COB: carbs not yet expected to be absorbed) from the
treatments it holds in memory. When AndroidAPS, or another app using API version 3, sent a bolus or
carb entry **late** (dated more than about 15 minutes before it reached Nightscout, for example
after the phone had been offline), or **changed an older entry**, Nightscout could leave that entry
out of its own IOB and COB, on the server and in the browser, until the server restarted (without
a restart, the entry was never counted). The same
cause could put treatments out of time order. That could make Nightscout's COB **too high**,
because carbs that should already have been absorbed were counted again, and could make the "last
carbs" line under the COB pill name an older entry instead of the newest one.

These entries now count as soon as they arrive, and treatments stay in time order. Nothing stored
changes. A **device status** (the status report a looping app uploads) that such an app sends late
is now also listed in its place by time when another app asks your site for the latest device
statuses; before, it could be left out. The same problem is in 15.0.8.

- Where your looping app reports its own IOB and COB (AndroidAPS does when it uploads its status),
  the IOB and COB pills show the app's values, so you may not have noticed this. Nightscout's own
  figures are still worked out and can be read by other apps.
- AndroidAPS's own dosing was not affected: it works out IOB and COB on the phone.
- After the update, Nightscout's own IOB and COB can differ from what you saw before on the same
  treatments. If they differ from your looping app's, go by the app that doses and talk to your care
  team before relying on the Nightscout numbers. This is not medical advice.

### AndroidAPS percentage Profile Switches: the numbers on your site change

In AndroidAPS a **Profile Switch** can run your profile at a percentage (for example 150% during
illness, or 80% for exercise), or shift its schedule a few hours earlier or later. Your profile
holds your **basal** rate (background insulin, in units per hour), your **ISF** (insulin
sensitivity factor: how far one unit is expected to lower glucose) and your **carb ratio** (grams
of carbohydrate one unit covers).

During such a switch, Nightscout named the profile correctly, for example "Default (150%)", but
showed and calculated with the 100% values and ignored a time shift. It now reads the switch the
way AndroidAPS does: basal is multiplied by the percentage, ISF and carb ratio are divided by it,
glucose targets are not changed, and a time shift moves the whole schedule. **So the basal, ISF and
carb ratio your site shows change to match the phone**, and so do the basal pill, the chart's basal
line, the Bolus Wizard Preview, Nightscout's own IOB and COB, and the reports. Nothing stored
changes.

- AndroidAPS's own insulin delivery was never affected: it works out its doses on the phone.
- If AndroidAPS uses **Dynamic ISF** or another feature that changes ISF on the phone, the ISF it
  doses with can still differ from the profile ISF your site shows.
- Switches from older AndroidAPS versions (2.x) are read exactly as before.

If the numbers on your site and in AndroidAPS still do not match, or you are unsure which numbers
are right, check with your care team.

---

## Security fixes

**These fixes are in this release. Earlier releases, including 15.0.8 (the release most sites
run today), are affected.** The descriptions are kept short on purpose until the related
security advisories are published.

1. **Sites set to require login now apply that to the live-update connection.** The live-update
   connection is what keeps your page current without reloading. If you set
   `AUTH_DEFAULT_ROLES=denied` so that only people you have given access can see your site, it
   now checks a visitor's access the same way the rest of the site does before sending live
   information, alarms or notifications. If your site uses the standard setting, where anyone
   with the address can read it (`AUTH_DEFAULT_ROLES=readable`), nothing changes. On a site set to
   `denied`, a page that is signed in, on an internet connection where another device (for example
   an app with an old password on the same home Wi-Fi) has recently failed to sign in, starts
   receiving alarms only after the failed-login delay described in item 7. An alarm raised in that
   time reaches it when the site repeats the alarm. Fix the device that is failing to sign in; the
   admin page's "Failed authentication" notice helps you find it.
2. **Silencing alarms through the live-update connection now requires the permission meant for
   it.** Among the built-in roles only `admin` has it, on the standard setting too. An app that
   silences Nightscout alarms with an access token needs a user with the `admin` role; with any
   other role the app's silence does nothing, and the app is not told.
3. **The older API (version 1) accepts only a fixed, documented list of filter conditions**
   and refuses anything else with an error. See
   [Corrections](#corrections-requests-answered-differently) for what this means for tools.
4. **Two shared read addresses in the API now check per-collection read permission**, as the
   rest of the API already does. On the standard setting nothing changes. On a site that has
   turned off anonymous access and gives out tokens limited to particular kinds of data, those
   addresses now refuse a token that lacks the permission.
5. **Alarm subscriptions no longer write credentials to the server log.** This matters if your
   logs are kept or shared.
6. **Editing a user on the admin page no longer writes that user's access token into your
   database.** It used to save the token in readable form, so anyone who could read your
   database — or a backup, snapshot or copy of it — could use it. **Fixing the code does not
   remove copies already written and does not retire those tokens.** Read
   [Access tokens stored in plain text](#access-tokens-stored-in-plain-text).
7. **The failed-login delay also follows the password, and its list no longer grows forever.**
   After a failed login, Nightscout makes the next request from that address wait before it
   checks the password, as it always has, so a correct guess made during the wait is answered no
   sooner than a wrong one. The wait now also follows the password or token that failed,
   wherever it is tried from, and the list of recent failures is cleared regularly and has a
   size limit. Every request from an address with recent failures waits, including ones with
   the correct password; once `TRUST_PROXY` is set to match your site, that address is the
   visitor's own, so only devices that really share an address (one home network, or a mobile
   carrier's shared address) share a wait. **On its own this does not stop someone who is
   guessing passwords from avoiding the delay**, because the address it counts attempts against
   is read from information any visitor can supply. That is closed only once you set
   `TRUST_PROXY` — see the next section.
8. **The "Nightscout readable by world" warning now appears when it should.** If you use the
   older `TREATMENTS_AUTH=off` setting, anyone with your address can read your data **and add
   treatments** without logging in. That is what the setting does and this release does not
   change it — but the admin warning that should tell you this was never shown. It is now.
9. **Error replies no longer show technical details about where Nightscout is installed.** When
   Nightscout hit an unexpected error, the error page or reply it sent back included a technical
   trace that names folders on the computer or service where Nightscout runs, and anyone who
   could reach your site could see it. It did not include your readings, treatments or
   `API_SECRET`. Error replies now carry only the error code and a short message, sometimes a
   standard phrase such as "Bad Request"; the full details still go to your server log, where
   you or someone helping you can read them. This applies to every site that does not set
   `NODE_ENV=development`, including sites where `NODE_ENV` is not set at all: on those, the
   error pages you see in a browser also stop showing the trace.
10. **A kind of request to two little-used API addresses could make Nightscout stop responding
    for several seconds, and it is now refused.** Nothing you see changes.

**What to do:** upgrade. If you rely on `AUTH_DEFAULT_ROLES=denied` to keep your data private,
this release is the one that makes the live-update connection respect it. If you use
`TREATMENTS_AUTH=off`, read the new warning and decide whether you still want it. If you have
ever edited a user on the admin page, read the token section below.

### The new `TRUST_PROXY` setting

Nightscout counts failed logins per visitor address, and per password or token tried. Today it
takes that address from labels
attached to the request (called *forwarded headers*), **whoever attached them**. A proxy
normally adds these labels, but a visitor can add them too. `TRUST_PROXY` tells Nightscout whose
labels to believe:

| `TRUST_PROXY` | What Nightscout believes | Who should use it |
|---|---|---|
| not set (the default) | forwarded headers from anyone — **exactly as today** | nobody needs to change anything to upgrade |
| `false` | no forwarded headers at all; only the address actually connecting, and whether that connection itself is https | sites that visitors reach directly, with no proxy in front |
| your proxy's IP address(es) or ranges, comma-separated (for example `10.0.0.5` or `10.0.0.0/24`) | forwarded headers only when they come from those addresses | sites behind a proxy whose address you know |
| a whole number of proxies, such as `1` | forwarded headers from that many proxies closest to Nightscout | sites behind a known number of proxies whose addresses change |
| `true` | every forwarded address; the visitor is taken to be the left-most one | only sites where every proxy in front of Nightscout rewrites these labels |

**Which value to use.** Most sites behind a proxy or a hosting service need a number. Each proxy
adds the address it received the request from to the end of the list of labels, after anything
the visitor wrote there. Counting back from Nightscout to the proxy you trust is what separates
the visitor's real address from whatever the visitor wrote: `1` if one proxy or hosting service
sits in front of Nightscout, `2` if there are two (for example Cloudflare in front of your own
proxy). Too small a number gives everyone your proxy's address, so one failing uploader slows
everybody; too large a number believes what the visitor wrote. To check, send one deliberately
wrong password from your phone on mobile data: the "Failed authentication" message on the admin
page should show your phone's address. Nightscout's README links to a proxy configuration guide
with a table of the value for common hosting services. On Azure App Service use `1`: Azure writes
the visitor's address with a port number on the end, and Nightscout now accepts that form.

**It also sets the address recorded for Loop remote commands.** When a caregiver sends Loop a
temporary override, carbs or a bolus through Nightscout, Loop saves where the command came from on
the override it records back in Nightscout. Before, on most hosted sites, that was your hosting
service's address. Now it is the caregiver's address, worked out from this setting the same way
as everywhere else. **That address is stored with each remote override in your Nightscout data,
where anyone who can read your site's data can see it**, including visitors without a login if
your site lets them read. Whether a command is accepted does not depend on it.

Once it is set, the failed-login delay counts attempts against an address a visitor cannot make
up, and it starts doing its job. **While it is unset, Nightscout writes a message to its log at
startup saying the delay does not protect against guessing passwords or tokens.** Until you set
it, restricting access at your proxy or hosting provider is what actually helps.

**Be careful setting it behind a proxy that handles https for you.** With `false`, or with a list
that does not include your proxy, Nightscout stops believing the proxy's "the visitor used https"
label, decides the visitor used plain http, and redirects them to https — over and over. **If
your site stops loading after you set `TRUST_PROXY`, remove the setting and check your proxy's
address.** The address to list is the one Nightscout *sees* the proxy connecting from, which on
hosting platforms can change or be shared; do not guess a range. With `true`, the startup message
warns that the visitor's address is only as trustworthy as the outermost proxy, because a visitor
can put any address first. Names like `loopback` are refused at startup, and a number of proxies
cannot be combined with addresses. Nightscout's README links to a proxy
configuration guide with more detail.

No release has been chosen in which the default will change; until one is, unset is a permanent,
supported choice.

---

## Corrections: requests answered differently

This section is for **apps and tools that talk to your site through the API**, not the pages you
look at. Each item below corrects behaviour that was never intended. Some requests that used to
get an answer now get an error, and that is deliberate.

**If a tool you use stops working after the upgrade**, with an error such as "Bad count" or a
refused filter condition, report it to that tool's author with the tool's name and version (not
your data). **If your glucose data stops arriving, use your meter or CGM app and your usual
routine while it is sorted out.**

### Asking for a number of records (`count`)

Apps add `count` to a request to say how many records they want back, for example "the last 10
readings". On 15.0.8, a request for **zero** records could send back your **entire** history,
and counts that are not plain whole numbers were read in surprising ways. On the version 1 API,
in this release:

| The request | 15.0.9 answers |
|---|---|
| a read with `count=0` and a date range (a "from" and a "to" on the same date field). GluPredKit asks this way. | **everything in that range**, as 15.0.8 did, with a deprecation warning. (Device status reports gave only the last 10 here on 15.0.8; they now give everything in the range.) |
| a read with `count=0` and no date range | the **usual default**, as if no count had been given, with a deprecation warning. On 15.0.8 this could return your whole history. |
| a read with a whole number followed by `?` and other text, such as `1?token=…`. OpenAPS (oref0) asks for its latest treatment this way. | the number is read as the count, as 15.0.8 did, with a deprecation warning. What follows the `?` is not logged. |
| a read with an ordinary count such as `10` or `288` | as before |
| a read with no `count` | the usual default (for glucose readings, the last 10), as before |
| a read with a count that is not a plain whole number: `abc`, `-3`, `2.5`, `1e2`, `0x10`, or a number too large to handle exactly (followed by `?` or not) | an error, "Bad count" (HTTP 400) |
| a save or an update that carries a `count` | carried out normally; `count` is ignored |
| a delete that carries `count=0` or a count that is not a plain whole number, including a number followed by `?` | **refused** with an error, and **nothing is deleted** |
| a delete that carries a valid count such as `2` | carried out as before. **The count does not limit a delete**: it still deletes every record the request matches. |

The newer API (version 3) keeps its own rule: a `limit` of `0`, or one that is not a whole
number within the site's maximum, gets an error.

The "deprecation warning" is two extra headers on the answer (`Deprecation: true` and a
`Warning` that says what to send instead), plus one line in the server log the first time it
happens. Nothing changes for the app today. A future major release may refuse these two forms,
so app authors should send a plain whole number of 1 or more.

Each form has a setting, and both are on unless you change them:
- `API_V1_COUNT_LEADING_NUMBER` covers the OpenAPS form. Set to `false`, it is refused with an error.
- `API_V1_COUNT_ZERO_WINDOW` covers the GluPredKit form. Set to `false`, every read with `count=0` gets an empty list.

Leave `API_V1_COUNT_LEADING_NUMBER` on if an OpenAPS rig uploads to your site. A future release is
expected to change both defaults to `false`.

### Filter conditions

Apps use filter conditions to ask for particular records, for example "readings at or above
180". The version 1 API now accepts a fixed, documented list of conditions: *equal*, *not
equal*, *greater than*, *less than* and their "or equal" forms, *in a list*, *not in a list*,
*has a value* (`$exists`), *type*, and text matching (`$regex`), combined with *and* / *or*.
Anything else gets an error (HTTP 400) that names the refused condition, instead of a server
error or a silently empty answer. A survey of 14 Nightscout apps found none that use a refused
condition. One condition that used to work is now refused: `$expr` on the profiles address. An
undocumented `pipeline` option on the counting addresses is also refused.

### Asking for a glucose reading by an ID that does not exist

When an app asks for one glucose reading by its ID (API version 1, `GET /api/v1/entries/<id>`) and
no reading has that ID, the answer is now "nothing found" (HTTP 200 with an empty list), as for any
other search that finds nothing. 15.0.8 answered with a server error (HTTP 500), which an app could
take to mean your site was down. If the database cannot be reached, the answer is still a server
error.

### Records deleted by AndroidAPS, and two server time fields

Records that AndroidAPS has deleted (marked `isValid: false`) are no longer returned by version 1
reads and counts. A tool that needs them can still ask for them with `find[isValid]=false`. Records
read through version 1 now also carry the server's `srvModified` and `srvCreated` times, as records
written by AndroidAPS already did. The server sets both; a value an app sends for them is replaced.

### Saving a glucose reading that is already stored

When an app sends a glucose reading (API version 1, `POST /api/v1/entries`) that matches one
already stored, the reply now carries the stored reading's ID. 15.0.8 answered with the ID the app
sent, or with none. The reading itself is stored as before.

### Carbs on board in `/api/v2/properties`

The `cob` property's `treatmentCOB` field changed shape. On 15.0.8, when carbs on board came from
treatments entered in Nightscout, `treatmentCOB` held a nested copy of that result. In this
release, carbs on board comes from the uploading system when its value is recent (see
[Numbers that may look different](#numbers-that-may-look-different-on-the-same-data)), and
`treatmentCOB` is a number, present only then and only when the treatment-based figure is not
zero. A tool that reads `treatmentCOB` should expect it to be missing.

### Fields stored on users and roles

When a user or role is created or saved, Nightscout now stores only these fields:

- for a **user**: name, roles, notes and the date it was created;
- for a **role**: name, permissions, notes and the date it was created.

**Any other field a third-party tool stored on a user or role is not kept** the next time that
user or role is saved, and is not stored when one is created. No open-source tool that stores
other fields was found. If you use a tool that manages users on your site, check it still works
after the upgrade.

---

## The old MiniMed and Dexcom connections are being retired

Nightscout has two ways to fetch readings from a CGM company's online service: the **built-in
CGM connector** (a component called *nightscout-connect*, configured with settings that start
with `CONNECT_`), and two **older built-in connections** that are being retired.

- **MiniMed CareLink through settings that start with `MMCONNECT_`**: this older connection is
  reported not to work, and it will be removed in a later release. Move to the built-in
  connector: add `connect` to your `ENABLE` setting, set `CONNECT_SOURCE=minimedcarelink`, and
  set your CareLink username, password, region and country with the connector's settings
  (`CONNECT_CARELINK_USERNAME`, `CONNECT_CARELINK_PASSWORD`, `CONNECT_CARELINK_REGION`,
  `CONNECT_COUNTRY_CODE`). Once readings arrive through the connector, remove the `MMCONNECT_`
  settings and `mmconnect` from `ENABLE`.
- **Dexcom Share through settings that start with `BRIDGE_`**: since 15.0.8, these settings are
  already handled by the built-in connector unless you set `DEXCOM_BRIDGE_USE_LEGACY=true`, and
  Nightscout writes a deprecation warning to its log. If you set `DEXCOM_BRIDGE_USE_LEGACY=true`
  to keep the old Dexcom bridge, plan to remove it: that option goes when the old bridge is
  removed. Moving to the connector's own settings (`CONNECT_SOURCE=dexcomshare`,
  `CONNECT_SHARE_ACCOUNT_NAME`, `CONNECT_SHARE_PASSWORD`, and `CONNECT_SHARE_REGION` if you are
  outside the US) means nothing changes for you when that happens.

The release that removes the older connections has not been numbered yet. The connector's own
documentation lists every setting. **After any change, check that your readings are arriving,
and keep a second way to see them** until you are sure.

---

## The built-in CGM connector

This release installs **nightscout-connect 0.1.0**, the built-in CGM connector (it fetches
readings from Dexcom Share, MiniMed CareLink, LibreLinkUp, Glooko, another Nightscout site and
others). It is installed as that exact version. If you use the connector — including if you use
Dexcom `BRIDGE_` settings, which the connector handles — compared with 15.0.8:

- **It no longer writes your CGM account details or readings to the log.** On 15.0.8 and earlier,
  the built-in connector printed your CGM account login details, session information and glucose
  data to the log every time it started, with no way to turn that off. In this release it logs
  short summaries instead, with or without the debug settings below.
- **Its detailed diagnostic logging is off unless you turn it on** (see
  [Quieter logs](#quieter-logs-and-two-new-settings)).
- **A MiniMed CareLink "no reading" marker is no longer stored as a glucose reading of 0.** While
  such a 0 was the newest reading, Nightscout did not check your high and low glucose alarms.
  Readings already stored are not changed. How often CareLink sends such a marker as the newest
  value has not been measured. Keep your pump's or CGM app's own alarms on; do not rely on
  Nightscout as your only alarm.
- **It waits properly between retries after a CGM service outage.** Earlier versions ignored the
  retry interval each source was designed with, so after an outage they started retrying within a
  fraction of a second instead of after minutes, and every site retried at the same moment.
  Retries now follow the intended interval, are spread out, and have an upper limit, so the
  connector does not stop trying for a very long time either.
- **Copying data from another Nightscout site that requires login now works.** If the site you
  copy from uses `AUTH_DEFAULT_ROLES=denied`, earlier versions could not read from it. **If an
  earlier version already created a user called `nightscout-connect-reader` on that site**, it is
  reused as it is and still cannot read: on that site's admin page, give that user the
  `readable` role, or delete it so the connector creates it again. The connector now says this
  once in its log when it finds such a user.
- **When copying from another Nightscout site, profile changes are copied too.** A profile (basal
  rates, insulin sensitivity, carb ratios) saved on the site you copy **from** reaches this site
  at the next poll. 15.0.8 copied only new profiles. **Make profile changes on the site you copy
  from:** a profile edited on the receiving site is overwritten when the source's copy changes,
  and can also be overwritten when the connector restarts. A profile changed on the source
  without the profile editor (for example by a script) is noticed only if it is the newest one.
  The connector now downloads only the profiles that are new or changed since its last check,
  instead of every profile every five minutes. If a profile on the receiving site does not match
  the source, check it on both sites before relying on the receiving site's reports, and talk to
  your care team about any settings you are unsure of.
- **It shuts down cleanly when Nightscout stops.**
- For developers: the connector's standalone `capture` command no longer fails for the
  Nightscout and Dexcom Share sources.

Two new optional settings, `CONNECT_START_JITTER_MS` and `CONNECT_INTERVAL_JITTER_MS`, spread out
when many connectors sharing one server contact the CGM service. Both default to `0`, so nothing
changes unless you set them. A single self-hosted site does not need them.

### Your CGM account password

**Most people do not need to do anything here.** A Nightscout log is normally seen only by the
person who runs the site, and sharing a whole log is uncommon. Consider changing your CGM account
password only if both of these are true:

- you ran Nightscout 15.0.8 or an earlier release with the built-in connector on (`connect` in
  your `ENABLE` setting), or you used Dexcom `BRIDGE_` settings on 15.0.8, which the connector
  handles; **and**
- you shared a Nightscout log with anyone (in a forum, an issue, a chat, or with a person
  helping you), or your hosting provider keeps logs that other people can read.

On those releases the connector wrote your CGM account username and password into Nightscout's
log. Upgrading stops new logs containing them. It cannot remove them from a log that already
exists.

If this applies to you:

1. **Change the password** at the CGM company's own website or app, and anywhere else you use
   the same password.
2. **Then update it in Nightscout's connector settings straight away, or readings will stop
   arriving.** That is the setting ending in `_PASSWORD` for your source, for example
   `CONNECT_SHARE_PASSWORD`, `CONNECT_CARELINK_PASSWORD` or `CONNECT_LINK_UP_PASSWORD`, or
   `BRIDGE_PASSWORD` if you use the Dexcom `BRIDGE_` settings. Until Nightscout has the new
   password it keeps trying the old one, and some CGM services lock an account for a while after
   repeated failed logins.
3. **Check that new readings arrive** afterwards, and keep your CGM app or meter to hand until
   they do.
4. **Delete old Nightscout log files you still have.**
5. **Check places where you pasted a log**, such as a GitHub issue, a forum or group post, a
   screenshot or a message, and remove the log where you can.

Whatever release you run, read a log before sharing it, and turn debugging off again when you
are done.

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

**The quick-pick list now shows your quick picks.** On 15.0.8 and earlier, the Quickpick list
in the bolus calculator only ever showed "(none)", however many quick picks were saved, because
the list was built before your food data had loaded. People had to add foods one at a time with
*Add from database* instead. The list is now built each time you open the bolus calculator. It
shows your saved quick picks in the order you set, and choosing one fills in the carbs with that
quick pick's own total. Quick picks marked hidden are not listed. A quick pick set to "hide after
use" disappears from the list the next time you open the calculator, after you submit with it.

Two things to know:

- **The bolus calculator is not shown to everyone.** It appears only if `boluscalc` is in your
  `SHOW_PLUGINS` setting, and only to someone who is allowed to enter treatments.
- **A quick pick added or changed elsewhere does not appear on a page that is already open.** It
  appears after that page reloads or reconnects. This is how Nightscout already sends food data
  to open pages, and this release does not change it.

The bolus calculator is a calculator, not a recommendation, and this release does not change
that. It does not decide a dose. **Always check that the carbohydrate amount shown is the one you
meant: check the carbs against the meal you are actually eating before you rely on them.** If you
use quick picks for meal dosing, go over how you use them with your care team. If you think a
past calculation used an amount you did not choose, raise it with your care team. This is not
medical advice.

### A page with no reading no longer hits an error when a device alarm arrives

Nightscout can raise alarms for things other than glucose, if you have switched them on: for
example a pump reservoir running low (`PUMP_ENABLE_ALERTS`), a loop that has stopped, or a
cannula or sensor that is overdue for a change. These are off unless you turned them on.

On 15.0.8 and earlier, if one of these alarms reached a Nightscout page that had **no glucose
reading to show** (the big number reads `---`), the page hit an internal error while handling it.
Nothing on screen changed, and the error was visible only in the browser's developer console.
This release removes that error.

**This fix does not make a `---` page sound device alarms.** What you see does not change. A
Nightscout page decides whether to sound an alarm from the server by looking at the latest glucose
reading. With no reading, it does not sound or show any of them, including pump, loop and age
alarms that have nothing to do with glucose. In testing, the same "URGENT: Pump Reservoir Low"
alarm turned the page red and played the alarm sound when a reading was on screen, and showed
nothing when no reading was on screen. This is listed under
[Known issues](#known-issues--not-fixed-in-this-release).

If you rely on a Nightscout page for device alarms such as pump, loop or site-change alerts,
**do not assume a page showing `---` will alert you. Keep the alarms on your devices themselves
(pump, phone app, CGM receiver) switched on.** This is not medical advice. Talk to your care team
about how you get alerted.

### Edited records no longer leave an old copy behind

Some records were saved with their ID (the label Nightscout uses to find a record again) in a
different form from the one Nightscout looks up: profiles, device status reports, foods and
activity records that arrived with their own ID, for example **copied from another Nightscout
site** or **restored from an export**, and treatments and glucose readings saved that way by
**Nightscout 15.0.6 or earlier**. Nightscout showed them, but **editing** one saved a **second copy**
and kept the old one, and **deleting** it by its ID did nothing. Apps using the newer API
(version 3), or the live connection some apps keep open, had the same trouble.

In this release those records are found. New records that arrive with their own ID are saved in
the normal form. Records already saved the old way are left as they are until one is edited or
deleted. Deleting one removes it, together with any old copy an earlier edit left beside it,
whether you delete it on a Nightscout page or from an app that uses the newer API, such as
AndroidAPS. Where an app can show only one of the two copies, it shows the one with the latest
edit. **If your site receives data from another Nightscout site, or you have restored data from an
export, or it has run since 15.0.6 or earlier**, look at any profile or treatment you have edited
there. If you see an old copy beside the one you edited, open the record in the profile editor, or
in the treatment list on the Reports page, and save it: the two become one record with that edit.
An edit made by dragging a treatment on the main chart, or from an app, changes the record but
leaves both copies. Deleting either copy deletes both. If you are unsure which settings or entries
are correct, check with your care team.

A device status report (the loop or pump status your phone app sends) that an app sends again is
recognised as already saved: it is not saved twice, and any new reports sent with it are saved.

A treatment or glucose reading sent to Nightscout without a usable ID is given one. One kind of
badly formed record could stop a Nightscout site from running, and stop it again after every
restart; that can no longer happen, and a site that already holds such a record keeps running.

The same change fixes deleting an access entry (a "subject" on the admin page) that was restored
from a backup or created by a tool that set its own ID. Before, the page reported success and the
entry stayed, **still able to access your site**. It is now removed. If you have deleted such an
entry before, check the list on the admin page to make sure it is gone.

### Moving a treatment on the chart now moves its insulin and carbs too

If you split a treatment by dragging it on the chart into the "Move carbs" or "Move insulin"
area, the chart showed the moved part at its new time, but Nightscout kept the **old** time when
it worked out insulin on board (IOB) and carbs on board (COB). In testing, 25 g of moved carbs
counted as 0 g on board. The same was true on 15.0.8 and earlier.

In this release, dragging a treatment to a new time, whether you move all of it or split it,
saves the new time everywhere Nightscout uses it. A treatment that an earlier version split this
way is corrected when you drag it to its time again, or when you open it in the Reports
treatment editor and save it. Other apps that edit treatments through Nightscout's API are not
changed by this fix.

**If you rely on Nightscout's IOB, COB or Bolus Wizard** and have split treatments by dragging
them before, look at those treatments after upgrading and check with your care team about any
you are unsure of. This is not medical advice.

### Searches, reports and filters return the right records

Some filters compared numbers as if they were words, so "temp basals of 30 minutes or more"
matched nothing and the site answered with an empty list instead of an error. Decimal amounts
such as "1.5 units or more" were rounded down to 1. A filter for records *without* a value
returned the records *with* it. Counting addresses could return zero for everything. Paging
through newer-API results could skip some records and repeat others.

**What you will notice:** reports, dashboards and tools that use these filters may show
different numbers — often many more records than before.

**Earlier results may have under- or over-reported delivered therapy.** If you have used a
report or tool built on these filters to look back at insulin, carbs or temp basals, the numbers
it showed may have been wrong. Nothing stored in your database was wrong; the question was being
asked wrongly. This is not medical advice. If a corrected figure changes your understanding of a
past period, discuss it with your care team rather than acting on it alone.

For a filter asking whether a value is present, only `true`, `false`, `1` and `0` are
understood. Other spellings, such as `null` or leaving the value empty, still mean "has the
value".

### Editing a user on the admin page keeps its notes and creation date

On earlier releases, opening a user on the admin page and saving it — for example to give it another
role — wiped that user's notes and replaced the date it was created with the date of the edit,
with no warning. Both are now kept, for users and for roles. You can still clear the notes on
purpose by emptying the notes box and saving. Notes and dates already lost to earlier edits
cannot be recovered.


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

### Quieter logs, and two new settings

Nightscout and its built-in CGM connector no longer write routine "heartbeat" and data-reload
messages to the log by default. Warnings and errors still appear. Two new settings turn the
detail back on when you are troubleshooting:

- `DEBUG_LOGGING=true` — more detail from Nightscout and the connector.
- `CONNECT_DEBUG=true` — more detail from the connector only (`CONNECT_DEBUG=false` turns the
  connector detail off even when `DEBUG_LOGGING` is on).

### If you run Nightscout with Docker Compose

*Docker Compose* runs Nightscout and its database together from one file, `docker-compose.yml`,
which ships with Nightscout. Docker lets a container keep only 1024 files open unless told
otherwise, which is too few for MongoDB: when it runs out it **stops completely** with "Too many
open files", and Nightscout cannot read or save anything until the database is restarted. Your
data is still there once it restarts. The bundled file now raises the limit to 64000, the
minimum MongoDB recommends.

**If you copied `docker-compose.yml` into your own set-up**, add these lines under your `mongo:`
service, then recreate the container (`docker compose up -d`):

```yaml
    ulimits:
      nofile:
        soft: 64000
        hard: 64000
```

To check it worked, look at the database's start-up log: the warning `Soft rlimits for open
file descriptors too low` should be gone. If you run MongoDB another way (MongoDB Atlas, a
hosting provider, or installed directly on a server), this does not affect you.

### Clock pages show when their reading is old, even when they lose their connection

The clock pages (the Clock, Color and Simple views, and custom clock faces) check your site for a
new reading every 20 seconds. On 15.0.8 and earlier, once those checks started failing, for
example because the network dropped or your site was down, the page kept showing the last
reading as if it were current: it never turned grey and never said how old it was. Only the time
of day kept changing. In this release the page keeps working out the reading's age while the
checks fail, and turns grey once the reading is old, as it does when readings simply stop.

A clock page is a display, not an alarm. Keep the alarms on your phone, CGM app or receiver
switched on. This is not medical advice.

### Clock pages opened from the menu on sites that need a login

Some sites are set up so that nobody can see them without logging in. On such a site, someone can
still be given read-only access with an **access token** (see the words list at the top) added to
the site's address. On 15.0.8, if that person then picked a clock page from the **Clock** menu, the
clock stayed blank: the menu did not pass the token on, so the site refused the clock's requests,
and nothing on the page said why. The menu links now carry the token, so the clock shows your
readings. If the site refuses a clock page anyway, the page now says it is not authorized instead
of staying blank. Opening a clock directly with `?token=` in its address worked before and still
does.

### A user without a name no longer stops your site

If a tool created a user or role on the admin page without a name, Nightscout stopped, and
stopped again at every restart, until that record was removed from the database by hand. Only
someone with administrator rights could cause this. A user or role without a name is now refused,
and a site that already holds one starts normally and notes it in the server log.

### Numbers that may look different on the same data

- **COB (carbs on board)** now shows the value reported by your looping app (Loop, AndroidAPS,
  Trio, OpenAPS) rather than Nightscout's own estimate, and appears on sites without a full
  profile. The tooltip says where the number came from. It may differ from what you saw before.
  COB is an estimate either way; how you use it is a question for your care team.
- **Daily Stats estimated A1c** was inflated in mg/dL mode. It is now calculated the same way in
  both units, so the figure may drop. It is an estimate, not a lab result.
- **Reports** no longer throw away valid readings after two closely spaced ones, so charts,
  averages and time-in-range may change slightly.
- **Basal, ISF and carb ratio during an AndroidAPS percentage Profile Switch**, and the IOB, COB,
  Bolus Wizard Preview and reports worked out from them, now match the phone. **Carbs and insulin
  that AndroidAPS deleted** no longer count in COB, IOB and reports. **Two treatments at the same
  time** are now both counted in daily totals. **AndroidAPS entries that arrived late or were
  edited** now count in Nightscout's own IOB and COB, and a COB that was too high because treatments
  were out of time order can drop. See
  [AndroidAPS, the careportal and caregivers](#androidaps-the-careportal-and-caregivers).

### A 48-hour view on the main chart

The "Hours:" choices on the main page, which set how much time the main chart shows, now include
**48**, after 24, so you can see two days at once. Nothing else about the chart changes, and the view it opens with is the same as before.

### Filter the treatments report by type

**Reports → Treatments** now has a list of event types above the table (for example "Meal Bolus"
or "Temp Basal", each with how many entries it has), so a long list can be narrowed to one kind of
entry. The default, "All event types", shows the same list as before.

### Day to Day report: events that run past midnight

In **Reports → Day to Day**, an event that lasts a while (for example Exercise, a Note with a
length, a Temporary Target, or a Loop override) now shows on every day it covers. An exercise
entered at 22:00 for four hours shows from 22:00 to midnight on the first day and from midnight to
02:00 on the next, including when you look at the next day on its own. Before, it showed only on
the day it started and ran off the edge of that day's chart. Events that start and end on the same
day look the same as before.

### Food Editor scrolls on phones

On a phone, the food list in the Food Editor could not be scrolled by swiping: it has room for
two or three foods, and a swipe that started on a food did nothing, so the rest of the list
could not be reached. A swipe that started on a quick pick did not scroll the page either. Both
now scroll. Dragging a food into a quick pick and reordering quick picks still need a mouse, as
before.

### Bulk deletes from xDrip4iOS remove the readings

xDrip4iOS can delete glucose readings from your site in bulk by listing the time of each
reading. Nightscout answered every such request with an error and deleted nothing, so readings
you deleted in the app stayed on your site, in the chart and in reports. Nightscout now deletes
the listed readings, and only those. No reading was changed or lost: the readings that stayed
were ones the app meant to remove. Readings you deleted in xDrip4iOS before upgrading are still
on your site; delete them again from the app, or in Nightscout, if you want them gone. Other
apps that ask for several readings or treatments by their times at once now get them, where
they got an error before.

### Translations

Updated translations from Nightscout's volunteer translators on Crowdin, as of early September
2026. Later Crowdin updates are not in this release.

### Settings documentation

The README now describes the API v3 settings (every name that starts with `API3_`), the webhook
plugin and its four `WEBHOOK_` settings, and `ENTRIES_COLLECTION`, and no longer lists
`MONGODB_COLLECTION`, which does nothing. It also says that `SECURE_HSTS_HEADER_INCLUDESUBDOMAINS`
is spelled as one word; the spelling with an underscore before `SUBDOMAINS` has no effect. The
Azure deployment template now uses Node 22 by default instead of a version Nightscout no longer
runs on. `AUTH_DEFAULT_ROLES` is now described as the setting that decides who can see or change your
data without logging in, with what each built-in role allows; `AUTHENTICATION_PROMPT_ON_LOAD` only
makes the page ask for a login and grants nothing. The roles `careportal`, `devicestatus-upload` and
`activity` do nothing in `AUTH_DEFAULT_ROLES` unless `readable` is also there. API v3 `settings`
records are stored exactly as sent, so an app that displays them must treat them as untrusted.

### An open page shows a cancelled temp basal as cancelled

When AndroidAPS (with its NSClient v3 connection) or Trio shortened or cancelled a temp basal, a
Nightscout page that was already open could keep showing the old rate in the basal display and on
the chart: for about a quarter of a minute when another temp followed, and until the temp's planned
end when it was simply cancelled. The pump and the app had the right value, and reloading the page
showed it. An open page now shows the change as soon as it arrives.

### The glucose value in a treatment's pop-up on the chart

When you point at (or tap) a carb or insulin entry on the chart, a small box (a tooltip) shows its
details, including a blood glucose (BG) value if one was entered with it. On a site set to show
mmol/L whose profile (your basal, carb ratio and sensitivity settings) is saved in mg/dL, or the
other way round, that box converted the BG even when it was already in your site's units: for example, a BG entered as 5 on an mmol/L site showed as
0.3. The box now converts from the units the BG was saved in, so it shows the
number you entered. Only that box changes; the saved entries were always right and are not changed.

### Other fixes

Faster data loading on sites with many treatments; deleted records no longer reappear; failed
treatment searches no longer crash the server; a problem reading from the database while answering a
request for the activity log or the current profile no longer stops Nightscout until it is
restarted (it answers that request with an error and keeps running); clearer error messages when a Loop remote
command fails (the form keeps what you entered); profile switches and unnamed profiles handled
correctly; a site with no profile no longer shows an alert that cannot be dismissed; the clock
view shows the worried face for low and falling readings; voice assistants (Alexa, Google Home)
always answer in your site's configured language (a language requested by the assistant is no
longer used, and one assistant request can no longer change the language of the whole site);
Alexa gets an immediate answer to a kind of request Nightscout does not handle, instead of being
left waiting; a misspelled plugin name in `ENABLE` now gets a suggestion in the server log; the
"Nightscout is having trouble" start-up page no longer fails on one kind of error message that
no current version produces; deployment with npm 12 no longer fails; the library that reads web
addresses and form posts is updated to a version that clears three published security notices
against it; a filter listing more than 20 values (for example, "these 30 records") now works,
where 15.0.8 refused it with an error, so a tool that deletes records by such a list now deletes
them; each Loop remote command (override, carbs or bolus) now closes its connection to Apple's push
service when the push is done, where 15.0.8 kept every one open until the server restarted, so a
busy site accumulated connections and memory; more software libraries are updated to versions
that clear security notices published against them in late September, with no change in how
Nightscout works (none of them changes what your browser loads); updated translations
and many other software library updates.

---

## What you must do

1. **Check the list in [Before you upgrade](#before-you-upgrade-what-to-check)** before you
   start.
2. **If you are on MongoDB 4.4**, plan your move to 5.0 or later. 15.0.9 still works with 4.4.
3. **If insulin-age alerts are on**, tell whoever receives your alerts about the new urgent
   alert (see [Read this first](#read-this-first-the-insulin-reservoir-urgent-alarm-starts-working)).
4. **If you have saved users on the admin page and think a token may have been exposed**,
   retire it by deleting and re-creating the user, or by changing `API_SECRET` — see
   [Access tokens stored in plain text](#access-tokens-stored-in-plain-text). Note that
   **renaming the user does not retire its token**, even though the token's appearance changes.
5. **If you use `MMCONNECT_` settings, or `DEXCOM_BRIDGE_USE_LEGACY=true`**, move to the built-in
   connector's settings (see
   [The old MiniMed and Dexcom connections are being retired](#the-old-minimed-and-dexcom-connections-are-being-retired)).
6. **If you ran the built-in connector on 15.0.8 or earlier and shared a log, or your hosting
   provider keeps logs others can read**, consider changing your CGM account password, and then
   update it in Nightscout's connector settings so readings keep arriving — see
   [Your CGM account password](#your-cgm-account-password).
7. **If you copied `docker-compose.yml`**, add the open-file limit to your `mongo:` service.
8. **If you use `TREATMENTS_AUTH=off`**, read the new admin warning and decide whether to keep it.
9. **If you want the stronger protection against password guessing**, set `TRUST_PROXY` as
   described in [The new `TRUST_PROXY` setting](#the-new-trust_proxy-setting). Otherwise leave it
   unset.
10. **If your site uses mmol/L**, check your alarm levels after upgrading (see
    [Low alarms on sites that use mmol/L](#low-alarms-on-sites-that-use-mmoll)).
11. **If you use `PUMP_WARN_ON_SUSPEND`**, tell whoever receives your alerts that a "Pump
    Suspended" warning can now arrive.
12. **If you use AndroidAPS with the careportal or a caregiver**, check the phone's treatment list
    for meals entered twice, and delete treatments in AndroidAPS as well as elsewhere (see
    [AndroidAPS, the careportal and caregivers](#androidaps-the-careportal-and-caregivers)).
13. **If you renamed IFTTT applets to translated names**, rename them back to the documented names
    (see [IFTTT alerts on sites not set to English](#ifttt-alerts-on-sites-not-set-to-english)).
14. **After upgrading, check that everything connected to your site still works**, and watch for
    a day.

## What to check afterwards

- Your glucose readings are arriving and the page updates.
- Uploaders, phone and watch apps, and follower apps still connect.
- Any tool that reads from or saves to your site through the API still works. An error such as
  "Bad count" or a refused filter condition is from the corrections above; report it to the
  tool's author.
- Any report or filtered view you rely on — expect numbers to change; that is the fix.
- The IAGE box, if you use insulin age: it may now show URGENT.
- If your site uses mmol/L: the target lines on your chart and your alarm levels are the numbers
  you meant. The server log's start-up lines show each alarm level Nightscout converted from
  mmol/L.
- If you use `PUMP_WARN_ON_SUSPEND`: while your pump is suspended, the pump box turns the warning
  colour.
- Bookmarked links that contain an underscore.
- If you set `TRUST_PROXY`: your site still loads over https, the startup warning about the
  failed-login delay is gone from the log, and one wrong password sent from your phone shows your
  phone's address in the "Failed authentication" message.
- If you moved from `MMCONNECT_` or `BRIDGE_` settings: readings arrive through the connector.
- If you changed your CGM account password: the new password is in Nightscout's connector
  settings, and readings arrive.
- If you use AndroidAPS: the treatment list on the phone has no meal twice, and during a percentage
  Profile Switch the basal, ISF and carb ratio on your site match the phone.
- If you use IFTTT on a site not set to English: a test alarm reaches your applets.
- If a watch face reads your site: its delta and bolus estimate look right without any adjustment.

---

## Known issues — not fixed in this release

- **Settings that nobody can look up can delete old data permanently.** Nightscout's API v3
  reads six settings that are not in its documentation: `API3_AUTOPRUNE_ENTRIES`,
  `API3_AUTOPRUNE_TREATMENTS`, `API3_AUTOPRUNE_DEVICESTATUS`, `API3_AUTOPRUNE_PROFILE`,
  `API3_AUTOPRUNE_FOOD` and `API3_AUTOPRUNE_SETTINGS` (also accepted in lower case, and with a
  `CUSTOMCONNSTR_` prefix on Azure). If one is set to a number of days, then whenever an app
  saves, changes or deletes a record of that kind through API v3, Nightscout deletes every record
  of that kind older than that many days. The deletion cannot be undone. They do nothing unless
  set, and this is the same on 15.0.8 and earlier. If a deletion fails (for example, the
  database is unreachable at that moment), Nightscout stops and must be restarted. Check your
  site's settings for any name that starts with `API3_` and remove one you did not set on
  purpose. The README now describes every `API3_` setting.
- **A page with no glucose reading does not sound or show any server alarm.** When the big
  number reads `---`, a Nightscout page ignores every alarm the server sends, including pump,
  loop, cannula, sensor and insulin-age alarms that have nothing to do with glucose. This is the
  same on 15.0.8 and earlier. A change is planned for a later release. Until then, keep your
  devices' own alarms on and do not rely on a `---` page to alert you.
- **If the device uploading your readings has its clock set ahead, the stale-data warning comes
  late.** Nightscout can warn you when no new glucose reading has arrived for a while; by default
  it warns in the browser at 15 and 30 minutes. If the phone or device uploading your readings
  has its clock set **ahead** of the real time, Nightscout treats each reading as newer than it
  is. If your readings then stop, the warning comes late, by roughly how far ahead that clock is.
  For example, if the clock is an hour fast, the 15-minute warning comes after about an hour and
  a quarter. What you might see is the "minutes ago" display reading "future", or staying at
  "1m" while readings are arriving. If you see that, check the date, time and time zone on the
  uploading device. If you depend on the stale-data warning, make sure you have another way to
  notice that readings have stopped. (A single reading dated in the future does **not** switch
  the warning off: Nightscout skips readings dated in the future when it decides whether your
  data is stale.) This is not medical advice; talk to your care team about what you rely on
  Nightscout for.
- **While `TRUST_PROXY` is unset, the failed-login delay can be avoided**, as on earlier
  releases. Nightscout says so in its log at startup. Set `TRUST_PROXY`, or restrict access at
  your proxy or hosting provider.
- **Access tokens already stored in plain text stay in your database** until you retire them
  or save that user again. See the next section.
- **Alarm thresholds entered in the wrong units are not caught.** Unless you have set
  Nightscout to mmol/L, it reads alarm thresholds (`BG_LOW`, `BG_HIGH` and the target range)
  as mg/dL. A low alarm entered as `3.9` (meaning mmol/L) is kept as 3.9 mg/dL, a level no
  reading ever reaches, so **that low alarm can never go off**, and nothing warns you. A high
  alarm entered as `14` is instead quietly changed to a different number, and only the server
  log says so. (How a site set to mmol/L reads its alarm levels is described
  [above](#low-alarms-on-sites-that-use-mmoll).) Check that the thresholds on your settings page
  are the numbers you meant, keep
  your device's own alarms on, and talk through your alarm settings with your care team. This
  is not medical advice.
- **Deleting a treatment anywhere except AndroidAPS does not reach AndroidAPS.** A treatment
  deleted in the careportal, Loop, Trio or xDrip+ is removed from your site but keeps counting on
  an AndroidAPS phone. Delete it in AndroidAPS as well.
- **Rarely, an entry can appear twice.** When the careportal and AndroidAPS record the same kind of
  treatment at exactly the same moment, and an app later sends the careportal entry again,
  Nightscout can show it twice. Check your treatment list if totals look high.
- **Some treatments at the same time are still stored as one.** Two careportal entries in the same
  minute with the same amount are stored as one, because nothing tells them apart from pressing
  Save twice. A bolus and carbs that AndroidAPS records in the same thousandth of a second, both as
  "Meal Bolus", can also be stored as one.
- **The careportal can fill in "Entered By" with the word `undefined`.** If you save a careportal
  entry with Entered By left empty, the next time you open the careportal that field shows
  `undefined`, and entries are saved as entered by "undefined" unless you clear or change it.
  Nothing else about the entry is affected. The same happens on 15.0.8 and earlier.
- **After you edit or delete a treatment in Reports → Treatments, the table can still show the old
  entry.** The change is saved, and the main chart shows it. Press **Show** again to refresh the
  table. The same happens on 15.0.8.
- **During an AndroidAPS percentage Profile Switch, the basal pill's pop-up can show ISF and carb
  ratio with many decimal places**, for example `1.866666666667`. The number is correct; it is
  only not rounded for display.
- **Reports → Profiles can leave out profiles saved on the last day of the report.** When more
  than one profile was saved on that day, only the earliest is listed, and other report pages may
  draw that day's basal and targets from it. The same happens on 15.0.8.
- **In Reports → Day to Day, a temporary target that was cancelled early is shown for the full
  time it was set for**, and a Loop override that was ended early probably is too. The main chart
  shows when it really ended. Because events that run past midnight now also show on the next
  day, such a band can now appear on that day's chart as well. The same happens on 15.0.8 within
  one day.
- **For about a minute after a new phone, or a reinstalled Loop, uploads its settings, a remote
  command from the careportal or LoopCaregiver can still go to the old phone**, and Nightscout
  answers as if it was sent. After changing phones, check on the phone in use that a remote
  command arrived before relying on it. This is not medical advice. The same happens on 15.0.8.
- **A record whose identity was saved as a list cannot be deleted through API v3**, which
  AndroidAPS uses. 15.0.8 deleted it. Nightscout shows such a record's list as its identity, and
  this release deletes a record only by the identity Nightscout shows for it. No commonly used app
  is known to save an identity as a list. If a record you deleted in AndroidAPS still shows on
  your site, delete it in the careportal as well.
- **A record saved with an empty identity cannot be edited through API v3 by the id Nightscout
  shows for it**: the edit is refused, or a second copy is saved. No commonly used app is known to
  save records this way. The same on 15.0.8.
- Filters asking "is this value present" understand only `true`, `false`, `1` and `0`.
- Silencing an alarm from an app has no upper limit on how long it can be silenced for.
- **A security check of this release reports two "high" findings that do not affect Nightscout.**
  If you, your hosting service or a security tool run a check such as `npm audit` on 15.0.9, it
  reports the same published notice twice (GHSA-86w9-cpqp-85rv, tracked by the project as
  BF-154). The notice concerns how a library called node-forge checks one kind of digital
  signature. Nightscout does not use that part of the library. node-forge is used only when Loop
  remote commands are set up, to read your site's own Apple push-notification key and certificate,
  and nothing in Nightscout asks it to check a signature. The project analysed this in the code,
  so for Nightscout the finding is a false positive. No fixed version of node-forge has been
  published yet, and the newer Apple push-notification library planned for the next releases
  still uses the same version, so the update is deferred to that modernization work and will be
  made once a fixed version exists. You do not need to do anything.
- **A security check also reports a "high" finding about a pattern-matching library called
  `braces`** (GHSA-vfj7-8cjw-p6xm, tracked by the project as BF-161). On three little-used web
  addresses (`/times`, `/times/echo` and `/slice`), a request built with a deeply nested bracket
  pattern can make that one request fail with an error. The site keeps running, and nothing is read
  or written. The same is true on 15.0.8, which is the release in use today. No fixed version of
  `braces` has been published yet; a limit on how deeply such a pattern can nest is planned for a
  later release. You do not need to do anything.
- **A security check also reports a "high" finding about `compression`**, the library Nightscout
  uses to shrink the responses it sends (GHSA-vc2v-76pw-4v95, tracked as BF-163). According to the
  notice, each response that is cut off before it finishes leaves some memory in use; if that
  happens often enough, the site can run out of memory and restart. This is the notice's
  description; it has not been measured on Nightscout. It is fixed in `compression` 1.8.2, which
  Nightscout takes up in the modernization releases that follow 15.0.9. The same version is on
  15.0.8. You do not need to do anything.

### Access tokens stored in plain text

An **access token** is the password-like string that lets a person or an app use your
Nightscout site with the roles you gave them. It is supposed to be worked out fresh each time
and never stored. On 15.0.8 and earlier, **saving a user on the admin page wrote that user's
token into your database in plain text.** Anyone who can read your database, or a backup,
replica or hosting snapshot of it, can read the token. This release stops new copies being
written.

**Upgrading does not delete it.** A copy already stored stays in your database until that user
is next saved on the admin page, and **removing the copy does not make the token stop working.**
Anyone who has had read access to your database since the first edit could have used it.

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

**Who this applies to:** anyone who has saved a user through the Nightscout admin page. If you
have only ever used your `API_SECRET` and never created separate users, there is nothing to
retire. If you can look inside your database, a user is affected if its record in the
`auth_subjects` collection has an `accessToken`, `accessTokenDigest` or `digest` field. **Never
paste a token or your `API_SECRET` into an issue, forum post, screenshot or chat** — those
values are the credential itself. Treat any database backup or export as containing working
credentials.


## About the version number

This release is **15.0.9**, the number the development version already carries. Some changes in
it refuse requests that earlier releases accepted (the `count`, filter-condition and user-field
items under [Corrections](#corrections-requests-answered-differently)); they are released as
corrections of behaviour that was never intended, not as new features, and nothing you receive
depends on the number. Sites that follow the development channel may already report `15.0.9`;
a report from "15.0.9" made before this release is from that channel.

---

*Draft, 2026-10-07, on the development version 43289dde; not yet released.*
