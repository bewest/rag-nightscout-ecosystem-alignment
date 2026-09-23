# Nightscout 15.0.9 — release notes

**DRAFT — not yet released. Prepared for maintainer review; the wording may change.**
**The version number is settled: 15.0.9.**

*For people who run a Nightscout site for themselves or a family member. Nightscout is not a
medical device, and nothing in these notes is medical advice or advice about insulin doses.
Where a change could affect decisions about your therapy, talk it through with your care team.*

> These notes complement the automatically generated changelog. The changelog lists what
> changed; these notes say what you will **notice**, what you must **do**, what to **check
> afterwards**, and what is **still broken**. If the two disagree, the changelog is right about
> *what changed* and these notes are right about *what it means for you*, and the disagreement
> is worth reporting.

This is a bug-fix and security release. Most of what is in it is something that should
already have worked. A few fixes change what you see on screen, one changes which alarms can
reach your phone, and some requests from apps and scripts are now answered differently. Please
read the first two sections even if you usually skip release notes.

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

Work through this list first. Most people will find that nothing applies to them except item 8.

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
8. **Have a second way to see your readings** while you upgrade and for a day afterwards —
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

## Security fixes

**These fixes are in this release. Earlier releases, including 15.0.8 (the release most sites
run today), are affected.** The descriptions are kept short on purpose until the related
security advisories are published.

1. **Sites set to require login now apply that to the live-update connection.** The live-update
   connection is what keeps your page current without reloading. If you set
   `AUTH_DEFAULT_ROLES=denied` so that only people you have given access can see your site, it
   now checks a visitor's access the same way the rest of the site does before sending live
   information, alarms or notifications. If your site uses the standard setting, where anyone
   with the address can read it (`AUTH_DEFAULT_ROLES=readable`), nothing changes.
2. **Silencing alarms through the live-update connection now requires the permission meant for
   it.**
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
7. **The failed-login delay no longer slows down the wrong people.** After a failed login,
   Nightscout makes the next attempt wait. It used to make *every* request wait, including ones
   with the correct password, so on a site behind a shared proxy one misconfigured uploader
   could slow down everyone. Now only failed attempts wait, and the list of recent failures is
   cleared regularly and has a size limit. **On its own this does not stop someone who is
   guessing passwords from avoiding the delay**, because the address it counts attempts against
   is read from information any visitor can supply. That is closed only once you set
   `TRUST_PROXY` — see the next section.
8. **The "Nightscout readable by world" warning now appears when it should.** If you use the
   older `TREATMENTS_AUTH=off` setting, anyone with your address can read your data **and add
   treatments** without logging in. That is what the setting does and this release does not
   change it — but the admin warning that should tell you this was never shown. It is now.

**What to do:** upgrade. If you rely on `AUTH_DEFAULT_ROLES=denied` to keep your data private,
this release is the one that makes the live-update connection respect it. If you use
`TREATMENTS_AUTH=off`, read the new warning and decide whether you still want it. If you have
ever edited a user on the admin page, read the token section below.

### The new `TRUST_PROXY` setting

Nightscout counts failed logins per visitor address. Today it takes that address from labels
attached to the request (called *forwarded headers*), **whoever attached them**. A proxy
normally adds these labels, but a visitor can add them too. `TRUST_PROXY` tells Nightscout whose
labels to believe:

| `TRUST_PROXY` | What Nightscout believes | Who should use it |
|---|---|---|
| not set (the default) | forwarded headers from anyone — **exactly as today** | nobody needs to change anything to upgrade |
| `false` | no forwarded headers at all; only the address actually connecting, and whether that connection itself is https | sites that visitors reach directly, with no proxy in front |
| your proxy's IP address(es) or ranges, comma-separated (for example `10.0.0.5` or `10.0.0.0/24`) | forwarded headers only when they come from those addresses | sites behind a proxy whose address you know |

Once it is set, the failed-login delay counts attempts against an address a visitor cannot make
up, and it starts doing its job. **While it is unset, Nightscout writes a message to its log at
startup saying the delay does not protect against guessing passwords or tokens.** Until you set
it, restricting access at your proxy or hosting provider is what actually helps.

**Be careful setting it behind a proxy that handles https for you.** With `false`, or with a list
that does not include your proxy, Nightscout stops believing the proxy's "the visitor used https"
label, decides the visitor used plain http, and redirects them to https — over and over. **If
your site stops loading after you set `TRUST_PROXY`, remove the setting and check your proxy's
address.** The address to list is the one Nightscout *sees* the proxy connecting from, which on
hosting platforms can change or be shared; do not guess a range. Values such as `true`, a number
of hops, or names like `loopback` are refused at startup. Nightscout's README links to a proxy
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
| a read with `count=0` | an **empty list**: no records, and no error. It never returns your whole history. |
| a read with an ordinary count such as `10` or `288` | as before |
| a read with no `count` | the usual default (for glucose readings, the last 10), as before |
| a read with a count that is not a plain whole number: `abc`, `-3`, `2.5`, `1e2`, `0x10`, or a number too large to handle exactly | an error, "Bad count" (HTTP 400) |
| a save or an update that carries a `count` | carried out normally; `count` is ignored |
| a delete that carries `count=0` or a count that is not a plain whole number | **refused** with an error, and **nothing is deleted** |
| a delete that carries a valid count such as `2` | carried out as before. **The count does not limit a delete**: it still deletes every record the request matches. |

The newer API (version 3) keeps its own rule: a `limit` of `0`, or one that is not a whole
number within the site's maximum, gets an error.

### Filter conditions

Apps use filter conditions to ask for particular records, for example "readings at or above
180". The version 1 API now accepts a fixed, documented list of conditions: *equal*, *not
equal*, *greater than*, *less than* and their "or equal" forms, *in a list*, *not in a list*,
*has a value* (`$exists`), *type*, and text matching (`$regex`), combined with *and* / *or*.
Anything else gets an error (HTTP 400) that names the refused condition, instead of a server
error or a silently empty answer. A survey of 14 Nightscout apps found none that use a refused
condition. One condition that used to work is now refused: `$expr` on the profiles address. An
undocumented `pipeline` option on the counting addresses is also refused.

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

<!-- PENDING: connector v0.1.0 tag -->
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
<!-- PENDING: connector v0.1.0 tag -->
- **A MiniMed CareLink "no reading" marker is no longer stored as a glucose reading of 0.** While
  such a 0 was the newest reading, Nightscout did not check your high and low glucose alarms.
  Readings already stored are not changed. How often CareLink sends such a marker as the newest
  value has not been measured. Keep your pump's or CGM app's own alarms on; do not rely on
  Nightscout as your only alarm.
<!-- PENDING: connector v0.1.0 tag -->
- **It waits properly between retries after a CGM service outage.** Earlier versions ignored the
  retry interval each source was designed with, so after an outage they started retrying within a
  fraction of a second instead of after minutes, and every site retried at the same moment.
  Retries now follow the intended interval, are spread out, and have an upper limit, so the
  connector does not stop trying for a very long time either.
<!-- PENDING: connector v0.1.0 tag -->
- **Copying data from another Nightscout site that requires login now works.** If the site you
  copy from uses `AUTH_DEFAULT_ROLES=denied`, earlier versions could not read from it. **If an
  earlier version already created a user called `nightscout-connect-reader` on that site**, it is
  reused as it is and still cannot read: on that site's admin page, give that user the
  `readable` role, or delete it so the connector creates it again.
- **It shuts down cleanly when Nightscout stops.**
<!-- PENDING: connector v0.1.0 tag -->
- For developers: the connector's standalone `capture` command no longer fails for the
  Nightscout and Dexcom Share sources.

Two new optional settings, `CONNECT_START_JITTER_MS` and `CONNECT_INTERVAL_JITTER_MS`, spread out
when many connectors sharing one server contact the CGM service. Both default to `0`, so nothing
changes unless you set them. A single self-hosted site does not need them.

### Your CGM account password

**Consider changing your CGM account password** if both of these are true:

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

<!-- PENDING: rc record for BF-69 (bf3/quickpick-rebuild 83cfff14) -->
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
<!-- PENDING: rc record for BF-69 (bf3/quickpick-rebuild 83cfff14) -->

The bolus calculator is a calculator, not a recommendation, and this release does not change
that. It does not decide a dose. **Always check that the carbohydrate amount shown is the one you
meant: check the carbs against the meal you are actually eating before you rely on them.** If you
use quick picks for meal dosing, go over how you use them with your care team. If you think a
past calculation used an amount you did not choose, raise it with your care team. This is not
medical advice.

### A page with no reading no longer hits an error when a device alarm arrives

<!-- PENDING: rc record for BF-90 (bf3/alarm-no-reading 92544d8f) -->
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
<!-- PENDING: rc record for BF-90 (bf3/alarm-no-reading 92544d8f) -->

### Searches, reports and filters return the right records

Some filters compared numbers as if they were words, so "temp basals of 30 minutes or more"
matched nothing and the site answered with an empty list instead of an error. Decimal amounts
such as "1.5 units or more" were rounded down to 1. A filter for records *without* a value
returned the records *with* it. Counting addresses could return zero for everything. Paging
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
longer used, and one assistant request can no longer change the language of the whole site);
Alexa gets an immediate answer to a kind of request Nightscout does not handle, instead of being
left waiting; a misspelled plugin name in `ENABLE` now gets a suggestion in the server log; the
"Nightscout is having trouble" start-up page no longer fails on one kind of error message that
no current version produces; deployment with npm 12 no longer fails; the library that reads web
addresses and form posts is updated to a version that clears three published security notices
against it, with no difference for any request a known app sends; updated translations and many
software library updates.

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
10. **After upgrading, check that everything connected to your site still works**, and watch for
   a day.

## What to check afterwards

- Your glucose readings are arriving and the page updates.
- Uploaders, phone and watch apps, and follower apps still connect.
- Any tool that reads from or saves to your site through the API still works. An error such as
  "Bad count" or a refused filter condition is from the corrections above; report it to the
  tool's author.
- Any report or filtered view you rely on — expect numbers to change; that is the fix.
- The IAGE box, if you use insulin age: it may now show URGENT.
- Bookmarked links that contain an underscore.
- If you set `TRUST_PROXY`: your site still loads over https, and the startup warning about the
  failed-login delay is gone from the log.
- If you moved from `MMCONNECT_` or `BRIDGE_` settings: readings arrive through the connector.
- If you changed your CGM account password: the new password is in Nightscout's connector
  settings, and readings arrive.

---

## Known issues — not fixed in this release

<!-- PENDING: rc record for BF-69 (bf3/quickpick-rebuild 83cfff14). If BF-69 does not ship in
     15.0.9, restore this item: "The bolus calculator's quick-pick list may show only "(none)"". -->
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
  log says so. Check that the thresholds on your settings page are the numbers you meant, keep
  your device's own alarms on, and talk through your alarm settings with your care team. This
  is not medical advice.
- Filters asking "is this value present" understand only `true`, `false`, `1` and `0`.
- Silencing an alarm from an app has no upper limit on how long it can be silenced for.

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

*DRAFT, 2026-09-23. Requires maintainer review before publishing. Nightscout is not a medical
device, and nothing in these notes is medical advice or guidance about insulin dosing. Where a
change here could affect decisions about your therapy, discuss it with your care team.*
