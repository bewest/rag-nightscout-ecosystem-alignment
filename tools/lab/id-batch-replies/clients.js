'use strict';
// Client reply-handling harnesses for the ID-BATCH lab. Each one reproduces,
// from the client's source, only what the client does with the reply to an
// API v1 batch POST: which status counts as success, what it requires of the
// body, which items it then treats as uploaded, whether it reads `_id`, and
// what it re-sends on its next cycle. Everything else (UI, storage, timers) is
// left out. Each rule carries the file:line it was read from, at the pins in
// PINS. A harness is a reproduction, not the client: the lab runs the real
// client where it can (nightscout-connect, connect-run.js).
//
// A harness is `handle(collection, sent, reply)` where `sent` is the array the
// client posted and `reply` is `{ status, headers, body }` as received. It
// returns:
//   ok        the client's own success/failure decision for the request
//   marked    per sent item: does the client now treat it as uploaded
//   ids       per sent item: the `_id` the client keeps from the reply, or null
//   resend    per sent item: does the client send it again on its next cycle
//   readsId   does the client read `_id` from the reply at all on this path
//   retry     the client's retry rule, in words, with its bound

const PINS = Object.freeze({
  loop: 'NightscoutKit 4ec9fd12a1 (= LoopWorkspace 548b332451 Package.resolved:104-109), NightscoutService 2cef4896f0, Loop c30b5c89',
  trio: 'Trio 0b29cd5341',
  xdripplus: 'xDrip 1ed760048a',
  xdripswift: 'xdripswift c268542e64',
  connect: 'nightscout-connect 04102f9d26 (run, not modelled: connect-run.js)',
  aaps: 'AndroidAPS 7e1d537d49'
});

const all = (sent, v) => sent.map(() => v);

// Loop: NightscoutKit postToNS and NightscoutService/RemoteDataServicesManager.
//  - status must be exactly 200: NightscoutClient.swift:545-548
//  - body must be an array of exactly the sent count: :488-491
//  - `_id` string per slot, else "NA", and "NA" still counts as uploaded: :493-503
//  - carbs and doses zip sent syncIdentifiers with ids BY POSITION into the
//    objectIdCache: NightscoutService.swift:207-213 (carbs), :250-256 (doses)
//  - the query anchor moves only on success: RemoteDataServicesManager.swift:278-287;
//    a failure marks the type failed (:106-111) and it is re-tried, from the
//    same anchor, on every later upload trigger (:182-183). No attempt counter,
//    no age limit: the same batch (up to carbDataLimit/doseDataLimit 1000,
//    NightscoutService.swift:195, :238) is re-sent, and everything after it waits.
function loop (collection, sent, reply) {
  const okStatus = reply.status === 200;
  const isArray = Array.isArray(reply.body);
  const okCount = isArray && reply.body.length === sent.length;
  const ok = okStatus && okCount;
  if (!ok) {
    // The guards at :488-491 and :545 come before the `_id` map at :493.
    return { ok, marked: all(sent, false), ids: all(sent, null), resend: all(sent, true), readsId: false
      , why: !okStatus ? 'status ' + reply.status + ' is not 200' : !isArray ? 'body is not an array' : 'array length ' + reply.body.length + ' != ' + sent.length
      , retry: 'whole batch on every upload trigger, no bound; later records wait behind it' };
  }
  const ids = reply.body.map(slot => (slot && typeof slot._id === 'string') ? slot._id : 'NA');
  return { ok, marked: all(sent, true), ids, resend: all(sent, false), readsId: true
    , why: ids.includes('NA') ? 'slot without _id -> "NA", counted as uploaded' : 'all slots carry _id'
    , retry: 'none (anchor advanced)' };
}

// Trio: NightscoutAPI.uploadTreatments/uploadGlucose ignore the body
// (`let (_, response)`, NightscoutAPI.swift:328, :363) and accept 2xx
// (:331, :366). NightscoutManager uploads in chunks of 100 and marks every
// item uploaded only if every chunk succeeded (uploadCarbs :1096-1110,
// uploadGlucose :966-983). Not-uploaded carbs are re-read by
// `isUploadedToNS == false` within the last day
// (Model/Helper/CarbEntryStored+helper.swift:28-35) and re-sent on the next
// upload pass.
function trio (collection, sent, reply) {
  const ok = reply.status >= 200 && reply.status < 300;
  return { ok, marked: all(sent, ok), ids: all(sent, null), resend: all(sent, !ok), readsId: false
    , why: ok ? '2xx: every item marked uploaded, body ignored' : 'status ' + reply.status + ': nothing marked'
    , retry: ok ? 'none' : 'whole chunk on every upload pass while within 1 day (carbs), no attempt counter' };
}

// xDrip+ (Android): entries are one POST array (NightscoutUploader.java:577-579,
// `isSuccessful()` = 2xx); on success the uploader queue marks every item done
// (UploaderTask.java:182-186); on failure the items stay queued and are
// re-sent on the next run; the queue drops anything older than 7 days
// (UploaderQueue.java:353-367). Treatments are NOT a batch: inserts go into
// upsert_array ("always use singular upserts", NightscoutUploader.java:803-806)
// and are PUT one at a time (:880-889); so a v1 batch reply never reaches them.
function xdripplus (collection, sent, reply) {
  if (collection !== 'entries') {
    return { na: true, why: 'treatments are PUT one object at a time (NightscoutUploader.java:803-806, :880-889)' };
  }
  const ok = reply.status >= 200 && reply.status < 300;
  return { ok, marked: all(sent, ok), ids: all(sent, null), resend: all(sent, !ok), readsId: false
    , why: ok ? '2xx: queue items marked done, body ignored' : 'status ' + reply.status + ': items stay queued'
    , retry: ok ? 'none' : 'whole batch on every upload run until the queue entry is 7 days old' };
}

// xDrip4iOS (xdripswift):
//  - success is 2xx, or a 500 whose body has description.code 66
//    (NightscoutSyncManager.swift:1692-1708)
//  - treatments: the body must parse as an array (TreatmentNSResponse.swift:155-161,
//    else the upload is failed, SyncManager :1807, :1820-1826); each slot yields records
//    only if it has a string `_id` AND a parseable `created_at` (:62); a local
//    treatment is marked uploaded, and takes the slot's `_id`, only if some slot
//    matches it by date, type, value, secondary value and notes
//    (:168-175; SyncManager checkIfUploaded :2107-2125). An unmatched local
//    treatment stays `uploaded == false` and is re-sent on the next sync while it
//    is among the latest 50 (SyncManager :636-643, ConstantsNightscout.swift:20).
//  - entries: body ignored; the upload timestamp bookmark moves on success
//    (SyncManager :1541-1546).
function xdripswift (collection, sent, reply) {
  const code66 = reply.status === 500 && reply.body && reply.body.description && reply.body.description.code === 66;
  const ok = (reply.status >= 200 && reply.status < 300) || code66;
  if (collection === 'entries') {
    return { ok, marked: all(sent, ok), ids: all(sent, null), resend: all(sent, !ok), readsId: false
      , why: ok ? '2xx: bookmark moved, body ignored' : 'status ' + reply.status
      , retry: ok ? 'none' : 'from the bookmark on every sync' };
  }
  if (!ok) {
    return { ok, marked: all(sent, false), ids: all(sent, null), resend: all(sent, true), readsId: false
      , why: 'status ' + reply.status, retry: 'every sync while among the latest 50 treatments' };
  }
  if (!Array.isArray(reply.body)) {
    return { ok: false, marked: all(sent, false), ids: all(sent, null), resend: all(sent, true), readsId: false
      , why: 'body is not an array: upload counted as failed', retry: 'every sync while among the latest 50 treatments' };
  }
  const slots = reply.body.filter(s => s && typeof s._id === 'string' && typeof s.created_at === 'string');
  const ms = s => Date.parse(s);
  const matches = (t, s) => ms(s.created_at) === ms(t.created_at) && s.eventType === t.eventType
    && (s.carbs === t.carbs) && (s.insulin === t.insulin) && ((s.notes || null) === (t.notes || null));
  const ids = sent.map(t => { const s = slots.find(x => matches(t, x)); return s ? s._id : null; });
  const marked = ids.map(Boolean);
  return { ok, marked, ids, resend: marked.map(m => !m), readsId: true
    , why: marked.every(Boolean) ? 'every item matched a slot with _id' : (marked.filter(m => !m).length + ' item(s) matched no slot with _id')
    , retry: marked.every(Boolean) ? 'none' : 'unmatched items on every sync while among the latest 50' };
}

// AndroidAPS sends no API v1 batch: its NS SDK writes one document per API v3
// request (core/nssdk/.../networking/NightscoutApi.kt:127-130, :160-163, :177).
function aaps ( ) {
  return { na: true, why: 'API v3, one document per request (NightscoutApi.kt:127-130, :160-163)' };
}

const CLIENTS = Object.freeze({ loop, trio, xdripplus, xdripswift, aaps });

// Which collections each client posts as a v1 array.
const POSTS = Object.freeze({
  loop: ['treatments', 'entries', 'devicestatus', 'profile'],
  trio: ['treatments', 'entries'],
  xdripplus: ['entries'],
  xdripswift: ['treatments', 'entries'],
  aaps: []
});

module.exports = { CLIENTS, POSTS, PINS };
