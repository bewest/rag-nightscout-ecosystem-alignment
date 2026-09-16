# Nightscout 15.0.9 — release notes (DRAFT)

**Status: DRAFT for maintainer review. Nothing has been merged, tagged or released.**
**The version number is not settled — see [About the version number](#about-the-version-number).**
**Nightscout is not a medical device and nothing here is medical advice.**

> **These notes complement the generated changelog; they do not replace it.** The changelog
> lists what merged. These notes say what you will **notice**, what you must **do**, what to
> **check afterwards**, and what is still **broken**.

This is a **bug-fix release**. There is nothing new in it. Everything in it is something
that was supposed to work and did not. But three of the fixes change what your site does in
ways you will see, and one of them changes what your phone does — so please read the first
two sections even if you never read release notes.

---

## Read this first: two things will happen that you did not ask for

### 1. An urgent insulin-reservoir alert starts arriving

**The short version:** Nightscout has always had a feature that tells you when your insulin
reservoir is overdue for a change. **It has never worked, on any release.** The code
compared your reservoir's age against a setting it never actually read, so the alert could
not fire. This release fixes that, which means **it starts firing.**

**Who gets what.** Two different things happen, to two different groups, and they are
easy to confuse:

| | Who it reaches | What it is |
|---|---|---|
| **The on-screen pill turns red and says URGENT** | **everyone** | The small "IAGE" box on your Nightscout page. It has been stuck showing WARN; it now correctly shows URGENT for as long as the reservoir is overdue. No sound, no phone notification. |
| **A notification: "Insulin reservoir change overdue!"** | **only if you have turned insulin-age alerts on** (the setting is `IAGE_ENABLE_ALERTS`, and it is **off unless you switched it on**) | An actual alert. On Pushover it is sent with the sound named `persistent`. |

**When.** When your reservoir reaches the age you configured — **72 hours unless you
changed it** (`IAGE_URGENT`).

**It fires once. It does not repeat.** This matters and we are not going to soften it. The
notification is raised in the **single** check where the reservoir's age first equals your
threshold, and only if the clock is within 20 minutes past the hour. **If you miss it,
nothing raises it again.** The red URGENT pill on the page stays red for as long as the
reservoir is overdue, and **the pill is the thing to watch.** Do not treat this as an alarm
that will keep nagging you, because it will not.

**What you must do.** Nothing, unless you want to. But:

- If you run with `IAGE_ENABLE_ALERTS` on, **tell everybody who receives your Nightscout
  alerts that a new one is coming, what it sounds like, and what it means.** In this
  community the person holding the phone is often a parent, a partner or a school nurse who
  was never told the site was upgraded. An urgent alert that has always meant "glucose"
  arriving to mean "change your reservoir" is confusing at 3 a.m.
- If you do not want it: set `IAGE_ENABLE_ALERTS` to off, or raise `IAGE_URGENT`. Turning
  alerts off does **not** stop the on-screen pill turning red.

**Nothing about your insulin, your pump or your therapy has changed.** Only whether
Nightscout tells you. This is not medical advice and it is not a schedule for changing a
reservoir. **An alert is not a substitute for your own routine. If you are unsure what
reservoir-change interval is right for you, that is a question for your care team.**

### 2. Six ways of writing a web-address setting now give an error instead of working

**This is the only change in this release that can break something that works today.**

Nightscout's older web interface (the "v1 API") accepts a `count` setting on a web address,
to say how many records you want back. Six ways of writing it were accepted before and now
return an error (`HTTP 400`):

`?count=0`, `?count=0x10`, `?count=2.5`, `?count=-3`, `?count=1e2`, `?count=abc`, and any
whole number larger than about 9 thousand million million.

**Ordinary values are unaffected:** `?count=1`, `?count=10`, `?count=` with nothing after
it, and leaving it off entirely all behave exactly as before.

**Why `?count=0` had to change.** It did not mean "no records". It reached the database as
"no limit", so it returned **your entire collection** — every reading you have ever stored,
in one response. That is slow, it is expensive, and anyone who can read your site could ask
for it.

**Who this can affect.** Not you, directly — you never type these. It affects **programs**
that talk to your Nightscout site: uploaders, watch faces, phone apps, syncing tools. A
program that builds its own count — "fetch the last N entries I do not already have" —
computes **zero** exactly when it is up to date, which is most of the time. That program
used to get a large, useless, successful answer. **It now gets an error, and if it treats
errors as fatal, it stops syncing.** For a Nightscout user, a syncing tool that stops is
**glucose data that stops arriving.**

**One more thing, because the branch's own changelog does not say it:** this check runs on
**everything**, not just on reading. Sending data in with `?count=0` on the address —
`POST /api/v1/treatments?count=0` — now fails where it used to succeed.

**What you must do.**

1. **After upgrading, check that everything that talks to your site still works.** Your
   uploader, your watch, your phone app, any script. Watch for a day.
2. **If something stopped, this is the first thing to suspect.** Report it — give the name
   and version of the tool, not your data.
3. **If your glucose data stops arriving, use your meter and your usual routine while you
   sort it out.** Nightscout is not a medical device and nothing here is medical advice; if
   a gap in your data affects decisions about your therapy, talk to your care team.

---

## What else you will notice

### Your bolus calculator's quick picks stop loading the wrong food

**This is the most important correction in the release.** In the bolus calculator, the
drop-down list of saved quick picks was built from your **whole** food database, but the
choice you made was looked up in a **shorter, filtered** list. So **picking a quick pick by
name could load a different record's food, and the carbohydrate total that went into the
insulin calculation was not the one you chose.** Nothing told you. The list also offered
plain foods that are not quick picks at all, and choosing one of the last entries produced
an error.

**This has been present since October 2017.**

**What you should do.** Nothing needs changing on your site. But if you use the bolus
calculator's quick picks, **it is worth opening it after upgrading and checking that the
carbohydrate number you see matches the item you picked.** That is the behaviour that was
wrong, and it is now the behaviour to confirm.

**Nightscout's bolus calculator is a calculator, not a recommendation, and this release
does not change that. Nothing here is advice about insulin dosing. If you think a past
calculation may have used a carbohydrate figure you did not choose, that is worth raising
with your care team.**

Also fixed in the same area: quick picks created by other software were missing from the
list entirely, and hidden quick picks were being silently un-hidden every time the food
editor loaded.

### Searches and reports that returned nothing start returning your data

Filters on your data were being compared as **text** against fields that hold **numbers**.
So a filter like "duration of at least 30 minutes" was compared as the *word* "30" and
matched nothing at all — and the site answered **successfully, with an empty list.** A
filter like "insulin of at least 1.5 units" was rounded down to 1.

**158 of these comparisons are corrected, across five kinds of record.**

**What you will notice:** a report that plotted an empty chart now plots a full one. A
dashboard that showed no temporary basal rates now shows them. If you have a saved filter
or a bookmarked report address, **its meaning has changed under you — it was answering the
wrong question before and is answering the right one now.**

> **Please read this sentence, which we are keeping exactly as the people who found the bug
> wrote it: earlier results may have under- or over-reported delivered therapy.** If you
> have looked at a total-insulin report, or any report built on a filter, **the numbers it
> showed you may have been wrong.** This is not medical advice and no action is being
> recommended here. **If you made or reviewed any decision based on such a report, that is
> worth mentioning to your care team.**

**What to check afterwards:** open any saved report or filtered view you rely on and
compare it against what you remember. A sudden change in a total is the expected outcome,
not a new fault.

### Pages that froze or never loaded now work

- A web address with a setting that has no value — a trailing `&`, or `?debug` or `?mute`
  instead of `?mute=true` — used to leave you looking at "Loading" forever, with nothing on
  screen. The page stopped before it started.
- Deleting a treatment and then editing an older one could freeze the display until you
  reloaded the page. (It did not go silently wrong — the time-since-last-reading indicator
  kept running and visibly showed the page going stale.)

**One small side effect worth knowing.** Web addresses used to have underscores turned into
spaces. They no longer do. **If you have a bookmarked report or chart address containing an
underscore, it may behave differently — open your bookmarks once and check.** This also
fixes a quiet corruption of access tokens belonging to users whose name contains an
underscore.

### Two security holes close, and one of them needs an action from you

**You do not need to change any setting.** But one of these needs you to decide something.

1. **Editing a user in the admin screen used to write that user's API access token into
   your database in plain text.** An API access token is the password-like string that lets
   a program talk to your Nightscout site. It is supposed to be worked out fresh each time,
   never stored. Anyone who could read your database could read it.
2. **The delay that slows down repeated failed logins could be bypassed**, so password
   guessing against your site ran at full speed.

> ### ⚠ The token fix does not undo what already happened, and it cannot
>
> **If a token of yours was written into your database in plain text, this release stops it
> happening again but does not make that token invalid.** This is not an oversight. Your
> access tokens are **worked out** from three things: the user's internal id, the user's
> **name**, and your site's key (`API_SECRET`). The same three inputs always produce the
> same token. So there is no code change that could make an existing token stop working —
> **changing the token means changing one of those three inputs, and that is your action,
> not the software's.**
>
> **If you think a token may have been exposed, you have exactly three ways to change it:**
>
> | What you change | What happens |
> |---|---|
> | **Rename the user** (in the admin screen) | That one user's token changes. Everything using the old token stops working until you give it the new one. |
> | **Delete the user and create a new one** with the same roles | That user's token changes. Same consequence. |
> | **Change your site's `API_SECRET`** | **Every token on your site changes at once.** Everything that talks to your site — uploaders, watches, phone apps — stops working until you update them all. |
>
> **The third option is the big hammer.** Use it if you believe your database contents were
> exposed to someone. Use one of the first two if you are only worried about one user.
> **Plan it for a time when you can update everything that connects to your site**, because
> until you do, your data will stop flowing. If your glucose data stops arriving while you
> do this, use your meter and your usual routine.
>
> **Who this applies to:** anyone who has edited a user through the Nightscout admin screen.
> If you have only ever used your `API_SECRET` and never created separate users, there is
> nothing to rotate.

**One thing for anyone running extra software against the admin interface:** the user and
role records now keep only the fields Nightscout itself understands (name, roles or
permissions, notes, and creation date). If some other tool has been storing its own extra
fields on a user, **it can no longer do so, and they will be dropped the next time that
user is saved.** Most of this was already happening on the current release — what is new is
that a tool can no longer keep its fields by sending them back. **A code revert does not
recover data already dropped.**

### Your site gets faster, and answers exactly the same

Internal copying was removed from the data cache. The bytes sent to your browser and to
every program that talks to your site are **identical**. Measured on a developer's machine:
one common request went from about 0.8 ms to about 0.03 ms. Treat the direction (much
faster) as solid and the numbers as specific to that machine.

### If you use the built-in CGM connector, its retry behaviour changes

This release is expected to carry **nightscout-connect v0.0.14**. The important part, in
one line: **after a Dexcom or CareLink outage, your data will appear to come back more
slowly than you are used to — up to about half an hour — and that is the fix, not a
regression.** The full explanation, including how to tell "waiting to retry" apart from
"something is actually wrong", is in that release's own notes and should be read alongside
these.

It also stops your Nightscout log printing your CGM account password and your glucose
readings. **If you have ever pasted your Nightscout log into a public place, consider
changing your CGM account password.**

---

## What you must do, in one list

1. **Tell whoever receives your Nightscout alerts about the new insulin-reservoir alert** —
   what it says, that it fires once, and that it does not repeat.
2. **After upgrading, check everything that talks to your site still works** — uploader,
   watch, phone app, scripts. Watch for a day.
3. **Open the bolus calculator's quick picks once** and confirm the carbohydrate number
   matches the item you picked.
4. **Open any saved report or filter you rely on** and expect the numbers to change. They
   were wrong before.
5. **Check your bookmarked report addresses** if any contain an underscore.
6. **Decide whether to rotate an API token**, if you have ever edited a user in the admin
   screen. See the table above.
7. **If you have pasted a Nightscout log in public**, change your CGM account password.

---

## Known issues — things this release does not fix

- **`find[<field>][$exists]=false` has never meant "records that lack this field"**, and
  still does not. It returns the records that **have** the field, on the current release and
  after this one, on every field of every kind of record. If you have a filter or a saved
  report using it, it is not asking what you think. Open defect; not fixed here.
- **Counting is still done in two different places** in the code after this release, so the
  two can drift apart in future. Not a fault you can see today.
- **`/api/v1/experiments?count=0` keeps the old behaviour** — it is the one address the new
  check does not cover.
- **The insulin-reservoir notification fires once and only within 20 minutes past the
  hour.** That matches how the cannula, sensor and battery age alerts already behave, so it
  is consistent rather than wrong — but it means **you can miss it.** Watch the pill.
- **Older Dexcom and MiniMed data paths are still present but are being retired** in a
  future release. Nothing changes for you in this release. When it does change, you will be
  told what to set and how long you have, before anything is removed.

---

## About the version number

Your site may already be reporting `15.0.9` if you run from the development channel, but
**`15.0.9` has never actually been released** — no tag, no version-numbered image. If you
report a problem and say "I was on 15.0.9", that is understood and not a contradiction.

The versioning analysis on file argues this release should be numbered **15.1.0 at least**,
because things an operator can observe change, and possibly **16.0.0**, because the
`?count=` restriction, the assistant-language removal and the user-record change each
remove something that worked. **Its preferred outcome is to split the release**: ship
everything you gain now, and hold those three back for a later release that warns you
first. **That decision has not been made.** It changes the number on this page and nothing
about the fixes described on it.

---

*Draft, 2026-09-15. Prepared locally; nothing merged, tagged, pushed or published. Requires
maintainer review before release. Nightscout is not a medical device, and nothing in these
notes is medical advice or guidance about insulin dosing. Where a change here could affect
decisions about your therapy, discuss it with your care team.*
