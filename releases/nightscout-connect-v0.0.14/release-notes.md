# nightscout-connect v0.0.14 — release notes (DRAFT)

**Status: DRAFT for maintainer review. Not published. The tag has not been pushed.**
**Nightscout is not a medical device and nothing here is medical advice.**

> **Status 2026-09-22: superseded. This version will not be published.** Its changes are in
> nightscout-connect `0.1.0` instead: a test version (`0.1.0-dev.1`) is published, the full
> release is not yet, and no Nightscout release uses either. Release notes for `0.1.0` have not
> been drafted; current state is queue item `P0-TAG`.

> **These notes complement the generated changelog; they do not replace it.** The
> changelog lists what merged. These notes say what you will **notice**, what you must
> **do**, what to **check afterwards**, and what is still **broken**. If the two disagree,
> the changelog is right about *what changed* and these notes are right about *what it
> means for you* — and the disagreement itself is worth reporting.

---

## What the connector is

"The connector" (`nightscout-connect`) is the part of Nightscout that logs in to your CGM
or pump account — Dexcom Share, LibreLinkUp, Glooko, or MiniMed CareLink — and fetches
your readings for you, so they appear on your Nightscout site. It runs inside Nightscout.
You do not install it separately; it arrives with the Nightscout release you are running.

Because of that, **the version of the connector you are running is decided by the version
of Nightscout you are running.** You do not choose it directly. This is the release the
next Nightscout release is expected to carry.

---

## The headline: your account details and your readings stop being written to the log

**This is the reason to take this release.** The retry change further down is what
prompted it, but it is not the important part.

### What a "log" is, and why this matters

Your Nightscout log is the running commentary the software prints while it works. It is
**not** part of your Nightscout data and it is not on your graph. Depending on how your
site is hosted, it is the text under "logs", "log stream" or "console output" in your
hosting provider's dashboard.

**On Nightscout 15.0.8 — the current release, which is what most people are running —
that log contains the username and password for your CGM account, your session token, and
a copy of your glucose readings.** It prints them all the time, not only when something
goes wrong, and **there is no setting in 15.0.8 that turns it off.**

This has never affected your readings, your alarms, or anything you see on screen. It
matters in exactly one situation: **when you show your log to somebody else.** The
realistic way that happens is somebody diagnosing "my data stopped" and pasting their log
into a GitHub issue, a Facebook group or a Discord channel.

### What this release changes

The connector no longer prints those lines. Measured on the actual release trees: the
version 15.0.8 carries prints from **112 places** in the code, **101 of which pass live
data** (credentials, sessions, response bodies, or your readings). This release prints
from **22 places, 20 of them passing data**, and none of the remaining ones is reachable
from Nightscout — see [Known issues](#known-issues-and-things-this-release-does-not-fix).

Four separate changes do this. Three of them remove the printing outright; the fourth
makes the connector's detailed diagnostic logging something you have to switch on rather
than something that is always on.

### What you should do

1. **Do not paste a Nightscout log into a public place without removing the personal parts
   first.** This is good practice regardless of version, and it is necessary on 15.0.8. If
   you are not sure what to remove, ask for help privately rather than posting it.
2. **If you have already posted a log somewhere public, change the password on your CGM or
   pump account.** The lines that matter begin with `INPUT PARAMS`, `SUBMITTING LOGIN`,
   `LIBRE LINKUP AUTH`, `GLOOKO AUTH`, `LIBRE SESSION FROM AUTH` or
   `INTERNAL PERSISTENCE`. You do not need to change anything on your site to look.
3. **Check who can see your hosting provider's log viewer.**

### What to expect afterwards

**Your log becomes much quieter. That is the fix working, not something breaking.** What
is *not* expected is your readings stopping. Because the log is now quiet, you cannot use
it to spot a problem the way you might have before — **watch the graph itself.**

---

## The counter-intuitive one: after a vendor outage, your data will look slower to come back

**Read this one even if you read nothing else, because it looks like a regression and it
is not.**

### What you will see

Dexcom or CareLink has a problem and stops answering. Previously, your readings resumed
the instant the vendor did. **After this release, they can take up to about half an hour
to resume.**

### Why that is the fix

The connector was retrying **586 times faster than its own authors configured** — a
straightforward bug: the code merged its settings with its defaults in the wrong order, so
every interval anyone configured was thrown away and a 256-millisecond default was used
instead of the intended 2.5 minutes. On top of that, random spacing was switched off, so
**every Nightscout site in the world was retrying at the same moments.**

Retrying that fast never helped. It could not make Dexcom or CareLink answer any sooner,
and because every site was doing it in lockstep, a whole group of sites could be refused
together for asking too often — which makes the outage **longer for everybody**, not
shorter. Measured: 100 simulated sites delivered the same 800 requests across **3 seconds**
before this fix, and across **67 seconds** after it.

So the connector has stopped retrying in a burst that could not have worked and was
hardest on the vendor at the exact moment it was already struggling. Retries now honour
the intended 2.5-minute interval, spread randomly rather than in lockstep, and capped at
30 minutes.

### How to tell "waiting to retry" from "something is actually wrong"

**This is the part that matters, because a pause looks exactly like a failure until it
ends.**

Your site already watches for this by itself. By default it shows a warning when no new
reading has arrived for **15 minutes**, and raises an urgent alarm at **30 minutes**
(the settings are `ALARM_TIMEAGO_WARN_MINS` and `ALARM_TIMEAGO_URGENT_MINS`, and both are
on by default). **Because the new worst-case wait is about 30 minutes, an ordinary vendor
outage can now reach that urgent stale-data alarm where before it would not have.**

- If readings come back within about half an hour and then continue normally, **nothing is
  broken.**
- If they do not come back, or the gap keeps repeating, check that your CGM or pump account
  password still works, and look at your site's logs.

If your readings stop, treat it the way you already treat a sensor you cannot see — use
your meter and your usual routine. **Nightscout is not a medical device and nothing here is
medical advice. If a gap in your data affects decisions about your therapy, talk to your
care team.**

---

## MiniMed CareLink: two corrections to what gets recorded

If you use MiniMed CareLink as your data source, two things change in what the connector
writes to your Nightscout site. Both are corrections.

1. **Gap markers are no longer recorded as a glucose reading of zero.** When CareLink has
   no sensor value for a period it sends a placeholder rather than a number. The older
   connector stored that placeholder as a reading of **0 mg/dL**. A zero does not raise a
   low alarm by itself — but **while it was the newest entry on your site, it stopped the
   high and low alarm check running at all**, because that check ignores anything at or
   below 39. So a placeholder could quietly suppress your high and low alarms until the
   next real reading arrived. This release filters the placeholders out.
2. **Device status entries are timestamped with when the measurement happened, not when
   Nightscout received it.** Previously, a reading that arrived late was filed as though
   it had just happened.

**What to check afterwards:** look back over your chart for the last few days after
upgrading. If you see isolated readings at or near zero in your history, those are the old
placeholders. They are historical records and this release does not remove them; it stops
new ones being created. **This release does not clean up past data.**

---

## Two new settings you almost certainly do not need

`CONNECT_START_JITTER_MS` and `CONNECT_INTERVAL_JITTER_MS` let an operator spread out when
the connector first contacts the vendor after a restart, and when it polls thereafter.
They exist for people running many sites from one place.

**Both default to zero, so if you do not set them, nothing about your site changes.**
Verified by running the setting-reading code directly: unset, empty, negative and
non-numeric values all produce zero.

---

## Known issues, and things this release does not fix

Named here so nothing surprises you later. None of these is new in this release.

- **A Dexcom session that the vendor ends early can leave your data dark for up to 24
  hours.** If Dexcom invalidates your login session from their side — which is the ordinary
  way a session ends — the connector's fetching machinery notices but does not tell the
  part that holds the session, so it keeps trying with a dead login until a hard-coded
  24-hour timer expires. Measured over 25 simulated hours of continuous rejection: one
  login attempt, then nothing. **The retired legacy Dexcom bridge recovers from this on
  the next poll, because it never reuses a session at all.** How often this actually
  happens depends on Dexcom's behaviour and nobody here has been able to measure it against
  a real account. **This is the one way this connector can be worse than what it replaces,
  and it is the kind of failure where your data stops without the software saying so.**
  If your readings stop and stay stopped, restarting your Nightscout site clears it.
- **`BRIDGE_SERVER=US` and other short spellings stop working.** If you are migrating from
  the older Dexcom bridge settings, a `BRIDGE_SERVER` value that is not empty, not `EU`,
  and not a full address like `share2.dexcom.com` is passed through as if it were a web
  address — so `US` becomes an address that does not exist, and the connector reports the
  setting as valid. `US` and `us` were the obvious things to write and the old bridge
  accepted them. **If your Dexcom data stops after migrating, check this setting first.**
- **Five older Dexcom bridge settings have no equivalent and are silently dropped** on
  migration: `BRIDGE_INTERVAL`, `BRIDGE_MINUTES`, `BRIDGE_MAX_COUNT`,
  `BRIDGE_FIRST_FETCH_COUNT` and `BRIDGE_MAX_FAILURES`. The connector polls every five
  minutes and that is not adjustable.
- **The device label on your readings changes.** Readings previously recorded as `share2`
  or `connect-paradigm` are now labelled `nightscout-connect://...`. Your history is not
  lost or duplicated — but a chart or report that groups by device will show a break.
- **If you run `nightscout-connect` as a standalone command-line tool** (not inside
  Nightscout), one place still prints your Nightscout API secret to the log
  (`lib/outputs/nightscout.js`). It is **not reachable from inside Nightscout** — the
  embedded path uses a different output — so this affects standalone users only.
- **MiniMed CareLink readings may be filed at the wrong time if your pump's clock is in a
  different time zone from your server.** When CareLink sends timestamps without a time
  zone marker, the connector treats them as if they were the server's time zone. For a pump
  **east** of the server, this files readings in the **future** — and a future-dated
  reading makes your site believe your data is current, so the stale-data alarm does not
  fire. This is an open defect, not fixed here. It is being tracked. Whether it affects
  real accounts depends on whether real CareLink payloads carry time zone markers, which
  has not been checked against a live account.

---

## About the version number

The analysis on file argues this release should be numbered **0.1.0, not 0.0.14**, because
five things change for anything that calls this code, and under npm's rules a `0.0.x`
number tells a consumer nothing. That is a maintainer's decision and it is not settled. It
does not change anything in these notes, and it does not change what you receive.

---

*Draft, 2026-09-15. Prepared locally; the tag has not been pushed and nothing has been
published. Requires maintainer review before publication. Nightscout is not a medical
device, and nothing in these notes is medical advice or guidance about insulin dosing. If
anything here affects decisions about your therapy, discuss it with your care team.*
