# Nightscout 15.0.9 — testing notes for the release candidate

**DRAFT — prepared for maintainer review before it is shared.** Kept current as reports arrive and
as the test build changes. Last updated 2026-10-03.

*For people who would like to help test the next Nightscout release before it comes out. Part 1 is
for people who **use** a Nightscout site, for themselves or a family member. Part 2 is for people who
**run** a site (set up its hosting and settings) or write apps and scripts that talk to it. Nightscout
is a secondary display, and this is test software. Nothing here is medical advice or advice about
insulin doses. For changes to your own or your family member's therapy settings, talk to your care
team.*

## Where testing stands

- As of 2026-09-29, one Loop, one Trio and one AndroidAPS user had each run the test build of that
  time (`7000eb18`) for about two days, with no errors and no changes in behaviour.
- On 2026-10-02 the maintainer reported that AndroidAPS, Trio and Loop users running the `dev`
  branch had reported stable, unsurprising behaviour all week. These reports are informal; how many
  sites and for how long is not recorded.
- Nobody has yet reported trying the unusual cases on purpose. That is what these notes ask for.

The release notes list what changed:
[release notes](release-notes.md). These notes pick out the changes that need someone with a
particular setup to try them.

## Words used here

| word | meaning |
|---|---|
| **site** | your Nightscout web page and the database behind it |
| **uploader** | anything that sends data to your site: Loop, Trio, AndroidAPS (AAPS), xDrip+, a CGM connector |
| **follower** | anything that only watches: a parent's phone, LoopFollow, a watch face, a report tool |
| **careportal** | your site's own form for entering treatments (the **+** button) |
| **token** | a limited-access login made on your site's admin page ("Admin tools"), for example read-only for a follower. Each one belongs to a **user** there and gets that user's **roles** (for example `readable` or `admin`) |
| **API secret** | your site's master password (`API_SECRET`) |
| **setting** | a value your site is started with, such as `DISPLAY_UNITS=mmol`. Where you change them depends on where your site is hosted |
| **server log** | the messages your site writes while it runs. Your hosting service has a page or command to show them |
| **IOB / COB** | insulin on board / carbs on board |

---

## Before you start (everyone)

**Stay safe while testing.**

- **Have a second way to see your readings** the whole time you test: your CGM app, your pump or
  your meter. **Keep the alarms on your CGM, pump and phone app switched on.** Do not rely on the
  test build to warn you.
- **Do not change any therapy to test something.** Where a check below needs a situation such as a
  suspended pump or an overdue reservoir, check it when that happens anyway. If you want to provoke
  it, use a separate test site with a simulated pump and CGM (Loop, Trio and AAPS each have one),
  not the site and phone that deliver your insulin.
- **Remote commands send real treatments.** Only send a remote bolus or carbs you would send anyway,
  or send them to a test phone with a simulated pump.
- **Back up your database before you switch** to the test build. Going back to 15.0.8 has not been
  tested as its own step; if you do go back, tell us how it went.

**Keep your data private when you report.**

- **Never post** your site's address, your API secret, tokens, or screenshots that show names, dates
  of birth or other personal details. Crop or blur them first. Glucose values in a screenshot are
  fine only if you are comfortable sharing them.
- Tell us what happened in words. If someone asks for a log, remove anything that looks like a
  password, token or web address first.

**What to put in a report** (copy this list):

1. What you did, what you expected, and what you saw.
2. Your apps and their versions (for example "Loop 3.x", "AAPS 3.3.x", "xDrip+ nightly of …").
3. Whether your site shows **mg/dL or mmol/L**.
4. Whether your site needs a login to view (`AUTH_DEFAULT_ROLES=denied`) or not (`readable`, the usual).
5. Where your site is hosted, and your database's MongoDB version if you know it.
6. For each app that uses a token: **which role** that token has (`readable`, `careportal`, `admin`…).
7. Whether the same thing happens on 15.0.8, if you can tell.

**Where to report:** *[maintainer to fill in: the channel or issue template for 15.0.9 reports]*.
"It worked" reports are useful too. Say which check you did.

**Already known — please don't report these again**, but do tell us if one looks worse than
described: the [known issues](release-notes.md#known-issues--not-fixed-in-this-release) in the release
notes.

## Getting the test build

The test build is the `dev` branch of `nightscout/cgm-remote-monitor` at commit **`43289dde`**
(full: `43289dde4c6913c22b6656c3321e3d7414c47870`, 2026-10-07). Its version reads **15.0.9**. Since
the earlier test build `7000eb18` it adds:

- the Day to Day report shows events that run past midnight on both days (see 1.7);
- the Food Editor's lists scroll by touch on phones (see 1.8);
- xDrip4iOS can delete readings from your site in bulk (see 2.4);
- error pages and error replies no longer show internal details (see 2.6);
- a fix that stops one kind of oversized request to two little-used API addresses from making the
  server stop responding for seconds; it is now refused (nothing to test by hand);
- a fix for a problem reading from the database while answering a request for the activity log or
  the current profile, which stopped Nightscout until it was restarted; it now answers that request
  with an error and keeps running (nothing to test by hand);
- a page that is already open shows a temp basal that AndroidAPS or Trio cancels or shortens as
  cancelled or shortened, without reloading (see 1.9);
- the small box that pops up over a carb or insulin entry on the chart shows a blood glucose value
  in the units it was entered in (see 1.2);
- on a site that needs a login, a clock page opened from the menu by someone using an access token
  shows the readings instead of staying blank (see 1.5);
- the setup guide (README) describes the settings the code reads, including the API v3 settings
  (nothing to test by hand; see the release notes);
- updated versions of several software libraries it uses, with no change to what you see.

If you are running `7000eb18` or a later `dev` build, keep going: your reports still count.

- **Docker:** `nightscout/cgm-remote-monitor:dev_43289dde4c6913c22b6656c3321e3d7414c47870`. This tag
  always means exactly this build. `latest_dev` means "the newest `dev`" and moves when `dev` changes,
  so check which commit it is before relying on it.
- **Deploying from your own copy of the code** (Heroku, Railway, Northflank, Render, a VPS and
  similar): update your copy's `dev` branch from `nightscout/cgm-remote-monitor` and deploy that
  branch. Check the commit is `43289dde`.
- **A hosting service that runs Nightscout for you:** ask them whether they offer the test build.

If `dev` moves to a new commit before the release, these notes will name it.

---

# Part 1: for people who use a site

Pick the checks that match your setup. Every check is useful on its own, and most take only a look.

## 1.1 Everyone: keep it running for three days or more

Most of the reports so far cover two quiet days. What we most need now is **three days or more that
include ordinary disruptions**. Note down when each of these happened and whether your site kept up:

- a sensor change, and a cannula or reservoir change;
- your phone restarting, or the app being force-closed and reopened;
- a period without signal (a flight, a basement, a phone left at home), and catching up afterwards;
- a caregiver or follower watching from another phone the whole time;
- editing or deleting a wrong entry, on the site and in your app.

**Working looks like:** readings keep arriving; after a gap the missing readings and treatments fill
in; the IOB and COB your site shows agree with your app as closely as they did on 15.0.8; nothing
appears twice; followers keep updating.

## 1.2 Sites that show mmol/L

**This is the most important check for anyone on mmol/L.** 15.0.9 reads each alarm level on its own,
so on some sites **low alarms start working** where they never did. See
[Low alarms on sites that use mmol/L](release-notes.md#low-alarms-on-sites-that-use-mmoll).

1. **Before switching,** write down the alarm levels you expect (urgent high, top and bottom of your
   target range, urgent low), and whether each is set on your site or left at the default.
2. **After switching,** look at the target lines on your chart and the alarm levels your site shows.
   Are they the numbers you meant?
3. If you can see your server log, look for lines like
   `Threshold bgTargetTop 8.5 taken as mmol/L, converted to 153 mg/dl`, one for each level.
4. Over the next days: did a low alarm go off that never used to, or did "Warning HIGH" on in-range
   readings stop? Either can be the fix. Tell us which, and tell whoever receives your alerts.
5. If you enter a blood glucose (BG) value together with carbs or insulin in the careportal, point
   at (or tap) that entry on the chart. **Working looks like:** the small box that pops up shows the
   BG you entered. This matters most if your profile (basal, carb ratio and sensitivity settings) is
   saved in mg/dL, as some apps upload it; on 15.0.8 such a site could show 5 as 0.3.

## 1.3 AndroidAPS

See [AndroidAPS, the careportal and caregivers](release-notes.md#androidaps-the-careportal-and-caregivers).

- **Silencing an alarm from AAPS.** In 15.0.9 an app can silence a Nightscout alarm only if its token's
  user has the `admin` role. With any other role, the silence does nothing, and **the app is not
  told**. When a Nightscout alarm next goes off on its own, silence it from AAPS and check whether it
  also goes quiet on your site. **Tell us your AAPS token's role and what happened.** Nobody has
  tested this from the phone yet.
- **Careportal and caregiver entries.** Carbs or insulin entered in the careportal, or by a caregiver,
  should reach the phone. An edit made on the site should show up in AAPS.
- **No meal twice.** Check the treatment list on the phone and on the site after a day that included
  a gap in signal.
- **Late entries.** An entry that reaches the site late (after being offline), or one you edit to an
  earlier time, should count in IOB and COB on the site, the same as on the phone.
- **Percentage Profile Switch.** During one you would make anyway, the basal, ISF and carb ratio on
  the site should match the phone. Also look at the **Bolus Wizard Preview** pill and
  **Reports**; neither has been checked in a browser during a switch yet.
- **Loop turned off and back on.** If you turn the loop off in AAPS and later back on, Nightscout's
  "not looping" and pump alerts (if you use them) should work again afterwards.

## 1.4 Loop, Trio and LoopCaregiver: remote commands

Remote overrides, remote carbs and cancelling an override from the careportal have been checked. Still
to check:

- **A remote bolus**, from the careportal and from the **LoopCaregiver app itself** (so far only
  scripted). Follow the safety note above. **Working looks like:** the phone in use receives it once,
  and the site records it.
- **After changing phones or reinstalling Loop:** for up to about a minute a remote command can still
  go to the old phone (a known issue). Tell us if you see it take longer.

## 1.5 Followers, clocks and watch faces

- **Clock views** (menu → Clock, or `/clock/…`): they should show when their reading is old, including
  after the page loses its connection.
- **Clock views on a site that needs a login**, if you open your site with an access token in its
  address (`?token=…`): pick a clock from the menu. **Working looks like:** the clock shows your
  readings. If the site refuses the clock (for example, the token does not allow reading), the page
  should say it is not authorized rather than stay blank.
- **Watch faces** that read your site: the change since the last reading (delta) and any bolus
  estimate should look right **without** any adjustment. If you had set up a watch face to multiply
  or divide by 18, undo that and tell us whether the numbers are right.
- **Sites that need a login** (`AUTH_DEFAULT_ROLES=denied`): followers such as LoopFollow and signed-in
  pages should keep receiving live updates and alarms.

## 1.6 Alarms that now reach your phone

These alerts could never fire before. Check them when the situation happens anyway.

- **Insulin age** (the IAGE box): past your urgent level (72 hours unless you changed `IAGE_URGENT`)
  the box should show **URGENT**. With `IAGE_ENABLE_ALERTS` on, one notification is sent when the
  reservoir reaches that age, and it does not repeat.
- **Pump suspended**: with `PUMP_ENABLE_ALERTS` and `PUMP_WARN_ON_SUSPEND` on, while your pump is
  suspended the pump box on the page should turn the warning colour and a "Pump Suspended" warning
  should arrive. Tell us your app and pump if the box says "suspended" but no warning arrives.
- **IFTTT** on a site not set to English: applets named `ns-warning`, `ns-urgent` and so on should now
  fire. If you had renamed them to translated names, rename them back.

## 1.7 Reports

- Reports you use at clinic visits (Day to day, Daily stats, Distribution, Treatments): **some numbers
  are expected to change**, because filters now return the right records. Tell us if a number
  changed in a way you can't explain, with the report name and date range, not the data itself.
- The treatments report can now be filtered by treatment type.
- **Day to day** (builds from `3014f883` on): an event that lasts a while and runs past midnight, such
  as an exercise at 22:00 for four hours, should show on both days and stay inside each day's chart.
  A temporary target cancelled early is still drawn for the full time it was set for (a known issue).

## 1.8 Food Editor on a phone or tablet

The Food Editor (menu → Food Editor, or `/food` after your site's address; the menu item shows when
you are signed in with admin access) keeps your saved foods and **quick picks** (groups of foods you
can pick in one go in the bolus calculator). On 15.0.8 its lists
could not be scrolled with a finger on a touch screen. With some foods and quick picks saved:

- On a phone or tablet, swipe up on a food in the list. **Working looks like:** the list scrolls to
  the foods below.
- Swipe up on a quick pick. **Working looks like:** the page scrolls.
- On a computer with a mouse: drag a food onto a quick pick (the food is added to it), and drag a
  quick pick by the empty end of its title line above another (the order changes). This should work
  as it did on 15.0.8.

Tell us your phone or tablet and browser if a swipe does not scroll.

## 1.9 AndroidAPS (NSClient v3) and Trio: a cancelled temp basal on an open page

On 15.0.8, when AndroidAPS (connected through NSClient v3) or Trio cancelled or shortened a temp
basal (a temporary change to the background insulin rate), a Nightscout page that was already open
could keep showing the old rate in the basal box and on the chart, until the temp's planned end.
Reloading the page showed the right value. Check this when your app cancels a temp basal anyway;
do not change any setting to make it happen.

- Keep your site open in a browser while your app is looping. When the app cancels a temp basal (it
  shows the scheduled basal again), look at the basal box and the chart on the open page.
  **Working looks like:** as soon as the change reaches your site, the page shows the scheduled
  rate again, without reloading.
- If the page still shows the old temp rate after a few minutes, reload it and note whether the
  reload changes what it shows. Tell us your app and its version.

---

# Part 2: for people who run a site, or write tools that use it

Contributor detail on what changed is in [contents](contents.md) and the
[consumer-impact survey](../../docs/60-research/remedial/consumer-impact-15.0.9-2026-09-23.md). The
checks below are the ones only a real deployment or a real client can answer.

## 2.1 `TRUST_PROXY` on your actual host

`TRUST_PROXY` is new and optional; unset behaves as 15.0.8. See
[The new `TRUST_PROXY` setting](release-notes.md#the-new-trust_proxy-setting). We would like one
report per hosting setup: Heroku, Railway, Northflank, Render, Fly, Azure App Service, a VPS behind
nginx or Caddy, Cloudflare in front of any of these, and hosted Nightscout services.

1. Start with the setting unset. The server log should say at startup that the failed-login delay does
   not protect against guessing.
2. Set the value you think is right (usually a number of proxies, such as `1`).
3. **Working looks like:** the site loads over https with no redirect loop; the startup warning is
   gone; one deliberately wrong password sent from a phone on mobile data shows **the phone's
   address** in the admin page's "Failed authentication" notice.
4. **If the site stops loading, remove the setting** and report the host and the value you tried.

Report: host, value, and whether each of the three results in step 3 held. Don't post the address you
saw, only whether it was the phone's, the proxy's or something else.

## 2.2 Sites that need a login (`AUTH_DEFAULT_ROLES=denied`)

- Signed-in pages and followers get live updates and alarms; a page that is not signed in gets none.
- After an uploader with an old password fails to sign in from the same network, a signed-in page may
  start receiving alarms only after the failed-login delay. Tell us if that delay looks long enough to
  matter.

## 2.3 Tokens and roles used by apps

- **Silencing alarms needs `admin`.** For each app on your site that silences alarms, tell us its
  token's role, and whether that app's setup guide tells people to use that role. This decides how
  many people the change reaches; it is not in any code we could read.
- **Users edited on the admin page** keep their notes and creation date. Other fields a tool stored on
  a user are dropped the next time that user is saved. Tell us if a tool you use stored its own fields
  there.

## 2.4 Clients we have no field evidence for

The replay lab reproduced these, but no one has run the real thing against the test build yet.

| client | what to check | working looks like |
|---|---|---|
| **OpenAPS / oref0 rig** | the rig's logs during normal looping | no `400 Bad count`; the rig does not re-upload its last 24 h of treatments on every loop; the site's server log shows one `API v1: … (logged once)` deprecation line |
| **GluPredKit** | building a dataset over a date range | entries, treatments and profiles come back, not empty lists; one `API v1: … (logged once)` line |
| **nightscout-reporter** (the current app), **Sugarmate**, **python-nightscout**, home-made scripts, spreadsheets | whatever you use them for | same results as on 15.0.8; any `Bad count` or "unsupported operator" error is from the [corrections](release-notes.md#corrections-requests-answered-differently): report the tool, its version and the request's shape (not its data) |
| **xDrip+, xDrip4iOS, Loop, tconnectsync** on a site with records from 15.0.6 or earlier, or copied from another site | edit and delete an old record from the app | the record updates in place or is deleted, with no second copy |
| **Bulk-delete tools** | a delete by a list of more than 20 ids | on 15.0.8 this failed and deleted nothing; on 15.0.9 it deletes every match. Check that is what you meant |
| **xDrip4iOS** (build `50bc1084` or later) | readings xDrip4iOS deletes from your site in bulk | the readings are removed from the site. On 15.0.8 these deletes answered with a server error and removed nothing; deletes of one reading or of a time range already worked |

## 2.5 Setup changes

- **Docker Compose** with the bundled `docker-compose.yml` or a copy: MongoDB should start and stay up
  (the file now raises its open-files limit). See
  [If you run Nightscout with Docker Compose](release-notes.md#if-you-run-nightscout-with-docker-compose).
- **`MMCONNECT_` or `BRIDGE_` settings:** move to the connector's `CONNECT_*` settings and check that
  readings arrive through the connector. See
  [The old MiniMed and Dexcom connections are being retired](release-notes.md#the-old-minimed-and-dexcom-connections-are-being-retired).
- **The built-in CGM connector** (Dexcom Share, LibreLinkUp, CareLink, Glooko): readings keep arriving
  over several days, including after the vendor app logs you out or you change your CGM account
  password.
- **MongoDB versions:** tell us your database's version (4.4, 5.0, 6.0, 7.0, or a hosted service). 4.4
  still works but is deprecated.
- **Node.js 20, 22 or 24:** tell us which one your host runs.

## 2.6 Logs worth sending (with secrets removed)

- Anything logged at startup that you did not see on 15.0.8.
- `API v1: … (logged once)` deprecation lines: which one, and which client you think sent it.
- Any line that mentions a refused alarm silence, a refused filter condition, or `Bad count`.
- Any error followed by the site restarting.
- **Error pages and error replies** now give only the status and a short message, unless the site
  runs with `NODE_ENV=development`; the full error is still written to the server log. If you used to
  read errors in the browser or in a tool's output, read the server log instead. Tell us if an error
  you need to see no longer reaches the log.
