# Nightscout 16.x: questions for controller and uploader authors

*What this is: an outreach draft for the authors of AndroidAPS, Loop, Trio, xDrip+ and xDrip4iOS. It is contributor-facing. Read it after the [architecture review](../../modernization/cgm-remote-monitor-architecture-review-2026-10-25.md), whose next step 6 it carries out. Status: **draft, not yet sent; for maintainer review** (2026-10-25). Facts are as of cgm-remote-monitor `dev` `428b20b7`. The client behaviour comes from the cited studies; most of it was read from source, not run. Each project's maintainers decide what, if anything, to do. The private AndroidAPS report and the public AndroidAPS issue from 2026-10-25 cover two of these topics in more depth for AndroidAPS.*

Hello AndroidAPS, Loop, Trio, xDrip+ and xDrip4iOS maintainers,

Nightscout 16.0.0 is a major release focused on robustness. We'd like to agree a few contracts with you before we change any default. Nothing below changes how your app works today: each change starts off by default or log-only, and moves only on a dated, announced plan.

We found that most recent Nightscout defects come from a few shared causes:

- Nightscout accepts the same data through four doors (API v1, API v3, the websocket and in-process callers), and each door applies its own rules.
- Readers trust whatever got stored.
- Each app validates in its own way.
- When Nightscout refuses something, most apps can't tell.

The [architecture review](../../modernization/cgm-remote-monitor-architecture-review-2026-10-25.md) has the evidence.

There are two parts to our plan:

- **Near term (16.x), for apps as they are today.** One shared write path inside Nightscout, with one set of checks, one reply shape and one change event per write.
- **Longer term, opt-in per app release: [controller registration](../spec/registration.md).**
  - Your app publishes typed definitions of its records: field types, units and ranges.
  - Nightscout validates your typed writes against *your* declaration, and never imposes another app's rules.
  - Typed writes come with a defined refusal protocol: a refusal is visible to the app, and the record is never silently dropped.
  - Registration is specified, not built yet.

The questions below shape both parts. Short answers are fine, and so is "we need to look".

## 1. Write replies and retries

We plan one reply shape for every write:

- Each item comes back with its stored `_id`, its `identifier`, and which of the two matched.
- A re-send that matches a stored record is answered with that record's ids, and no second copy is stored.
- Status codes stay as clients already handle them, and a client error is never answered with a 5xx.

We read your upload code to see how each app reacts when Nightscout refuses part of a batch. Most rows are read from source, not run; see the [study](../../../60-research/remedial/upload-refusal-client-behaviour-2026-10-25.md).

| App | What it needs from a batch reply | If one item is refused inside a 200 | If the whole batch gets a 4xx |
| --- | --- | --- | --- |
| Loop (NightscoutKit) | exactly 200, with one object per item sent | the item is recorded as uploaded, with id "NA" | the batch is resent on every trigger |
| Trio | any 2xx; the body isn't read | the item is treated as uploaded | the pipeline retries for up to 24 h |
| xDrip+ | any 2xx | entries are treated as uploaded | entries stay queued for up to 7 days |
| xDrip4iOS | any 2xx; treatments are matched by content | the item stays pending and is resent | for readings, the cursor waits for up to 7 days |
| AndroidAPS (API v3, one record per request) | 201 or 200 | n/a | on a 400, the record is dropped and the cursor moves on; on any other 4xx, that kind's queue waits |

**Our draft batch reply** is opt-in, behind `WRITE_VALIDATION=reject`:

- The reply is 200, with one object per item, in order.
- A refused item has no `_id`, and has a `refused: {status, message, rules}` member.
- If every item is refused, the reply is 400.

Questions:

- Is that shape safe for your app? Would you read `refused`, so that a refusal can reach the person instead of being lost?
- Does your app depend on an exact status (Loop: exactly 200), or on the reply's length?
- AndroidAPS: is the difference between 400 (drop) and other 4xx (hold) intentional? Which should Nightscout use for "this record can never be accepted"?

## 2. Who validates what

We propose that Nightscout checks the *structure* of what it stores, and leaves *policy* to you.

Today API v3 checks only `identifier`, `date`, `utcOffset` and `app`. Most protection therefore lives in your apps, and each app does it differently:

- AndroidAPS drops records at about 24 points.
- Trio clamps temp targets to 80–200 mg/dL.
- Loop reads only two units spellings.

| Kind of check | Example | Who would enforce it |
| --- | --- | --- |
| Structural: true for every app | targets are finite numbers, bottom ≤ top, units come from a known set, duration ≥ 0, a timed record has a time | Nightscout, on every write path, opt-in first (`off` → `log` → `reject`) |
| Policy: your app's own limits | AndroidAPS's 72–180 mg/dL temp targets, Trio's 80–200 clamp, the maximum bolus | your app. With registration you can declare these; Nightscout shows them, but never enforces them on another app's records |
| Time sanity | a reading dated ahead of the server clock | Nightscout flags it, and never refuses it |

**With registration,** your app declares each field's type, unit and range in its own typed definition, and Nightscout validates your typed writes against that declaration. Records from apps that haven't registered keep today's shapes, and get only the structural checks above. See the [write-validation design](../../../60-research/modernization/write-validation-design-2026-10-25.md).

Questions:

- Which of your ingestion checks would you want Nightscout to enforce at write time, for every path?
- For your users, is a record that Nightscout refuses or flags better than one your app drops quietly?
- Would you publish your ranges and units in a registration, if Nightscout served them to other apps and to followers?

## 3. Records already stored

Sites hold years of records written by many app versions, so stricter checks can't assume clean data. We propose:

- normalise on write from now on;
- tolerate older shapes on read;
- flag a record that doesn't meet the contract, rather than hide it.

A stored record must never stop Nightscout itself.

Two effects matter to you:

- **Apps that re-send what they read.** oref0, tconnectsync, nightscout-connect's Nightscout source, the profile editor and AndroidAPS 3.4.2.6 copy stored content back to Nightscout. Refusing a value that a working site may already hold would make those uploads fail repeatedly. For such values, Nightscout therefore logs and flags first, and refuses only in a later major, after operators have been told.
- **Shapes your app can't read.** Some stored records fail to decode in some apps. Two examples: a `timestamp` that some uploaders send as text, and fractional durations. A flag on read could let your app skip one record instead of a whole page.

Questions:

- If API v3 marked a nonconforming record with a flag on read, what would your app do with it: skip it, show it, or warn?
- Does your app re-send records it downloaded? If so, which fields does it copy without retyping?

## 4. Delivery and cursors

We'd like to write down what an app may assume when it syncs from Nightscout. Today nothing states it, and the gaps cost records.

The API v3 `/storage` socket announces only writes made through API v3. In our lab, an app that sets its history cursor from each pushed event can permanently miss careportal, API v1 and connector records. See the [lab](../../../60-research/remedial/aaps-websocket-delivery-lab-2026-10-25.md); its client behaviour is modelled from AndroidAPS source.

The proposed contract, from the [sync-transport spec](../spec/sync-transport.md):

1. History is the record. `srvModified` is set by Nightscout, never by the client, and only moves forward.
2. A socket event is a hint to read history. It never moves the client's cursor past records it hasn't fetched yet.
3. Writes from other paths are announced on `/storage` only once Nightscout checks every write path, and only records that pass those checks are announced. Until then, `/storage` stays as it is today.

Questions:

- Does this contract match how your app syncs, or would it need a change?
- Which apps besides AndroidAPS subscribe to `/storage`?
- Would it help if each event carried the cursor position before it, so that an app can detect a gap?

## 5. Units and identity

**Units.** Apps spell and convert units differently, so one app can misread a record another app wrote. With registration, units are declared per field and never assumed. Until then, records in today's shapes need a common convention.

| App | mmol/L spelling it reads | Conversion it uses |
| --- | --- | --- |
| AndroidAPS | exactly `mmol`; anything else is read as mg/dL | 18 |
| Loop (NightscoutKit) | exactly `mmol/L`, alongside `mg/dL` | to confirm |
| Trio | reads no units on a temp target | to confirm |
| Nightscout | several | three constants in use: 18, 18.016 and 18.01559 |

**Identity.** Nightscout follows a [two-id rule](../spec/identity.md):

- `identifier` is the record id your app assigns. It is stable across retries and devices, compared exactly, and not required to be a UUID.
- `_id` is the storage key Nightscout assigns.
- Every write reply will return both.
- Planned for 16.0.0 (PR #8845): API v3 refuses a client-supplied `_id` with a 400 that asks for `identifier` instead. We found no app that sends one.
- Next, Nightscout plans to match re-sends on `identifier` first, so an app needs no cache of server ids.

Questions:

- Which units spellings should Nightscout accept and store, and which constant should it use?
- Loop: does the simple contract we discussed still hold with identifier-first matching?
- xDrip+ and xDrip4iOS: today, entries uploaded with your own `_id` have it moved to `identifier`. Would identifier-first matching change how you de-duplicate?

## Questions by project, and where to reply

Not every question applies to every app. The table shows where your answer matters most.

| Topic | AndroidAPS | Loop | Trio | xDrip+ / xDrip4iOS |
| --- | --- | --- | --- | --- |
| 1. Reply shape and retries | yes | yes, especially | yes | yes |
| 2. Validation and declaring ranges | yes | yes | yes | — |
| 3. Flags on stored records; re-sending | yes | yes | yes | — |
| 4. Delivery and cursors | yes, first | — | — | if you use `/storage` |
| 5. Units spelling and constant | yes | yes | yes | — |
| 5. Identity and matching | yes | yes, especially | yes | yes |
| Registration: would you adopt it, and what would you need first? | yes | yes | yes | yes |

Reply wherever suits you: here, in your own tracker, or in a call. We'll collect the answers in one public place, and link it back to each of you before anything changes by default.

Thank you,
The Nightscout maintainers
