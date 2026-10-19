# L0–L5 Compatibility: what each app does with a hub today, and what it sees from one that implements the specifications

*Contributor-facing. Living specification table, current at `main` `8cb0b5ed` (2026-10-18). Covers
layers L0–L5 of the [platform index](../README.md); terms are in the [glossary](glossary.md).
Queue: `SPEC-COMPAT-APPS`.*

*A companion to the eight specifications in the [reading order](../README.md#reading-order), read
after them or beside the one a reader's app touches. Expect, for every app the corpus holds, what
it does at each layer today and what it sees from a hub that implements the specifications
without the app changing, an overview by layer, the cells where an answer changes, and what the
table does not cover.*

Each specification has a compatibility section that says, in general, what an older client sees
from a newer hub ([registration §17](registration.md#17-compatibility),
[sync-transport §7](sync-transport.md#7-compatibility), [commands §8](commands.md#8-compatibility),
[plans §8](plans.md#8-compatibility)). This page names the apps. Every `today` cell is read from
the app's source at the ref named, through the per-client files of the
[15.0.9 consumer-impact survey](../../../60-research/remedial/consumer-impact-15.0.9-2026-09-23.md)
and the controller notes behind [commands §8](commands.md#8-compatibility); nothing was run. Every
`with a hub that implements the specifications` cell cites the rule that decides it.

Status: evidenced for `today`, read from the specifications for the rest, which are proposed or
specified and not implemented.

## 1. Files

| file | holds |
|---|---|
| `specs/sync/compat/{ios,android,uploaders,readers}.yaml` | one entry per app, per layer: today, with a newer hub, the verdict, the rules and anchors; format in `specs/sync/compat/FORMAT.md` |
| `tools/nsschema/compat_tables.py` | writes the tables in §3 and §4 from the files |
| `tools/nsschema/test_compat.py` | the checks in §7 |
| `reports/consumer-impact-15.0.9/clients/` | the per-client files each entry cites |

## 2. How to read the verdicts

| verdict | means |
|---|---|
| `unchanged` | the app behaves as today; nothing it sends or reads changes |
| `gains` | the app benefits without changing, from the rule named |
| `opt-in` | a capability exists for it, which it uses only if it changes (typed writes, registration, the command record, plans) |
| `affected` | something it does today answers differently; §5 lists each one |
| `none` | the app does not touch this layer |

L0 identity, L1 records, L2 definitions and instances, L3 state, intent and commands, L4 change
and sync, L5 authority, as the [platform index](../README.md) defines them.

## 3. Overview

<!-- BEGIN GENERATED: compat-overview -->
| app | kind | read at | L0 | L1 | L2 | L3 | L4 | L5 |
|---|---|---|---|---|---|---|---|---|
| AndroidAPS | controller | AndroidAPS@598e2eb39c (3.4.2.6); 4.0.0 prereleases read at dev 7e1d537d49 | gains | unchanged | gains | opt-in | opt-in | unchanged |
| AndroidAPS client control | controller | AndroidAPS@d5e7f5bd (4.0.0-rc1); local reads at dev 7e1d537d49; absent from 3.4.2.6 | unchanged | unchanged | unchanged | opt-in | unchanged | unchanged |
| Loop | controller | LoopWorkspace@f841285 (NightscoutKit 4ec9fd1, NightscoutService fe075ef); commands read at v3.14.9 548b3324 (NightscoutService 2cef4896) | gains | unchanged | gains | opt-in | opt-in | unchanged |
| oref0 | controller | oref0@88cf032a (master; dev d219baf9 differs in none of the Nightscout files read) | affected | opt-in | unchanged | opt-in | unchanged | unchanged |
| Trio | controller | Trio@e41c9db37 (dev; main c0160aeaf differs on no row); commands read at v1.0.2 0b29cd53 | gains | unchanged | gains | opt-in | opt-in | unchanged |
| cgmsim-lib | uploader | cgmsim-lib@c09f9c0 (0.10.3) | unchanged | unchanged | unchanged | none | unchanged | unchanged |
| DiaBLE | uploader | DiaBLE@e6a909c (main = dev) | unchanged | unchanged | unchanged | none | opt-in | unchanged |
| glooko-nightscout-eu | uploader | glooko-nightscout-eu@2b7fbc4 | unchanged | unchanged | unchanged | none | unchanged | unchanged |
| glooko2nightscout | uploader | glooko2nightscout@9ab8c60 | none | none | none | none | none | none |
| minimed-connect-to-nightscout | uploader | minimed-connect-to-nightscout@57bb042 (1.5.8) | gains | unchanged | unchanged | none | unchanged | unchanged |
| nightscout-connect | uploader | nightscout-connect@977da8a (v0.1.0-dev.3) | gains | unchanged | unchanged | unchanged | unchanged | unchanged |
| nightscout-librelink-up | uploader | nightscout-librelink-up@bff2317 (3.3.0) | unchanged | unchanged | unchanged | none | unchanged | unchanged |
| share2nightscout-bridge | uploader | share2nightscout-bridge@518c85c (0.2.12) | unchanged | unchanged | unchanged | none | unchanged | unchanged |
| tconnectsync | uploader | tconnectsync@7c4b2f4 | gains | unchanged | unchanged | unchanged | unchanged | unchanged |
| xDrip+ | uploader | xDrip@1ed760048 (2026.09.18) | gains | unchanged | unchanged | none | unchanged | unchanged |
| xDrip4iOS | uploader | xdripswift@c268542e (master = develop) | affected | unchanged | unchanged | none | opt-in | unchanged |
| LoopCaregiver | follower | LoopCaregiver@2305718 (dev; gestrich/NightscoutKit d63fb73) | unchanged | unchanged | none | opt-in | opt-in | unchanged |
| LoopFollow | follower | LoopFollow@4a74b781 (v7.1.0) | unchanged | unchanged | none | opt-in | opt-in | unchanged |
| nightguard | follower | nightguard@75404bd (master) | unchanged | unchanged | unchanged | opt-in | opt-in | unchanged |
| GluPredKit | reader | GluPredKit@e5bd635 | gains | unchanged | unchanged | opt-in | unchanged | unchanged |
| GlycemicGPT | reader | GlycemicGPT@d1a9adb7 (origin/main; Nightscout integration identical on develop ec902563) | unchanged | unchanged | unchanged | opt-in | unchanged | unchanged |
| nightscout-cgm-skill | reader | nightscout-cgm-skill@91a53ea | gains | unchanged | unchanged | opt-in | unchanged | unchanged |
| nightscout-reporter | reader | nightscout-reporter@518d61f (retired AngularDart app; last code change b664fba, 2022-12-22) | gains | unchanged | unchanged | opt-in | unchanged | unchanged |
| oref-digital-twin | reader | oref-digital-twin@a2e8610 | gains | unchanged | unchanged | opt-in | unchanged | unchanged |
| nightscout-roles-gateway | hub | nightscout-roles-gateway@90840ac (replit branch; default branch master 4fdd490, Nightscout call sites identical) | none | none | none | none | unchanged | unchanged |
| Nocturne | hub | nocturne@42275c812 | opt-in | opt-in | opt-in | opt-in | opt-in | opt-in |
| babelbetes | tool | babelbetes@07a7f07 (origin/develop) | none | none | none | none | none | none |
| GlookoServiceKit | tool | GlookoServiceKit@8e2cad1 (main) | none | none | none | none | none | none |
| Not read | tool | not read | none | none | none | none | none | none |
| openaps | tool | openaps@bd9a831 | none | none | none | none | none | none |
| trio-telemetry | tool | trio-telemetry@681ea86 | none | none | none | none | none | none |
| xdrip-js | tool | xdrip-js@0cd1c55 (dev e301273 also read) | none | none | none | none | none | none |
<!-- END GENERATED: compat-overview -->

## 4. By layer

### 4.1 L0 Identity

<!-- BEGIN GENERATED: compat-L0 -->
| app | today | with a hub that implements the specifications | verdict | rules |
|---|---|---|---|---|
| AndroidAPS | The v3 client never sends `_id`; it keeps the `identifier` from the POST reply and PATCHes and DELETEs by it. The 3.4.x v1 socket client reads `_id` from the `dbAdd` reply and sends it back on `dbUpdate`. | v3 creates, edits and deletes by `identifier` answer as today, and the reply adds `_id` and `matchedBy` beside the `identifier` it reads (I4, I5). The v1 `dbAdd` reply still carries a 24-hex `_id` (I2), and a 3.4.x treatment `dbUpdate` whose `_id` is the UUID of a v3-created record is moved to `identifier` and matched to that record (I9, I5) instead of the exact-string `_id` match it gets today. | gains | I2, I4, I5, I9 |
| AndroidAPS client control | Each message is a v3 `settings` document under a fixed identifier (`aaps_clientcontrol_hello_`, `cmd_<type>_`, `ack_`, `progress_`, `offer_` plus the client id), overwritten in place; the document `date` is a constant placeholder because API v3 refuses a changed `date` on a re-sent identifier. | One identifier names one document and is compared exactly, so each slot is overwritten in place as today (I6, I5). The v3 refusal of a changed `date` is an open decision, and the constant `date` is unaffected either way (identity §5). | unchanged | I5, I6, identity §5 |
| Loop | Posts override treatments with `_id` set to the override's upper-case UUID and deletes them by that UUID; posts doses with `syncIdentifier` and no `_id`, so a re-send is matched by `created_at` + `eventType`; caches the 24-hex `_id` of carb treatments from the POST reply for later PUT and DELETE. | Treatments match on client identity (`syncIdentifier`) before `created_at` + `eventType`, so two doses of one type at one time stay two records; the override UUID is moved to `identifier` as today and recorded as `quirksApplied`, and the upper-case DELETE still matches exactly (I6, I9). | gains | identity §3, I5, I6, I9 |
| oref0 | Sends no `_id` or `identifier`; re-sent pump-history treatments rely on the server's `created_at`+`eventType` upsert, which replaces the stored treatment, and `ns-dedupe-treatments.sh` reads `_id` back to delete duplicates. | A re-sent treatment matches on `created_at`+`eventType` among records without client identity and is merged, not replaced, so fields added in Nightscout that the rig does not send are kept (identity §3, T2). The dedupe tool's deletes by `_id` find every stored form of the id (I2). | affected | identity §3, T2, I2 |
| Trio | Sends its own upper-case UUID in a plain `id` member, which the hub does not read, and deletes carbs and insulin by `find[id][$eq]`; on 15.0.8 a re-send without `identifier` is matched by `created_at` + `eventType` alone (QUIRK-TREATMENTS-007). | Treatments match on client identity (`id`) before `created_at` + `eventType`, so two records of one type at one time stay two; `id` is still not `identifier` and gets no mapping (Q4a). | gains | identity §3, I5, Q4a |
| cgmsim-lib | Sends no `_id` or `identifier` on any upload and makes no PUT or DELETE by id. | Its writes match on each collection's natural key as today and are answered with both ids (identity §3, I4). | unchanged | identity §3, I4 |
| DiaBLE | Posts sgv entries without `_id` and reads no id back; it posts only readings newer than the newest it read. | A re-send matches on `date` + `type` as today (identity §3). | unchanged | identity §3 |
| glooko-nightscout-eu | Sends no `_id`; each treatment carries `glookoGuid`, and de-duplication is a client-side set of guids saved to disk. | `glookoGuid` is not a client id the hub reads, so a re-send matches on `created_at`+`eventType` among records without client identity, as today (identity §3). | unchanged | identity §3 |
| glooko2nightscout | Makes no Nightscout request: it writes Nightscout-shaped entries to a local JSON file. | Nothing. | none | — |
| minimed-connect-to-nightscout | Sends no `_id`; de-duplication is an in-memory recency filter on `date` and `created_at`, and API v1 devicestatus has no key, so a devicestatus sent twice is stored twice. | An identical devicestatus re-sent with the same `created_at` and `device` is answered unchanged instead of stored again; entries match on `date`+`type` (identity §3, T2). | gains | identity §3, T2 |
| nightscout-connect | Copies records from a source hub with the source's 24-hex `_id`. On the 15.0.9 candidate a devicestatus or profile re-send that collides with a stored string copy is refused as a duplicate key, and the persist fails until that record leaves the window. | Its in-process writes go through the one write step, which keeps a 24-hex `_id` as the ObjectId and matches every stored form of it, so such a re-send is answered with the stored ids, never an error (T1, I2, I4, identity §3). | gains | T1, I2, I4, identity §3 |
| nightscout-librelink-up | Sends entries without `_id`; on API v3 the hub computes a UUID v5 `identifier` from device and date. It sends only readings newer than the newest stored entry. | A re-sent reading matches on `identifier`, then `date`+`type` (I5, identity §3). | unchanged | I5, identity §3 |
| share2nightscout-bridge | Sends entries without `_id` (`device: 'share2'`) and relies on the server's entries upsert for re-sent readings. | A re-sent reading matches on `date`+`type` and merges (identity §3, T2). | unchanged | identity §3, T2 |
| tconnectsync | Sends no `_id` on POST and keeps `pump_event_id` as its own key. It reads `_id` back to DELETE a treatment, and in profile replace mode PUTs the profile with the `_id` from `profile/current`, which 15.0.8 stores as a second copy when that profile was stored with a string `_id`. | A PUT or DELETE by `_id` finds every stored form of the id, so replace mode updates the profile in place (I2, identity §3). `pump_event_id` is not a client id the hub reads, so its re-sends match on the natural key. | gains | I2, identity §3 |
| xDrip+ | Sends its own 24-hex `_id` (derived from its treatment uuid) on `PUT /api/v1/treatments` and deletes by it; on 15.0.8 a treatment stored with a string `_id` by an earlier release gets an ObjectId copy on the next PUT, and the DELETE misses the string copy. | The 24-hex `_id` is kept as that ObjectId, and an `_id` matches every stored form of it, so the PUT finds the existing record and the DELETE removes it, as #8758 does on `dev` (I2, identity §3). | gains | I2, identity §3 |
| xDrip4iOS | Sends a random 24-character alphanumeric `_id` on entries and some treatments, which the hub moves to `identifier` or drops; reads treatment `_id` back for PUT and DELETE; counts a 500 whose body has code 66 as a successful duplicate. | A duplicate is answered with the stored ids, never a 5xx, and xDrip4iOS counts that as success too (I4); the moved `_id` is recorded as `quirksApplied` and matched first on a re-send (I5, I9). | affected | I4, I5, I9 |
| LoopCaregiver | Writes no v1 records, so sends no `_id`; its experimental Remote Commands 2 option keys on a record `_id` from a route the hub does not implement. | Nothing it reads on implemented routes changes (I2). | unchanged | I2 |
| LoopFollow | Writes no records; reads `_id` only from the subjects reply, to derive its token. | Nothing it reads changes (I2). | unchanged | I2 |
| nightguard | Posts treatments through API v3 without `_id` or `identifier`, and keys its local cache on `identifier`, falling back to `_id`. | Every reply carries both ids, and a projected document keeps one `identifier` and `_id` across reads, so its keys stay stable (I4, I8). | unchanged | I1, I4, I8 |
| GluPredKit | Writes nothing and reads no ids; sums insulin, carbs and temporary basals client-side from what it downloads. | A record re-sent by an uploader is stored once on every write path, so it is counted once (I5, T1). | gains | I5, T1 |
| GlycemicGPT | Writes nothing; pages entries with `find[_id][$gt]=<24-hex>`, a cursor whose order is the `_id`'s time. | Every legacy `_id` is 24 hex, an assigned one carries the receipt time, and a projected document gets an ObjectId at its typed write, so the cursor reaches every new record (I2, I3, I8). | unchanged | I2, I3, I8 |
| nightscout-cgm-skill | Writes nothing; keys its SQLite cache of entries on `_id` and sums insulin and carbs client-side. | Every legacy `_id` is 24 hex (I2), and a record re-sent by an uploader is stored once, so it is summed once (I5, T1). | gains | I2, I5, T1 |
| nightscout-reporter | Writes nothing; reads treatment `_id` as an opaque string and drops adjacent identical treatments and `enteredBy == 'sync'` before summing. | A re-send is matched on `identifier`, then `_id`, then the natural key on every write path, so a treatment re-sent by an uploader is stored once and summed once (I5, T1). | gains | I5, T1, I2 |
| oref-digital-twin | Writes nothing; drops records with a repeated `_id` across its windows. | A record re-sent by an uploader is stored once on every write path, so the replay's inputs carry no second copy under another `_id` (I5, T1). | gains | I5, T1, I2 |
| nightscout-roles-gateway | Reads and writes no records. | Reads and writes no records. | none | — |
| Nocturne | v1 by-id routes accept 24-hex and 32-hex (UUID v7 without dashes) ids, and look up by GUID, then by exact `LegacyId`, then by GUID prefix. | It would serve a 24-hex `_id` on v1 and v3, keep a client 24-hex `_id` in lower case (I2), answer each write with both ids and `matchedBy` (I4), and match a re-send on `identifier`, then `_id`, then the natural key (I5). | opt-in | I2, I4, I5, I8 |
| babelbetes | Makes no Nightscout requests. | Makes no Nightscout requests. | none | — |
| GlookoServiceKit | No Nightscout traffic: it uploads Loop or Trio data to Glooko. | Nothing at this layer. | none | — |
| Not read | not read | not read | none | — |
| openaps | Makes no Nightscout request; a rig reaches Nightscout through oref0's `ns` device. | Nothing; what a rig sees is under oref0. | none | — |
| trio-telemetry | Makes no Nightscout requests. | Makes no Nightscout requests. | none | — |
| xdrip-js | A Bluetooth library for Dexcom transmitters; it makes no Nightscout request on master or dev. | Nothing. | none | — |
<!-- END GENERATED: compat-L0 -->

### 4.2 L1 Records

<!-- BEGIN GENERATED: compat-L1 -->
| app | today | with a hub that implements the specifications | verdict | rules |
|---|---|---|---|---|
| AndroidAPS | Writes entries, treatments (boluses, carbs, temp basals, profile switches, temporary targets, running modes as `OpenAPS Offline`), profile, food and devicestatus with `openaps.{suggested,enacted,iob}`. The 4.0.0 prereleases also write scene definitions and active-scene state to the v3 `settings` collection (`aaps`, `aaps-state`). | The hub decomposes its devicestatus, treatments and profile into primitives as its well-known registration declares and keeps each document beside them, so every read it makes is answered from the composite as today (R1, R2). Publishing a `ControllerSettings` snapshot is open to it and not used (R5). | unchanged | R1, R2, R5 |
| AndroidAPS client control | Signed command, acknowledgement and progress envelopes are stored as ordinary documents in the v3 `settings` collection and never deleted. | The hub stores and serves them as documents and reads none of them (commands §3, CM10). | unchanged | commands §3, CM10 |
| Loop | Writes entries, treatments (overrides, carbs, doses), devicestatus with `loop.*` (IOB, COB, prediction, enacted) and profiles with `loopSettings`; reads only `/api/v1/profile/current`. | The hub decomposes its devicestatus and profile into primitives and keeps each document as sent, so what Loop writes and reads back is unchanged (R1, R2). | unchanged | R1, R2 |
| oref0 | Writes devicestatus with `openaps.iob`, `suggested`, `enacted`, `pump`, `uploader` and `preferences` every cycle, treatments from pump history, entries, and a whole profile document (`OpenAPS Autosync`) when it changes. | Stored and served as today, the composite kept beside its primitives (R1). Its preferences remain configuration repeated per cycle; publishing them as a `ControllerSettings` snapshot on change is open to it if it changes (R5). | opt-in | R1, R5, records §5 |
| Trio | Writes entries, treatments, devicestatus under `openaps` (IOB, suggested, enacted) and a new profile document on each settings change, with its remote-control routing fields; reads sgv entries when Nightscout is its CGM, carbs and temporary targets, and the latest profile. | The hub decomposes devicestatus and profiles into primitives and keeps each document as sent, so the profile fields followers read stay (R1, R2). | unchanged | R1, R2 |
| cgmsim-lib | Writes simulated entries, treatments (temp basals with explicit `carbs: null` and `insulin: null`), devicestatus, notes and activity; deletes devicestatus by `find[created_at][$lte]`. | Stored as today (R1). A write that matches a stored record merges, and an explicit `null` it carries removes that field (T2). | unchanged | R1, T2 |
| DiaBLE | Writes sgv entries and reads the last 100. | Entries are stored and served as sent (R1). | unchanged | R1 |
| glooko-nightscout-eu | Writes `Meal Bolus`, `Correction Bolus` and `Carb Correction` treatments with `enteredBy: 'glooko-bridge'`. | Stored and served as today; a treatment with insulin and carbs also decomposes into a bolus and a carb intake beside the composite (R1). | unchanged | R1 |
| glooko2nightscout | Writes no records to a hub. | Nothing. | none | — |
| minimed-connect-to-nightscout | Writes `sgv` entries and devicestatus with `device: 'connect-<family>'`, `uploader`, `pump` (with `pump.iob.bolusiob`) and a `connect` block. | Stored and served as today (R1). | unchanged | R1 |
| nightscout-connect | Writes entries, treatments, devicestatus and profiles as each source produced them, plus Glooko pump-state `Note` treatments and checkpoint rows keyed by `identifier` and `glookoGuid`. | Stored and served as today; decomposition runs above storage and keeps the composite (R1, R3). | unchanged | R1, R3 |
| nightscout-librelink-up | Writes `sgv` entries only. | Stored and served as today (R1). | unchanged | R1 |
| share2nightscout-bridge | Writes `sgv` entries; its devicestatus battery write never runs. | Stored and served as today (R1). | unchanged | R1 |
| tconnectsync | Writes treatments (boluses, basal, IOB records, Sleep and Exercise), `sgv` entries, pump battery devicestatus, activity and profiles. | Stored and served as today (R1); activity gets server dates and soft delete like the other collections (T2). | unchanged | R1, T2 |
| xDrip+ | Uploads entries (one POST with BG, meter and calibration), treatments, devicestatus with `device` and uploader battery, and activity; the follower reads entries, `devicestatus.json?count=1` and treatments. | Its documents are kept as written beside any decomposition, so what it reads back is answered as today (R1). | unchanged | R1 |
| xDrip4iOS | Writes sgv, mbg and cal entries, treatments and an uploader-battery devicestatus; reads looping-app COB and IOB from devicestatus and the first profile. | Documents are stored and served as sent (R1). | unchanged | R1 |
| LoopCaregiver | Reads entries, treatments, Loop's `loop.iob` and `loop.cob` from devicestatus, and `/api/v1/profile/current` for override presets. | Documents are served as stored (R1). | unchanged | R1 |
| LoopFollow | Reads entries, treatments, devicestatus (Loop `loop.*`, Trio and AndroidAPS `openaps.*`) and profiles, including the device token and bundle id for remote control. | Documents are served as stored (R1); a record a newer controller writes typed reaches it as a projected document in the carrier's shape (registration §13). | unchanged | R1, registration §13 |
| nightguard | Writes `Temporary Target`, `Carb Correction` and site, sensor and battery change treatments; reads entries, treatments, devicestatus and the hub-computed COB and IOB from `/api/v2/properties`. | Documents are served as stored (R1); typed records reach it as projected documents (registration §13). | unchanged | R1, registration §13 |
| GluPredKit | Reads entries, treatments and profiles; its treatment model is patched to accept Loop and Trio fields. | v1 reads are answered from the stored composite documents (R1). | unchanged | R1 |
| GlycemicGPT | Reads entries, treatments, devicestatus and profile into its own database. | v1 reads are answered from the stored composite documents (R1). | unchanged | R1 |
| nightscout-cgm-skill | Reads entries, treatments (including site, sensor and insulin changes by `eventType`) and profile. | v1 reads are answered from the stored composite documents (R1). | unchanged | R1 |
| nightscout-reporter | Downloads entries, treatments, devicestatus, activity and profiles per day and computes every total, COB and IOB client-side. | The hub keeps each composite document beside its primitives and answers v1 reads from the composite, so the documents it parses are served as written (R1). | unchanged | R1 |
| oref-digital-twin | Reads entries, treatments, devicestatus and profile as replay inputs; totals are computed client-side. | v1 reads are answered from the stored composite documents (R1); the declared replay inputs and their status are a registration's to publish, not a read it makes (R8). | unchanged | R1, R8 |
| nightscout-roles-gateway | Issues no data read; the collection checks in its comments are not implemented. | Issues no data read. | none | — |
| Nocturne | Stores typed V4 records, the source of the records catalogue's sixteen primitives, and routes treatments into them by `eventType`; `Suspend Pump` documents are unroutable because the decomposition keys on `Pump Suspend` (records §4, measured). | It already decomposes (R1); R2 has decomposition declared by each registration's `decomposesTo` instead of fixed routing, and R4 and R9 add an evidence grade and a sensitivity label to every field. | opt-in | R1, R2, R4, R9 |
| babelbetes | Makes no Nightscout requests; one notebook reads archived Nightscout export files. | Makes no Nightscout requests. | none | — |
| GlookoServiceKit | No Nightscout records. | Nothing at this layer. | none | — |
| Not read | not read | not read | none | — |
| openaps | Formats Dexcom records with Nightscout dates but sends nothing. | Nothing; see oref0. | none | — |
| trio-telemetry | Makes no Nightscout requests. | Makes no Nightscout requests. | none | — |
| xdrip-js | Writes no records to a hub. | Nothing. | none | — |
<!-- END GENERATED: compat-L1 -->

### 4.3 L2 Definitions and instances

<!-- BEGIN GENERATED: compat-L2 -->
| app | today | with a hub that implements the specifications | verdict | rules |
|---|---|---|---|---|
| AndroidAPS | Declares nothing; the hub stores its documents with no record of which product or copy wrote them. | Its writes carry no instance id, so the hub attributes them to AndroidAPS's unregistered instance by the structural discriminators and carriers in specs/sync/registrations/androidaps.yaml, and never refuses one for exclusivity (registration §11, registration §17). Typed registration with fallback to carriers is open to a newer build (registration §6). | gains | registration §11, registration §17, registration §6 |
| AndroidAPS client control | Neither the AAPSClient build nor the master declares anything; the well-known registration lists the `nightscout-settings` command transport as dev-only. | Its `settings` writes carry no instance id and are never refused for exclusivity (registration §11, registration §17). | unchanged | registration §11, registration §17 |
| Loop | Declares nothing and sends no instance id. | The well-known Loop registration describes its writes by structural discriminator (`loop` is an object) and carrier; they are attributed to Loop's unregistered instance and never refused for exclusivity. | gains | registration §17, registration §11 |
| oref0 | Declares nothing; the hub ships no well-known registration for oref0 (specs/sync/registrations covers Loop, Trio and AndroidAPS). | Its writes are carrier writes attributed to the product's unregistered instance and never refused for exclusivity (registration §11, §17). | unchanged | registration §11, registration §17 |
| Trio | Declares nothing and sends no instance id. | The well-known Trio registration describes its writes by discriminator and carrier; they are attributed to Trio's unregistered instance and never refused for exclusivity. | gains | registration §17, registration §11 |
| cgmsim-lib | Declares nothing; no well-known registration describes it. | Its writes are attributed to the product's unregistered instance (registration §11, §17). | unchanged | registration §11, registration §17 |
| DiaBLE | Declares nothing and sends no instance id. | No well-known registration describes it; its carrier writes are stored as today. | unchanged | registration §11 |
| glooko-nightscout-eu | Declares nothing. | Its writes are attributed to the product's unregistered instance (registration §11, §17). | unchanged | registration §11, registration §17 |
| glooko2nightscout | Declares nothing and writes nothing to a hub. | Nothing. | none | — |
| minimed-connect-to-nightscout | Declares nothing. | Its writes are attributed to the product's unregistered instance (registration §11, §17). | unchanged | registration §11, registration §17 |
| nightscout-connect | Declares nothing; the connector writes no product or instance id of its own. | Its writes go to an unregistered instance, and a copied document that matches a well-known registration's structural discriminator (Loop, Trio, AndroidAPS) is attributed to that product's unregistered instance (registration §11, §17, R2). | unchanged | registration §11, registration §17, R2 |
| nightscout-librelink-up | Declares nothing. | Its writes are attributed to the product's unregistered instance (registration §11, §17). | unchanged | registration §11, registration §17 |
| share2nightscout-bridge | Declares nothing. | Its writes are attributed to the product's unregistered instance (registration §11, §17). | unchanged | registration §11, registration §17 |
| tconnectsync | Declares nothing. | Its writes are attributed to the product's unregistered instance (registration §11, §17). | unchanged | registration §11, registration §17 |
| xDrip+ | Declares nothing, and no well-known registration describes it. | Its writes carry no instance id and are stored as today; exclusivity never blocks a carrier write (registration §11, registration §17). | unchanged | registration §11, registration §17 |
| xDrip4iOS | Declares nothing and sends no instance id. | No well-known registration describes it; its carrier writes are stored as today and never blocked by exclusivity. | unchanged | registration §11 |
| LoopCaregiver | Writes no records and declares nothing. | Nothing to attribute. | none | — |
| LoopFollow | Writes no records and declares nothing. | Nothing to attribute. | none | — |
| nightguard | Declares nothing; writes treatments with no instance id. | No well-known registration describes it; its carrier writes, including temporary targets for a controller's slot, are never blocked by exclusivity. | unchanged | registration §11 |
| GluPredKit | Declares nothing and reads no attribution. | Typed records reach it as projected documents in the carrier's shape (registration §13, I8). | unchanged | registration §13, I8 |
| GlycemicGPT | Declares nothing and reads no attribution. | Typed records reach it as projected documents in the carrier's shape (registration §13, I8). | unchanged | registration §13, I8 |
| nightscout-cgm-skill | Declares nothing and reads no attribution. | Typed records reach it as projected documents in the carrier's shape (registration §13, I8). | unchanged | registration §13, I8 |
| nightscout-reporter | Declares nothing and reads no attribution. | A record a newer controller writes as a typed record reaches it as a projected document in the carrier's shape, with both ids and a `projectedFrom` member it does not read (registration §13, I8). | unchanged | registration §13, I8, registration §17 |
| oref-digital-twin | Declares nothing and reads no attribution. | Typed records reach it as projected documents in the carrier's shape (registration §13, I8). | unchanged | registration §13, I8 |
| nightscout-roles-gateway | Declares nothing. | Declares nothing. | none | — |
| Nocturne | Serves v1-v3 reads from V4 records through a legacy projection, with no projection marker on the projected treatment (registration §13 prior art). | A projected document carries `projectedFrom`, is read-only (409 `projected-read-only`) and keeps one ObjectId stored with the typed record (registration §13, I8); registrations, instances and read selection (§11, §12) are new. | opt-in | registration §13, I8, registration §11, registration §12 |
| babelbetes | Makes no Nightscout requests. | Makes no Nightscout requests. | none | — |
| GlookoServiceKit | No Nightscout writes. | Nothing at this layer. | none | — |
| Not read | not read | not read | none | — |
| openaps | Declares nothing and writes nothing. | Nothing; see oref0. | none | — |
| trio-telemetry | Makes no Nightscout requests. | Makes no Nightscout requests. | none | — |
| xdrip-js | Declares nothing and writes nothing to a hub. | Nothing. | none | — |
<!-- END GENERATED: compat-L2 -->

### 4.4 L3 State, intent and commands

<!-- BEGIN GENERATED: compat-L3 -->
| app | today | with a hub that implements the specifications | verdict | rules |
|---|---|---|---|---|
| AndroidAPS | Profile switches, temporary targets and running modes are treatments that end by amending their duration; it applies such treatments written by other clients only when the matching `NsClientAccept*` preference is on (default off), or on the AAPSClient build or a full sync. Remote commands come by SMS with an allowed number, TOTP and PIN, outside the hub; automation rules run on the phone; the 4.0.0 prereleases add scenes and client control (its own entry). | Downloaded treatments stay data the hub stores and broadcasts without an expiry, destination or outcome, and the hub's active-state answers for its kinds follow its declarations (S10, A5, A7, A8, commands §3). The command record, fetch and plans are open to it; it registers no command sink, so a hub command or plan for it is refused at routing (CM1, CM18, plans §8). | opt-in | S10, A5, A7, A8, commands §3, CM1, CM18, plans §8 |
| AndroidAPS client control | The master accepts a command only with a valid per-client HMAC, a strictly increasing stored counter advanced before dispatch, a timestamp within ±5 min and before `validUntil`; doses are prepare and commit, computed and capped on the master. It acknowledges with signed `Executing`, `Done` (`Ok`, `Failed`, `Expired`) and a late `Delivery` `Failed`, correlated by the counter. | The counter already decides each command once across restarts, as CM21 asks, and the hub carries its signed envelopes unread (CM21, CM10). The hub's outstanding list and cancel are there for a build that sends through the command record (CM24, CM25). | opt-in | CM21, CM10, CM24, CM25, state-intent §7, commands §8 |
| Loop | Writes overrides as `Temporary Override` treatments; receives override, cancel, bolus and carbs commands only as APNs pushes, from the hub's `/api/v2/notifications/loop` relay or directly from a follower; reports a failure as a `Note` and a success only as the resulting record. | The relay route is outside CM1–CM25 and a hub keeps it as it is or retires it; the command record, enact-once by `commandId`, the outstanding list and cancel apply only once Loop registers and fetches (CM18, CM21, CM24, CM25). | opt-in | commands §8, state-intent §3, CM18, CM21, CM24, CM25 |
| oref0 | Downloads `Temporary Target` treatments and carbs from Nightscout every loop and applies them by its own rules; posts a `Profile Switch` treatment with its profile upload. It receives no commands through the hub. | Temporary targets stay data it downloads, as today (commands §3). The command record, its outcomes and delivery are for a controller that registers and accepts `command` (commands §4, commands §8, S10). | opt-in | commands §3, commands §4, commands §8, S10 |
| Trio | Writes overrides as `Exercise` treatments (ended by delete and re-post) and temporary targets; downloads other clients' carbs and temporary targets; takes remote commands only as encrypted APNs pushes sent straight from a follower, and posts a `Note` on a refusal. | Downloads stay data whose effect the hub does not track (state-intent §7); the command record, enact-once by `commandId`, the outstanding list and cancel apply only if Trio registers and fetches. | opt-in | state-intent §3, state-intent §7, commands §8, CM18, CM21, CM24, CM25 |
| cgmsim-lib | No overrides, targets, profile switches or commands; it reads profiles only. | Nothing it touches changes. | none | — |
| DiaBLE | Writes no overrides, targets or commands. | Nothing at this layer. | none | — |
| glooko-nightscout-eu | No overrides, targets, profile switches or commands. | Nothing it touches changes. | none | — |
| glooko2nightscout | No overrides, targets, profile switches or commands. | Nothing. | none | — |
| minimed-connect-to-nightscout | No overrides, targets, profile switches or commands. | Nothing it touches changes. | none | — |
| nightscout-connect | Sends no commands; treatments copied from a source are stored as data whatever their `eventType`, and it creates no profile-switch treatments. | Copies stay data (commands §3); active state is derived per product from that product's records (A1). | unchanged | commands §3, A1 |
| nightscout-librelink-up | No overrides, targets, profile switches or commands. | Nothing it touches changes. | none | — |
| share2nightscout-bridge | No overrides, targets, profile switches or commands. | Nothing it touches changes. | none | — |
| tconnectsync | Writes Tandem Sleep and Exercise activity as treatments, ending an open one by DELETE and re-POST with the same `created_at`; sends no commands or profile switches. | Stored as data; active state is derived per product from that product's records (A1), and no registration describes these treatments. | unchanged | A1 |
| xDrip+ | No profile, profile switch, override or remote command call was found (S10, S14 in the per-client file). | Nothing in state, intent or commands reaches it. | none | — |
| xDrip4iOS | Writes no overrides, targets or commands. | Nothing at this layer. | none | — |
| LoopCaregiver | Sends override, cancel, bolus and carbs to `POST /api/v2/notifications/loop`, needs exactly 200, and learns failures by parsing Loop's `Note` treatments; Remote Commands 2 uses `/api/v2/remotecommands`, which the hub does not implement. | The relay route is outside CM1–CM25 and a hub keeps it as it is or retires it (commands §8); a command record with an outcome from the destination is used only if it changes (CM1, CM7, CM25). | opt-in | commands §8, CM1, CM7, CM24, CM25 |
| LoopFollow | Sends Loop and Trio commands as APNs pushes straight to Apple, using routing data it reads from the hub's profile; its `/api/v2/notifications/loop` sender has no caller. | Its commands stay outside the hub, which sees only the resulting records (commands §8); a follower may read the outstanding list with `api:commands:read`, if it changes (CM24). | opt-in | commands §8, CM24 |
| nightguard | Writes temporary targets as treatments, cancelling with a new one of duration 0; sends no commands. | These stay data that a controller may act on without the hub knowing (state-intent §7); a request with an outcome is a command record it uses only if it changes (CM1). | opt-in | state-intent §7, CM1 |
| GluPredKit | Derives basal rates from the profile and temporary basals from treatments client-side. | The hub's derived answer of what was active is a new read it would have to call (state-intent §6). | opt-in | state-intent §6 |
| GlycemicGPT | Reads treatments and devicestatus as records; reads no derived state and no commands. | The hub's answer of what was active (state-intent §6) and the outstanding command list (CM24) are new reads it would have to call. | opt-in | state-intent §6, CM24 |
| nightscout-cgm-skill | Reads no override, target or profile-switch state and no commands. | The hub's answer of what was active is a new read it would have to call (state-intent §6). | opt-in | state-intent §6 |
| nightscout-reporter | Builds synthetic profiles from `Profile Switch` treatments and reads `Temp Basal` treatments, deciding what was in effect itself. | Its own reading of those treatments is unchanged; the hub's derived answer of what was active at a time is a new read it would have to call (state-intent §6, A1-A13). | opt-in | state-intent §6, A1, A10 |
| oref-digital-twin | Reads the profile and treatments and runs oref0 on them; reads no derived state. | The hub's answer of what was active is a new read it would have to call (state-intent §6). | opt-in | state-intent §6 |
| nightscout-roles-gateway | Touches no intents or commands. | Touches no intents or commands. | none | — |
| Nocturne | Keeps intents as StateSpans; measured: a temporary-target cancel becomes an open span of its own, a backfilled earlier override leaves two open spans, Loop's applied override duration is read as minutes and AndroidAPS `timeshift` as hours (state-intent §6.2); its `POST /api/v4/state-spans` reaches no controller (state-intent §7). | The rules answer each of those cases differently: a zero-duration record ends the instance (A5), supersession is by start (A7), and units are read only as declared (A11); the outstanding list (CM24) and the plan mirror (PN11) are new reads it would serve. | opt-in | A5, A7, A8, A11, A2, CM24, PN11 |
| babelbetes | Makes no Nightscout requests. | Makes no Nightscout requests. | none | — |
| GlookoServiceKit | No Nightscout commands. | Nothing at this layer. | none | — |
| Not read | not read | not read | none | — |
| openaps | No overrides, targets, profile switches or commands. | Nothing; see oref0. | none | — |
| trio-telemetry | Makes no Nightscout requests. | Makes no Nightscout requests. | none | — |
| xdrip-js | No overrides, targets, profile switches or commands. | Nothing. | none | — |
<!-- END GENERATED: compat-L3 -->

### 4.5 L4 Change and sync

<!-- BEGIN GENERATED: compat-L4 -->
| app | today | with a hub that implements the specifications | verdict | rules |
|---|---|---|---|---|
| AndroidAPS | The v3 client reads each collection with `history/{srvModified}` or `date$gt`/`created_at$gt` at constant limits of at most 1000 and listens on the `/storage` and `/alarm` sockets; writes through API v1 or the v1 socket do not reach `/storage` (BF-164). The 3.4.x v1 client uses the main socket (`authorize`, `dbAdd`, `dbUpdate`, `dataUpdate`), which the 4.0.0 prereleases remove. | API v3, its history read and both sockets stay, as do the v1 socket and its events (sync-transport §7); which writes reach `/storage` stays open, so v1 writes still arrive only through its history read (T12, T10). One read and one write across collections are there for a build that calls them (T5, T7). | opt-in | sync-transport §7, T5, T7, T10, T12 |
| AndroidAPS client control | Writes with v3 `PUT`, `PATCH` and `DELETE` on `/api/v3/settings`, reads with a limit of 100, and reacts to `/storage` create and update events on `settings` while also polling. | API v3 and the `/storage` socket stay, and v3 writes reach the socket today (sync-transport §7, T12). | unchanged | sync-transport §7, T12 |
| Loop | API v1 only, no socket; posts batches and requires a reply array as long as the request, and any non-200 holds the batch, so one refused record stalls that data type. | API v1 stays and re-sends keep today's outcomes; one read and one write per cycle are used only if it changes. | opt-in | sync-transport §7, T2, T5, T7 |
| oref0 | API v1 only, by curl. Every loop it reads `treatments.json?…&count=1?<secret>`, which 15.0.8 reads as count 1 and 15.0.9 refuses with 400 Bad count; the empty result makes the rig re-POST its whole 24 h of pump-history treatments each loop. | API v1 stays (sync-transport §7) and the specifications set no rule for `count`, so the malformed read is answered as the hub release answers it; the re-POSTed treatments are merged as L0 says. | unchanged | sync-transport §7, T2 |
| Trio | API v1 only, no socket; posts in chunks and retries a refused chunk forever with no notice; the CGM-from-Nightscout read turns any error into no data. | API v1 stays and re-sends keep today's outcomes; one read and one write per cycle are used only if it changes. | opt-in | sync-transport §7, T2, T5, T7 |
| cgmsim-lib | API v1 GET with `count=<maxCount>` when set, `find[created_at]` bounds on activity, and POST and DELETE that resolve on any HTTP status, so a refused write is logged as success. | API v1 stays (sync-transport §7). | unchanged | sync-transport §7 |
| DiaBLE | API v1 only; also shows the Nightscout web page in a web view, whose own socket client runs there. | API v1 and the v1 socket stay; one read and one write per cycle are used only if it changes. | opt-in | sync-transport §7, T5, T7 |
| glooko-nightscout-eu | POST `/api/v1/treatments`, one treatment per request; any 4xx or 5xx abandons the run, which retries later. | API v1 stays (sync-transport §7). | unchanged | sync-transport §7 |
| glooko2nightscout | Its only `/api/v3/…` URLs are Glooko's. | Nothing. | none | — |
| minimed-connect-to-nightscout | Standalone: POST `/api/v1/entries.json` and `/api/v1/devicestatus.json`; a refused batch is dropped. Embedded (`MMCONNECT_*`): cgm-remote-monitor writes in-process. | API v1 stays (sync-transport §7); the embedded path is an in-process caller of the one write step (T1). | unchanged | sync-transport §7, T1 |
| nightscout-connect | Writes in-process through `ctx.entries/treatments/devicestatus/profile`, with no HTTP and no `count` middleware; these writes reach no API v3 storage-socket event (BF-164). As a source it reads a remote hub over API v1 with `count` and `find[...][$gt]`. | Its in-process writes join the one write step with the other paths (T1); whether they reach the socket stays open (T12), and v1 reads of a source stay (sync-transport §7). | unchanged | T1, T12, sync-transport §7 |
| nightscout-librelink-up | API v1 (`count=1` watermark, POST entries) or API v3 (`limit=1&sort$desc=date`, one POST per reading that must answer 201). | Both stay (sync-transport §7); an identical re-send keeps each path's answer today (T2). | unchanged | sync-transport §7, T2 |
| share2nightscout-bridge | Standalone: POST `/api/v1/entries.json`, error logged and the batch dropped. Embedded in cgm-remote-monitor (only with `DEXCOM_BRIDGE_USE_LEGACY=true`): in-process `entries.create`. | API v1 stays (sync-transport §7); the embedded path is an in-process caller of the one write step (T1). | unchanged | sync-transport §7, T1 |
| tconnectsync | API v1 only: `count=1` watermark reads with `find[...]` filters and date bounds, POST, PUT and DELETE; any non-200 ends the run, which retries on the next schedule. | API v1 stays (sync-transport §7). | unchanged | sync-transport §7 |
| xDrip+ | API v1 REST only, with no socket: `count` is 10, 2880 or 1, `find[date][$gt]` and `find[uuid]` are its only filters, and a failed entries upload is retried every cycle. | API v1 stays as it is (sync-transport §7). | unchanged | sync-transport §7 |
| xDrip4iOS | API v1 only, no socket; re-sends a refused entries batch every cycle, and marks a treatment deleted when `find[_id]` answers 2xx with an empty array. | API v1 stays; one read and one write per cycle are used only if it changes. | opt-in | sync-transport §7, T5, T7 |
| LoopCaregiver | Polls API v1 on a timer; no socket. | API v1 stays; one read per cycle is used only if it changes. | opt-in | sync-transport §7, T5 |
| LoopFollow | Polls API v1 and joins the v1 socket, sending `authorize` with its access token; uses `dataUpdate` only as a trigger to re-poll and triples its poll interval while connected. | API v1 and the v1 socket stay; subscribing by product and channel is used only if it changes. | opt-in | sync-transport §7, T10, T11 |
| nightguard | API v3 first with an API v1 fallback; pages its statistics read with `skip` and `sort$desc`; no socket. | API v3 and v1 stay; the history read across collections is used only if it changes. | opt-in | sync-transport §7, T5, T6 |
| GluPredKit | API v1 GETs of profile, treatments and entries, each with `count=0` and a `$gte`/`$lte` date window; 15.0.8 reads `count=0` as no limit, and `dev` keeps that for a window bounded on both sides (#8761, a setting on by default, with a deprecation warning). | Per-collection API v1 reads stay (sync-transport §7); its reads still depend on the `count=0` tolerance setting being on. | unchanged | sync-transport §7 |
| GlycemicGPT | API v1 GETs with `count=5000`, `$gte` date filters and the `_id` cursor; `status.json`, and API v3 `version` and `status` to detect v3; no socket. | Per-collection API v1 reads stay (sync-transport §7); the single read across collections is available if it adopts it (T5). | unchanged | sync-transport §7, T5 |
| nightscout-cgm-skill | API v1 GETs only, `count` from 1 to 10000, entries paged by `find[date][$lte]`; no socket, no API v3. | Per-collection API v1 reads stay (sync-transport §7). | unchanged | sync-transport §7 |
| nightscout-reporter | API v1 GETs only, `count` literals from 2 to 100000, `$gte $lte $gt $lt $eq $ne` filters, `status.json` at start-up; no socket, no API v3. | Per-collection API v1 reads stay; nothing is retired (sync-transport §7). | unchanged | sync-transport §7 |
| oref-digital-twin | API v1 GETs with `count=50000` per 7-day window and `$gte`/`$lte` bounds, in Python and in the browser; no socket, no API v3. | Per-collection API v1 reads stay (sync-transport §7). | unchanged | sync-transport §7 |
| nightscout-roles-gateway | Calls `GET /api/v1/status.json` anonymously and with the hashed secret to inspect a site, and a non-200 marks it not ok; the socket path is proxied by an NGINX configuration outside the repository. | `status.json` and the v1 socket stay (sync-transport §7); a socket client receives events only for what its own credential may read, not for a gateway header (T11). | unchanged | sync-transport §7, T11 |
| Nocturne | Serves API v1 and v3 and a socket.io bridge; v3 pages by offset `Link` headers and clamps `limit=0` to 1; on the shared v1 contract it answers a negative `count` and an unsupported operator with 200 `[]`, reads `$exists` with an empty or `null` value as absent, and ignores bracket `find` on `/count`. | The merged read across collections (T5), its `srvModified` cursor (T6) and low watermark (T9) are new; per-collection reads stay (sync-transport §7), and a socket event never moves the history cursor (T10). | opt-in | T5, T6, T9, T10, sync-transport §7 |
| babelbetes | Makes no Nightscout requests. | Makes no Nightscout requests. | none | — |
| GlookoServiceKit | Its socket client connects to Glooko, not to Nightscout. | Nothing at this layer. | none | — |
| Not read | not read | not read | none | — |
| openaps | No HTTP client and no Nightscout URL in the repository. | Nothing; see oref0. | none | — |
| trio-telemetry | Makes no Nightscout requests. | Makes no Nightscout requests. | none | — |
| xdrip-js | No HTTP or socket client. | Nothing. | none | — |
<!-- END GENERATED: compat-L4 -->

### 4.6 L5 Authority

<!-- BEGIN GENERATED: compat-L5 -->
| app | today | with a hub that implements the specifications | verdict | rules |
|---|---|---|---|---|
| AndroidAPS | The v3 client exchanges an access token at `/api/v2/authorization/request/<token>` for a JWT sent as `Authorization: Bearer`, refreshing once on 401 or 403; the 3.4.x v1 socket sends `sha1(API_SECRET)` in `authorize`. It needs per-collection write permissions, and on `/alarm` read and `notifications:*:ack`. | Under `single` the credentials and per-collection permissions are as today (AU5). Under `TENANCY_MODE=multi` the token or secret it holds must be the tenant's own, because tokens are signed with the tenant's key and resolution runs first (AU3). | unchanged | AU5, AU3 |
| AndroidAPS client control | Both apps authenticate to the hub with the v3 access-token exchange and need read and write on `settings`; the commands themselves are authenticated end to end by the per-client signature, not by the hub. | Per-collection permissions and the single-tenant credentials are as today (AU5); under `multi` each app's token must be the tenant's own (AU3). | unchanged | AU5, AU3 |
| Loop | Sends the SHA-1 of the API secret as the `api-secret` header on every request and checks it at setup with `/api/v1/experiments/test`; no tokens. | Under single, API_SECRET behaves as today (AU3). Under multi there is no deployment secret; Loop presents the tenant's root credential, and whether that is accepted as today's header is not yet specified (authority §9). | unchanged | AU3, AU5, authority §9 |
| oref0 | Sends the SHA-1 of `API_SECRET` as an `api-secret` header, or appends `token=<t>` to the query; the check script exchanges the token at `/api/v2/authorization/request` and reads `permissionGroups`. | Unchanged under `single`. Under `TENANCY_MODE=multi` it keeps a native credential (AU1), and the secret or token it sends is its tenant's, since there is no deployment-wide secret (AU3). | unchanged | AU1, AU3 |
| Trio | Sends the SHA-1 of the API secret as the `api-secret` header and drops any `token=` from the configured URL, so a token-only site cannot be used. | Under single, API_SECRET behaves as today (AU3). Under multi it presents the tenant's root credential, and whether that is accepted as today's header is not yet specified (authority §9). | unchanged | AU3, AU5, authority §9 |
| cgmsim-lib | Sends the SHA-1 of the secret as `api-secret` on every request, with TLS verification turned off. | Unchanged under `single`; under `TENANCY_MODE=multi` the secret is its tenant's own root credential (AU1, AU3). | unchanged | AU1, AU3 |
| DiaBLE | One setting serves as `token=` on reads and, hashed, as the `api-secret` header on writes; the web view opens the site with `?token=`. | Under single, unchanged. Under multi a token issued by the tenant resolves there and nowhere else (AU3). | unchanged | AU3 |
| glooko-nightscout-eu | Sends the SHA-1 of `NIGHTSCOUT_SECRET` as `api-secret`. | Unchanged under `single`; under `TENANCY_MODE=multi` the secret is its tenant's own root credential (AU1, AU3). | unchanged | AU1, AU3 |
| glooko2nightscout | Holds no Nightscout credential. | Nothing. | none | — |
| minimed-connect-to-nightscout | Sends the SHA-1 of the secret as `api-secret`. | Unchanged under `single`; under `TENANCY_MODE=multi` the secret is its tenant's own root credential (AU1, AU3). | unchanged | AU1, AU3 |
| nightscout-connect | In-process writes carry no credential. As a source it uses `API-SECRET` to find or create a `nightscout-connect-reader` subject with `readable`, then exchanges its token for a JWT, or uses a `token=` from the source URL. | Unchanged under `single`. Under `TENANCY_MODE=multi` the source's subjects and tokens are its tenant's, re-rooted on that tenant's credential (AU3), and `readable` still reads every collection (AU5). | unchanged | AU3, AU5 |
| nightscout-librelink-up | v1 sends `NIGHTSCOUT_API_TOKEN` verbatim as `api-secret`; v3 exchanges it at `/api/v2/authorization/request` before every request and sends `Authorization: Bearer`. | Unchanged under `single`. Under `TENANCY_MODE=multi` the secret and token are its tenant's, the JWT signed with the tenant's key, so it fails on another tenant (AU1, AU3). | unchanged | AU1, AU3 |
| share2nightscout-bridge | Sends the SHA-1 of `API_SECRET` as `api-secret`, with TLS verification turned off; embedded mode uses no credential. | Unchanged under `single`; under `TENANCY_MODE=multi` the secret is its tenant's own root credential (AU1, AU3). | unchanged | AU1, AU3 |
| tconnectsync | Sends the SHA-1 of the secret as `api-secret`, and also the plaintext secret as an `api_secret` query parameter that Nightscout ignores. | Unchanged under `single`; under `TENANCY_MODE=multi` the secret is its tenant's own root credential (AU1, AU3). | unchanged | AU1, AU3 |
| xDrip+ | Sends `api-secret: sha1(secret)` taken from the URL on the uploader and the follower, with no token or JWT; a follower without a secret sends no header. | Under `single` this is as today (AU5, AU3). Under `multi` the secret must be the tenant's own root credential (AU3); AU1–AU5 do not say whether a tenant root is accepted in the `api-secret` header form. | unchanged | AU5, AU3 |
| xDrip4iOS | Sends the SHA-1 of the API secret as the `api-secret` header, adding any configured access token as `token=`. | Under single, unchanged (AU3). Under multi a token issued by the tenant resolves there, and whether the tenant's root credential is accepted as today's header is not yet specified (authority §9). | unchanged | AU3, authority §9 |
| LoopCaregiver | Sends only the SHA-1 of the API secret as `api-secret`; the relay needs `notifications:loop:push`, which of the default roles only admin holds. | Under single, unchanged. Under multi the relay sends with the deployment's APNs key and a process-wide device lookup (commands §3), and CM20 allows only a tenant's own push credentials, so the route it depends on has no tenant-scoped form. | unchanged | AU3, CM20, commands §3 |
| LoopFollow | Reads with an access token in `token=`; given the API secret it creates a `readable` subject through `/api/v2/authorization/subjects` and derives the token locally from the returned `_id`. | Under single, unchanged. Under multi the load cycle's `dataUpdate` is withheld (commands §3), so a connected LoopFollow keeps its slowed polling with no trigger, and AU3 re-roots subject tokens on the tenant's credential, which its local derivation must match. | unchanged | AU3, commands §3 |
| nightguard | Uses an access token: a JWT from `/api/v2/authorization/request`, the raw token in the `API-SECRET` header on the v1 fallback, or `token=`. | Under single, unchanged. Under multi a token issued by the site's tenant resolves there and nowhere else (AU3); reading stays one permission (AU5). | unchanged | AU3, AU5 |
| GluPredKit | Authenticates with the API secret through `python-nightscout` (header format not read); no token, no JWT. | On `single` nothing changes (AU5). Under `multi` there is no deployment-wide secret, so the secret it was configured with must be replaced by the tenant's root credential (AU3). | unchanged | AU3, AU5 |
| GlycemicGPT | Sends `api-secret: sha1(secret)` on v1 or a Bearer token on v3, or nothing; 401 and 403 stop the sync without retry. | On `single` nothing changes (AU5). Under `multi` the deployment-wide secret is gone and subject tokens are re-rooted, so its configured secret or token must be replaced with the tenant's (AU3). | unchanged | AU3, AU5 |
| nightscout-cgm-skill | Sends no credential, so it works only against a site readable anonymously. | Reading stays one bit, and a site readable anonymously serves it as today (AU5). | unchanged | AU5 |
| nightscout-reporter | Sends an access token as `?token=` on every request; no `api-secret` header, no Bearer. | On `single` nothing changes and its token still reads every collection (AU5). Under `multi` subject tokens are re-rooted on the tenant's credential, so the token a person entered before the move stops working and must be re-entered (AU3). | unchanged | AU3, AU5 |
| oref-digital-twin | Sends `token=` and/or a pre-hashed `api-secret` header from the environment (Python), `token=` only (browser); 401 and 403 raise without retry. | On `single` nothing changes (AU5). Under `multi` the deployment-wide secret is gone and subject tokens are re-rooted, so its configured token or secret must be replaced with the tenant's (AU3). | unchanged | AU3, AU5 |
| nightscout-roles-gateway | Serves NGINX `auth_request` decisions (200/403, `X-NSJWT`); lists subjects with `API-SECRET: sha1(secret)` and exchanges each policy's stored subject token at `/api/v2/authorization/request/<token>`. | On `single` nothing changes. Under `multi` there is no deployment-wide secret and subject tokens are re-rooted on the tenant's credential, so the secret it inspects with and every stored policy token must be replaced (AU3); its time-bounded policies are prior art for the delegation requirements DR1-DR7. | unchanged | AU3, AU4, DR1, DR3, DR6 |
| Nocturne | Socket clients authorize with a handshake ticket or a legacy secret or token and join their tenant's room, and a credential-less `authorize` is disconnected; subjects are typed, notes are not stored, and an edit with no roles leaves the grant unchanged. | AU3 (per-tenant signing, tenant resolved before any credential) and AU4 (bindings to subjects) apply to its subjects; AU5 keeps reading one bit, and DR1-DR7 are requirements no hub implements. | opt-in | AU3, AU4, AU5, DR1 |
| babelbetes | Makes no Nightscout requests. | Makes no Nightscout requests. | none | — |
| GlookoServiceKit | Authenticates to Glooko only. | Nothing at this layer. | none | — |
| Not read | not read | not read | none | — |
| openaps | Holds no Nightscout credential. | Nothing; see oref0. | none | — |
| trio-telemetry | Makes no Nightscout requests. | Makes no Nightscout requests. | none | — |
| xdrip-js | Holds no Nightscout credential. | Nothing. | none | — |
<!-- END GENERATED: compat-L5 -->

## 5. Where an answer changes

The verdicts describe a hub under `TENANCY_MODE=single`, the one every app reaches today. Two
cells answer differently there:

- **oref0, L0.** A re-sent pump-history treatment without client identity matches on `created_at`
  and `eventType` and is merged into the stored one instead of replacing it, so fields added in
  Nightscout that the rig does not send are kept (identity §3, T2). On 15.0.9 the rig's malformed
  `count` read is refused, and it then re-posts a day of treatments every loop, which makes this
  merge the common path ([consumer impact §2.1](../../../60-research/remedial/consumer-impact-15.0.9-2026-09-23.md#21-oref0-sends-a-malformed-count)).
- **xDrip4iOS, L0.** A duplicate is answered with the stored ids instead of a server error (I4);
  the app counts both as success.

Under `TENANCY_MODE=multi` every app reaches its tenant with its tenant's credential: there is no
deployment-wide secret, tokens are signed with the tenant's key, and subject tokens are re-rooted
on the tenant's credential (AU3). Each L5 cell says what that means for the app. Three apps meet
more than a new credential:

- **LoopFollow, L4 and L5.** The load cycle's `dataUpdate` is withheld under `multi` on the seam
  branch (commands §3); LoopFollow slows its polling while its socket is connected, so it would
  refresh less often with nothing to trigger a re-poll ([sync-transport §8](sync-transport.md#8-open)).
- **LoopCaregiver, L3 and L5.** The `/api/v2/notifications/loop` relay sends with the
  deployment's push key and looks devices up across the process (commands §3); CM20 allows only a
  tenant's own push credentials, so the route it depends on has no tenant-scoped form until a hub
  gives one.
- **nightscout-roles-gateway, L5.** The secret it inspects with and every stored policy token must
  be its tenant's.

For a hub, the right-hand column is what it would serve to implement each layer: Nocturne's cells
name the rules and the differences state and intent §6.2 measured on shared cases.

## 6. Open

1. **Today's credential forms under `multi`:** whether a tenant's root credential is accepted as
   the hashed `api-secret` header and the v1 socket's `secret` that apps send today
   ([authority §9](authority.md#9-open) item 7).
2. **The v1 socket's events under `multi`** ([sync-transport §8](sync-transport.md#8-open) item 7).
3. **Not read:** the maintained nightscout-reporter (Angular), `python-nightscout` (GluPredKit's
   entries and treatments calls go through it), Sugarmate, Spike, closed-source apps, and xDrip+'s
   direct MongoDB uploader.
4. **Refs.** Each row names the ref it was read at; the 15.0.9 survey read the apps on 2026-09-23,
   and the controllers' command paths were read at their releases on 2026-10-18. A row is re-read
   when its app releases a version that changes a cell.
5. **Well-known registrations** exist for Loop, Trio and AndroidAPS only
   (`specs/sync/registrations/`); every other writer's L2 attribution rests on
   [registration §11 and §17](registration.md#17-compatibility).

## 7. Checks

6 checks, in `tools/nsschema/test_compat.py`, run with `python3 -m pytest -q
tools/nsschema/test_compat.py`.

| check | holds that |
|---|---|
| `tools/nsschema/test_compat.py::test_apps_are_unique` | no app has two entries |
| `tools/nsschema/test_compat.py::test_every_surveyed_client_has_an_entry` | every per-client file of the 15.0.9 survey is the source of an entry |
| `tools/nsschema/test_compat.py::test_what_is_not_read_is_listed` | an entry lists the apps not read |
| `tools/nsschema/test_compat.py::test_entry` | every entry has a kind, a ref and a source that exists, and every layer a verdict, both cells and rules that exist; a gains, opt-in or affected cell names its rule |
| `tools/nsschema/test_compat.py::test_page_tables_are_generated` | the tables in §3 and §4 are the files', as `python3 -m tools.nsschema.compat_tables` writes them |
| `tools/nsschema/test_compat.py::test_page_lists_every_affected_cell` | §5 names every app and layer whose verdict is `affected` |
